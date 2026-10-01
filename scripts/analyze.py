"""
Purchase-to-pay analysis of the BPI Challenge 2019 log.

Reads data/cases.parquet and data/events.parquet (see xes_to_parquet.py) and
writes output/results.json. Every number in the README and the write-up comes
from results.json.

    python scripts/analyze.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

CREATE = "Create Purchase Order Item"
GR, IR, CLEAR = "Record Goods Receipt", "Record Invoice Receipt", "Clear Invoice"
VENDOR_INV = "Vendor creates invoice"
FLOWS = ["3-way match, invoice before GR", "3-way match, invoice after GR", "2-way match", "Consignment"]


def load():
    cases = pd.read_parquet(ROOT / "data" / "cases.parquet")
    ev = pd.read_parquet(ROOT / "data" / "events.parquet")
    return cases.set_index("case_id"), ev


def clean_cases(cases, ev):
    """The log covers purchase orders from 2018, but a few hundred events carry
    impossible dates (back to 1948). Keep cases whose items were created in 2018
    and whose events all fall between 2017 and 2019."""
    span = ev.groupby("case_id")["timestamp"].agg(["min", "max"])
    created = ev[ev["activity"] == CREATE].groupby("case_id")["timestamp"].min()
    ok = (span["min"] >= "2017-01-01") & (span["max"] < "2020-01-01")
    ok &= created.reindex(span.index).dt.year.eq(2018)
    return set(span.index[ok])


def first_times(ev, activities):
    sub = ev[ev["activity"].isin(activities)]
    return sub.groupby(["case_id", "activity"])["timestamp"].min().unstack()


def pct(x):
    return round(100 * float(x), 1)


def compliance(t):
    """Check each flow against its own matching rule. t has one row per item:
    first timestamp of each activity plus the item's flow."""
    comp = {}
    after = t[t["flow"] == "3-way match, invoice after GR"]
    both = after.dropna(subset=[GR, IR])
    comp["invoice_after_GR: invoice recorded before goods receipt"] = {
        "cases": len(both), "violations": int((both[IR] < both[GR]).sum()), "pct": pct((both[IR] < both[GR]).mean())}
    before = t[t["flow"] == "3-way match, invoice before GR"]
    cleared = before.dropna(subset=[CLEAR])
    no_gr = cleared[GR].isna() | (cleared[CLEAR] < cleared[GR])
    comp["invoice_before_GR: invoice cleared before any goods receipt"] = {
        "cases": len(cleared), "violations": int(no_gr.sum()), "pct": pct(no_gr.mean())}
    cons = t[t["flow"] == "Consignment"]
    comp["consignment: invoice recorded on a consignment item"] = {
        "cases": len(cons), "violations": int(cons[IR].notna().sum()), "pct": pct(cons[IR].notna().mean())}
    return comp


def after_the_fact(t):
    """Items whose vendor invoice is dated before the purchase-order item was created."""
    vi = t.dropna(subset=[VENDOR_INV])
    atf = vi[VENDOR_INV] < vi[CREATE]
    lead = (vi.loc[atf, CREATE] - vi.loc[atf, VENDOR_INV]).dt.total_seconds().div(86400)
    return {"cases_with_vendor_invoice": len(vi), "count": int(atf.sum()), "pct": pct(atf.mean()),
            "median_days_invoice_before_po": round(float(lead.median()), 1)}


def main():
    OUT.mkdir(exist_ok=True)
    cases, ev = load()
    keep = clean_cases(cases, ev)
    r = {"raw": {"cases": len(cases), "events": len(ev), "activities": int(ev["activity"].nunique())}}
    r["clean"] = {"cases": len(keep), "excluded_cases": len(cases) - len(keep)}
    ev = ev[ev["case_id"].isin(keep)].copy()
    cases = cases.loc[sorted(keep)]
    r["clean"]["events"] = len(ev)

    flow = cases["Item Category"]
    r["flows"] = {f: {"cases": int((flow == f).sum()), "share_pct": pct((flow == f).mean())} for f in FLOWS}

    t = first_times(ev, [CREATE, GR, IR, CLEAR, VENDOR_INV])
    last_clear = ev[ev["activity"] == CLEAR].groupby("case_id")["timestamp"].max()
    t["flow"] = flow.reindex(t.index)

    # Throughput: item created to its last invoice cleared, completed cases only
    days = (last_clear - t[CREATE]).dt.total_seconds().div(86400).dropna()
    r["throughput_days"] = {}
    for f in FLOWS:
        d = days[t.loc[days.index, "flow"] == f]
        if len(d):
            r["throughput_days"][f] = {"completed": len(d), "median": round(float(d.median()), 1),
                                       "p75": round(float(d.quantile(.75)), 1), "p90": round(float(d.quantile(.9)), 1)}

    r["compliance"] = compliance(t)
    r["after_the_fact_po"] = after_the_fact(t)

    # Rework
    per_case = ev.groupby(["case_id", "activity"]).size().unstack(fill_value=0)
    rework = {}
    for a in ["Change Price", "Change Quantity", "Delete Purchase Order Item", "Remove Payment Block",
              "Cancel Invoice Receipt", "Cancel Goods Receipt"]:
        if a in per_case:
            rework[a] = {"cases": int((per_case[a] > 0).sum()), "pct": pct((per_case[a] > 0).mean())}
    r["rework"] = rework

    # Where payment blocks concentrate, and what they go with
    blocked = set(ev.loc[ev["activity"] == "Remove Payment Block", "case_id"])
    is_blocked = cases.index.isin(blocked)
    areas = pd.DataFrame({"area": cases["Spend area text"].replace("", "(blank)"), "blocked": is_blocked})
    by_area = areas.groupby("area")["blocked"].agg(items="size", blocked="sum").sort_values("items", ascending=False)
    r["payment_blocks"] = {
        "by_spend_area": {a: {"items": int(row["items"]), "block_pct": pct(row["blocked"] / row["items"]),
                              "share_of_all_blocks_pct": pct(row["blocked"] / max(len(blocked), 1))}
                          for a, row in by_area.head(8).iterrows()},
        "by_item_type": {k: pct(v) for k, v in pd.Series(is_blocked, index=cases.index)
                         .groupby(cases["Item Type"]).mean().sort_values(ascending=False).items()},
    }
    main_flow = days[t.loc[days.index, "flow"] == FLOWS[0]]
    b, nb = main_flow[main_flow.index.isin(blocked)], main_flow[~main_flow.index.isin(blocked)]
    r["payment_blocks"]["main_flow_median_days"] = {"blocked": round(float(b.median()), 1), "blocked_n": len(b),
                                                    "not_blocked": round(float(nb.median()), 1), "not_blocked_n": len(nb)}
    # Blocks pile up in slow areas, so compare blocked and unblocked items within
    # each spend area (areas with at least 500 of each)
    mf = pd.DataFrame({"days": main_flow, "blocked": main_flow.index.isin(blocked),
                       "area": areas["area"].reindex(main_flow.index)})
    g = mf.groupby(["area", "blocked"])["days"].agg(["median", "size"]).unstack()
    g = g[(g[("size", True)] >= 500) & (g[("size", False)] >= 500)].sort_values(("size", False), ascending=False)
    gap = g[("median", True)] - g[("median", False)]
    r["payment_blocks"]["main_flow_within_area"] = {
        "areas": {a: {"blocked": round(float(g.loc[a, ("median", True)]), 1),
                      "not_blocked": round(float(g.loc[a, ("median", False)]), 1),
                      "gap_days": round(float(gap[a]), 1)} for a in g.index},
        "block_weighted_gap_days": round(float((gap * g[("size", True)]).sum() / g[("size", True)].sum()), 1)}

    # Variants: the ordered activity sequence of each case
    ev = ev.sort_values(["case_id", "timestamp"], kind="stable")
    seq = ev.groupby("case_id")["activity"].agg(tuple)
    vc = seq.value_counts()
    cum = vc.cumsum() / vc.sum()
    r["variants"] = {"distinct": int(len(vc)), "top1_pct": pct(vc.iloc[0] / vc.sum()),
                     "top10_pct": pct(cum.iloc[9]), "variants_for_80pct": int((cum < 0.8).sum() + 1),
                     "singleton_variants": int((vc == 1).sum()),
                     "top1": list(vc.index[0]),
                     "top5": [{"share_pct": pct(n / vc.sum()), "steps": list(v),
                               "flow_mix_pct": {k: pct(x) for k, x in
                                                flow.reindex(seq.index[seq == v]).value_counts(normalize=True).items()}}
                              for v, n in vc.head(5).items()]}
    np.save(OUT / "variant_coverage.npy", cum.to_numpy())

    # Directly-follows graph for the process map: activities on at least 10% of
    # items, edges between them seen at least 15,000 times. Self-loops are left
    # out and the largest one is reported on its own.
    share = ev.groupby("activity")["case_id"].nunique() / len(cases)
    nodes = share[share >= 0.10].sort_values(ascending=False)
    nxt = ev.groupby("case_id")["activity"].shift(-1)
    dfg = pd.DataFrame({"a": ev["activity"], "b": nxt}).dropna().value_counts()
    first, last = seq.str[0].value_counts(), seq.str[-1].value_counts()
    loops = dfg[[a == b for a, b in dfg.index]]
    loop_act = loops.index[0][0]
    r["process_map"] = {
        "largest_self_loop": {"activity": loop_act, "count": int(loops.iloc[0]), "items_pct": pct(share[loop_act])},
        "nodes": {a: pct(v) for a, v in nodes.items()},
        "edges": [[a, b, int(c)] for (a, b), c in dfg.items()
                  if a in nodes.index and b in nodes.index and a != b and c >= 15000],
        "starts": {a: int(c) for a, c in first.items() if a in nodes.index and c >= 15000},
        "ends": {a: int(c) for a, c in last.items() if a in nodes.index and c >= 15000},
    }

    # Where the time goes on the happy path: median gap between consecutive steps
    happy = vc.index[0]
    h = ev[ev["case_id"].isin(seq.index[seq == happy])].copy()
    h["step"] = h.groupby("case_id").cumcount()
    w = h.pivot(index="case_id", columns="step", values="timestamp")
    gaps = []
    for i in range(len(happy) - 1):
        d = (w[i + 1] - w[i]).dt.total_seconds().div(86400)
        gaps.append({"from": happy[i], "to": happy[i + 1],
                     "median_days": round(float(d.median()), 1), "p90_days": round(float(d.quantile(.9)), 1)})
    total = (w[len(happy) - 1] - w[0]).dt.total_seconds().div(86400)
    r["happy_path_steps"] = {"items": int(len(w)), "total_median_days": round(float(total.median()), 1), "gaps": gaps}
    # Is the invoice-entry wait (goods receipt to invoice recorded) one area's problem or everyone's?
    entry = (w[happy.index(IR)] - w[happy.index(GR)]).dt.total_seconds().div(86400)
    by_area = entry.groupby(areas["area"].reindex(entry.index)).agg(["median", "size"])
    by_area = by_area[by_area["size"] >= 1000].sort_values("size", ascending=False)
    r["happy_path_steps"]["invoice_entry_by_area"] = {
        a: {"items": int(row["size"]), "median_days": round(float(row["median"]), 1)} for a, row in by_area.iterrows()}

    # Automation: who executes each activity
    kind = ev["resource"].str.extract(r"^(batch|user)_", expand=False).fillna("none")
    auto = pd.crosstab(ev["activity"], kind)
    auto["total"] = auto.sum(axis=1)
    top = auto.sort_values("total", ascending=False).head(12)
    r["automation"] = {a: {"events": int(row["total"]),
                           "batch_pct": pct(row.get("batch", 0) / row["total"]),
                           "user_pct": pct(row.get("user", 0) / row["total"]),
                           "none_pct": pct(row.get("none", 0) / row["total"])} for a, row in top.iterrows()}

    (OUT / "results.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()

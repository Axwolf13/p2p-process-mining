"""
Purchase-to-pay analysis of the BPI Challenge 2019 log.

Reads data/cases.parquet and data/events.parquet (see xes_to_parquet.py) and
writes output/results.json plus output/report.md. Every number in the README
and the write-up comes from results.json.

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

    # Compliance with each flow's own matching rule
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
    r["compliance"] = comp

    # After-the-fact purchase orders: the vendor's invoice predates the PO item
    vi = t.dropna(subset=[VENDOR_INV])
    atf = vi[VENDOR_INV] < vi[CREATE]
    r["after_the_fact_po"] = {"cases_with_vendor_invoice": len(vi), "count": int(atf.sum()), "pct": pct(atf.mean()),
                              "median_days_invoice_before_po": round(float(
                                  (vi.loc[atf, CREATE] - vi.loc[atf, VENDOR_INV]).dt.total_seconds().div(86400).median()), 1)}

    # Rework
    per_case = ev.groupby(["case_id", "activity"]).size().unstack(fill_value=0)
    rework = {}
    for a in ["Change Price", "Change Quantity", "Delete Purchase Order Item", "Remove Payment Block",
              "Cancel Invoice Receipt", "Cancel Goods Receipt"]:
        if a in per_case:
            rework[a] = {"cases": int((per_case[a] > 0).sum()), "pct": pct((per_case[a] > 0).mean())}
    r["rework"] = rework

    # Variants: the ordered activity sequence of each case
    ev = ev.sort_values(["case_id", "timestamp"], kind="stable")
    seq = ev.groupby("case_id")["activity"].agg(tuple)
    vc = seq.value_counts()
    cum = vc.cumsum() / vc.sum()
    r["variants"] = {"distinct": int(len(vc)), "top1_pct": pct(vc.iloc[0] / vc.sum()),
                     "top10_pct": pct(cum.iloc[9]), "variants_for_80pct": int((cum < 0.8).sum() + 1),
                     "singleton_variants": int((vc == 1).sum()),
                     "top1": list(vc.index[0])}
    np.save(OUT / "variant_coverage.npy", cum.to_numpy())

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

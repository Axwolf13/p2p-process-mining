"""
The rule checks in analyze.py, run on a hand-built log where every answer is known.

Run from the repo root: python tests/test_rules.py (pytest also picks it up)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from analyze import CLEAR, CREATE, GR, IR, VENDOR_INV, after_the_fact, clean_cases, compliance

AFTER, BEFORE, CONS = "3-way match, invoice after GR", "3-way match, invoice before GR", "Consignment"


def items(rows):
    """rows: case_id -> (flow, {activity: 'YYYY-MM-DD'})"""
    t = pd.DataFrame({c: {a: pd.Timestamp(d) for a, d in acts.items()} for c, (_, acts) in rows.items()}).T
    t = t.reindex(columns=[CREATE, GR, IR, CLEAR, VENDOR_INV]).apply(pd.to_datetime)
    t["flow"] = pd.Series({c: f for c, (f, _) in rows.items()})
    return t


T = items({
    # invoice after GR: recording the invoice before the goods is the violation
    "a1": (AFTER, {CREATE: "2018-01-01", GR: "2018-01-05", IR: "2018-01-03"}),
    "a2": (AFTER, {CREATE: "2018-01-01", GR: "2018-01-05", IR: "2018-01-07"}),
    "a3": (AFTER, {CREATE: "2018-01-01", GR: "2018-01-05", IR: "2018-01-09"}),
    "a4": (AFTER, {CREATE: "2018-01-01", GR: "2018-01-05"}),  # no invoice yet, not judged
    # invoice before GR: clearing before any goods receipt is the violation
    "b1": (BEFORE, {CREATE: "2018-01-01", IR: "2018-01-04", CLEAR: "2018-01-10"}),
    "b2": (BEFORE, {CREATE: "2018-01-01", IR: "2018-01-04", CLEAR: "2018-01-10", GR: "2018-01-12"}),
    "b3": (BEFORE, {CREATE: "2018-01-01", GR: "2018-01-05", IR: "2018-01-04", CLEAR: "2018-01-20"}),
    "b4": (BEFORE, {CREATE: "2018-01-01", GR: "2018-01-03", IR: "2018-01-02", CLEAR: "2018-01-15"}),
    "b5": (BEFORE, {CREATE: "2018-01-01", IR: "2018-01-04"}),  # not cleared, not judged
    # consignment: any invoice on the item is the violation
    "c1": (CONS, {CREATE: "2018-01-01", GR: "2018-01-05", IR: "2018-01-06"}),
    "c2": (CONS, {CREATE: "2018-01-01", GR: "2018-01-05"}),
    # after-the-fact POs: vendor invoice dated before the item exists
    "v1": (BEFORE, {CREATE: "2018-02-11", VENDOR_INV: "2018-02-01"}),
    "v2": (BEFORE, {CREATE: "2018-02-01", VENDOR_INV: "2018-02-04"}),
    "v3": (BEFORE, {CREATE: "2018-02-01", VENDOR_INV: "2018-02-02"}),
})


def test_invoice_after_gr_rule():
    c = compliance(T)["invoice_after_GR: invoice recorded before goods receipt"]
    assert (c["cases"], c["violations"]) == (3, 1)


def test_invoice_before_gr_rule_counts_missing_and_late_receipts():
    c = compliance(T)["invoice_before_GR: invoice cleared before any goods receipt"]
    assert (c["cases"], c["violations"]) == (4, 2)


def test_consignment_rule():
    c = compliance(T)["consignment: invoice recorded on a consignment item"]
    assert (c["cases"], c["violations"], c["pct"]) == (2, 1, 50.0)


def test_after_the_fact_po():
    r = after_the_fact(T)
    assert (r["cases_with_vendor_invoice"], r["count"]) == (3, 1)
    assert r["median_days_invoice_before_po"] == 10.0


def test_clean_cases_drops_bad_dates_and_other_years():
    ev = pd.DataFrame([
        ("ok", CREATE, "2018-03-01"), ("ok", GR, "2018-03-09"),
        ("old_event", CREATE, "2018-03-01"), ("old_event", GR, "1948-01-26"),
        ("created_2017", CREATE, "2017-12-30"), ("created_2017", GR, "2018-01-04"),
        ("too_late", CREATE, "2018-11-01"), ("too_late", CLEAR, "2020-02-01"),
    ], columns=["case_id", "activity", "timestamp"])
    ev["timestamp"] = pd.to_datetime(ev["timestamp"])
    assert clean_cases(None, ev) == {"ok"}


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} rule checks passed")

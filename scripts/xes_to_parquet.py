"""
Stream the BPI Challenge 2019 XES log into two Parquet tables.

The log is 728 MB of XML (251,734 cases, ~1.6M events). Parsing it whole would
hold the entire element tree in memory at several times the file size, so this
walks it with iterparse and clears each trace as soon as it has been read.

    python scripts/xes_to_parquet.py

Writes data/cases.parquet (one row per purchase-order item) and
data/events.parquet (one row per event).
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
XES = ROOT / "data" / "raw" / "BPI_Challenge_2019.xes"
ATTR_TAGS = {"string", "date", "int", "float", "boolean"}


def cast(tag, value):
    if tag == "boolean":
        return value == "true"
    if tag == "float":
        return float(value)
    if tag == "int":
        return int(value)
    return value


def main():
    cases, events = [], []
    trace_attrs = None
    in_event = False

    for kind, el in ET.iterparse(XES, events=("start", "end")):
        tag = el.tag
        if kind == "start":
            if tag == "trace":
                trace_attrs = {}
            elif tag == "event":
                in_event = True
            continue

        if tag in ATTR_TAGS and trace_attrs is not None and not in_event:
            # a trace-level attribute (log-level globals are skipped: trace_attrs is None there)
            trace_attrs[el.get("key")] = cast(tag, el.get("value"))
        elif tag == "event":
            row = {c.get("key"): cast(c.tag, c.get("value")) for c in el if c.tag in ATTR_TAGS}
            row["case_id"] = trace_attrs.get("concept:name")
            events.append(row)
            in_event = False
            el.clear()
        elif tag == "trace":
            cases.append(trace_attrs)
            trace_attrs = None
            el.clear()
            if len(cases) % 25000 == 0:
                print(f"  {len(cases):,} cases, {len(events):,} events", flush=True)

    cases_df = pd.DataFrame(cases).rename(columns={"concept:name": "case_id"})
    ev = pd.DataFrame(events).rename(columns={
        "concept:name": "activity", "time:timestamp": "timestamp",
        "org:resource": "resource", "Cumulative net worth (EUR)": "net_worth_eur"})
    ev["timestamp"] = pd.to_datetime(ev["timestamp"], utc=True, format="ISO8601")
    cases_df.to_parquet(ROOT / "data" / "cases.parquet", index=False)
    ev.to_parquet(ROOT / "data" / "events.parquet", index=False)
    print(f"done: {len(cases_df):,} cases, {len(ev):,} events, "
          f"{ev['activity'].nunique()} activities, {ev['timestamp'].min()} to {ev['timestamp'].max()}")


if __name__ == "__main__":
    main()

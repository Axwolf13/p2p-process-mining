# Purchase-to-pay process mining on a real purchasing log

What does a purchasing process look like once you stop reading the process manual and start reading the event log? This repo takes the public [BPI Challenge 2019](https://doi.org/10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1) log, one year of purchase orders from a large Dutch coatings and paints company. Then it measures: how long orders take, whether each flow follows its own matching rule, where people step in by hand and how many different paths an order really takes.

251,734 purchase-order items, 1.6 million events, 42 activities, several of them SAP SRM steps ("SRM: Created", "SRM: Awaiting Approval"). Everything below is computed by [`scripts/analyze.py`](scripts/analyze.py) into [`output/results.json`](output/results.json).

## Findings

**Almost everything is three-way matched, invoice first.** 87.9% of items run as "3-way match, invoice before GR": the invoice may arrive before the goods, but it should only be cleared once goods are received. 6.0% are "invoice after GR", 5.8% consignment and 0.3% two-way match.

**An order takes about 11 weeks to close.** From purchase-order item to last invoice cleared, the median is 77 days for the dominant flow (p90: 128). Two-way match, with no goods receipt to wait for, closes in a median of 7 days.

![Throughput by flow](output/throughput.png)

**On the happy path, most of the time sits around the invoice.** For the 50,286 items that follow it exactly, the median is 64 days end to end:

| Step | Median days | p90 |
|---|---:|---:|
| Create Purchase Order Item to Vendor creates invoice | 4.7 | 25.3 |
| Vendor creates invoice to Record Goods Receipt | 1.5 | 4.8 |
| Record Goods Receipt to Record Invoice Receipt | 12.1 | 47.4 |
| Record Invoice Receipt to Clear Invoice | 30.1 | 73.0 |

The vendor's invoice is dated a median of 1.5 days before the goods arrive, yet it's recorded 12 days after them. Some of that is the invoice travelling. With 96% of invoice entry done by hand, some of it is likely a queue, which makes invoice capture the obvious automation target. It isn't one spend area's problem either: in each of the four biggest spend areas the median wait is between 8 and 20 days. The 30 days from recording to clearing looks like payment terms at work rather than delay.

**The matching rules mostly hold, with one gap worth a look.** No "invoice after GR" item recorded its invoice before the goods receipt. No consignment item carries an invoice. But 654 items in the invoice-first flow (0.4% of the completed ones) had their invoice cleared before any goods receipt was recorded. That's the list an auditor would ask for first.

**1.7% of purchase orders were raised after the invoice.** For 3,528 items the vendor's invoice predates the purchase-order item, by a median of 11.7 days. That's the classic "after-the-fact PO": the buying happened first and the paperwork caught up.

**Payment blocks are the biggest source of rework.** 22.2% of items needed a payment block removed, far more than price changes (4.5%), quantity changes (7.0%) or deleted items (3.5%). A payment block usually means the invoice didn't match the order or receipt, so this is where matching problems surface as manual work.

**Half of all payment blocks come from one spend area.** Packaging is 43% of all items and needs a block lifted on 26% of them, which makes it 52% of every block in the log. Its rate isn't the worst (Latex & Monomers blocks 28%, on 5,004 items); volume is what puts it on top. Logistics barely has any (3%). Standard items are blocked far more often (25%) than services (7%). In the main flow, items that needed a block lifted closed at a median of 87 days against 73 for the rest. Most of that gap is where blocks happen: Packaging items take 98 days even without one. Within the same spend area, blocked items close about 4 days later (block-weighted average, at most 8 in any area with at least 500 items of each kind). That's days rather than weeks. It's still a correlation, not a measured cost of the block.

![Payment blocks by spend area](output/payment_blocks.png)

**Invoice handling is almost entirely manual.** Batch jobs record 27% of goods receipts but only 4% of invoice receipts. They clear no invoices at all: 96% of both invoice steps are done by people. Price and quantity changes are 100% manual, as you'd expect for exceptions.

![Who executes each step](output/automation.png)

**The map puts the payment block on the main road.** It keeps the eight activities that touch at least 10% of items and every direct handover between them seen at least 15,000 times. Line width follows frequency. Vendor invoice and goods receipt come in either order (110k one way, 81k the other), which is the invoice-first flow doing what it allows. Remove Payment Block isn't a side branch: 49k times, lifting a block leads straight into clearing the invoice.

```mermaid
flowchart TD
    start((start))
    finish((end))
    a0["Create Purchase Order Item<br/>100% of items"]
    a1["Record Goods Receipt<br/>93% of items"]
    a2["Record Invoice Receipt<br/>84% of items"]
    a3["Vendor creates invoice<br/>84% of items"]
    a4["Clear Invoice<br/>73% of items"]
    a5["Remove Payment Block<br/>22% of items"]
    a6["Create Purchase Requisition Item<br/>18% of items"]
    a7["Receive Order Confirmation<br/>13% of items"]
    start -->|200k| a0
    start -->|47k| a6
    a2 -->|135k| a4
    a1 -->|112k| a2
    a3 -->|110k| a1
    a0 -->|103k| a3
    a3 -->|95k| a2
    a1 -->|81k| a3
    a0 -->|77k| a1
    a5 -->|49k| a4
    a6 -->|46k| a0
    a2 -->|38k| a5
    a0 -->|31k| a7
    a7 -->|20k| a1
    a2 -->|16k| a1
    a1 -->|15k| a5
    a4 -->|181k| finish
    a2 -->|23k| finish
    a1 -->|23k| finish
    linkStyle 0 stroke-width:6.0px
    linkStyle 1 stroke-width:2.2px
    linkStyle 2 stroke-width:4.4px
    linkStyle 3 stroke-width:3.8px
    linkStyle 4 stroke-width:3.8px
    linkStyle 5 stroke-width:3.6px
    linkStyle 6 stroke-width:3.4px
    linkStyle 7 stroke-width:3.0px
    linkStyle 8 stroke-width:2.9px
    linkStyle 9 stroke-width:2.2px
    linkStyle 10 stroke-width:2.2px
    linkStyle 11 stroke-width:1.9px
    linkStyle 12 stroke-width:1.8px
    linkStyle 13 stroke-width:1.5px
    linkStyle 14 stroke-width:1.4px
    linkStyle 15 stroke-width:1.4px
    linkStyle 16 stroke-width:5.5px
    linkStyle 17 stroke-width:1.6px
    linkStyle 18 stroke-width:1.6px
    classDef block fill:#E3F4EA,stroke:#11A05A,stroke-width:2px,color:#1A2740
    class a5 block
```

Drawn by `scripts/charts.py` from `results.json` (source in `output/process_map.mmd`). Repeats of the same step are left out. The largest, Record Service Entry Sheet, happens 139k times on 2% of items and would swamp the picture.

**The process has a long tail.** 11,938 distinct paths for 251,270 items. The happy path (create, vendor invoice, goods receipt, invoice receipt, clear) covers 20.0% on its own, the top 10 cover 59.5% and 45 variants cover 80%. 9,001 paths occur exactly once.

The five most common paths:

| Items | Path |
|---|---|
| 20.0% | Create Purchase Order Item > Vendor creates invoice > Record Goods Receipt > Record Invoice Receipt > Clear Invoice |
| 12.3% | Create Purchase Order Item > Record Goods Receipt > Vendor creates invoice > Record Invoice Receipt > Clear Invoice |
| 4.9% | Create Purchase Order Item > Record Goods Receipt |
| 4.5% | Create Purchase Order Item > Vendor creates invoice > Record Goods Receipt > Record Invoice Receipt > Remove Payment Block > Clear Invoice |
| 3.9% | Create Purchase Order Item > Receive Order Confirmation > Record Goods Receipt > Vendor creates invoice > Record Invoice Receipt > Clear Invoice |

The fourth path is the happy path plus a payment block, which puts blocks inside the normal process rather than at its edges. The third, goods received and nothing else, is 72% consignment, where invoicing never happens on the item.

![Variant coverage](output/variants.png)

## Data quality

464 items (0.2%) were left out: their events carry impossible dates (the earliest is 1948) or the item wasn't created in 2018, the year the log covers. That leaves 251,270 items and 1,591,969 events. Throughput only counts items that reached "Clear Invoice".

## Run it

```sh
pip install -r requirements.txt
# download BPI_Challenge_2019.xes (728 MB) from the DOI above into data/raw/
python scripts/xes_to_parquet.py   # streams the XES into two Parquet tables
python scripts/analyze.py          # writes output/results.json
python scripts/charts.py           # writes the four charts and the process map
python tests/test_rules.py         # checks the rules on a hand-built log
```

The XES converter streams the file with `iterparse` and clears each element after reading it, so the 728 MB XML tree never has to fit in memory. The analysis is plain pandas: every metric is a few readable lines, which matters more here than a process-mining library's defaults. The rule checks (compliance and after-the-fact POs) are tested on 14 hand-built items where every answer is known, including cases each rule should skip.

## Limitations

- **The rules are simplified.** "Cleared before any goods receipt" ignores partial deliveries and item-level tolerances that a real SAP configuration would apply, so the 654 are candidates for review, not confirmed violations.
- **"Vendor creates invoice" is a document date.** It's the date on the vendor's invoice, not when it arrived, so the after-the-fact rule can include vendors who backdate invoices.
- **No payment terms.** The log has no due dates, so it can't say whether invoices were paid on time, only when they were cleared.
- **One company, one year.** The numbers describe this log, not purchasing in general.

---

Akshay Ashok · [axwolf13.github.io](https://axwolf13.github.io/)

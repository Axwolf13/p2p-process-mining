"""
Charts for the README, drawn from output/results.json and output/variant_coverage.npy.

    python scripts/charts.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

# Same validated pair as the portfolio charts (accent vs recessive gray, both >= 3:1 on white)
ACCENT, MUTED = "#11A05A", "#838EA2"
INK, SUB, GRID = "#1A2740", "#5A6B85", "#E2E4DB"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": SUB,
    "xtick.color": SUB, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "figure.dpi": 150, "savefig.bbox": "tight", "savefig.facecolor": "white",
})


def throughput(r):
    d = r["throughput_days"]
    flows = list(d)
    fig, ax = plt.subplots(figsize=(7.5, 2.4))
    for i, f in enumerate(flows):
        y = len(flows) - 1 - i
        ax.plot([d[f]["median"], d[f]["p90"]], [y, y], color=MUTED, lw=2, solid_capstyle="round", zorder=1)
        ax.scatter([d[f]["median"]], [y], s=60, color=ACCENT, zorder=3, edgecolor="white", linewidth=1.5)
        ax.scatter([d[f]["p90"]], [y], s=60, color=MUTED, zorder=3, edgecolor="white", linewidth=1.5)
        ax.text(d[f]["p90"] + 3, y, f"median {d[f]['median']:.0f} d · p90 {d[f]['p90']:.0f} d",
                va="center", fontsize=9, color=SUB)
    ax.set_yticks(range(len(flows)))
    ax.set_yticklabels([f"{f}  (n={d[f]['completed']:,})" for f in reversed(flows)])
    ax.set_xlim(0, 175)
    ax.set_xlabel("days from purchase-order item to last invoice cleared")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Throughput by flow: median (green) to 90th percentile", loc="left", fontsize=11, color=INK)
    fig.savefig(OUT / "throughput.png")


def automation(r):
    a = r["automation"]
    acts = [k for k in a if a[k]["none_pct"] < 50][:9]
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    for i, k in enumerate(acts):
        y = len(acts) - 1 - i
        b, u = a[k]["batch_pct"], a[k]["user_pct"]
        ax.barh(y, b, height=0.55, color=ACCENT)
        ax.barh(y, u, left=b, height=0.55, color=MUTED, edgecolor="white", linewidth=2)
        ax.text(101.5, y, f"{u:.0f}% manual", va="center", fontsize=9, color=SUB)
    ax.set_yticks(range(len(acts)))
    ax.set_yticklabels(list(reversed(acts)))
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of events")
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    handles = [plt.Rectangle((0, 0), 1, 1, color=ACCENT), plt.Rectangle((0, 0), 1, 1, color=MUTED)]
    ax.legend(handles, ["batch (automated)", "user (manual)"], loc="lower center", bbox_to_anchor=(0.45, 1.0),
              ncol=2, frameon=False, fontsize=9)
    ax.set_title("Who executes each step", loc="left", fontsize=11, color=INK, pad=24)
    fig.savefig(OUT / "automation.png")


def variants(r):
    cum = np.load(OUT / "variant_coverage.npy")
    x = np.arange(1, len(cum) + 1)
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    ax.plot(x, cum * 100, color=ACCENT, lw=2)
    v = r["variants"]
    for n, label in [(10, f"top 10: {v['top10_pct']:.0f}%"), (v["variants_for_80pct"], f"{v['variants_for_80pct']} variants: 80%")]:
        ax.scatter([n], [cum[n - 1] * 100], s=40, color=ACCENT, zorder=3, edgecolor="white", linewidth=1.5)
        ax.annotate(label, (n, cum[n - 1] * 100), xytext=(8, -14), textcoords="offset points", fontsize=9, color=SUB)
    ax.set_xscale("log")
    ax.set_ylim(0, 102)
    ax.set_xlabel(f"variants, most common first (log scale, {v['distinct']:,} in total)")
    ax.set_ylabel("% of cases covered")
    ax.grid(color=GRID, lw=0.8)
    ax.spines["left"].set_visible(True)
    ax.set_axisbelow(True)
    ax.set_title("A few variants cover most cases; thousands occur once", loc="left", fontsize=11, color=INK)
    fig.savefig(OUT / "variants.png")


def blocks(r):
    areas = r["payment_blocks"]["by_spend_area"]
    names = [a for a in areas if a != "(blank)"][:7]
    fig, ax = plt.subplots(figsize=(7.5, 2.9))
    top = max(names, key=lambda a: areas[a]["share_of_all_blocks_pct"])
    for i, a in enumerate(names):
        y = len(names) - 1 - i
        v = areas[a]
        ax.barh(y, v["block_pct"], height=0.55, color=ACCENT if a == top else MUTED)
        ax.text(v["block_pct"] + 0.6, y, f"{v['block_pct']:.0f}% of {v['items']:,} items", va="center", fontsize=9, color=SUB)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(list(reversed(names)))
    ax.set_xlim(0, 40)
    ax.set_xlabel("% of items that needed a payment block removed")
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_title(f"Payment blocks by spend area ({top}, in green, holds {areas[top]['share_of_all_blocks_pct']:.0f}% of all blocks)",
                 loc="left", fontsize=11, color=INK)
    fig.savefig(OUT / "payment_blocks.png")


def process_map(r):
    """Mermaid source for the README's process map. GitHub renders it natively."""
    pm = r["process_map"]
    ids = {a: f"a{i}" for i, a in enumerate(pm["nodes"])}
    lines = ["flowchart TD", "    start((start))", "    finish((end))"]
    lines += [f'    {ids[a]}["{a}<br/>{p:.0f}% of items"]' for a, p in pm["nodes"].items()]
    links = [("start", ids[a], c) for a, c in pm["starts"].items()]
    links += [(ids[a], ids[b], c) for a, b, c in pm["edges"]]
    links += [(ids[a], "finish", c) for a, c in pm["ends"].items()]
    top = max(c for _, _, c in links)
    lines += [f"    {x} -->|{c / 1000:.0f}k| {y}" for x, y, c in links]
    # line width follows frequency, 1 to 6 px
    lines += [f"    linkStyle {i} stroke-width:{1 + 5 * c / top:.1f}px" for i, (_, _, c) in enumerate(links)]
    lines += ["    classDef block fill:#E3F4EA,stroke:#11A05A,stroke-width:2px,color:#1A2740",
              f"    class {ids['Remove Payment Block']} block"]
    (OUT / "process_map.mmd").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    r = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    throughput(r); automation(r); variants(r); blocks(r); process_map(r)
    print("charts written")

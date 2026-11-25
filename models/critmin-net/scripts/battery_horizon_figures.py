"""Figures for docs/battery-horizon.md, from results/battery_horizon/ (scripts/battery_horizon.py writes it) and the
horizon's own curves. PRELIMINARY numbers. Needs a full Gurobi licence for the curve examples.

    PYTHONPATH=src python scripts/battery_horizon.py
    PYTHONPATH=src python scripts/battery_horizon_figures.py
"""
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results" / "battery_horizon"
OUT = ROOT / "docs" / "figures"
# categorical slots in fixed order (validated: CVD and normal-vision separation pass; contrast is relieved by direct
# labels and the tables in the doc)
REGION = {'CHN': ('China', '#2a78d6'), 'US': ('US', '#eb6834'), 'ALLY': ('Allies', '#1baf7a'),
          'ROW': ('Rest of world', '#eda100'), 'SPC': ('DRC', '#e87ba4')}
INK, MUTED, GRID, SURFACE = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'


def style(ax, title, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=10, color=INK)
    ax.set_ylabel(ylabel, fontsize=8.5, color=MUTED)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def stacked(ax, q, title, ylabel, label_year=2040):
    w = q.pivot_table(index="year", columns="region", values="output", aggfunc="sum").fillna(0.0)
    cols = [r for r in REGION if r in w and w[r].max() > 0]
    base = pd.Series(0.0, index=w.index)
    for r in cols:
        top = base + w[r]
        ax.fill_between(w.index, base, top, color=REGION[r][1], linewidth=0, alpha=0.9)
        ax.plot(w.index, top, color=SURFACE, linewidth=1.2)              # a surface gap between fills
        share = w.loc[label_year, r] / w.loc[label_year].sum()
        if share > 0.04:                                                 # direct labels, selectively
            ax.text(label_year + 0.3, (base + top).loc[label_year] / 2, f"{REGION[r][0]} {share:.0%}",
                    fontsize=7.5, color=INK, va="center")
        base = top
    ax.axvline(2024.5, color=MUTED, linewidth=0.8, linestyle=(0, (2, 2)))
    style(ax, title, ylabel)
    ax.set_xlim(2023, 2045)
    ax.set_xticks([2025, 2030, 2035, 2040])


def fig_cells(P):
    cases = ["no policy", "policy", "no policy + onshore", "policy + onshore"]
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 6.2), sharey=True, facecolor=SURFACE)
    for ax, c in zip(axes.flat, cases):
        q = P[(P.demand == "STEPS") & (P.case == c) & (P.stage == "cell")]
        stacked(ax, q, c, "GWh of cells")
    fig.suptitle("Where cells are made, STEPS demand (left of the dashed line: observed, calibrated)", x=0.01,
                 ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "cells_by_case.png", dpi=150)


def fig_lithium(P):
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True, facecolor=SURFACE)
    for ax, c, t in zip(axes, ["no policy", "no policy, new mines at own cost", "no policy, myopic",
                               "no policy, offsets kept"],
                        ["perfect foresight", "new mines at own cost", "myopic (5 years in view)",
                         "2024's offsets kept"]):
        q = P[(P.demand == "STEPS") & (P.case == c) & (P.stage == "mine") & (P.key == "Li")]
        stacked(ax, q, t, "kt lithium mined")
    fig.suptitle("Lithium mining by region, no policy after 2024", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "lithium_mining.png", dpi=150)


def fig_costs(S):
    s = S[~S.case.isin(["no policy, myopic", "no policy, offsets kept",            # these count other things
                        "no policy, new mines at own cost"])].copy()
    base = s[s.case == "no policy"].set_index("demand").resource_cost
    s["delta"] = (s.resource_cost - s.demand.map(base)) / 1000.0
    s = s[s.case != "no policy"]
    fig, ax = plt.subplots(figsize=(7.5, 3.4), facecolor=SURFACE)
    labels = [f"{c} ({d})" for d, c in zip(s.demand, s.case)]
    ax.barh(range(len(s)), s.delta, color="#2a78d6", height=0.55)
    for i, v in enumerate(s.delta):
        ax.text(v + 0.8, i, f"+{v:.0f}", va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(s)), labels)
    ax.invert_yaxis()
    style(ax, "Resource cost over the no-policy case, 2023-2040", "")
    ax.set_xlabel("billion USD, discounted at 8% to 2024; tariffs and credits (transfers) excluded", fontsize=8,
                  color=MUTED)
    ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(OUT / "cost_by_case.png", dpi=150)


def fig_curves():
    from critmin_net import horizon as H
    inp = H.load("STEPS")
    cal = H.calibrate(inp)
    net, params, bkw, _, _ = H.network(inp, cal=cal)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4), facecolor=SURFACE)
    ax = axes[0]
    for (y, ls) in ((2024, "-"), (2035, "--")):
        for nodes, yy, blocks in bkw["cost_curve"]:
            if yy == y and nodes and nodes[0][:2] == ('mine', 'Li') and nodes[0][-1] == 'ALLY':
                P = net["cost"]['mine'][0][('Li', 'ALLY', y)]
                xs, ps, cum = [0.0], [], 0.0
                for size, adder in blocks:
                    if size is None:
                        break
                    cum += size; xs.append(cum); ps.append(P + adder)
                ax.step(xs[1:], ps, where="pre", color="#1baf7a", linestyle=ls, linewidth=2, label=str(y))
    ax.set_ylim(0, 60); ax.set_xlim(0, 600)
    ax.legend(frameon=False, fontsize=8, title="year", title_fontsize=8)
    style(ax, "Supply curve: allied (Australian) lithium mining", "USD per kg Li (offset included)")
    ax.set_xlabel("kt lithium a year", fontsize=8.5, color=MUTED)
    ax.annotate("2035: operations at their own costs, then new" + chr(10) + "capacity at the region's cost, then rising",
                xy=(130, 24), fontsize=7.5, color=INK)
    ax.annotate("2024: with the calibration's offset (+20)", xy=(130, 40), fontsize=7.5, color=INK)
    ax = axes[1]
    for (g, r, y), blocks in bkw["demand_curve"].items():
        if g == ('use', 'ev') and r == 'US' and y in (2030, 2040):
            xs, vs, cum = [], [], 0.0
            for size, value in blocks:
                cum += size; xs.append(cum); vs.append(value)
            ax.step(xs, vs, where="pre", color="#eb6834", linestyle="-" if y == 2030 else "--", linewidth=2,
                    label=str(y))
    ax.set_ylim(0, None); ax.set_xlim(0, None)
    ax.legend(frameon=False, fontsize=8, title="year", title_fontsize=8)
    style(ax, "Demand curve: US EV batteries", "value, USD per kWh")
    ax.set_xlabel("GWh a year", fontsize=8.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "curves_examples.png", dpi=150)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    P = pd.read_csv(RES / "production.csv")
    S = pd.read_csv(RES / "summary.csv")
    fig_cells(P)
    fig_lithium(P)
    fig_costs(S)
    fig_curves()
    print("written to", OUT)


if __name__ == "__main__":
    main()

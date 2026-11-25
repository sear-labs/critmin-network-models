"""Read results/battery_scenarios/ (scripts/battery_scenarios.py) and say what each axis does: for every headline
result, its range over the whole set and its mean at each value of each axis. PRELIMINARY.
Writes results/battery_scenarios/headlines.csv and axis_effects.csv (not committed).

EXCLUDE: runs to leave out, as {axis: value} filters; none since 0.15.1, which fixed the two myopic artefacts the
first full run showed (share floors met by shrinking the market; plants built for a window's last year and
abandoned).

    PYTHONPATH=src python scripts/battery_scenarios_summary.py
"""
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "results" / "battery_scenarios"
AXES = ["demand", "policy", "newmines", "foresight", "persistence", "costpath"]
# headline: (stage, key, regions summed, year)
HEADLINES = {
    "li_mined_allies_2040": (('mine', 'Li'), ('ALLY',), 2040),
    "li_mined_row_drc_2040": (('mine', 'Li'), ('ROW', 'SPC'), 2040),
    "li_mined_china_2040": (('mine', 'Li'), ('CHN',), 2040),
    "li_refined_china_2040": (('refine', 'Li'), ('CHN',), 2040),
    "ni_refined_china_2040": (('refine', 'Ni'), ('CHN',), 2040),
    "co_refined_china_2040": (('refine', 'Co'), ('CHN',), 2040),
    "anode_china_2040": (('anode', 'anode'), ('CHN',), 2040),
    "cells_china_2040": (('cell', 'cell'), ('CHN',), 2040),
    "cells_us_allies_2040": (('cell', 'cell'), ('US', 'ALLY'), 2040),
    "cells_china_2030": (('cell', 'cell'), ('CHN',), 2030),
}


EXCLUDE = []


def main():
    S = pd.read_csv(OUT / "summary.csv")
    drop = pd.Series(False, index=S.index)
    for e in EXCLUDE:
        drop |= pd.concat([S[k] == v for k, v in e.items()], axis=1).all(axis=1)
    print(f"excluded {int(drop.sum())} runs: {EXCLUDE}")
    S = S[~drop].copy()
    P = pd.read_csv(OUT / "production.csv")
    for h, ((s, k), regions, y) in HEADLINES.items():
        q = P[(P.stage == s) & (P.key == k) & (P.year == y)]
        tot = q.groupby("name").output.sum()
        part = q[q.region.isin(regions)].groupby("name").output.sum()
        S[h] = S.name.map((part / tot).fillna(0.0) * 100)
    base = S.groupby("demand").resource_cost.transform(
        lambda c: c[(S.loc[c.index, "policy"] == "none")].mean())
    S["cost_vs_no_policy_pct"] = (S.resource_cost / base - 1) * 100
    S.to_csv(OUT / "headlines.csv", index=False)
    cols = list(HEADLINES) + ["recycled_2040", "yards_2040", "cost_vs_no_policy_pct"]
    rows = []
    for c in cols:
        rows.append(dict(result=c, axis="(all runs)", value="min", mean=S[c].min()))
        rows.append(dict(result=c, axis="(all runs)", value="max", mean=S[c].max()))
        for a in AXES:
            for v, g in S.groupby(a):
                rows.append(dict(result=c, axis=a, value=v, mean=g[c].mean()))
    A = pd.DataFrame(rows)
    A.to_csv(OUT / "axis_effects.csv", index=False)
    print(f"{len(S)} runs; failed: {int((S.status != 2).sum())}; unmet demand in any run: {S.unmet.max():.3g}")
    for c in cols:
        a = A[A.result == c]
        spread = {ax: a[a.axis == ax]["mean"].max() - a[a.axis == ax]["mean"].min() for ax in AXES}
        top = sorted(spread.items(), key=lambda kv: -kv[1])[:2]
        print(f"{c:24s} range {a[a.value == 'min']['mean'].iloc[0]:7.1f} to {a[a.value == 'max']['mean'].iloc[0]:7.1f};"
              f" moved most by " + ", ".join(f"{ax} ({d:.1f})" for ax, d in top))


if __name__ == "__main__":
    main()

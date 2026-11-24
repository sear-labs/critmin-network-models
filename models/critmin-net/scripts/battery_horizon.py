"""Run the battery horizon (critmin_net.horizon) in both scenarios under both demand cases and write the results to
results/battery_horizon/ (not committed): production, capacity and builds by stage group, region and year, and a
summary of cost and shares. PRELIMINARY. Needs a full Gurobi licence; about ten seconds.

    PYTHONPATH=src python scripts/battery_horizon.py
"""
from pathlib import Path

import pandas as pd

from critmin_net import battery as B
from critmin_net import horizon as H

OUT = Path(__file__).resolve().parents[1] / "results" / "battery_horizon"
SHOW = [('mine', 'Li'), ('refine', 'Li'), ('refine', 'Ni'), ('anode', 'anode'), ('cath', 'lfp'), ('cath', 'nmc_hi'),
        ('cell', 'cell')]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cal = B.calibrate()
    rows, built, summary = [], [], []
    for demand in ("STEPS", "CPS"):
        inp = H.load(demand)
        for sc in ("cost", "onshore"):
            r = H.run(sc, inputs=inp, cal=cal)
            assert r["status"] == 2, (demand, sc, r["status"])
            for (s, k, rg, y), v in r["prod"].items():
                rows.append(dict(demand=demand, scenario=sc, stage=s, key=k, region=rg, year=y, output=v,
                                 capacity=r["cap"][s, k, rg, y]))
            for (s, k, rg, y), v in r["built"].items():
                built.append(dict(demand=demand, scenario=sc, stage=s, key=k, region=rg, online=y, built=v))
            summary.append(dict(demand=demand, scenario=sc, cost_musd=r["obj"],
                                unmet=sum(r["short"].values())))
    prod = pd.DataFrame(rows)
    prod.to_csv(OUT / "production.csv", index=False)
    pd.DataFrame(built).to_csv(OUT / "built.csv", index=False)
    sm = pd.DataFrame(summary)
    sm.to_csv(OUT / "summary.csv", index=False)
    print(sm.to_string(index=False))
    for demand in ("STEPS", "CPS"):
        for sc in ("cost", "onshore"):
            q = prod[(prod.demand == demand) & (prod.scenario == sc)]
            print(f"\n{demand} {sc}: share of output, China / US+allies / rest of world and DRC (%)")
            for s, k in SHOW:
                g = q[(q.stage == s) & (q.key == k)]
                cells = []
                for y in (2024, 2030, 2035, 2040):
                    gy = g[g.year == y]; t = gy.output.sum()
                    sh = {a: gy[gy.region.isin(rs)].output.sum() / t * 100 for a, rs in
                          (('C', ['CHN']), ('U', ['US', 'ALLY']), ('R', ['ROW', 'SPC']))}
                    cells.append(f"{y}: {sh['C']:3.0f}/{sh['U']:3.0f}/{sh['R']:3.0f}")
                print(f"  {s:6s} {k:7s}", "  ".join(cells))


if __name__ == "__main__":
    main()

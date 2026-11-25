"""Run the battery horizon (critmin_net.horizon) and write results/battery_horizon/ (not committed): production,
capacity, builds, demand served and recycling by stage group, region and year, and a summary of costs and transfers,
and cem-impacts' export of each case (results/battery_horizon/export/<demand>_<case>/, critmin_net.export),
for each case: no policy after 2024 or current policy (tariffs, 45X), each with and without the onshoring floors,
and current policy with China's export controls on the US from 2027, under stated (STEPS) and current (CPS) policies
demand, with perfect foresight; and, for STEPS, the cost case myopic (five years in view), with today's unexplained
costs (the calibration's offsets) kept after 2024, and with new mines at their region's own cost instead of the
greenfield studies' (the sensitivity lithium's regional split turns on). PRELIMINARY. Needs a full Gurobi licence; about a minute.

    PYTHONPATH=src python scripts/battery_horizon.py
"""
from pathlib import Path

import pandas as pd

from critmin_net import export as E
from critmin_net import horizon as H

OUT = Path(__file__).resolve().parents[1] / "results" / "battery_horizon"
KEEP = {"wedge_carry": {2024: 1.0, 2025: 1.0}}    # today's unexplained costs (the calibration's offsets) kept
NO_GF = {"greenfield": {}}                        # new mines at the region's own cost, not the greenfield studies'
CONTROLS = {"china_controls": {"from_year": 2027}}   # China's export controls on the US from 2027
CASES = [("no policy", "cost", None, None, None), ("policy", "cost", {}, None, None),
         ("no policy + onshore", "onshore", None, None, None), ("policy + onshore", "onshore", {}, None, None),
         ("policy + China controls", "cost", CONTROLS, None, None),
         ("no policy, myopic", "cost", None, 5, None), ("no policy, offsets kept", "cost", None, None, KEEP),
         ("no policy, new mines at own cost", "cost", None, None, NO_GF)]
SHOW = [('mine', 'Li'), ('refine', 'Li'), ('refine', 'Ni'), ('anode', 'anode'), ('cath', 'lfp'), ('cath', 'nmc_hi'),
        ('cell', 'cell')]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    prod, built, served, summary = [], [], [], []
    for demand in ("STEPS", "CPS"):
        inp = H.load(demand)
        cal = H.calibrate(inp)
        for name, sc, pol, fs, kn in CASES:
            if (fs or kn) and demand != "STEPS":
                continue
            r = H.run(sc, inputs=inp, cal=cal, policy=pol, foresight=fs, knobs=kn)
            assert r["status"] == 2, (demand, name, r["status"])
            slug = f"{demand}_{name}".replace(" + ", "_").replace(", ", "_").replace(" ", "-")
            E.write(r, OUT / "export" / slug, scenario=f"{demand}, {name}",
                    meta=dict(demand=demand, case=name, scenario_kind=sc, policy=pol is not None, foresight=fs,
                              knobs=sorted(kn) if kn else [], preliminary=True))
            tag = dict(demand=demand, case=name)
            for (s, k, rg, y), v in r["prod"].items():
                prod.append(dict(tag, stage=s, key=k, region=rg, year=y, output=v, capacity=r["cap"][s, k, rg, y]))
            for (s, k, rg, y), v in r["built"].items():
                built.append(dict(tag, stage=s, key=k, region=rg, online=y, built=v))
            for (g, rg, y), v in r["served"].items():
                served.append(dict(tag, good=f"{g[0]}:{g[1]}", region=rg, year=y, served=v))
            summary.append(dict(tag, resource_cost=r["resource_cost"], tariffs_paid=r["tariffs_paid"],
                                credits=r["credits"], unmet=sum(r["short"].values()),
                                recycled_2040=sum(v for (q, y), v in r["recycled"].items() if y == 2040)))
    P = pd.DataFrame(prod)
    P.to_csv(OUT / "production.csv", index=False)
    pd.DataFrame(built).to_csv(OUT / "built.csv", index=False)
    pd.DataFrame(served).to_csv(OUT / "served.csv", index=False)
    S = pd.DataFrame(summary)
    S.to_csv(OUT / "summary.csv", index=False)
    print("Discounted (8%, to 2024) million USD; resource cost excludes tariffs and credits (transfers).")
    print(S.round(0).to_string(index=False))
    for (demand, name), q in P.groupby(["demand", "case"], sort=False):
        print(f"\n{demand}, {name}: share of output, China / US+allies / rest of world and DRC (%)")
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

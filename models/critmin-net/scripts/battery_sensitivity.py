"""One knob at a time: the battery horizon's results at a low and a high value of each scenario knob whose value
nobody publishes (horizon.KNOBS), against the default, so the knobs that move results become the scenario axes.
A one-at-a-time sweep, not a Morris screen: it misses interactions, but each solve takes seconds. PRELIMINARY.
Needs a full Gurobi licence; a few minutes. Writes results/battery_horizon/sensitivity.csv (not committed).

    PYTHONPATH=src python scripts/battery_sensitivity.py
"""
from pathlib import Path

import pandas as pd

from critmin_net import horizon as H

OUT = Path(__file__).resolve().parents[1] / "results" / "battery_horizon"
K = H.KNOBS


def scaled(d, f):
    return {k: v * f for k, v in d.items()}


# (knob, label, knobs override); each knob at a low and a high value, ours unless the comment says otherwise
SWEEP = [
    ("supply_elasticity", "x0.5", {"supply_elasticity": scaled(K["supply_elasticity"], 0.5)}),
    ("supply_elasticity", "x2", {"supply_elasticity": scaled(K["supply_elasticity"], 2.0)}),
    ("demand_elasticity", "x0.5", {"demand_elasticity": scaled(K["demand_elasticity"], 0.5)}),
    ("demand_elasticity", "x2", {"demand_elasticity": scaled(K["demand_elasticity"], 2.0)}),
    ("entry", "0.01", {"entry": 0.01}),
    ("entry", "0.05", {"entry": 0.05}),
    ("discount", "0.05", {"discount": 0.05}),
    ("discount", "0.12", {"discount": 0.12}),
    ("cost_path", "low", {"cost_path": "low"}),
    ("cost_path", "high", {"cost_path": "high"}),
    ("chem_band", "0.05", {"chem_band": 0.05}),
    ("chem_band", "0.20", {"chem_band": 0.20}),
    ("retire", "2%/yr", {"retire": {'mine': 0.02, 'refine': 0.02}}),
    ("retire", "6%/yr", {"retire": {'mine': 0.06, 'refine': 0.06}}),
    ("second_life", "anchor 0.10", {"second_life": {**K["second_life"], 'anchor': 0.10}}),
    ("second_life", "anchor 0.40", {"second_life": {**K["second_life"], 'anchor': 0.40}}),
    ("greenfield", "own cost", {"greenfield": {}}),
    ("wedge_carry", "kept", {"wedge_carry": {2024: 1.0, 2025: 1.0}}),
    ("no_entry", "DRC open", {"no_entry": []}),
    ("yard", "off", {"yard": False}),
]


def summary(r):
    def share(g, regions, y=2040):
        d = {k[-2]: v for k, v in r["prod"].items() if k[:2] == g and k[-1] == y}
        t = sum(d.values())
        return sum(d.get(x, 0.0) for x in regions) / t if t else float("nan")
    return dict(resource_cost=r["resource_cost"],
                li_mined_allies_2040=share(('mine', 'Li'), ('ALLY',)),
                li_mined_row_drc_2040=share(('mine', 'Li'), ('ROW', 'SPC')),
                li_refined_china_2040=share(('refine', 'Li'), ('CHN',)),
                cells_china_2040=share(('cell', 'cell'), ('CHN',)),
                cells_us_allies_2040=share(('cell', 'cell'), ('US', 'ALLY')),
                recycled_2040=sum(v for (q, y), v in r["recycled"].items() if y == 2040))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inp = H.load("STEPS")
    cal = H.calibrate(inp)
    rows = [dict(knob="default", value="", **summary(H.run("cost", inputs=inp, cal=cal)))]
    for knob, label, kn in SWEEP:
        r = H.run("cost", inputs=inp, cal=cal, knobs=kn)
        assert r["status"] == 2, (knob, label, r["status"])
        rows.append(dict(knob=knob, value=label, **summary(r)))
    r = H.run("cost", inputs=inp, cal=cal, foresight=5)
    rows.append(dict(knob="foresight", value="5 years", **summary(r)))
    S = pd.DataFrame(rows)
    base = S.iloc[0]
    S["cost_change_pct"] = (S.resource_cost / base.resource_cost - 1) * 100
    S.to_csv(OUT / "sensitivity.csv", index=False)
    show = S.copy()
    for c in [c for c in S.columns if c.endswith("_2040") and c != "recycled_2040"]:
        show[c] = (show[c] * 100).round(0)
    print("STEPS, no policy after 2024; shares in %, recycling in GWh-equivalent; PRELIMINARY")
    print(show.drop(columns="resource_cost").round(1).to_string(index=False))


if __name__ == "__main__":
    main()

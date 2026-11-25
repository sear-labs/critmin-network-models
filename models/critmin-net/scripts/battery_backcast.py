"""Backcast: the battery horizon calibrated on 2023-2024, its 2025 against what was observed in 2025. 2025 demand is an
input (IEA's), so the test is where things were made: each stage's regional shares, the model's against the observed.
PRELIMINARY. Needs a full Gurobi licence; about a minute. Writes results/battery_horizon/backcast.csv (not committed).

The observed shares come from src/critmin_net/data/battery_horizon/backcast/observed_2025.csv (sourced and checked,
one row per number): the rows marked `compare`, one source per group (USGS for mining, as the calibration's 2023-2024
are; IEA's Global EV Outlook 2026 for cells; IEA's Global Critical Minerals Outlook 2026 for refining, cathode and
anode, whose cathode and anode shares are China's alone and given as text: "98", "two-thirds (~67)", ">90", read as
the number, a lower bound for ">"). Nickel-based cathode compares with high- and low-nickel NMC together.

    PYTHONPATH=src python scripts/battery_backcast.py
"""
from pathlib import Path

import pandas as pd

from critmin_net import battery as B
from critmin_net import export as E
from critmin_net import horizon as H
from critmin_net import network as N

OUT = Path(__file__).resolve().parents[1] / "results" / "battery_horizon"
OBS = N.RAW / "battery_horizon" / "backcast" / "observed_2025.csv"
GROUPS = [('mine', 'Li'), ('mine', 'Ni'), ('mine', 'Co'), ('mine', 'graphite'), ('refine', 'Li'), ('refine', 'Ni'),
          ('refine', 'Co'), ('anode', 'anode'), ('cath', 'lfp'), ('cath', 'nmc'), ('cell', 'cell')]


def model_shares(r, y):
    """Each group's regional shares in year y, from the export's production (co-products counted: cobalt mined with
    nickel, metals recovered by recycling), cells summed over chemistries."""
    P = E.tables(r)["production"]
    P = P[P.year == y].copy()
    P.loc[P.stage == 'cell', 'good'] = 'cell'
    P.loc[(P.stage == 'cath') & P.good.str.startswith('nmc'), 'good'] = 'nmc'
    rows = []
    for g in GROUPS:
        q = P[(P.stage == g[0]) & (P.good == g[1])]
        d = q.groupby("region").amount.sum().to_dict()
        t = sum(d.values())
        for rg in B.REGIONS:
            rows.append(dict(stage=g[0], good=g[1], model_region=rg, year=y, model_share=d.get(rg, 0.0) / t if t else 0.0,
                             model_amount=d.get(rg, 0.0)))
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inp = H.load("STEPS")
    cal = H.calibrate(inp)
    r = H.run("cost", inputs=inp, cal=cal, policy={})     # 2025 had the policy then in force
    M = pd.concat([model_shares(r, 2024), model_shares(r, 2025)], ignore_index=True)
    if OBS.is_file():
        O = pd.read_csv(OBS)
        O = O[O["compare"]].copy()
        num = pd.to_numeric(O.share_of_world, errors="coerce")
        txt = pd.to_numeric(O.value.astype(str).str.extract(r"(\d+(?:\.\d+)?)")[0], errors="coerce") / 100
        O["share"] = num.fillna(txt.where(O.unit.astype(str).str.startswith("%")))
        O[["stage", "good"]] = O.group.str.split(":", expand=True)
        O = O.groupby(["stage", "good", "model_region", "year"], as_index=False).agg(
            observed_share=("share", "sum"), ids=("id", lambda s: " ".join(map(str, s))))
        M = M.merge(O, on=["stage", "good", "model_region", "year"], how="left")
        M["miss_points"] = (M.model_share - M.observed_share) * 100
    M.to_csv(OUT / "backcast.csv", index=False)
    show = M[M.year == 2025].copy()
    show["model_share"] = (show.model_share * 100).round(1)
    if "observed_share" in show:
        show["observed_share"] = (show.observed_share * 100).round(1)
    print("2025, policy then in force; shares of world output in %; PRELIMINARY")
    print(show.drop(columns=["model_amount"]).to_string(index=False))


if __name__ == "__main__":
    main()

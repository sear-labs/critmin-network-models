"""Write a solved horizon run as the folder cem-impacts reads (sear-labs/cem-impacts, cem_impacts.adapters.critmin:
"THE EXPORT"), so its supply-chain studies (the Flows contract) can take critmin-net's results without importing it.

    from critmin_net import horizon as H, export as E
    r = H.run("cost", inputs=inp, cal=cal, policy={})
    E.write(r, "results/battery_horizon/export/STEPS_policy", scenario="STEPS, policy")

One folder per solved scenario, all years:

    run.json        model, model_version, network, scenario, years, status ("optimal"), plus `meta`
    production.csv  stage, process, good, region, year, amount, unit: what each process made, its co-products as
                    their own rows under it; process is the process tuple joined by ":" (mine:Li,
                    refine:bm_nmc_hi:Ni, mine:expand:Li, refine:pyro_nmc_hi:Ni)
    trade.csv       stage, good, origin, destination, year, amount, unit: between regions, summed over makers
    shortfall.csv   stage, good, region, year, amount, unit: demand not met (none in a feasible horizon run)
    stock.csv       stage, good, region, year, amount, unit: held at the end of the year (the yards)
    price.csv       stage, good, region, year, price, unit: the good's balance dual, undiscounted, in million USD
                    per unit of the good (USD per kg for kt, USD per kWh for GWh)

Names are critmin-net's own (stage codes, goods, regions); cem-impacts maps them. Units are the network's
(`net["units"]`): kt contained, kt graphite, GWh, GWh-equivalent. Amounts below 1e-9 are left out. Region cost
(cost.csv) is not written: the horizon reports resource cost for the world, not by region.
"""
import json
from pathlib import Path

import pandas as pd

from . import __version__
from .horizon import by_year_or

MIN = 1e-9


def tables(result):
    """The export's tables, as DataFrames, from horizon.run()'s result (which must hold "detail")."""
    d = result["detail"]
    units = d["units"]
    prod = {}
    for (n, y), x in d["prod"].items():
        p, r = n[:-1], n[-1]
        rows = [((p[0], p[-1]), x)]                # a process makes the good named last in it
        for g, coef in d["coproducts"].get(p, {}).items():
            rows.append((g, by_year_or(coef, y) * x))
        for (s, good), amt in rows:
            key = (s, ":".join(p), good, r, y)
            prod[key] = prod.get(key, 0.0) + amt
    production = pd.DataFrame([dict(stage=s, process=pr, good=g, region=r, year=y, amount=a, unit=units[(s, g)])
                               for (s, pr, g, r, y), a in prod.items() if abs(a) > MIN],
                              columns=["stage", "process", "good", "region", "year", "amount", "unit"])
    trade = pd.DataFrame([dict(stage=s, good=g, origin=e, destination=i, year=y, amount=a, unit=units[(s, g)])
                          for (s, g, e, i, y), a in result["trade"].items() if a > MIN],
                         columns=["stage", "good", "origin", "destination", "year", "amount", "unit"])
    shortfall = pd.DataFrame([dict(stage=s, good=g, region=r, year=y, amount=a, unit=units[(s, g)])
                              for (s, g, r, y), a in d["short"].items() if a > MIN],
                             columns=["stage", "good", "region", "year", "amount", "unit"])
    stock = pd.DataFrame([dict(stage=s, good=g, region=r, year=y, amount=a, unit=units[(s, g)])
                          for (s, g, r, y), a in d["stock"].items() if a > MIN],
                         columns=["stage", "good", "region", "year", "amount", "unit"])
    price = pd.DataFrame([dict(stage=g[0], good=g[1], region=r, year=y, price=v, unit=f"million USD per {units[g]}")
                          for (g, r, y), v in d["price"].items() if g in units],
                         columns=["stage", "good", "region", "year", "price", "unit"])
    return dict(production=production, trade=trade, shortfall=shortfall, stock=stock, price=price)


def write(result, folder, scenario, network="battery", meta=None):
    """Write `result` (horizon.run(), optimal) to `folder` as cem-impacts' critmin-net export. Returns the folder.
    meta: extra JSON-serialisable fields for run.json (demand path, case, knobs changed)."""
    if result.get("status") != 2:
        raise ValueError(f"export.write: only an optimal run is exported, got status {result.get('status')}")
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables(result).items():
        df.sort_values([c for c in df.columns if c not in ("amount", "price", "unit")]).to_csv(
            out / f"{name}.csv", index=False, lineterminator="\n")
    run = dict(model="critmin-net", model_version=__version__, network=network, scenario=scenario,
               years=[int(y) for y in result["detail"]["years"]], status="optimal", **(meta or {}))
    (out / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    return out

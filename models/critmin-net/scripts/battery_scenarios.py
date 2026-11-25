"""The battery horizon's scenario set: every combination of the axes below (the knobs the sensitivity sweep and the
2025 backcast showed move results), each run exported for cem-impacts and summarised. PRELIMINARY.

Axes (AXES): demand path x policy x new-mine costs x foresight x persistence of 2024's patterns x cost path.
Each run's export goes to results/battery_scenarios/export/<name>/ (critmin_net.export); summary.csv has one row per
run; production.csv the regional output of the main stages. Resumable: a run whose export exists is skipped (pass
--redo to rerun). Needs a full Gurobi licence. Each perfect-foresight run takes seconds, a myopic one about half a
minute; the whole set about an hour on one machine, less with --jobs.

    PYTHONPATH=src python scripts/battery_scenarios.py --list          # the runs, nothing solved
    PYTHONPATH=src python scripts/battery_scenarios.py --jobs 4        # all, four at a time
    PYTHONPATH=src python scripts/battery_scenarios.py --only demand=STEPS policy=current
"""
import argparse
import itertools
import json
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from critmin_net import export as E
from critmin_net import horizon as H

OUT = Path(__file__).resolve().parents[1] / "results" / "battery_scenarios"
# axis -> {value: (run() arguments, knobs)}
AXES = {
    "demand": {"STEPS": {}, "CPS": {}},
    "policy": {"none": dict(scenario="cost", policy=None),
               "current": dict(scenario="cost", policy={}),
               "current+onshore": dict(scenario="onshore", policy={}),
               "current+controls": dict(scenario="cost", policy={"china_controls": {"from_year": 2027}})},
    "newmines": {"studies": {}, "owncost": {"knobs": {"greenfield": {}}}},
    "foresight": {"perfect": {}, "5yr": {"foresight": 5}},
    "persistence": {"fade2030": {}, "kept": {"knobs": {"wedge_carry": {2024: 1.0, 2025: 1.0}}}},
    "costpath": {"mid": {}, "low": {"knobs": {"cost_path": "low"}}, "high": {"knobs": {"cost_path": "high"}}},
}
SHOW = [('mine', 'Li'), ('mine', 'Ni'), ('mine', 'Co'), ('mine', 'graphite'), ('refine', 'Li'), ('refine', 'Ni'),
        ('refine', 'Co'), ('anode', 'anode'), ('cath', 'lfp'), ('cath', 'nmc_hi'), ('cath', 'nmc_lo'), ('cell', 'cell')]


def runs():
    names = list(AXES)
    for combo in itertools.product(*(AXES[a] for a in names)):
        yield dict(zip(names, combo))


def name_of(spec):
    return "_".join(spec[a] for a in AXES).replace("+", "-")


def arguments(spec):
    kw, knobs = {}, {}
    for a, v in spec.items():
        d = dict(AXES[a][v])
        knobs.update(d.pop("knobs", {}))
        kw.update(d)
    return kw, knobs


def calibration(demand):
    """The calibration for a demand path, cached (it does not depend on the later years' knobs)."""
    f = OUT / f"cal_{demand}.pkl"
    if f.is_file():
        return pickle.loads(f.read_bytes())
    cal = H.calibrate(H.load(demand))
    f.write_bytes(pickle.dumps(cal))
    return cal


def solve(spec, redo=False):
    name = name_of(spec)
    folder = OUT / "export" / name
    if (folder / "run.json").is_file() and not redo:
        return name, None
    kw, knobs = arguments(spec)
    inp = H.load(spec["demand"])
    t = time.time()
    r = H.run(kw.pop("scenario", "cost"), inputs=inp, cal=calibration(spec["demand"]), knobs=knobs or None, **kw)
    if r["status"] != 2:
        return name, dict(spec, name=name, status=r["status"])
    E.write(r, folder, scenario=name, meta=dict(axes=spec, knobs=sorted(knobs), preliminary=True))
    row = dict(spec, name=name, status=2, seconds=round(time.time() - t, 1), resource_cost=r["resource_cost"],
               tariffs_paid=r["tariffs_paid"], credits=r["credits"], unmet=sum(r["short"].values()),
               recycled_2040=sum(v for (q, y), v in r["recycled"].items() if y == 2040),
               yards_2040=sum(v for k, v in r["detail"]["stock"].items() if k[3] == 2040))
    prod = [dict(name=name, stage=s, key=k, region=rg, year=y, output=v) for (s, k, rg, y), v in r["prod"].items()
            if (s, k) in SHOW and y in (2025, 2030, 2035, 2040)]
    pd.DataFrame(prod).to_csv(folder / "production_summary.csv", index=False)
    (folder / "summary.json").write_text(json.dumps(row, default=str) + "\n", encoding="utf-8")
    return name, row


def collect():
    rows, prod = [], []
    for f in sorted((OUT / "export").glob("*/summary.json")):
        rows.append(json.loads(f.read_text(encoding="utf-8")))
        prod.append(pd.read_csv(f.parent / "production_summary.csv"))
    if rows:
        pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)
        pd.concat(prod, ignore_index=True).to_csv(OUT / "production.csv", index=False)
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--only", nargs="*", default=[], help="axis=value filters")
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    want = dict(x.split("=", 1) for x in a.only)
    todo = [s for s in runs() if all(s[k] == v for k, v in want.items())]
    if a.list:
        for s in todo:
            print(name_of(s))
        print(f"{len(todo)} runs")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for d in sorted({s["demand"] for s in todo}):          # calibrate once per demand, before any workers
        calibration(d)
    t0 = time.time()
    if a.jobs > 1:
        with ProcessPoolExecutor(a.jobs) as pool:
            futs = [pool.submit(solve, s, a.redo) for s in todo]
            for k, f in enumerate(as_completed(futs), 1):
                name, row = f.result()
                print(f"[{k}/{len(todo)}] {name} {'skipped' if row is None else row.get('seconds', row)}", flush=True)
    else:
        for k, s in enumerate(todo, 1):
            name, row = solve(s, a.redo)
            print(f"[{k}/{len(todo)}] {name} {'skipped' if row is None else row.get('seconds', row)}", flush=True)
    print(f"{collect()} runs collected in {OUT}; {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

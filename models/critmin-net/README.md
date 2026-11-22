# critmin-net: the lab's critical-minerals network model

**This is the SEAR lab's one maintained network model.** Any network model elsewhere in the lab (a
student's repo, a paper's working repo, a course) should derive from this one: start from a release
here, and keep a test that checks your version against it. If your version needs something this model
lacks, propose it here by pull request, so the lab keeps one model rather than several drifting copies.

## What it is

A six-stage battery-mineral supply-chain network (mine, refining, cathode, cell, pack, recycling)
solved as a mixed-integer program in gurobipy: regions, trade arcs, integer capacity builds, yields,
and policy and shock scenarios. One module: [`src/critmin_net/network.py`](src/critmin_net/network.py).

- **The formulation is Alavi's** (sear-labs/mineralnet-optsc, `notebooks/full6stage-network.ipynb`),
  ported to a module and checked against her notebook to 1e-6 (`check_agreement()`).
- **Added since:** the scenario hooks (storage demand bought by an energy model, tariffs, quotas,
  embargoes, friendshoring, yields, output limits, a stylised cobalt add-on, a stockpile), and `calibrated()`, a
  calibration on LLNL's four regions (US, US allies, China, rest of world) from published sources.
- **The regional map is our calibration, not Alavi's or LLNL's.** LLNL's report supplies only the
  region taxonomy (LLNL-TR-859392). The shares, costs and tariffs come from USGS, IEA, Stanford GSB's
  cost model and the US Section 301 fact sheet (`src/critmin_net/data/calibration/`, one row per number with its
  source); three assumptions (rest of world's costs, trade cost as a share of value, the price of unmet
  demand) are ours. Say so wherever the map appears.
- **Preliminary.** Results from it are labelled so until the full models replace the testbed.

Every hook is off by default. With none on and her notebook's parameters, it is her model.

## How the network is described (0.4.0)

As sets, at the top of `network.py`, from which `build()` makes every balance, trade arc and input variable:

- `MINERALS`: the mineral set. Lithium only, for now.
- `GOODS`: (the stage that makes it, its name), e.g. `('proc', 'lce')`; `MINERAL_OF` gives each good's mineral,
  or `None` for a product carrying several (cathode, cells, packs).
- `PROCESSES`: a mine is (stage, ore); every other process is (stage, input, output) and makes one good.
- `RECIPE[process]`: {input good: output per unit of that input}. Lithium's chain has one input per process,
  at Alavi's ratios; a process with several inputs (a precursor and lithium into cathode) is a recipe with
  several entries, so new minerals and stages are new entries here rather than new constraints.

`build(..., net=...)` takes a network as data: its sets, and optionally its own years, costs and demand
(`network.LITHIUM` documents the format). Lithium, the default, reads Alavi's tables as before.

**The multi-mineral test network** (`critmin_net.battery`, PRELIMINARY): lithium, nickel, cobalt, manganese
and graphite through mining, refining, pCAM, anode, cathode and cells, on LLNL's regions plus "Special" (the
DRC), for 2023 and 2024. pCAM takes nickel, cobalt and manganese sulfates together; NMC cathode takes pCAM and
lithium; cells take cathode and anode, at GREET's kg per kWh. The quantities are real and sourced
(`src/critmin_net/data/battery_2023_2024/`): USGS mine output times each mineral's EV share (IEA), IEA refining,
cathode and cell shares, and IEA's EV battery demand by region and chemistry; every cost is a placeholder. It
tests the mechanism, not the world: `python -m critmin_net.battery` solves it, and the solver tests check that
both years are supplied with nothing unmet, that every mineral is taken in exactly demand x intensity, and
that China, which refines most lithium and cobalt but mines little lithium and no cobalt, imports ore.

0.4.0 changed only how the model is written: across Alavi's parameters, the calibration and every hook, it
builds the same Gurobi model as 0.3.0, by Gurobi's model fingerprint, and reports the same results and
US cell prices.

## Where it came from

Moved here in 0.1.0 from `critmin-energy-surrogatecoupling` (`src/surrogatecoupling/sara_net.py` at
`5c3616a`, branch `paper2-testbed`), where it was built as the mineral half of the energy coupling.
The move changed nothing: `tests/test_solver.py` gets that repo's numbers back exactly
(`tests/baseline/working_repo_5c3616a.json`). Alavi's original is beside this folder as
[`../six-stage-mineralnet/`](../six-stage-mineralnet/) (copied 2026-10-06); her live repo is
sear-labs/mineralnet-optsc.

## Running it

    cd models/critmin-net
    pip install -e ".[dev]"            # or PYTHONPATH=src with numpy, pandas and gurobipy installed
    python -m critmin_net.network      # agreement with her notebook, then her published multipliers

    from critmin_net import network as N
    r = N.solve(N.calibrated())                      # the calibrated model, alone
    price, base = N.us_cell_price(params=N.calibrated(), extra_cell_demand={...})

Gurobi is required: the pip wheel's size-limited licence imports the module but cannot solve the model.

## Tests

    pytest -q                  # everything; the solver checks skip without a full licence
    pytest -q -m solver        # only the checks that solve (under a minute)

- `test_raw_frozen.py`: every input matches `src/critmin_net/data/MANIFEST.sha256`.
- `test_smoke.py`: imports, the inputs load and are sane, and bad stockpile options are refused. No solver.
- `test_solver.py`: her notebook to 1e-6, the baseline numbers to 1e-9, and the stockpile's properties
  (it never raises the cost, bridges a cut it sees coming, and keeps its end condition).

## Data

The inputs ship inside the package, in `src/critmin_net/data/`, so `pip install` brings them and a
project using the model needs no copy of its own. They are frozen; [`SOURCES.md`](src/critmin_net/data/SOURCES.md)
says where each file came from. To run on other inputs (a student's variant, a refresh being tested), set
`CRITMIN_NET_DATA` to a folder laid out the same way, with its own `MANIFEST.sha256`; the model then
reads that folder or refuses to start, never the shipped copy in its place.

Alavi's inputs are unpublished lab data, so this repository stays private. The calibration is from
public sources.

**Using it from another project** (pin a commit; the repository is private, so the machine or CI job
needs read access to it):

    pip install "critmin-net @ git+https://github.com/sear-labs/critmin-network-models.git@<commit>#subdirectory=models/critmin-net"

## The stockpile (0.3.0)

`build(..., stockpile={})`, or `solve(params, stockpile={...})`: stock of a good carried from year to year
in a region, built up and drawn down as the model chooses, at a holding cost a year. Ours, not Alavi's.
Off unless asked for, and off it adds nothing to the model. The options and their defaults are `STOCKPILE`:

| Option | Default | |
|---|---|---|
| `regions` | `['US']` | who holds stock: a US strategic reserve; `'all'` for inventory in any region |
| `stages` | every stage but recycling | whose outputs can be stocked |
| `hold_share` | `0.10` | **placeholder, no source yet**: holding cost a year, as a share of the good's value (China's embedded cost, as the trade cost uses) |
| `initial` | none | stock at the start, by (stage, good, region) |
| `max` | none | ceiling on a stage's stock in a region, every good summed |
| `end_at_least_start` | on | no stock drawn in the last year, and each good ends at least where it started |

The end condition matters: without it the model empties the stockpile in the horizon's last year for
free, and builds stock to stand in for capacity that year lacks only because it serves one year (the
same reason unmet demand is not allowed there). With it, the calibrated model holds essentially no stock
in the base case, and under China's refining cut to 70% from 2031 the US reserve builds stock of refined
lithium in 2030-2031 and draws it down over 2032-2034 (PRELIMINARY; the placeholder holding cost). Results report `stock`
and `hold_cost`. Drawn stock is not production, so under rules of origin (`no_transship`) a reserve serves
the region that holds it and is not re-exported.

## Planned

- The rest of the battery chain on the sets above: precursor (pCAM) from nickel, cobalt and manganese
  sulfates; an anode (natural and synthetic graphite); nickel and manganese supply; cobalt as a byproduct of
  copper and nickel mining, with the DRC as LLNL's "Special" region (no "Trade Embargoed" region: those
  countries are not producers). Chemistry choice, at least as a scenario. One unit convention.
- Recycling from retired packs by age, plus manufacturing scrap: every retired pack is shredded where it
  retires, black mass can be traded, and hydromet returns lithium and Ni/Co/Mn products to precursor and
  cathode. This replaces the fixed recycling demand.
- Rare earths, as LLNL's taxonomy covers many minerals.

## Credit

Alavi built the network (formulation and data). Cite LLNL-TR-859392 for the regions, and the sources
in `src/critmin_net/data/calibration/` for the calibration.

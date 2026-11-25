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

## How the network is described (0.4.0, 0.5.0)

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

**Losses** (`build(..., losses=...)`): the share of what goes into a process that is lost, keyed by a stage
(`'cell'`), a process or a node (process + region), as a number or `{year: share}`; the most specific key wins.
A process then makes `(1 - loss) x recipe x input`, so a loss downstream raises everything upstream of it, and
embedded values rise with it. A network may carry defaults (`net["losses"]`), which the argument overrides key
by key. Off for lithium, whose ratios are Alavi's. The battery network's defaults (`battery.LOSSES`) are chosen
from `data/battery_2023_2024/stage_losses.csv`, 62 published values with their sources and the gaps marked:
refining 7.7% (lithium), 7.4% (nickel), 0.4% (cobalt, refinery step only), 13% (manganese); natural graphite
loses 60% in spheronisation; pCAM and cathode none (GREET's assumption, nothing measured); cell scrap 10% in
2023 (IEA). Most are single projects or model assumptions. Mining recovery stays the `yields` hook, since mine capacity
is already contained output. Manufacturing scrap is lost for now; with recycling it will feed black mass.

**Lifecycle, reserves and co-products (0.5.0).** All optional parts of a network, none in lithium's:
- *Lifetimes:* what a process places in an end use retires there over later years, by a lifetime distribution
  (Weibull, by mean and shape or by shape, scale and location, or a table by age), into an end-of-life good;
  `history` gives what was placed before the horizon. `build(life=)` changes a lifetime.
- *Repurposing and recycling:* a process may take an end-of-life good (repurposing, capped at a share of what
  retires by `route_caps`; shredding); `collect` is the share of what retires that must be taken. A stage's
  losses can become scrap (`scrap`). End uses, retired products and scrap can be kept from trade (`no_trade`).
- *Co-products:* a process may make other goods in fixed ratios to its output (`coproducts`): metals out of black
  mass, and in time the oxides out of a mixed rare-earth concentrate or cobalt out of copper and nickel ores. A
  good with co-product supply may leave surplus unused (stored with the stockpile, or discarded), as may any good
  in `dispose`.
- *Reserves:* extraction to date within reserves that grow (discoveries, reclassification) up to identified
  resources, also growing (`reserves`, `reserves_available`).
- *Engine additions (0.6.0, 0.11.0, 0.12.0, 0.13.0):* build lead times by stage and, from 0.11.0, by region (`lead`),
  capacity built in any amount (`lumpy` False) and observed years kept as observed (`observed_to`); from 0.12.0
  stepped cost curves (`cost_curve`) and demand curves (`demand_curve`), discounting (`params["discount"]`),
  capacity by vintage that retires (`params["capacity_rule"]`), shared capacity (`pools`), tariffs by good, exporter
  and importer (`tariffs`), and route shares by region; recipes and co-products that change by year,
  bounds on a route's share of its good (`route_share`), demand on any good (`extra_demand`) with `price()` reading
  back any good's marginal cost, and a unit per good (`units`); from 0.13.0 lead times by process
  (`lead` keyed by a process), a ceiling on a node's capacity (`params["cap_max"]`), reserves shared by several
  nodes (a mine and its expansion), a stockpile that opens in a given year (`stockpile["from_year"]`), and rules of
  origin from a given year (`no_transship=<year>`).
- *Base materials (0.7.0):* goods whose supply dwarfs energy uses (iron, phosphorus, manganese, copper,
  aluminium, steel) are bought in each region at a price, with no chain behind them (`base`: a price, optional
  regional and world ceilings; `build(base=)` changes one for a run). `critmin_net.base` holds their USGS prices
  and world output, shared by every network.
- *Zoom (0.7.0):* `zoom(goods, params, net=...)` solves the whole network, then cuts it at `goods` (`cut()`
  removes what makes them and what only feeds that; recycling stays) and buys each cut good at what it is worth in
  the whole network: its marginal price by region and year, the whole network's value for it, and what each region
  got (as a cap). The zoomed network reproduces the whole one's plan: tested on the lithium model as the working
  repository runs it (cut at lithium chemicals; every node and build the same) and on the battery network zoomed
  on lithium. One model, studied at any scale: the prices hold for the case they came from, so check a large change
  near the cut against the whole network.
- Goods are valued (for trade costs and unmet demand) at their cost made new: routes fed by waste, which is
  valued at nothing, count only where a good has no other route.

Every stage is pulled only by the stage after it; final demand may sit on any good.

**The battery test network** (`critmin_net.battery`, PRELIMINARY): lithium, nickel, cobalt, manganese and
graphite through mining, refining, precursor (pCAM; battery-grade iron phosphate for LFP, from bought iron and
phosphorus),
anode, cathode and cells into every lithium-ion end use (EVs, stationary storage, portable electronics, other),
on LLNL's regions plus "Special" (the DRC), for 2023 and 2024. What is placed retires by age; up to a share of
retired EV packs is repurposed as storage (5% by default, low on purpose); everything else retired, and the cells'
manufacturing scrap, is shredded where it is, into black mass that can be traded and is recycled
(hydrometallurgy) into refined metals. Mines have their whole USGS output, within reserves growing at their
2015-2025 rate to resources; the minerals' other uses are demand where they leave the battery chain (refined
lithium, nickel and cobalt; mined natural graphite). Manganese, iron and phosphorus are base materials, bought at a
price (USGS's for manganese and iron). The quantities are sourced
(`src/critmin_net/data/battery_2023_2024/`, one row per number); losses (`LOSSES`) and lifecycle (`LIFECYCLE`)
defaults are chosen from published tables there. Costs are sourced too (0.8.0; `src/critmin_net/data/battery_costs/`,
`costs()`): each stage's own cost per unit made, by region, in USD per kg or kWh (so the objective is in million
USD), from company reports, feasibility studies, the Stanford GSB cost model, IEA and others; PRELIMINARY, since
several are price spreads or single projects (`selected.csv` says which, and how each was derived). `python -m critmin_net.battery`
solves it; `run(life=..., repurpose=..., collect=..., losses=..., base=...)` changes a default for one run, and
`run(focus=['Li'])` zooms in on some minerals (`zoom()`: the others bought at their battery-grade good, `CUT`).
At sourced costs the cheapest region fills its headroom (China makes every cell in 2024); `run(calibrated=True)`
reproduces the observed regional shares instead (0.9.0, `calibrate()`: positive mathematical programming, a cost that
rises with output for each region and stage, set from what the sourced costs leave unexplained). With the
published EV lifetimes (Xu et al. 2020: most packs last 15-20 years) almost no EV packs retire in 2023-2024, so
manufacturing scrap and electronics are most of the recycling feed; an 8-year life, the older assumption,
retires 100 to 200 times more.

`critmin_net.horizon` (0.11.0; on curves from 0.12.0) projects the battery network to 2040, PRELIMINARY. Demand comes from IEA's outlooks
(stated or current policies; `src/critmin_net/data/battery_horizon/`), and 2023-2024 are calibrated to the observed
shares. After that, capacity is built where it is cheapest: at sourced operating and capital costs, and after each
region's own lead time (`LEAD`: US and allied plants take longer than China's). `run("onshore")` adds floors on the
US's and allies' share of their own demand at every processing and manufacturing stage.
`scripts/battery_horizon.py` runs every case: no policy or current policy, each with and without onshoring
floors; China's export controls; and sensitivities (myopic, today's offsets kept, new mines at their region's own
cost).

From 0.12.0 every market is a curve, as in the lab's Texas energy-system model (`critmin_net.curves`, stepped
constant-elasticity curves anchored at an observed or projected point):
- *supply (cost) curves* on every stage in every region and year, with known operations below the anchor at their
  own costs (Australia's lithium mines, Indonesia's nickel complexes, ...);
- *demand curves* for every end use (anchored at IEA's projection), the minerals' other uses and the base materials;
- *cost curves over time*: operating and capital costs on low, mid and high paths (`COST_PATHS`).
The observed years are calibrated as offsets on the curves (`calibrate()`), and `audit()` refuses to solve while a
fixed amount or flat price has no reason in `ALLOW`. Scenario knobs are in `horizon.KNOBS` (elasticities, the
anchor's entry share, the share of today's unexplained costs kept, the chemistry band, retirement, the discount
rate). Policy (`critmin_net.policy`): US tariffs by good, exporter and year (Section 301, the forced-labour duty,
IEEPA and Section 122 as history) and 45X with its phase-outs; `run(policy={})` keeps current law after 2024,
`run(policy=None)` drops it (2023-2024 always have the policy then in force). `run(foresight=5)` is myopic.
From 0.13.0:
- **Policy:** 45X's foreign-entity rules (`policy={"feoc": True}`), China's export controls as a scenario
  (`china_controls`) and the DRC's cobalt export quota.
- **Trade:** rules of origin (a region exports only what it makes), and no new DRC midstream by default (`no_entry`).
- **Mines:** brownfield expansions, greenfield costs and royalties (`EXPANSION`, `GREENFIELD`, `ROYALTY`, from
  `data/battery_horizon/mining/`).
- **Recycling:** yards for retired packs and black mass, and second life on a cost curve.
**[docs/battery-horizon.md](docs/battery-horizon.md)** explains it with a network diagram, examples, the knobs and the
results; `scripts/battery_horizon_figures.py` draws its figures. From 0.15.0:
- `critmin_net.export.write()` writes a run as the folder cem-impacts reads (its critmin-net reader and Flows
  contract), and `scripts/battery_horizon.py` exports every case.
- `scripts/battery_backcast.py` compares the model's 2025 with observed 2025.
- `scripts/battery_sensitivity.py` moves one knob at a time.

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

- Base materials still to source: phosphorus (USGS gives no grade for phosphate rock's price) and steel (USGS gives
  only a price index). Copper and aluminium in cells (foil, casings) once their intensities are sourced.

- The lithium network on the battery network's structure: its fixed recycling demand replaced by retirement,
  repurposing and recycling. Cobalt as a co-product of copper and nickel mining. Chemistry choice, at least as a
  scenario. Recycling capacity by region.
- More networks on the same engine: rare earths (separation as co-production; magnets, catalysts, electronics,
  defence), and energy equipment: gas turbines, wind, solar, transformers (grain-oriented electrical steel), power
  electronics (inverters and converters), data-centre components. Shared goods named alike, so networks can be
  combined.

## Credit

Alavi built the network (formulation and data). Cite LLNL-TR-859392 for the regions, and the sources
in `src/critmin_net/data/calibration/` for the calibration.

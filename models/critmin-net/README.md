# critmin-net: the SEAR Lab's critical-minerals supply-chain network model

critmin-net models battery-mineral supply chains as networks: mining, refining, precursor, anode and cathode
material, cells, end uses, and recycling, in five regions (China, the US, US allies, the rest of the world, the
DRC) with trade between them. Its main network is the **lithium-ion battery supply chain to 2040**: every market a
calibrated supply, demand or cost curve; capacity built after each region's lead time; mine expansions, greenfield
costs, royalties and quotas; recycling (yards, second life, hydromet+, pyromet+); and policy (US tariffs, 45X and
its foreign-entity rules, China's export controls, the DRC's cobalt quota, rules of origin). It is calibrated to
2023-2024 and checked against 2025. **[docs/battery-horizon.md](docs/battery-horizon.md)** explains it. Results
are PRELIMINARY.

**This is the SEAR Lab's one maintained network model** (Erick C. Jones Jr.). Other network models in the lab
should derive from it: start from a release, and propose what it lacks by pull request.

## How to cite

Cite the release you used (the repository's `CITATION.cff`; GitHub's "Cite this repository" gives the formats):

```bibtex
@software{jones_critmin_network_models,
  author  = {Jones, Erick C., Jr.},
  title   = {critmin-network-models: the SEAR Lab's critical-mineral network models (critmin-net)},
  version = {0.16.0},
  year    = {2026},
  url     = {https://github.com/sear-labs/critmin-network-models}
}
```

**Credits.** The network engine began as a port of Sara Alavi's six-stage lithium network (SEAR Lab); the
energy-side context is Raziye Aghapour's. LLNL-TR-859392 supplies the
regions. The regional calibration, the battery network and everything since are this model's own.

**Licence.** Code: MIT (`LICENSE`). Data (`src/critmin_net/data/`): CC BY 4.0; every number carries its source
(`SOURCES.md`).

## What it is

One engine for supply-chain networks passed as data, solved as a mixed-integer or linear program in gurobipy:
regions, trade arcs, capacity built after a lead time, costs, demand, policy and shocks
([`src/critmin_net/network.py`](src/critmin_net/network.py)). The battery network (`battery.py`) and its projection
to 2040 (`horizon.py`) are built on it; other networks (rare earths, energy equipment) are planned on the same
engine.

- **Every number is sourced** (`src/critmin_net/data/`, one row per number with its source). Where a number is an
  assumption of ours, the code and the data say so.
- **The regional map is our calibration, not LLNL's.** LLNL's report supplies only the region taxonomy
  (LLNL-TR-859392).
- **Preliminary.** Results from it are labelled so.

Every hook is off by default.

## How a network is described

A network is a dict (the notes above `build()` in `network.py` list its keys), from which `build()` makes every
balance, trade arc, capacity and input variable:

- `minerals`: the mineral set.
- `goods`: (the stage that makes it, its name), e.g. `('refine', 'Li')`; `mineral_of` gives each good's mineral,
  or `None` for a product carrying several (cathode, cells).
- `processes`: a mine is (stage, ore); every other process is (stage, input, ..., output) and makes one good.
- `recipe[process]`: {input good: output per unit of that input}; a process with several inputs (a precursor and
  lithium into cathode) is a recipe with several entries, so new minerals and stages are new entries rather than
  new constraints.
- `years`, `cost` and `demand`: the network's own data. `params` give its regions and starting capacity.

`check_net()` checks that the sets describe one connected network.

**Losses** (`build(..., losses=...)`): the share of what goes into a process that is lost, keyed by a stage
(`'cell'`), a process or a node (process + region), as a number or `{year: share}`; the most specific key wins.
A process then makes `(1 - loss) x recipe x input`, so a loss downstream raises everything upstream of it, and
embedded values rise with it. A network may carry defaults (`net["losses"]`), which the argument overrides key
by key. The battery network's defaults (`battery.LOSSES`) are chosen
from `data/battery_2023_2024/stage_losses.csv`, 62 published values with their sources and the gaps marked:
refining 7.7% (lithium), 7.4% (nickel), 0.4% (cobalt, refinery step only), 13% (manganese); natural graphite
loses 60% in spheronisation; pCAM and cathode none (GREET's assumption, nothing measured); cell scrap 10% in
2023 (IEA). Most are single projects or model assumptions. Mines have no loss: their capacity is already contained
output. Manufacturing scrap is lost for now; with recycling it will feed black mass.

**Lifecycle, reserves and co-products (0.5.0).** All optional parts of a network:
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
  got (as a cap). The zoomed network reproduces the whole one's plan: tested on a toy network and on the battery
  network zoomed on lithium. One model, studied at any scale: the prices hold for the case they came from, so check a large change
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

## Where it came from

The engine began in `critmin-energy-surrogatecoupling` as a port of Sara Alavi's six-stage lithium network
(sear-labs/mineralnet-optsc), the mineral half of an energy coupling, and moved here in 0.1.0. That lithium
network, its inputs and the calibration that moved it to LLNL's regions were retired in 0.16.0: the battery network
replaced it. They remain in this repository's history (the 0.15.x releases). Alavi's original is beside this
folder as [`../six-stage-mineralnet/`](../six-stage-mineralnet/).

## Running it

    cd models/critmin-net
    pip install -e ".[dev]"            # or PYTHONPATH=src with numpy, pandas and gurobipy installed
    python -m critmin_net.battery      # the battery network, 2023-2024
    python scripts/battery_horizon.py  # the horizon's cases, to 2040, exported for cem-impacts

    from critmin_net import horizon as H
    r = H.run("cost", policy={})       # current law after 2024, perfect foresight

Gurobi is required: the pip wheel's size-limited licence imports the module and solves the toy tests, not the
battery network.

## Tests

    pytest -q                  # everything; the solver checks skip without a full licence
    pytest -q -m solver        # only the checks that need a full licence (a few minutes)

- `test_raw_frozen.py`: every input matches `src/critmin_net/data/MANIFEST.sha256`.
- `test_smoke.py`: imports, and the inputs load and hang together. No solver.
- `test_lifecycle.py`: the engine's mechanics on a toy network with round numbers (lifecycle, losses, lead times,
  base materials, zoom, curves, the stockpile, ...). The pip wheel's licence solves it.
- `test_horizon.py`: the horizon's inputs and tables.
- `test_solver.py`: the battery network and its horizon, solved: calibration, policy, export, myopic runs.

## Data

The inputs ship inside the package, in `src/critmin_net/data/`, so `pip install` brings them and a
project using the model needs no copy of its own. They are frozen; [`SOURCES.md`](src/critmin_net/data/SOURCES.md)
says where each file came from. To run on other inputs (a student's variant, a refresh being tested), set
`CRITMIN_NET_DATA` to a folder laid out the same way, with its own `MANIFEST.sha256`; the model then
reads that folder or refuses to start, never the shipped copy in its place.

**Using it from another project** (pin a release or commit):

    pip install "critmin-net @ git+https://github.com/sear-labs/critmin-network-models.git@<commit>#subdirectory=models/critmin-net"

## The stockpile (0.3.0)

`build(..., stockpile={})`, or `solve(params, stockpile={...})`: stock of a good carried from year to year
in a region, built up and drawn down as the model chooses, at a holding cost a year.
Off unless asked for, and off it adds nothing to the model. The options and their defaults are `STOCKPILE`:

| Option | Default | |
|---|---|---|
| `regions` | `['US']` | who holds stock: a US strategic reserve; `'all'` for inventory in any region |
| `stages` | every stage of the network | whose outputs can be stocked |
| `hold_share` | `0.10` | **placeholder, no source yet**: holding cost a year, as a share of the good's value (China's embedded cost, as the trade cost uses) |
| `initial` | none | stock at the start, by (stage, good, region) |
| `max` | none | ceiling on a stage's stock in a region, every good summed |
| `from_year` | none | no stock held before this year |
| `hold_unit` | none | a cost per unit held a year, by stage, on top of `hold_share` (goods worth nothing still cost to store) |
| `end_at_least_start` | on | no stock drawn in the last year, and each good ends at least where it started |

The end condition matters: without it the model empties the stockpile in the horizon's last year for
free, and builds stock to stand in for capacity that year lacks only because it serves one year (the
same reason unmet demand is not allowed there). The horizon uses the stockpile for its yards (retired packs and
black mass held for later, at a sourced cost per unit: `horizon.KNOBS["yard_cost"]`). Results report `stock` and
`hold_cost`. Drawn stock is not production, so under rules of origin (`no_transship`) a reserve serves
the region that holds it and is not re-exported.

## Planned

- Base materials still to source: phosphorus (USGS gives no grade for phosphate rock's price) and steel (USGS gives
  only a price index). Copper and aluminium in cells (foil, casings) once their intensities are sourced.

- Cobalt as a co-product of copper and nickel mining. Chemistry choice, at least as a
  scenario. Recycling capacity by region.
- More networks on the same engine: rare earths (separation as co-production; magnets, catalysts, electronics,
  defence), and energy equipment: gas turbines, wind, solar, transformers (grain-oriented electrical steel), power
  electronics (inverters and converters), data-centre components. Shared goods named alike, so networks can be
  combined.

## Credit

The engine began as a port of Sara Alavi's six-stage lithium network (SEAR Lab). The battery network, its
calibration and its data are this model's own. Cite LLNL-TR-859392 for the
regions, and the sources in `src/critmin_net/data/` (`SOURCES.md`) for every number.

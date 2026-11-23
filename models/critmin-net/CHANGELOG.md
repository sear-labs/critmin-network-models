# Changelog

Versions follow SemVer. A change that moves `tests/baseline/` numbers on purpose is at least a minor
version and says why here.

## 0.8.0 (2026-11-23)

Battery network costs, sourced (docs/networks-outline.md 3.1: "real costs"). The lithium model is unchanged (12 cases,
identical fingerprints, results and prices).
- `data/battery_costs/`: two compiled source tables (`sources_upstream.csv`, 181 rows: mining, refining and 2023-24
  prices; `sources_midstream.csv`, 141 rows: precursor, cathode, anode, cells, packs, repurposing, shredding and
  recycling), one row per published number with its URL, table or page, and conversion; and `selected.csv`, the 57
  numbers the network uses, each naming its source rows and its arithmetic. `verification.csv`: every source row the
  selection names was checked against its source (57 confirmed, 4 corrected: two rounding slips, and natural anode's
  spread, 2.6 USD/kg rather than 0.95, as IEA's flake price is per tonne of anode); the check's notes on bases
  (price vs cost, mixed stages, exchange rates) are in the rows.
- `battery.costs()`: each stage's own cost per unit made (purchased inputs counted where they are made), by region
  and year, in USD per kg contained or per kWh. Mines by region from each region's operations; refining, iron
  phosphate and anode costed in China, other regions by the Stanford GSB precursor ratio (labour and electricity);
  precursor, cathode and cell processing from the Stanford GSB model for China, the US and Korea (the allies), plus
  bought cell materials; recycling by IEA's and BNEF's US/China and Europe/China ratios; the rest of the world halfway
  between China and the US, the DRC at China's. Cobalt, a by-product, is priced (hydroxide payables x LME), not
  costed; anode costs are price spreads (natural anode then costs more than synthetic, as IEA's prices show). Capital costs are in the source tables but unused (capacity is fixed).
- `battery.base_prices()`: manganese and iron at USGS's prices per tonne contained; phosphorus derived from iron
  phosphate's price less its conversion and iron. The placeholders (`UNIT_COST`, `SYNTHETIC_COST`, `REPURPOSE_COST`,
  `SHRED_COST`, `RECYCLE_COST`, `BASE_PRICE`) and the US/China `cost_ratio` input are gone; `alpha_stage` is 1.
- What it shows (PRELIMINARY): with capacity at observed output x 1.2, the cheapest region fills its headroom, so
  China makes all cells in 2024; matching observed shares needs a calibration like the lithium model's
  (`network.calibrated()`), for the projection-horizon work.
- Engine: `net["trade_only"]`, processes kept only for their trade routes (no recipe, nothing made). A good is traded
  on its makers' arcs, so `cut()` keeps a cut good's removed makers this way; `zoom()`'s cap is now what each region
  made in the removed chain. Without it a co-product such as recycled cobalt could not leave the region it was
  recovered in, once the primary refinery was cut: the placeholder costs had hidden this. The battery zoom test now
  matches to 1e-12 on sourced costs (perturbed 1% where regions share a cost, as the DRC shares China's).
- Engine: under `no_transship` (calibration's rule of origin), what a region buys of a base good counts as its own
  supply, so a bought good can be exported. Without it the zoomed lithium model could not ship the lithium
  chemicals it buys, once their makers were kept as trade routes. The lithium model has no base goods, so its
  fingerprints, results and cell prices are identical to 0.7.0's.

## 0.7.0 (2026-11-22)

The base-materials layer (docs/networks-outline.md, section 5: Jones's decision). The lithium model is unchanged
(12 cases, identical fingerprints, results and prices).
- `net["base"]` and `build(base=)`: goods bought in each region at a price (a number, by year, or by region),
  with optional regional and world ceilings, and no mines, capacity or trade behind them. They may also have
  makers; what is bought adds to them. Valued at China's price, or at `value` if given (a good cut from a
  larger network keeps its value there, so trade costs downstream are unchanged). `results()` reports `bought`;
  the build handle carries `value`, the engine's valuation of any good.
- `critmin_net.base`: USGS MCS 2025 prices (USD per tonne contained: iron ore, manganese, copper, aluminium) and
  world output, frozen in `data/base_materials/usgs_mcs2025.csv`. Phosphate rock and steel have no contained price
  there yet.
- Battery network: manganese is bought (its mines, reserves and other uses are gone from the network), and
  battery-grade iron phosphate is made from bought iron and phosphorus by mass (37% and 21%). Base prices are
  placeholders in the network's placeholder unit, like its other costs. `network(base=)` and `run(base=)` change
  one; `run()` reports `bought`. Every other quantity is as in 0.6.0.
- `cut(net, goods)` and `zoom(goods, params, net=..., caps=True)`: a network cut at some goods, each bought at its
  marginal price in the whole network (LP duals with the integers fixed), valued as there, and capped at what each
  region got from the removed chain. Price and value alone keep the whole network's plan optimal at the same cost;
  the caps pin the quantities where plans tie. Tests: the lithium model (calibrated, cobalt add-on) cut at lithium
  chemicals reproduces every node's output and every build; the battery network zoomed on lithium reproduces every
  node (costs perturbed 1% to break the placeholder costs' ties); the toy, in CI. Battery: `CUT`, `zoom(focus)`,
  `run(focus=)`.

## 0.6.0 (2026-11-22)

Engine additions from the networks outline (docs/networks-outline.md), each off by default; the lithium model is
unchanged (12 cases, identical fingerprints, results and prices).
- `build(lead=)` and `net["lead"]`: build lead time by stage (5, Alavi's, wherever unset).
- Recipe and co-product coefficients may be `{year: number}`: intensities that change over time.
- `build(route_share=)` and `net["route_share"]`: a route's share of its good's output between bounds, per region
  or world-wide, optionally by year (technology or chemistry choice).
- `build(extra_demand=)`: demand on any good, region and year (numbers or linear expressions), and `price()`: the
  marginal cost of any good by year, from the balance duals after fixing the integers. `results()` with duals adds
  `dual` and `dual_total` for every good.
- `net["units"]`: a unit per good (the battery network has one).

## 0.5.0 (2026-11-22)

- Lifecycle in the engine, all optional and none in lithium: lifetimes (`net["life"]`, `history`, `build(life=)`,
  `retire_share()`), end-of-life goods, repurposing caps (`route_caps`), collection (`collect`), scrap from
  losses (`scrap`), co-products with free disposal (`coproducts`, `dispose`), and stages kept from trade
  (`no_trade`). `results`' handle adds `retire`.
- Reserves: `build(reserves=)`, extraction to date within reserves growing up to resources (`reserves_available`).
- Goods are valued at their cost made new: routes fed by waste count only where nothing else makes a good.
- The battery network covers every lithium-ion end use (EVs, storage, electronics, other) with retirement by age,
  repurposing (5%, low on purpose), and recycling of retired products and manufacturing scrap. Mines have their
  whole output, within growing reserves; the minerals' other uses are demand where they leave the chain. New
  frozen inputs in `data/battery_2023_2024/`: `battery_demand_by_use.csv`, `mineral_demand_by_use.csv`,
  `refined_production.csv`, `reserves.csv` (with resources and the 2015 edition's reserves), `lifecycle.csv`;
  `regions.csv` gains 11 names.
- No change to the lithium model (12 cases, fingerprints identical; results and prices identical).

## 0.4.0 (2026-11-21)

- The network is described as sets: `MINERALS` (lithium only for now), `GOODS` (with `MINERAL_OF`),
  `PROCESSES` and `RECIPE` (inputs per process, output per unit input), and `build()` makes every balance,
  trade arc and input variable from them. A process may now take several inputs. `IN_T` and `OUT_T` move to
  module level; the input variables are keyed (node, input good, year).
- `build(..., net=...)`: the network is an argument, its sets and optionally its own years, costs and demand
  (`network.LITHIUM`, the default, documents the format; `check_net()` checks a network's sets). Embedded
  values follow the recipes; levers, the stockpile and results read the network's stages and goods.
- `critmin_net.battery`: a multi-mineral test network (Li, Ni, Co, Mn, graphite; mining, refining, pCAM,
  anode, cathode, cells; LLNL's regions plus Special) for 2023-2024 on sourced quantities
  (`data/battery_2023_2024/`, new frozen inputs) and placeholder costs. Both years are supplied with nothing
  unmet and each mineral is taken in exactly demand x intensity. A test of the mechanism, PRELIMINARY.
- `build(..., losses=...)`: a loss per stage, process or node, optionally by year (output = (1 - loss) x
  recipe x input), over a network's own defaults (`net["losses"]`); `check_losses()` validates them. Off for
  lithium. The battery network's defaults, `battery.LOSSES`, are chosen from `data/battery_2023_2024/stage_losses.csv`
  (new frozen input: published losses by stage with sources); with them both years are still supplied. The
  synthetic graphite placeholder cost rises from 3.0 to 4.0 so natural flake, after its spheronisation loss,
  is still used first.
- The battery network's LFP cathode takes battery-grade iron phosphate, a pCAM good with capacity and cost and no
  mined input.
- No change to the lithium model: across Alavi's parameters, the calibration and every hook (12 cases), `build()`
  makes the same Gurobi model as 0.3.0 (same fingerprint, variables, constraints and nonzeros). The baseline
  numbers are unchanged.

## 0.3.0 (2026-11-21)

- The stockpile hook (`build(stockpile=...)`, options and defaults in `STOCKPILE`): stock carried between
  years by stage, good and region, at a holding cost, with no drawdown in the last year and an end at least
  at the start. Off by default, and off it adds no variables or constraints: the baseline numbers are
  unchanged. The holding cost (10% of value a year) is a placeholder with no source yet.
- Results gain `stock` and `hold_cost`. The pack balance's local `sp` is renamed `spk`; no behaviour change.

## 0.2.0 (2026-11-20)

- The frozen inputs move from `data/raw/` into the package (`src/critmin_net/data/`), so `pip install
  git+...` ships them; a project using the model no longer keeps a copy. Byte-identical; same checksums.
- `network.data_dir()`: `$CRITMIN_NET_DATA` names another inputs folder (used or refused, never replaced
  by the shipped copy); otherwise the shipped copy. The baseline numbers are unchanged.

## 0.1.0 (2026-11-20)

- Moved here from critmin-energy-surrogatecoupling (`src/surrogatecoupling/sara_net.py` at `5c3616a`)
  as the lab's network model. Only the module's opening lines and its data path changed; the
  calibrated model's objective and US cell prices are identical to that repo's.
- Inputs frozen from there: Alavi's network data (mineralnet-optsc @ `18e67de`), her notebook's
  reference solution, and the published-source calibration.

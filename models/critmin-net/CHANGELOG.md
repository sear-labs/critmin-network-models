# Changelog

Versions follow SemVer. A change that moves `tests/baseline/` numbers on purpose is at least a minor
version and says why here.

## 0.12.0 (2026-11-24)

The battery horizon on curves, with recycling built where it pays, US tariffs and 45X (Jones, 2026-11-24: "costs
should be curves just like supply and demand ... fixed projections are terrible for scenarios"). The lithium model is
unchanged (12 cases, identical fingerprints, results and prices), and so is the battery network's 2023-2024 (same
fingerprint, 142,530 M$). The 0.11.0 horizon's results are superseded.
- Engine (`build()`), each off by default:
  - `cost_curve`: stepped supply curves on a group of nodes, or on a base material's purchases (`("buy", good, region)`).
  - `demand_curve`: stepped demand curves on any good, valued in the objective.
  - `params["discount"]`: every year's terms are discounted.
  - `params["capacity_rule"] = "cumulative"`: capacity is starting capacity by year (so it can retire) plus builds still within `build_life`.
  - `pools`: capacity shared by nodes of one region, with unit coefficients.
  - `tariffs`: by (stage[, good], exporter, importer) and year.
  - Route shares by region.
  - Handles `served`, `curve_x` and `weight` are returned.
- `curves.py`: `ladder()`, `supply_blocks()` (with known operations below the anchor, rising from the dearest one
  above it) and `demand_blocks()`. These are the Texas model's stepped constant-elasticity curves, with 0.2% steps near a supply anchor.
- `battery.sets()` and `network()`, both off by default:
  - `chem_choice`: one good per end use, met by any chemistry; each chemistry retires into its own good.
  - `co_per_ni`: cobalt as a co-product of nickel mining.
- `horizon.py` rebuilt on curves (`KNOBS`):
  - Supply curves on every stage in every region and year. They are anchored at observed output, growing with the world's need, plus an entry share of 2%.
  - Known operations below each anchor, from operations' 2024 output and costs:
    - Australia's four lithium mines: Greenbushes 7.81 to Wodgina 23.04 USD per kg Li.
    - South American and Chinese lithium, Indonesian and Canadian nickel.
  - Demand curves after 2024 for every end use, anchored at IEA's projection and its 2024 price, which moves with the cell cost path. The minerals' other uses and the base materials (anchored at their whole markets) are curves too.
  - Cost curves over time (`COST_PATHS`, low, mid and high):
    - Cells: BatPaC to 2035, then NREL; mid -24% by 2030, -42% by 2040.
    - Cathode processing: no learning.
    - Refining and mining: flat; high case has mining +15% by 2040.
  - Calibration (`calibrate()`): curve offsets put 2023-2024 on the observed shares, refined until within 0.5% of each stage's output (graphite mining 2%). After 2024 the offsets are dropped (`wedge_carry`).
  - Discounted at 8%.
  - Capacity:
    - Nameplate cell capacity from 2025 (IEA 2024).
    - Mines and refining retire at 4% of 2024's capacity a year; builds serve 25 years.
    - Plants are shared: anode routes, cell chemistries, NMC precursor and cathode, hydromet.
  - Chemistry within 10 points of IEA's mix by region.
  - Cobalt mined as a co-product of nickel (0.019 kt per kt outside the DRC, 2024), with primary cobalt mines in the DRC only.
  - Recycling:
    - Shredding is open but costed.
    - Hydromet starts from IEA's 2023 capacity (China 1.78 Mt cell-equivalent) and is built at its capital cost, so only where it pays.
    - Capital cost, USD per kWh a year: US 26.9, allies 16.7, China 2.5.
  - `audit()` refuses to solve while a fixed amount or flat price has no reason in `ALLOW`.
  - `run(foresight=)` gives myopic runs.
  - Costs are reported as resource cost, tariffs paid and credits received.
- `policy.py`, applied in the observed years always and after them by scenario (`run(policy={})` or `None`).
  - US tariffs by good, exporter and year:
    - MFN.
    - Section 301 on China: 25% on chemicals, cathode, anode and nickel ore; cobalt ore from 2024-09; EV cells from 2024-09; other cells and natural graphite from 2026.
    - IEEPA, 2025-02 to 2026-02, ended by the Supreme Court.
    - Section 122, 2026-02 to 07.
    - The forced-labour Section 301 duty from 2026-07-24: China 12.5%, allies about 10% (cells 12.5%), others 10%; minerals and refined chemicals exempt.
    - Rates in force on 2026-11-24 are held after. Chinese cells into the US pay 40.9% from 2027.
  - The EU's on China stands for the allies'.
  - Not applied: Section 232 on vehicle batteries (`s232=True`; contested), the graphite AD/CVD (no orders: the ITC found no injury), China's export controls (licences).
  - 45X: cells 35 USD per kWh; cathode and anode 10% and refined minerals 10% of production cost, recycled feed included. Phase-out under PL 119-21: components 2030-32, minerals 2031-33. The foreign-entity thresholds are read (`feoc_thresholds()`) but not yet applied.
- Data (`data/battery_horizon/policy/`, `curves/`):
  - `tariffs.csv` (129 rows, R), `credits.csv` (407, C), `paths_elasticities.csv` (312, E), `operations_capacity.csv` (464, S).
  - Independent checks: policy 376 rows, 372 confirmed, 4 corrected in wording; curves 87 rows, 85 confirmed, 2 corrected (Pilgangoora 17.76 USD per kg Li, not 17.42; the EV elasticity's source).
  - The checks' notes changed the allies' hydromet capital cost (per t of capacity, not of throughput) and the allies' cells tariff (KORUS's zero MFN).
- What it shows (PRELIMINARY; STEPS, discounted to 2024, resource cost excluding transfers). Nothing unmet in any case.
  - Resource cost:

    | Case | M M$ |
    |---|---|
    | No policy after 2024 | 1.423 |
    | Current policy | 1.429 |
    | Onshoring | 1.467 (+3.1%) |
    | Policy and onshoring | 1.506 |
    | Myopic (5 years in view) | 1.451 |

    45X pays 39.5 B$ (discounted) under current policy. CPS: 1.329 with no policy, 1.371 onshoring.
  - Lithium mining: Australia's share rises to 48% in 2030. Greenbushes sits low on its curve; 0.11.0 had Australia out by 2027. Myopic runs move mining to the rest of the world (76% by 2040), whose short lead time suits short sight.
  - China: 92% of cells in 2040, 87% of refined lithium, all LFP cathode.
  - Current policy: the US's cell share rises to 11% in 2025, fading as 45X phases out.
  - Onshoring: the US and allies make 24% of cells, cathode, anode and refined lithium in 2040.
  - Hydromet rises to about 1,470 GWh-equivalent in 2040, all of it built in China. The US builds none, even with 45X.
- Still weak:
  - No elasticities found: EV and storage demand by battery price, refining, components and cells, graphite supply. The EV one is derived; the rest are ours.
  - No cost paths for refining, mining or components.
  - No nameplate capacity outside cells and recycling.
  - The foreign-entity rules are not applied.
  - The 2% entry anchor and the curves' share persistence are knobs to test.

## 0.11.0 (2026-11-24)

The battery network to 2040 (`horizon.py`), with lead times by stage and region. The lithium model is unchanged (12
cases, identical fingerprints, results and prices), and so is the battery network over 2023-2024 (same fingerprint,
142,530 M$).
- Engine (`build()`), each off by default:
  - `lead` may give a stage's years by region, `{stage: {region: years}}` (5 for a region not given).
  - A network with `lumpy` False builds capacity in any amount, priced by its cost's `var` per unit added, with no
    plants (`inv` stays 0) and no plant ceiling; the model stays an LP (or QP).
  - `params["observed_to"]` keeps capacity at the starting capacity through that year whatever the lead, so observed
    years stay observed while builds are still decided from the first year.
  - Handles `cap` and `newc` are returned.
- `battery.network(years=, capex=, lead=, crf=)`: years after 2024 take 2024's costs and capacity, and with `capex`
  capacity is built (continuous, from 2023 decisions) at capex x crf for each year a plant serves to the last year.
  `battery.capex_key()` names a process's capital cost. Without them, nothing changes.
- `horizon.py` (PRELIMINARY):
  - `load("STEPS" | "CPS")`: demand to 2040 from IEA's Global EV Outlook 2026 and Global Critical Minerals Outlook
    2025. EVs are world deployment by mode and regional shares, each region's 2025 chemistry moved as IEA's world mix
    moves, with sodium-ion left out. Storage is anchored in 2025, at IEA's 2030 additions, and IEA's installed power in
    2035 and 2040 at 3 hours, plus replacements. Electronics, other applications and the minerals' other uses are
    held at 2024. Manufacturing scrap falls to 6% in 2030.
  - `CAPEX`, by stage and region, from the cost tables and IEA:
    - IEA GCMO 2025's top producer and rest-of-world capital intensities for lithium, nickel and refining;
    - IEA's ACTM per-kWh costs for cathode, anode and cells;
    - single projects for graphite, manganese and cobalt.
    Annualised at 8% over 25 years.
  - `LEAD`, by stage and region (Jones: US and allied plants long, China short, the rest of the world shorter still
    for mines). Mines: China 5, ROW 2, DRC 3, US 10, allies 5. Cells: China 1, ROW 2, US 3, allies 4.
  - `run("cost" | "onshore")`: the observed years calibrated, and from 2025 the model's decision (Jones). "onshore"
    is a floor on the US's and allies' share of their own demand at every processing and manufacturing stage:
    40% from 2030 (the EU's 2030 benchmarks), rising to 60% in 2040 (ours). Mines have no floor.
  - The anode's 2024 capacity is split between its routes in later years as the observed solve uses them.
  - Solved by dual simplex (barrier stalls on the open capacities beside the retirement tails).
- `data/battery_horizon/`:
  - `demand.csv` (385 rows, D), `pipeline_capex.csv` (224, P: IEA's supply outlook, announced recycling capacity,
    capital costs) and `lead_times.csv` (91, T), one row per number with its source;
  - `verification.csv`: an independent check of 188 rows (184 confirmed, 4 corrected, the corrections applied in the
    rows: two chart reads, and IEA's manganese sulphate chart labelled kt where it means Mt).
- `scripts/battery_horizon.py` writes `results/battery_horizon/` (not committed).
- What it shows (PRELIMINARY; STEPS, then CPS in brackets). Nothing unmet in any case.
  - The four cases cost 3.15 M M$ for 2023-2040 (2.83), and onshoring adds 141 B$, 4.5% (129 B$, 4.6%).
  - Cost-based, China makes 97% of cells in 2040 and 87% of refined lithium. The rest of the world mines 93% of
    lithium, its new mines (11.4 USD per kg plus 5.2 annualised capital) undercutting Australia's existing ones
    (17.6). Without the calibration's costs after 2024, the US and allies' existing cell and pCAM plants run little,
    as the 2024 wedges said they would at sourced costs.
  - Onshoring, the floors bind: the US and allies make 24% of cells, cathode, anode and refined lithium in 2040. The
    US builds most of the midstream, being cheaper to run and quicker to build than the allies. The allies build
    most of the cells.
  - Against IEA's supply outlook (the comparison, not a constraint), nickel mining and refining are close: 4.0 Mt
    against IEA's 4.5 in 2030, refining about 35% China in both. Anode and natural graphite are not: IEA's outlook
    is announced projects, flat after 2030, while here anode follows demand and is made from synthetic graphite,
    whose feed is not modelled.
- Still weak:
  - The storage path (3 hours, and 2035-40 from installed power).
  - Capital costs from single projects (graphite, manganese, cobalt).
  - Cobalt mining is priced alike everywhere, so its new mines sit near refining, within reserves.
  - Recycling capacity is open.
  - Costs are held at 2024 (no learning).
  - Australia's mines against new ROW mines are within 1 USD per kg.
  - The policy cases (US tariffs, the 45X credit) need a sourcing pass.

## 0.10.0 (2026-11-23)

Lithium's battery-network costs re-sourced: the calibration's largest wedges (0.9.0) were lithium's, and China's mining
cost was a 2019 concentrate price. The lithium model is unchanged (12 cases, identical fingerprints, results and
prices).
- `data/battery_costs/`: 136 new source rows (U181-U316) from three searches: China's lithium mining (its miners'
  annual reports and investor-relations records), mining in the rest of the world and the US (SEC and NI 43-101
  technical reports, company results), and conversion (a Chinese converter's annual report, studies, NRGI). The 29
  rows the selection names were checked against their sources: all confirmed; the check's notes on basis (CIF or
  plant gate, what is excluded, the denominator) are in the rows and in `verification.csv`.
- Refining, USD per kg Li: China 15.6 (2023) and 16.4 (2024), spodumene to lithium salt excluding concentrate
  (Chengxin; CIFCO and NRGI agree); the rest of the world 16.7 (Albemarle's La Negra brine plant, Chile); the US 17.9
  (Piedmont Tennessee study); the allies 28.7 (Rock Tech Guben study). Each region's own, no longer China's by a ratio.
- Mining, USD per kg Li, as each region's mix of resources by output, an integrated cost split as the integrated cost
  less the region's conversion (so mining plus refining is what the operation costs): China 18.8 (2023) and 14.8
  (2024), from lepidolite (Yongxing), brine (Qinghai Salt Lake, Zangge) and spodumene (Rongjie's Jiajika mine) at
  Fastmarkets' 2023 split (was 32.3); the rest of the world 13.0 and 11.4, from Chilean brine (Albemarle Atacama's
  salar costs, 7.55), Argentine brine (Olaroz, Cauchari-Olaroz) and hard rock (Sigma; no Zimbabwe mine cost was
  found) at USGS output (was 14.8, one Brazilian mine); the US 16.9, from Thacker Pass and Silver Peak (was 4.8,
  Thacker Pass's mining area alone). The allies' Australian median is unchanged.
- What it shows (PRELIMINARY): the battery network costs 142,530 M$ (was 143,264), nothing unmet. Calibrated, lithium
  mining's wedges fall to 6.1 USD per kg in the rest of the world (was 16.9), 3.0 in China and under 0.05 in the
  allies (was 14.1). Refining's stay large (China 12.1, the rest of the world 11.4, the US 9.9): the allies' study
  cost, 28.7, is the marginal refiner's, and the allies refined 2.5% of lithium in 2024 at that cost or more (IGO's
  Kwinana reports cash costs of 108-183 while ramping up), so the wedge measures plants run at a loss, not a missing
  cost.
- `battery.TIE` 0.001 -> 0.01 USD per kg or kWh. With the new costs, splits that only `TIE` pins (pCAM between China
  and the allies) moved by up to 0.5% between the whole calibrated network and a zoomed one, the solver's price
  tolerance divided by a nearly flat slope; at 0.01 they match to 0.01% (the solver's floor; 0.05 does no better), and
  prices rise by about 0.05 USD per kg or kWh (0.1%). The calibrated zoom test asserts 0.1% node by node. Wedges are
  step 1's, so `TIE` does not change them.
- Still weak: China's costs are accounting cost of sales (with depreciation) where Australia's are cash costs;
  lepidolite's dearer conversion sits in China's mining share; Zimbabwe, the rest of the world's second producer, has no
  mine cost.

## 0.9.0 (2026-11-23)

The battery network calibrated to the observed regional shares (docs/networks-outline.md 3.1). Off by default: the
lithium model is unchanged (12 cases, identical fingerprints, results and prices), and so is the battery network
uncalibrated.
- `battery.calibrate()`: positive mathematical programming (Howitt 1995). Step 1 holds each region's output at each
  stage with an observed regional split (mining, primary refining, anode, pCAM and cathode by chemistry, cells) at
  its observed share of the model's output, recomputing the targets until the totals settle (two solves); each
  hold's dual, its wedge, is what the sourced costs leave unexplained. Step 2 replaces the holds with a cost rising
  with output, 0.5 * gamma * x^2, gamma = (wedge + `TIE`) / target, which reproduces step 1's plan without them.
  `TIE` (0.001 USD per kg or kWh) splits regions with equal costs (cobalt mines) by their observed shares. Prices are
  step 1's to within a few thousandths of a dollar, except in regions that only import a good, where the LP's price
  was not unique (up to 0.3 USD per kg higher).
- `run(calibrated=True)` and `zoom(..., calibrated=True)`; `network(..., quad=)` takes calibrate()'s costs.
- Engine: `build(..., quad_cost=[(nodes, year, gamma)])`, a cost of 0.5 * gamma * (the nodes' output)^2 per term.
  None by default. zoom() carries it: zoomed on lithium, or on nickel and cobalt, the calibrated battery network
  matches the whole one node by node to the solver's tolerance (2e-6), with no perturbation, since the rising costs
  make the plan unique.
- What it shows (PRELIMINARY): every share matches, each region and year (to 1e-4), with nothing unmet; cells in 2024
  are China 85%, the allies 9% and the US 6% (100% China uncalibrated). The largest wedges, USD per kg contained, 2024:
  lithium mining in the rest of the world 16.9 and in the allies 14.1 (China's mining cost is roughly a 2019
  concentrate price, 32.3, so these largely measure that number), lithium refining in China 13.4, nickel mining in the
  rest of the world 5.4, cobalt refining in China 4.7; cells in China 3.7 USD per kWh. A large wedge marks a cost
  worth re-sourcing or a policy the network leaves out.
- For 2023 and 2024 only: projecting needs a rule for gamma as capacity grows (the horizon work).

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

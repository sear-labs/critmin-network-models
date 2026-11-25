# Changelog

Versions follow SemVer. A change that moves `tests/baseline/` numbers on purpose is at least a minor
version and says why here.

## 0.16.0 (2026-11-25)

**The lithium network is retired.** critmin-net began as a port of Alavi's six-stage lithium network; the battery
network replaced it, and every test now runs on the current model. The lithium network remains in history (0.15.x).
The battery model's numbers are unchanged: the same objectives and exported tables for the battery network, its
calibration, and the horizon's cases, before and after.

- **Removed from `network.py`:** Alavi's table readers (`load_data`, `data`, `CRITMIN_ALAVI_DATA`, `HAS_ALAVI`), the
  lithium sets (`LITHIUM`, `GOODS`, `PROCESSES`, `RECIPE` and the rest), her parameters (`NOTEBOOK`, `PUBLISHED`),
  `check_agreement()`, the lithium calibration (`calibrated()`, `shares_2024()`, `pipeline_shares()`, `ramp_rates()`,
  `grid_demand()`), paper 2's cell prices (`us_cell_price()`, `us_cell_prices()`), and the hooks only the lithium
  network used: `extra_cell_demand`, `tactics`, `yields`, `cobalt`, `ev_scale`, and the params `fixed_cap`, `pipeline`,
  `ramp`, `ramp_floor`, `grid_demand`, `tariff_advalorem` and `shortage_mult_region`. `extra_demand` and `tariffs` do
  what the first and fourth did, on any network.
- **build() needs a network and its params** (no default network). `ship_value_share` defaults to
  `SHIP_VALUE_SHARE` (it was her per-unit shipping cost). The stockpile's `stages` default to every stage of the
  network. `results()` keeps the generic results (cost, unmet demand, stock, purchases, output by stage, duals) and
  drops the lithium summaries (cell shares, US imports, coupled-year cell output, the build pattern, cell duals).
- **Removed data:** Alavi's inputs and reference solution (already out of the tree) and five of six calibration
  tables (`capacity_pipeline`, `grid_storage`, `regional_shares_2024`, `stage_costs_us_china`, `us_tariffs_2024`).
  `country_shares_2024.csv`, which the battery network reads, stays. The manifest lists 33 files.
- **Tests:** the 13 lithium tests and their baseline (`working_repo_5c3616a.json`) are gone, with
  `scripts/reference_sara_network.py`, the `alavi` marker and `tests/conftest.py`. The engine checks they carried
  (one balance per good, region and year; losses checked and costing more; the stockpile's options, its bridging a cut
  it sees coming, its holding cost, and its end condition) now run on the toy network in `test_lifecycle.py`, which
  the pip wheel's licence solves. New: `test_battery_numbers_unchanged` compares the battery network's and the
  horizon's objectives with `tests/baseline/battery_0.16.0.json`.
- **For the working repository** (critmin-energy-surrogatecoupling): paper 2's code calls `calibrated()` and
  `us_cell_price()`, so its pin must stay on 0.15.x until it moves to the battery network.

## 0.15.1 (2026-11-25)

- **The scenario set** (`scripts/battery_scenarios.py`, `scripts/battery_scenarios_summary.py`): 192 runs.
  - Axes: demand x policy x new-mine costs x foresight x persistence of 2024's patterns x cost path.
  - Each run is exported for cem-impacts. The runner can be resumed and run in parallel, and takes about 20 minutes
    on one machine.
  - All 192 solve with no unmet demand.
  - Cells and refining move with policy only. Lithium mining moves with new-mine costs, persistence and foresight.
- **Two myopic artefacts fixed,** found by the first full run (perfect-foresight results unchanged):
  - A myopic window charged a plant's capital only to its own end, so the US built half the world's cells for 45X's
    last full year and abandoned them. Capital is now charged to the horizon's end in every window
    (`battery.network(charge_to=)`).
  - Onshoring floors are soft (`KNOBS["floor_penalty"]`, 100 USD per kg or kWh short; ours, above their shadow
    prices, under 30). Before, a myopic run met the share by shrinking world output, with 2040 cells falling to about
    a quarter. `run()` returns `floor_short`.
- Tests: a myopic run builds no stranded US cells for 2030; myopic floors do not shrink the market; with perfect
  foresight every floor is met.

## 0.15.0 (2026-11-24)

- **The cem-impacts export** (`critmin_net.export`): `write(run, folder, scenario)` writes one folder per solved run
  in the format cem-impacts' critmin-net reader takes (`cem_impacts.adapters.critmin`, its Flows contract):
  - `run.json` and `production.csv`: what each process made, co-products as their own rows, the process tuple
    joined by ":";
  - `trade.csv`, `shortfall.csv`, `stock.csv` (the yards) and `price.csv` (balance duals, undiscounted).

  Names and units are critmin-net's own. `run()` returns the node-level `detail` this needs.
  `scripts/battery_horizon.py` writes every case's export to `results/battery_horizon/export/`. A test checks the
  format and that the amounts add up to the run's; it runs cem-impacts' own reader when that is installed. It passed
  with the local clone at c17a8e7.
- **Rules of origin in every year** (`KNOBS["rules_of_origin"]=True`). From 2025 only, the US had bought China's cells
  and anode through the DRC in 2023-2024, so it paid no tariff. Graphite mining's calibration tolerance goes from 2%
  to 4%, since its natural/synthetic split is not observed. 2040 results do not change.
- **Yards cost to hold** (`KNOBS["yard_cost"]`, engine `stockpile["hold_unit"]`, a cost per unit held a year):
  - The cost is Argonne's 150 USD per tonne a year (X165; an uncited assumption of theirs, for hybrid batteries, no
    dollar year). That is 1.30 USD per kWh for retired packs (module mass) and 0.75 for black mass (cell mass).
  - Holding had been free, since these goods carry no value: retired packs piled up to 3,200 GWh by 2040 and 2040
    recycling fell to 1,035 GWh-equivalent. With the cost, about 170 GWh remain and 1,390 is recycled.
  - Legal storage limits are recorded (X172-X178: a year in the US and China, three years in the EU), not imposed.
  - The data are 14 rows, X165-X178, all checked (9 confirmed, 5 corrected).
- `scripts/battery_sensitivity.py`: one knob at a time, low and high, against the default (not a Morris screen).
  China's cell and refining shares hold under every knob. Lithium mining moves only with greenfield costs,
  foresight and kept offsets. Cost moves with the discount rate, cost paths and supply elasticities.
- **The 2025 backcast** (`scripts/battery_backcast.py`, `data/battery_horizon/backcast/`): 258 observed rows for
  2024-2025 (cells, mining, refining, cathode, anode, capacity, prices), all checked (249 confirmed, 9 region
  assignments corrected). The model's 2025 shares miss the observed by 4.3 points on average. The large misses are
  the allies' cells (2% against 12%) and cobalt refining (allies 3% against 15%): 2024's offsets are dropped at once
  in 2025. Fading them to zero by 2030 cuts the mean miss to 2.9 points, with 2040 unchanged.
- **2024's offsets fade to zero by 2030** (`KNOBS["wedge_carry"]={2024: 1, 2025: 0.8, 2030: 0}`), not dropped at
  once in 2025 (Jones, 2026-11-24, on the backcast).
  - The allies' 2025 cells come out at 7% (12% observed), and 250 GWh-equivalent is recycled in 2025, not none.
  - Totals now count the offsets while they fade: 1.54 M M$ (STEPS, no policy), not comparable with 0.14.0's 1.43.
  - Onshoring adds 44 B USD (2.8%); current policy adds 14 B USD and pays 40 B USD of credits.
  - Lithium mined in 2040: allies 69%, rest of world and DRC 28% (new mines at own cost: 11% and 84%; myopic: 17% and
    79%).
  - Cells are still 92% Chinese in 2040.

## 0.14.0 (2026-11-24)

The battery model's last pieces. Horizon results move again (PRELIMINARY); the lithium model is unchanged (all 12
fingerprinted cases), and so is the battery network's 2023-2024 calibration.
- **Chile's Atacama held at its CORFO quotas** (`QUOTA_OPS`, `KNOBS["quotas"]`). Albemarle runs at 15.9 kt Li a year
  to 2043, SQM at 32.5 over 2026-2030, and the SQM-Codelco venture at 62.0 from 2031. They do not retire, and the
  region keeps their capacity. `curves.supply_blocks` takes a step (size, cost, size_2024) that keeps its size.
- **Pyromet+ on** (`PYRO`, `KNOBS["pyro"]`), as a refining route beside hydromet+ (one pooled plant):
  - NMC black mass to refined nickel and cobalt at 98%; lithium and manganese lost.
  - Costs from Argonne's EverBatt 2019, run at its defaults for the US, China and Korea. Its scope includes refining
    the alloy, and an independent check reproduced it from the workbook's formulas.
  - Converted at 3.7 kg of cells per kWh and to 2024 dollars by CPI-U.
  - China's and Korea's operating costs are derived from their totals (ours).
  - Existing capacity: Umicore Hoboken. At these costs it is never chosen, since hydromet+ also recovers lithium
    and manganese.
- **China's lithium royalty** from the provinces' rates by its mix: Jiangxi 6.5%, Qinghai 6%, Sichuan 4.5%. That is
  2.91 USD per kg, against 2.89 at the old midpoint.
- **Second life** cited:
  - The 80% viable share agrees with NREL's 80-90%.
  - The 20% anchor is the JRC's 2030 scenario.
  - Repurposing's 30 USD per kWh sits in NREL's 20-49.
- **Indonesia's nickel ore benchmark** is sourced (about 3.06 USD per kg Ni). Its royalty stays out of the cost,
  since it is in the HPAL plants' ore costs.
- Data: 37 rows added to `battery_horizon/mining/` (X128-X164), all confirmed by an independent check.
- `run()` returns `pyro` (GWh-equivalents of black mass by region and year).
- What it shows (STEPS, no policy):

  | Lithium mined, 2040 | Allies | Rest of world + DRC |
  |---|---|---|
  | Default (0.13.0 had 76% / 20%) | 70% | 27% |
  | New mines at their region's own cost | 15% | 81% |
  | Myopic | 23% | 74% |

## 0.13.0 (2026-11-24)

Committed together with 0.12.1: the two were developed in the same files. 0.12.1's horizon results are superseded;
the lithium model is unchanged (all 12 fingerprinted cases), and so is the battery network's 2023-2024 calibration.

Engine (`build()`): lead times by process; `params["cap_max"]`; reserves shared by several nodes; a stockpile that
opens in a given year; `no_transship` from a given year.


Structural fixes found when the foreign-entity rule and export controls showed no effect:
- **Rules of origin in the horizon** (`KNOBS["rules_of_origin"]`, from 2025): a region exports only what it made.
  Without it the US bought China's cathode and anode through the DRC, the one region with no US tariff, so tariffs,
  45X's foreign-entity rule and export controls all missed. Not in 2023-2024: trade there is not observed, and with
  the rule graphite mining calibrates to 3.5%, not 2%. `build(no_transship=)` takes a first year as well as True.
- **The DRC's costs**: `battery.costs()` gave the DRC China's cost at every stage without a number of its own (every
  stage but mining). It now takes the rest of the world's. The lithium model and the 2023-2024 calibration tests are
  unchanged.
- **No new DRC midstream by default** (`KNOBS["no_entry"]`): with rest-of-world costs and no US tariff, the DRC
  became the US's cathode and cell supplier from 2030 (230 GWh-eq of cathode), though it has no such plants and
  none is announced. Precursor, cathode, anode and cells there are held at 2024's (none); refining stays open.
  `no_entry=[]` lets it build.
- `run()` returns `trade` {(stage, good, exporter, importer, year): units}.
- Tests: regions export only what they make; the DRC builds no midstream; China's export controls stop its sales to
  the US; the foreign-entity cap holds and costs no less.

Mining realism (data: `battery_horizon/mining/`, 128 rows, ids X, every row checked independently: 114 confirmed, 14
corrected):
- **Brownfield expansions** (`EXPANSION`) where one is sourced:
  - lithium in Australia (47.9 USD per kg a year, 2-year lead), the rest of the world (18.49), China (115.11) and the
    US (309.74);
  - nickel in the allies (72.73) and the rest of the world (27.3).

  Each is a process beside the region's mines, at their operating cost, with room for half of 2024's capacity (ours).
- **Greenfield operating costs** (`GREENFIELD`) price new capacity on later years' lithium curves: allies 14.52, rest
  of the world 14.11, US 15.35. Chile's cheap Atacama brine cannot grow, since it has quotas.
- **Royalties and lease payments** (`ROYALTY`), added to every year's mining cost (calibration absorbs them in
  2023-2024):
  - lithium: allies 2.41, rest of the world 4.77 (Chile's CORFO payments 6.92), China 2.89;
  - nickel: allies 0.42, rest of the world 0.27;
  - graphite: rest of the world 0.015.
- **The DRC's cobalt export quota** (96.6 kt a year from 2026; `policy.drc_cobalt_quota()`) with policy on.
  `drc_quota=False` turns it off.
- `run()` counts expansions as their mineral's mining, returns `expanded`, and reports their builds at their own
  lead.
- U58 (Matawinie capex) was converted at the 2023 exchange rate; now 2022's (3.6905, was 3.5561).
- Pyrometallurgy stays off: recoveries are sourced, but no operating cost is.
- What it does (PRELIMINARY; STEPS, no policy after 2024):
  - Lithium mining in 2040:

    | Region | 0.12.1 | Now |
    |---|---|---|
    | Allies | 6% | 76% |
    | Rest of world | 87% | 17% |

    The flip comes from the greenfield costs and royalties: new rest-of-world supply no longer comes at Chile's brine
    cost.
  - Rest-of-world lithium expansions fill their room (61 kt) by 2030.
  - Nickel grows from 3.56 Mt (2024) to 4.25 Mt (2040), mostly through Indonesian HPAL expansions.

Policy, recycling and docs:
- 45X's foreign-entity rules (`policy={"feoc": True}`) and China's export controls (`china_controls`), as scenarios.
- Yards for retired packs and black mass (from 2025), and second life on a cost curve (up to 80% of retired EV packs
  viable). Pyromet+ is built but off.
- `KNOBS["greenfield"]`: `{}` prices new mines at their region's own cost (0.12.1's rule).
- `scripts/battery_horizon.py` adds two cases: China's export controls, and new mines at their region's own cost.
- `docs/battery-horizon.md`, its figures and the network diagram are redrawn: shredding and black mass as one stage,
  yards, hydromet+ and pyromet+, expansions and royalties.
- What it shows (PRELIMINARY; STEPS):
  - Policy changes who supplies the US (allies and the rest of the world instead of China), not where cells are made
    (China 92% in 2040).
  - The foreign-entity rule cuts China's anode to the US by up to a quarter in 2030-2032.
  - Onshoring adds 44 B USD (3.0%).
  - Lithium mining's regional split turns on the greenfield costs and on foresight:

    | Lithium mined, 2040 | Allies | Rest of world + DRC |
    |---|---|---|
    | Default | 76% | 20% |
    | New mines at their region's own cost | 8% | 88% |
    | Myopic | 19% | 78% |

## 0.12.1 (2026-11-24)

Fixes to the horizon's supply curves, found while drawing them, and visual docs. 0.12.0's horizon results are
superseded; the lithium model and the battery network's 2023-2024 are unchanged.
- Later years' supply curves are a merit order (`curves.supply_blocks(steps_total=)`):
  - existing operations at their own size (retiring) and costs;
  - new capacity up to the anchor at the region's sourced cost;
  - the curve's steps above the anchor.

  0.12.0 scaled known operations with world demand, so Greenbushes-cost lithium grew about sixfold by 2035. A first
  fix priced growth at each region's dearest operation instead, which set China's at Jiangte's lepidolite
  (43.6 USD per kg). Neither is what new capacity costs.
- The curve anchors for mining and refining now grow with the minerals' other uses as well as the batteries' need
  (about 3.4x to 2040, not 6x).
- `scripts/battery_horizon.py`: a case keeping 2024's offsets after 2024 (`wedge_carry`), the sensitivity the
  lithium result turns on.
- `docs/battery-horizon.md`: what the horizon is, how to run it, the knobs, results and what is weak. Figures
  (`docs/figures/`) are drawn by `scripts/battery_horizon_figures.py`, plus a network diagram
  (`battery_network.svg`).
- What it shows (PRELIMINARY; STEPS, discounted):
  - Resource cost:

    | Case | M M$ |
    |---|---|
    | No policy after 2024 | 1.423 |
    | Current policy | 1.430 |
    | Onshoring | 1.468 (+3.1%) |
    | Policy and onshoring | 1.506 |

  - Lithium mining by default goes 90% to the rest of the world by 2040, the cheapest new capacity (11.4 USD per kg).
    Keeping 2024's offsets reverses it (China 74%). It is the one result that turns on a choice; refining, cathode,
    cells and onshoring's cost barely move.
  - Cells: China 92% in 2040 (75% with onshoring floors). The US makes 11% in 2025 with 45X, falling to 5% by 2033.
  - Hydromet feed is about 1,650 GWh-equivalent in 2040, built almost all in China.

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

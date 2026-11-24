# critmin-net: outline of the next networks

Reviewed by Jones, 2026-11-22 (decisions in section 5). Nothing here is built. No numbers appear without a source; where a stage
or a data source is uncertain, it says so.

## 1. What stays the same

One engine (`network.build`), with each supply chain passed in as data: goods, processes and recipes. As in the
battery network (0.5.0):

- **Each stage is pulled only by the stage after it.** Final demand may sit on any good: a refined metal, an
  oxide, a component or a finished piece of equipment.
- **Several inputs per process** (recipes) and **several outputs per process** (co-products, with surplus
  stored or discarded).
- **Lifetimes, repurposing, scrap and recycling** for anything placed in an end use.
- **Mines within reserves** that grow up to identified resources.
- **Regions:** LLNL's (US, ALLY, CHN, ROW), plus Special (DRC) where cobalt is in the network. Countries map to
  regions through a `regions.csv` of ours.
- **Inputs are frozen and sourced**, one row per number. Placeholders are marked. Results are PRELIMINARY until
  costs are real.

## 2. What the outline shows the engine still needs

These come up in more than one network, so they belong in the engine, not in each network.

| Need | Why | Where it bites |
|---|---|---|
| **Build lead time per stage** | The engine has one five-year lead (Alavi's), built into its constraints. Mines, fabs, casting shops and module lines differ widely. | gas turbines (castings, forgings), transformers, mines, everything run over a projection horizon |
| **Recipes that change by year** | Material intensity falls over time: thrifting, new designs. Recipes are fixed today. | REE per magnet, silver per PV cell, rhenium per blade, battery chemistries |
| **Bounds on route shares** | Technology choice within limits (direct-drive vs geared wind, amorphous vs grain-oriented cores, LFP vs NMC). The repurposing cap is a special case; generalise it to a min/max share of a good's output by route. | wind, transformers, batteries, magnets |
| **Links to the energy model on any good** | Today the link is cells only: `extra_cell_demand` in, the US cell price out. Generalise both: extra demand on any good (GW of turbines, MVA of transformers), and a price and availability by year for any good. | every equipment network; paper 2's coupling |
| **Combining networks** | Shared goods (NdFeB magnets, copper, electrical steel, power modules, nickel, gallium) should be one good, so EV motors and wind turbines compete for the same magnets. A `combine(nets)` that merges sets by name; regions and years must match. | REE + batteries + wind + power electronics |
| **A unit for every good** | Networks mix kt, GWh, GW, MVA and units. A `units` map for checks and reports. | all |
| **Byproduct metals whose host is outside the network** | Gallium (from alumina), germanium (zinc), rhenium (molybdenum and copper), indium (zinc). The host's output is set from outside; the minor metal is its co-product, and the host good may be left unused. This already works with fixed capacity, co-products and disposal; it needs a worked example and a test. | power electronics, gas turbines, solar |

## 3. The networks

### 3.1 Batteries (0.5.0; what is left)

Still to do:
- a projection horizon (about 2023-2040) with capacity built, not fixed (*0.11.0, `horizon.py`: to 2040, IEA
  demand, capital costs and lead times by stage and region, a cost-based and an onshoring scenario; 0.12.0: on
  supply, demand and cost curves, with US tariffs and 45X*);
- real costs (*sourced in 0.8.0, `data/battery_costs/`; PRELIMINARY: several are price spreads or single projects*);
- calibration to the observed regional shares (*0.9.0, `battery.calibrate()`, 2023-2024; over the horizon, where
  production goes after 2024 is the model's decision (Jones, 2026-11-23)*);
- cobalt as a co-product of copper and nickel mining (*0.12.0: of nickel; the DRC's copper-cobalt mines primary*);
- recycling capacity by region (*0.12.0: hydromet capacity and builds; shredding open but costed*);
- chemistry choice as bounded route shares (*0.12.0: within a band of IEA's mix by region*);
- a decision on whether it replaces the lithium network in the working repo. The lithium network stays as it
  is for paper 2.

Energy-model link: stationary storage, already in place.

### 3.2 Rare earths and magnets

- **Minerals:**
  - magnet REEs: Nd, Pr, Dy, Tb;
  - the oversupplied co-products: La, Ce;
  - Sm, Y and others as needed (samarium-cobalt magnets for defence; yttrium, which also links to gas turbine
    coatings).
- **Stages:**
  - mine (bastnaesite, monazite, ionic clays as separate mine processes);
  - cracking and leaching to a mixed concentrate;
  - separation (solvent extraction) into individual oxides, **co-products in proportions set by deposit type**;
  - reduction to metal;
  - magnet alloy;
  - magnets (sintered, bonded);
  - end uses.
- **End uses:**
  - magnets: EV traction motors, wind generators, industrial motors, electronics, defence;
  - oxides directly: catalysts (refining and automotive), polishing, glass, phosphors, nickel-metal-hydride
    batteries.
- **Lifecycle:** magnet manufacturing scrap (swarf) and end-of-life magnets, recycled to oxide or alloy.
- **What it tests:** co-production at scale, and surplus disposal (cerium and lanthanum).
- **Shared goods:** magnets (batteries' EV end use, wind), yttrium (gas turbines).
- **Energy link:** wind (the share of permanent-magnet turbines) and EV motors.
- **Data:** USGS MCS (REE), IEA Global Critical Minerals Outlook (magnet REEs). Separation and magnet capacity
  by country may be thin in public sources.

### 3.3 Electrical steel and transformers

- **Electrical steel:** grain-oriented (GOES) for transformer cores; non-oriented (NOES) for motors and
  generators: EV motors, wind generators, industrial motors. One steel network, two products.
- **Transformers:**
  - inputs: core (GOES, or amorphous steel as an alternative route for distribution transformers), copper or
    aluminium windings, insulation and oil, bushings and tap changers;
  - products: distribution, power and generator step-up transformers; reactors.
- **Lifecycle:** long lifetimes; replacement of an ageing fleet is a demand of its own.
- **Energy link:** transmission and distribution expansion and interconnection. Lead times matter most here.
- **Data:** USGS (copper, iron and steel); US DOE and NREL work on transformer supply and demand. Market studies
  are mostly paywalled.

### 3.4 Power electronics (inverters and converters)

- **Stages:**
  - substrates and wafers: silicon; silicon carbide; gallium nitride on silicon or SiC;
  - device fabrication (IGBTs, MOSFETs, diodes);
  - power modules;
  - converters.
  Passive parts beside them: film capacitors (tantalum in some), magnetics, copper, aluminium.
- **Products (end uses):**
  - PV inverters, wind converters, battery-storage power conversion;
  - EV traction inverters and chargers;
  - data-centre power supplies and UPS;
  - HVDC converter valves, industrial drives.
  All compete for the same module and device capacity, which is the point of one network.
- **Byproducts:** gallium (alumina refining) and germanium (zinc), hosts set from outside.
- **Energy link:** solar, storage, wind, HVDC.
- **Data:** USGS (gallium, germanium, silicon); IEA and US DOE supply-chain reviews. Fab capacity by device type
  is likely thin in public sources.

### 3.5 Gas turbines

- **Materials:** nickel superalloys (Ni, Co, Cr, Re, Ta, Hf, Mo, Al, Ti); steel and nickel-alloy forgings;
  thermal barrier coatings (yttria-stabilised zirconia: a link to REE).
- **Stages:**
  - superalloy melt;
  - investment castings (single-crystal and directionally solidified blades and vanes);
  - large forgings (rotors, discs);
  - coatings;
  - assembly.
- **End uses:** heavy-duty power generation, aeroderivative units, mechanical drive, and **aviation engines,
  which compete for the same superalloy and casting capacity**.
- **Energy link:** gas capacity a year that can be built, and its cost by year.
- **Data:** USGS for the metals. **Casting and forging capacity is probably proprietary**, which makes this the
  hardest network to source. Capacity may have to be a scenario parameter rather than data.

### 3.6 Wind and solar (assemblies)

Mostly assemblies of the networks above, plus their own stages.
- **Wind:**
  - towers (steel);
  - nacelles: a permanent-magnet generator (magnets) or a geared doubly-fed generator (copper), gearboxes,
    bearings, castings;
  - blades: glass and carbon fibre, resin;
  - converters (power electronics);
  - offshore foundations and cables.
- **Solar:**
  - quartz, metallurgical silicon, polysilicon, ingot and wafer;
  - cell (silver paste);
  - module (glass, aluminium frame, encapsulant);
  - inverters (power electronics).
- **Data:** IEA's *Solar PV Global Supply Chains* (2022); USGS.

### 3.7 Data centres: an end use, not a network

I suggest data centres appear as demand in several networks rather than as a chain of their own. They need:
- transformers and switchgear (3.3);
- power supplies and UPS (3.4);
- UPS and storage batteries (3.1);
- backup generation, sometimes gas turbines (3.5);
- cooling equipment.

Chips themselves (germanium, gallium, high-purity quartz) could come later. The energy link is their electricity
demand, which belongs to the energy model, not to this one.

### 3.8 A shared base-materials layer?

*Zooming (0.7.0, `zoom()`): any network can be cut at some goods and run with them bought at their whole-network
prices, values and quantities; it then reproduces the whole network's plan. So a study of one mineral uses the full
network with the others fixed, rather than a separate model.*

*Built in 0.7.0 (`net["base"]`, `critmin_net.base`); the battery network buys manganese, iron and phosphorus.*

Copper, aluminium, steel and nickel run through almost every network, and most of their demand is outside
energy. One option is a small base-materials network that the others draw on. Their other uses would be final
demand there, as the battery network now does for lithium's. That way, combining networks shows competition for
copper without each network carrying its own copper.

## 4. Suggested order

1. **Engine additions in section 2:** lead times by stage, recipes by year, route-share bounds, links to the
   energy model on any good, units, `combine()`. Each is small and testable on the toy network. Each is off by
   default, so lithium is unchanged.
2. **Batteries to a projection horizon with real costs:** the first network useful to the energy model.
3. **Rare earths and magnets:** co-production at scale; shares magnets with batteries and wind.
4. **Electrical steel and transformers:** the clearest grid-expansion link.
5. **Power electronics.**
6. **Gas turbines:** a strong energy link, but its data is the hardest.
7. **Wind and solar as assemblies;** data centres as an end use throughout; base materials when combining starts.

## 5. Decisions (Jones, 2026-11-22)

All four agreed:
- **The order** in section 4 stands.
- **Data centres** are an end use across networks, not a network of their own.
- **A shared base-materials layer**, for minerals whose supply is so large that energy uses are a small, steady
  part of it: copper, aluminium, steel, iron, phosphate, manganese and the like. They get simple supply at a
  price, not a full chain.
- **The battery network replaces the lithium network in the working repo.** This is task one; the lithium
  network stays for paper 2's committed numbers.

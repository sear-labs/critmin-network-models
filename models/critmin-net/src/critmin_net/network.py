"""The lab's critical-minerals network model: Alavi's six-stage network, ported, with hooks and a calibration.

The formulation is hers (sear-labs/mineralnet-optsc, notebooks/full6stage-network.ipynb), read from
her committed data, frozen in critmin_net/data/mineralnet-optsc/. Run with her notebook's parameters and no hooks, the port must
reproduce her objective; `check_agreement()` asserts that against
scripts/reference_sara_network.py's run of her notebook.

Hooks (all off by default):
  * extra_cell_demand  stationary-storage GWh the energy model buys, added to US cell demand
  * tactics            LLNL-TR-859392 levers on CHN->target arcs (targets: US, or US + allies):
                       tariff (cost multiplier on the arc), quota (bound on arc flow), embargo
                       (arc fixed to zero), friendshore (every CHN->target arc closed)
  * yields             extraction yield per (mine tech, region): capacity x yield, and cost / yield
  * losses             material lost in a process, as a share of what goes in, by stage, process or node
                       (process + region), optionally by year: output = (1 - loss) x recipe x input. A network
                       may carry its own defaults (net["losses"]); the argument overrides them key by key
  * reserves           extraction to date within what is extractable, per mine node: a fixed total, or reserves
                       that grow (discoveries and reclassification) up to identified resources, also growing
                       (reserves_available)
  * lead               build lead time by stage, years from a build decision to capacity (5, Alavi's, for all
                       stages unless a network or the argument says otherwise)
  * route_share        bounds on a route's share of its good's output, per region or world-wide, optionally by year
                       (technology or chemistry choice within limits)
  * extra_demand       demand added on any good, region and year, numbers or linear expressions (an energy model's
                       purchases); price() reads back any good's marginal cost
  * base               goods bought at a price, with no chain behind them (see the base-materials notes); zoom()
                       cuts a network at some goods and buys them at their whole-network price, value and quantity,
                       which reproduces the whole network's plan (cut() is the cut alone)
  * life               product lifetimes, over a network's own (net["life"]): what a process places in a region
                       (an end use) retires there over the following years, by a lifetime distribution, into an
                       end-of-life good that repurposing and recycling take (see LIFECYCLE)
  * limits             output ceiling per (stage, region) and year, e.g. China's refining cut to a
                       share of its business-as-usual output (the refining shock)
  * cobalt             a Co add-on: NMC cathode needs refined Co, mined in DRC (stylized)
  * stockpile          stock carried between years, by stage, good and region, built up and drawn down as
                       the model chooses, at a holding cost; none is drawn in the last year, and it ends
                       with at least what it started with. Ours, not Alavi's (STOCKPILE: options, defaults)

Calibration (params from `calibrated()`, off unless asked for): her inputs cost the same in every
region and start every region with the same capacity, so the cheapest region runs every stage.
`calibrated()` moves her model from her three regions (US, China, Australia) to LLNL's: US, US
allies, China and rest of world (LLNL_REGIONS), and adds, from published sources
(data/calibration/; country rows grouped as LLNL groups them):
  * region_share       her world demand split by 2024 EV battery demand by region
  * grid_demand        every region's grid storage, outside ERCOT (IEA), as cell demand
  * alpha_stage        cost multiplier by stage and region: the US and allies at the US/China ratio
                       (Stanford GSB model); rest of world priced as ROW_PRICED_AS (no published estimate)
  * fixed_cap          mines, every year, at each region's share of IEA's base-case mined lithium
  * init_cap           refining, cathode and cells in the start years (2026-2030), at each region's
                       share of IEA's base case (refined lithium; cathode capacity by chemistry;
                       committed cell capacity), so new plants take her five-year build lead. Shares
                       are of the world's throughput in a solve where every region costs the same,
                       times HEADROOM. This is where capacity starts; it is not a ceiling.
  * ramp, ramp_floor   from 2031 no ceiling: each region's capacity at a stage grows by at most its
                       own growth rate in IEA's base case, 2024-2030 (ramp_rates(); at least the
                       world's), plus RAMP_FLOOR of world capacity a year (ramp_floor), so a region
                       starting near zero can start. `pipeline` keeps IEA's path, for reporting only.
  * shortage_mult      grid-cell and pack demand the network cannot supply goes unmet in the region that
                       demands it, at SHORTAGE_MULT x China's
                       cost of the cell (SHORTAGE_MULT_REGION where a region's demand weighs more),
                       so a shock beyond what others can build is a price, not an infeasible model
  * tariff_advalorem   current US Section 301 tariffs on Chinese cells and packs, on their value
  * ship_value_share   trade cost as a share of the goods' value, the same at every stage, in place
                       of her shipping cost per unit (which is ~10x the value of ore and ~1% of a pack's)
  * no_transship       rules of origin: a region exports only what it makes, so a tariff on China
                       cannot be dodged by re-exporting Chinese goods through a third region
Policies and shocks that close or cut China's arcs act from tactics["from_year"] (2031 in config.yaml),
so the other regions have the five-year lead to build; the network sees them coming.
"""
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import gurobipy as gp
from gurobipy import GRB, quicksum



def data_dir(env=None):
    """Where the inputs are. $CRITMIN_NET_DATA if set: a named location, so it is used or refused (no
    MANIFEST.sha256 there), never silently replaced by the shipped copy. Otherwise the copy shipped in the
    package (critmin_net/data/), which `pip install` brings along."""
    env = os.environ if env is None else env
    named = env.get("CRITMIN_NET_DATA")
    if named:
        p = Path(named).resolve()
        if not (p / "MANIFEST.sha256").is_file():
            raise FileNotFoundError(f"CRITMIN_NET_DATA={named}: no MANIFEST.sha256 there; not a critmin-net data folder")
        return p
    return Path(__file__).resolve().parent / "data"


RAW = data_dir()

DATA = RAW / "mineralnet-optsc" / "data" / "raw" / "input_data_3region"

MINE_T = ['spod', 'brine', 'clay']
PROC_T = ['loh', 'lce']
CATH_T = ['nmc', 'lfp']
CELL_T = ['GWh_nmc', 'GWh_lfp']
PACK_T = ['bev_nmc', 'bev_lfp', 'phev_nmc', 'phev_lfp']
REC_T = ['lce', 'loh']
STAGES = ['mine', 'proc', 'cath', 'cell', 'pack', 'rec']
RATIO = {'proc': {'loh': 3.45101, 'lce': 5.324},
         'cath': {'nmc': 1 / 3.45101, 'lfp': 1 / 5.324},
         'cell': {'GWh_nmc': 8.11, 'GWh_lfp': 10.58},
         'pack': {'bev_nmc': 1 / 62, 'phev_nmc': 1 / 15, 'bev_lfp': 1 / 62, 'phev_lfp': 1 / 15},
         'rec': {'loh': 30, 'lce': 35}}
SHORT_GWH = {**{t: 1.0 for t in CELL_T}, **{t: 1 / RATIO['pack'][t] for t in PACK_T}}   # cell GWh per unit unmet

# ---- the network as sets: minerals, goods, processes and their recipes
# A good is (the stage that makes it, its name). A process makes one good: a mine is (stage, ore), every other
# process (stage, input, output), and RECIPE[process] = {input good: output per unit of that input} (empty for
# mines). A node is a process in a region: process + (region,). build() makes every balance, trade arc and
# input variable from these sets, so a new mineral, stage or input is new entries here, not new constraints.
# Lithium's chain has one input per process; a process with several (a precursor and lithium into cathode,
# say) is a recipe with several entries.
MINERALS = ['Li']
STAGE_IN = {'proc': 'mine', 'cath': 'proc', 'cell': 'cath', 'pack': 'cell', 'rec': 'pack'}   # whose goods a stage uses
OUT_T = {'mine': MINE_T, 'proc': PROC_T, 'cath': CATH_T, 'cell': CELL_T, 'pack': PACK_T, 'rec': REC_T}
IN_T = {st: OUT_T[u] for st, u in STAGE_IN.items()}
GOODS = [(st, g) for st in STAGES for g in OUT_T[st]]
MINERAL_OF = {g: ('Li' if g[0] in ('mine', 'proc', 'rec') else None) for g in GOODS}   # None: a product carrying several
PROCESSES = ([('mine', t) for t in MINE_T]
             + [(st, a, b) for st in STAGES[1:] for a in IN_T[st] for b in OUT_T[st]])
RECIPE = {p: ({} if p[0] == 'mine' else {(STAGE_IN[p[0]], p[1]): RATIO[p[0]][p[2]]}) for p in PROCESSES}


def output(p):
    """The good process p makes."""
    return (p[0], p[-1])


def _check_sets():
    """The sets describe one connected network: every input is a good, every good is made, every mineral used."""
    goods = set(GOODS)
    assert {output(p) for p in PROCESSES} == goods, "a good no process makes, or a process making no good"
    assert all(g in goods for p in PROCESSES for g in RECIPE[p]), "a recipe input that is not a good"
    assert set(MINERAL_OF.values()) - {None} == set(MINERALS), "MINERALS and MINERAL_OF disagree"


_check_sets()

MAX_CAP = {'mine': 25, 'proc': 100, 'cath': 12, 'cell': 100, 'pack': 1, 'rec': 15}
MAX_NEW_UNITS, INIT_ACTIVE = 25, 80
INIT_CAPACITY = {'mine': 1000, 'proc': 2500, 'cath': 500, 'cell': 2500, 'pack': 80, 'rec': 250}
SHIP_COST = {'US': 80, 'CHN': 60, 'AUS': 50}
# LLNL's regions (Yao et al., LLNL/CMU interdiction model, 2026; LLNL-TR-859392 had the first four):
# USA, US allies (active US defense treaty), China, rest of world, plus "Special" (DRC) and "Trade
# Embargoed" in mining only. Neither of the last two mines lithium, so the lithium network has four
# regions; Special supplies the cobalt add-on.
LLNL_REGIONS = ['US', 'ALLY', 'CHN', 'ROW']
GROUP = {'USA': 'US', 'USAllies': 'ALLY', 'China': 'CHN', 'ROW': 'ROW', 'Special': 'SPC', 'TradeEmbargoed': 'EMB'}
ROW_PRICED_AS = 'MID'      # no published ROW stage costs: halfway between China and the US (see calibrated())
COUPLED_YEARS = list(range(2031, 2036))      # ERCOT's 2035 storage fleet is bought over these years: by
                                             # 2035, and clear of the horizon's last year (2036), whose
                                             # capacity serves one year and prices as if scarce

# Her notebook's active values (a CHN-weighted exploratory setting) ...
NOTEBOOK = dict(alpha={'US': 10, 'CHN': 0.01, 'AUS': 0.7},
                import_coef={'US': 0.5, 'CHN': 1, 'AUS': 0.3},
                region_share={'US': 0.2, 'CHN': 0.6, 'AUS': 0.1})
# ... and the multipliers of her published-track models (the notebook's commented-out line;
# US 1.3 / China 1.0 as in Alavi & Jones, SCA, and the IISE 2026 FTA paper). The toy uses these.
PUBLISHED = dict(alpha={'US': 1.3, 'CHN': 1.0, 'AUS': 1.1},
                 import_coef={'US': 0.5, 'CHN': 2.0, 'AUS': 0.3},
                 region_share={'US': 0.2, 'CHN': 0.6, 'AUS': 0.1})

# Cobalt add-on (stylized; her model is lithium-only). kt Co per kt NMC cathode (NMC622-like).
CO_PER_NMC = 0.12
CO_MINE = dict(cap=60.0, cost=25.0)               # DRC (LLNL's "Special") mine supply, kt/yr and cost per kt
CO_REFINE = {'US': 60.0, 'CHN': 20.0, 'AUS': 45.0, 'ALLY': 45.0, 'ROW': 45.0}  # per kt refined Co, before alpha
CO_SPOT = 400.0                                   # cost per kt above DRC supply (stockpile/spot)


CAL = RAW / "calibration"
HEADROOM = 1.20                                   # capacity over business-as-usual throughput: covers
                                                  # the EV-share range (her GCAM runs, up to 1.16x)
RAMP = None                                       # growth a year from 2031: None, each region's own IEA base-case
                                                  # growth 2024-2030, at least the world's (ramp_rates()); a
                                                  # number, that rate everywhere (a sensitivity). Jones,
                                                  # 2026-10-30: IEA sets where capacity starts and how fast it
                                                  # can grow, never a ceiling (was: a cap at the pipeline,
                                                  # +25%/yr past it, and no new rest-of-world cathode)
RAMP_FLOOR = 0.01                                 # a region can always add this share of world capacity a year (about
                                                  # one plant; her plant, MAX_CAP, is 4-9% of world output), so a
                                                  # region starting near zero can start. Our assumption
BUILD_EVERY = 2                                   # build decisions every other year (2026, 2028, 2030 ->
                                                  # online 2031, 2033, 2035). Jones, 2026-10-29: the joint MILP
                                                  # took 1-5 min per solve with yearly builds, 6-7 s with these
                                                  # (network cost +0.03% at base; deeper shortages at a 30% cut)
ACT_INTEGER = False
SHORTAGE_MULT = 5.0                               # unmet cells cost 5x China's cost of the cell
SHORTAGE_MULT_REGION = {'US': 10.0}               # Jones, 2026-10-30: losing US demand weighs more. With one
                                                  # price everywhere the planner shorted the US first, the
                                                  # costliest region to supply (30-45% of the unmet cells)
SHIP_VALUE_SHARE = 0.02                           # assumption: trade costs 2% of the goods' value

# The stockpile hook (build(stockpile=...)): defaults, each overridable per call. Ours; her model holds no stock.
# Stock of a good is carried from year to year in a region; what is drawn down supplies that year's balance
# like production, and what is built up leaves it like demand. It is not production, so under rules of origin
# (no_transship) stock is not re-exported: a reserve serves the region that holds it.
STOCKPILE = dict(
    regions=['US'],                               # who holds stock: a US strategic reserve; 'all' for any region
    stages=['mine', 'proc', 'cath', 'cell', 'pack'],   # whose outputs can be stocked (every stage but recycling)
    hold_share=0.10,                              # PLACEHOLDER, no source yet: holding cost a year, as a share of
                                                  # the good's value (China's embedded cost, the trade-cost basis)
    initial={},                                   # {(stage, good, region): stock at the start}; none by default
    max={},                                       # {(stage, region): ceiling on that stage's stock, every good
                                                  # summed, each year}; none by default
    end_at_least_start=True)                      # no stock drawn in the horizon's last year, and each good ends at
                                                  # least where it started. Otherwise the end reads as a free
                                                  # drawdown, and stock stands in for capacity the last year lacks
                                                  # only because it serves one year (as unmet demand is not allowed
                                                  # there either)


# A network for build(): its sets and per-stage capacity settings, and optionally its data. LITHIUM (the default)
# takes its costs, years and demand from Alavi's tables; a network that carries its own data adds
#   years   [year, ...]
#   cost    {stage: (prod, var, fixed)}, each {node[1:] + (year,): cost}: per unit made, per unit of capacity
#           added, per unit (plant) built
#   demand  {(good, region, year): final demand}
# and takes its regions from params["regions"] and its starting capacity from params["init_cap"].
LITHIUM = dict(minerals=MINERALS, stages=STAGES, goods=GOODS, mineral_of=MINERAL_OF, processes=PROCESSES,
               recipe=RECIPE, out_t=OUT_T,
               max_cap=MAX_CAP, init_capacity=INIT_CAPACITY, init_active=INIT_ACTIVE, max_new_units=MAX_NEW_UNITS,
               short_stages=('cell', 'pack'),     # stages whose final demand may go unmet, at a penalty
               value_alone=('rec',),              # goods valued at their own stage's cost (recycled chemicals)
               short_gwh=SHORT_GWH)               # cell GWh per unit unmet, for reporting


# Lifecycle, for a network that carries it (none of it is in LITHIUM):
#   life        {process: (end-of-life good, spec)}: what the process makes in a region in a year is placed there
#               (an end use) and retires over later years into the end-of-life good, by the spec: {"mean": years,
#               "shape": k} or {"shape": k, "scale": years, "loc": years}, a Weibull distribution, or {age: share}
#               directly. build(life=) changes the spec.
#   history     {(process, region, year): units placed} before the horizon, so retirements start where they are
#   collect     share of what retires that must be taken by repurposing or recycling (a number or {year: share});
#               the rest stays in place. 1.0, the default: every retired unit is repurposed or recycled
#   route_caps  {process: share}: a process taking an end-of-life good may take at most this share of what retires
#               (repurposing)
#   scrap       {stage: scrap stage}: what a stage loses (losses) becomes a scrap good of the same name there
#   coproducts  {process: {good: units per unit of output}}: e.g. hydrometallurgy's other metals. A good with
#               co-product supply may leave surplus unused, as may any good in `dispose`
#   no_trade    stages whose goods are not traded (end uses; retired products, shredded where they retire)
#
# Base materials, for a network that carries them (net["base"]; build(base=) replaces a good's spec for one run):
#   base        {good: {"price": p, "cap": {region: c}, "world_cap": c}}: goods whose supply is so large that energy
#               uses are a small, steady part of it (iron, phosphate, manganese, copper, aluminium, steel). They are
#               bought in each region at a price, with no chain behind them: no mines, capacity or trade. p is a
#               number, {year: number} or {region: number or {year: number}} (a region not named pays nothing
#               extra: give every region). "cap" (per region) and "world_cap" (all regions together) are optional
#               ceilings on what is bought, numbers or {year: number}. A base good may also have makers (recycling,
#               say); what is bought adds to them. It is valued at China's price, as made goods are at China's cost,
#               unless "value" (a number or {year: number}) says otherwise: a good cut from a larger network keeps
#               the value it had there, so trade costs and penalties downstream are unchanged.


def reserves_available(spec, t):
    """What can have been extracted by the end of year t of the horizon (t = 0 its first year).

    A number: a fixed total. A dict: reserve x (1 + growth)^t, as reserves grow with discoveries and as resources are
    reclassified, but never above resources x (1 + resource_growth)^t, identified resources being the larger
    category that reserves are drawn from. "growth" and "resource_growth" default to 0, "resources" to no ceiling.
    Reserve and resources are what remains at the horizon's start."""
    if not isinstance(spec, dict):
        return float(spec)
    r = float(spec["reserve"]) * (1.0 + spec.get("growth", 0.0)) ** t
    if "resources" in spec:
        r = min(r, float(spec["resources"]) * (1.0 + spec.get("resource_growth", 0.0)) ** t)
    return r


def retire_share(spec, age):
    """Share of what is placed that retires at this age (years after the year placed; none at age 0)."""
    if age < 1:
        return 0.0
    if "scale" in spec:                            # Weibull by shape, scale and location (years before any retire)
        k, lam, loc = float(spec["shape"]), float(spec["scale"]), float(spec.get("loc", 0.0))

        def G(t):
            return 1.0 - math.exp(-(((t - loc) / lam) ** k)) if t > loc else 0.0
        return G(age) - G(age - 1)
    if "mean" in spec:
        k = float(spec["shape"])
        lam = float(spec["mean"]) / math.gamma(1.0 + 1.0 / k)

        def F(t):
            return 1.0 - math.exp(-((t / lam) ** k)) if t > 0 else 0.0
        return F(age) - F(age - 1)
    if all(isinstance(a, int) for a in spec):
        return float(spec.get(age, 0.0))
    raise ValueError(f"life: a spec is {{'mean': years, 'shape': k}} or {{age: share}}, got {spec!r}")


def check_net(net):
    """A network's sets describe one connected network (see _check_sets). Raises ValueError."""
    goods = set(net["goods"])
    unmade = ({eol for eol, _ in net.get("life", {}).values()} | {g for g in goods if g[0] in net.get("scrap", {}).values()}
              | set(net.get("base", {})))
    if {output(p) for p in net["processes"]} | unmade != goods:
        raise ValueError("a good no process makes (and nothing retires, is scrapped into or is bought), or a process "
                         "making no good")
    for q, (eol, spec) in net.get("life", {}).items():
        if q not in net["processes"] or eol not in goods:
            raise ValueError(f"life: {q!r} is not a process or {eol!r} not a good")
        retire_share(spec, 1)
    for q, outs in net.get("coproducts", {}).items():
        if q not in net["processes"] or not set(outs) <= goods:
            raise ValueError(f"coproducts: {q!r} is not a process, or names a good that is not one")
    for q, ins in net["recipe"].items():
        for k in ins.values():
            if not all(x > 0 for x in (k.values() if isinstance(k, dict) else [k])):
                raise ValueError(f"recipe of {q!r}: coefficients must be positive numbers or {{year: number}}")
    if set(net.get("units", {})) - goods:
        raise ValueError("units: a key that is not a good")
    for q in net.get("route_caps", {}):
        if q not in net["processes"] or len(net["recipe"][q]) != 1:
            raise ValueError(f"route_caps: {q!r} must be a process with one input")
    if not all(g in goods for p in net["processes"] for g in net["recipe"][p]):
        raise ValueError("a recipe input that is not a good")
    if set(net["mineral_of"].values()) - {None} != set(net["minerals"]):
        raise ValueError("minerals and mineral_of disagree")
    if [g for g in net["goods"]] != [(st, n) for st in net["stages"] for n in net["out_t"][st]]:
        raise ValueError("goods must be out_t's, stage by stage")


def check_losses(L, net, regions):
    """Losses keyed by a stage, a process or a node (process + region), each a share in [0, 1) or {year: share}.
    A key must name something with inputs to lose. Raises ValueError; returns L."""
    procs = set(net["processes"])
    has_in = {p for p in procs if net["recipe"][p]}
    for k, v in L.items():
        if k in net["stages"]:
            if not any(p[0] == k for p in has_in):
                raise ValueError(f"losses: no process at stage {k!r} has inputs (mining recovery is `yields`)")
        elif isinstance(k, tuple) and (k in procs or (k[:-1] in procs and k[-1] in regions)):
            if (k if k in procs else k[:-1]) not in has_in:
                raise ValueError(f"losses: {k!r} has no inputs to lose")
        else:
            raise ValueError(f"losses: {k!r} is not a stage, process or node")
        for x in (v.values() if isinstance(v, dict) else [v]):
            if not 0.0 <= x < 1.0:
                raise ValueError(f"losses: {k!r} must be in [0, 1), got {x!r}")
    return L


def by_year(v, y):
    return v[y] if isinstance(v, dict) else v


def _read(name):
    return pd.read_csv(DATA / f"{name}.csv")


def load_data(regions=None):
    """Her inputs. With `regions`, every cost table is re-keyed to those regions: her costs are the
    same in every region (checked here), so regional differences come only from the multipliers.
    Demand is read from her US rows and split by region_share in build(), as in her model."""
    idx = _read("index")
    R = idx["Region"].dropna().tolist()
    Y = [int(y) for y in idx["Year"].dropna().tolist()]
    d = dict(R=list(regions) if regions else R, Y=Y)
    for s in STAGES:
        d[f"{s}_demand"] = _read(f"{s}_demand")
        for k in ("prod", "var", "fixed"):
            df = _read(f"{s}_{k}_cost")
            if regions:
                keys = [c for c in df.columns if c not in ("Region", "Cost")]
                assert (df.groupby(keys).Cost.nunique() == 1).all(), f"{s}_{k}_cost differs by region"
                us = df[df.Region == 'US']
                df = pd.concat([us.assign(Region=r) for r in regions], ignore_index=True)
            d[f"{s}_{k}"] = df
    return d


DATA_CACHE = {}


def data(regions=None):
    key = ("d", tuple(regions or ()))
    if key not in DATA_CACHE:
        DATA_CACHE[key] = load_data(regions)
    return DATA_CACHE[key]


def build(m, params=None, extra_cell_demand=None, tactics=None, yields=None, cobalt=False,
          ev_scale=1.0, fix_int=None, limits=None, stockpile=None, net=None, losses=None, reserves=None, life=None,
          lead=None, route_share=None, extra_demand=None, base=None):
    """Add the network to model m; returns (objective expression, handles).

    extra_cell_demand: {(cell tech, region, year): GWh}, numbers or linear expressions.
    fix_int: integer solution from a previous solve; fixes the integers so the LP gives duals.
    stockpile: None (off), or a dict overriding STOCKPILE's defaults ({} for the defaults as they are).
    net: the network (LITHIUM by default): its sets, and its data if it carries any (see LITHIUM).
    losses: {stage | process | node: share lost, or {year: share}}, over the network's own (net["losses"]); the
      most specific key wins. Applies to processes with inputs; mining recovery is `yields`.
    reserves: {mine node: a number (a fixed total), or {"reserve", "growth", "resources", "resource_growth"}},
      over the network's own (net["reserves"]); see reserves_available.
    life: {process: lifetime spec}, replacing the network's spec for that process (net["life"]; see LIFECYCLE).
    lead: {stage: years}, over the network's (net["lead"]); 5 where neither says.
    route_share: {process: {"min": share, "max": share, "scope": "region" or "world"}}, shares a number or by year,
      over the network's (net["route_share"]).
    extra_demand: {(good, region, year): units}, numbers or linear expressions, added to final demand.
    base: {good: spec}, replacing the network's spec for that good (net["base"]; see the base-materials notes by LITHIUM).
    Recipe and co-product coefficients may be numbers or {year: number} (intensities that change over time).
    """
    p = params or NOTEBOOK
    nt = LITHIUM if net is None else net
    STG, GDS, RCP, OUTT = nt["stages"], nt["goods"], nt["recipe"], nt["out_t"]
    alavi = "cost" not in nt                       # lithium on Alavi's tables, or a network carrying its own data
    if not alavi:
        check_net(nt)
        if cobalt:
            raise ValueError("cobalt is the lithium network's add-on; a network with cobalt in it has it as a mineral")
    alpha, import_coef, region_share = p["alpha"], p["import_coef"], p["region_share"]
    alpha_stage, init_cap, fixed_cap = p.get("alpha_stage", {}), p.get("init_cap"), p.get("fixed_cap", {})
    adv = p.get("tariff_advalorem", {"targets": [], "rates": {}})
    kappa, no_transship = p.get("ship_value_share"), p.get("no_transship", False)
    pipeline, ramp, short_mult = p.get("pipeline", {}), p.get("ramp"), p.get("shortage_mult")
    ramp_floor = p.get("ramp_floor", {})

    def a_(s, r):                                  # her alpha, unless a stage-specific one is given
        return alpha_stage.get(s, {}).get(r, alpha[r])
    if alavi:
        D = data(p.get("regions")); R, Y = D["R"], D["Y"]
    else:
        R, Y = list(p["regions"]), list(nt["years"])
    Y_start = [y for y in Y if y < min(Y) + 5]     # the calibration's ramp starts after five years
    tactics = tactics or {}; yields = yields or {}; limits = limits or {}
    LOSS = check_losses({**nt.get("losses", {}), **(losses or {})}, nt, R)
    RES = {**nt.get("reserves", {}), **(reserves or {})}
    LIFE = {q: (eol, (life or {}).get(q, spec)) for q, (eol, spec) in nt.get("life", {}).items()}
    if set(life or {}) - set(LIFE):
        raise ValueError(f"life: {sorted(set(life) - set(LIFE))} have no lifetime in the network")
    COPROD = nt.get("coproducts", {})              # {process: {good: units per unit of the process's output}}
    SCRAP = nt.get("scrap", {})                    # {stage: scrap stage}: what a stage loses becomes scrap there
    NO_TRADE = set(nt.get("no_trade", ()))         # stages whose goods stay where they are made or retire
    ROUTE_CAP = nt.get("route_caps", {})           # {process: share}: its input <= share x that good's retirement
    COLLECT = nt.get("collect", 1.0)               # share of what retires that must be taken (repurposed or recycled)
    LEAD = {**nt.get("lead", {}), **(lead or {})}  # {stage: years from a build decision to capacity}
    if not all(s in STG and int(v) == v and v >= 0 for s, v in LEAD.items()):
        raise ValueError(f"lead: stages must be the network's and years whole and >= 0, got {LEAD!r}")
    RSHARE = {**nt.get("route_share", {}), **(route_share or {})}
    if set(RSHARE) - set(nt["processes"]):
        raise ValueError(f"route_share: {sorted(set(RSHARE) - set(nt['processes']))} are not processes")
    XD = dict(extra_demand or {})                  # {(good, region, year): units} on top of final demand
    BASE = {**nt.get("base", {}), **(base or {})}  # {good: spec}: bought at a price, no chain behind it
    if set(BASE) - set(GDS):
        raise ValueError(f"base: {sorted(set(BASE) - set(GDS))} are not goods of the network")
    for g, spec in BASE.items():
        if "price" not in spec or set(spec) - {"price", "cap", "world_cap", "value"}:
            raise ValueError(f"base: {g!r} needs a price, and takes only price, cap, world_cap and value")
        if set(spec.get("cap", {})) - set(R):
            raise ValueError(f"base: {g!r} caps regions not in the model")

    def base_price(g, r, y):                       # a number, {year: p} or {region: number or {year: p}}
        pr = BASE[g]["price"]
        if isinstance(pr, dict) and pr and all(isinstance(k, str) for k in pr):
            pr = pr.get(r, 0.0)
        return float(by_year(pr, y))

    def loss(n, y):                                # share lost at node n in year y: node, then process, then stage
        for k in (n, n[:-1], n[0]):
            if k in LOSS:
                return by_year(LOSS[k], y)
        return 0.0
    extra = dict(extra_cell_demand or {})
    for k, v in p.get("grid_demand", {}).items():  # calibration: other grids' storage, exogenous
        extra[k] = extra.get(k, 0.0) + v

    def io(df, ins, outs):
        w = df[df.Year.isin(Y) & df.Input.isin(ins) & df.Output.isin(outs)]
        return {(r.Input, r.Output, r.Region, int(r.Year)): r.Cost for r in w.itertuples()}

    def mine_d(df):
        w = df[df.Year.isin(Y) & df.Technology.isin(MINE_T)]
        return {(r.Technology, r.Region, int(r.Year)): r.Cost for r in w.itertuples()}

    if alavi:
        cost = {'mine': tuple(mine_d(D[f"mine_{k}"]) for k in ("prod", "var", "fixed"))}
        for s, (ins, outs) in {'proc': (MINE_T, PROC_T), 'cath': (PROC_T, CATH_T),
                               'cell': (CATH_T, CELL_T), 'pack': (CELL_T, PACK_T),
                               'rec': (PACK_T, REC_T)}.items():
            cost[s] = tuple(io(D[f"{s}_{k}"], ins, outs) for k in ("prod", "var", "fixed"))
    else:
        cost = nt["cost"]

    def share(df, techs, scale=1.0):
        w = df[df.Year.isin(Y) & df.Technology.isin(techs) & (df.Region == 'US')]
        return {(r.Technology, rg, int(r.Year)): scale * region_share[rg] * r.Demand
                for r in w.itertuples() for rg in R}

    if alavi:
        demand_pack = share(D["pack_demand"], PACK_T, ev_scale)
        demand_rec = share(D["rec_demand"], REC_T)

    def final_demand(g, r, y):                     # a good's final demand; cells add grid storage (extra)
        d = _final_demand(g, r, y)
        return d + XD[g, r, y] if (g, r, y) in XD else d

    def _final_demand(g, r, y):
        s, name = g
        if alavi:
            return {'cell': extra.get((name, r, y), 0.0), 'pack': demand_pack.get((name, r, y), 0.0),
                    'rec': demand_rec.get((name, r, y), 0.0)}.get(s, 0.0)
        d = ev_scale * nt["demand"].get((g, r, y), 0.0) if s == 'pack' else nt["demand"].get((g, r, y), 0.0)
        return d + extra.get((name, r, y), 0.0) if s == 'cell' else d

    N = {s: [p + (r,) for p in nt["processes"] if p[0] == s for r in R] for s in STG}   # nodes, by stage
    ALL = [n for s in STG for n in N[s]]
    trade = {s: ([] if s in NO_TRADE else [p + (i, j) for p in nt["processes"] if p[0] == s for i in R for j in R if i != j])
             for s in STG}
    t_in = {s: {n: [] for n in N[s]} for s in STG}; t_out = {s: {n: [] for n in N[s]} for s in STG}
    for s in STG:
        for k, a in enumerate(trade[s]):           # an arc carries its node's output from region a[-2] to a[-1]
            t_out[s][a[:-2] + (a[-2],)].append(k); t_in[s][a[:-2] + (a[-1],)].append(k)
    makers = {(g, r): [] for g in GDS for r in R}     # the nodes in r that make good g
    users = {(g, r): [] for g in GDS for r in R}      # the nodes in r whose recipe takes good g
    for n in ALL:
        makers[output(n[:-1]), n[-1]].append(n)
        for g in RCP[n[:-1]]:
            users[g, n[-1]].append(n)

    flow = {s: {(k, y): m.addVar() for k in range(len(trade[s])) for y in Y} for s in STG}
    vt = GRB.CONTINUOUS if fix_int is not None else GRB.INTEGER
    prod = {(n, y): m.addVar() for n in ALL for y in Y}
    prod_nodes = set(ALL)
    cap = {(n, y): m.addVar() for n in ALL for y in Y}
    newc = {(n, y): m.addVar() for n in ALL for y in Y}
    inv = {(n, y): m.addVar(vtype=vt) for n in ALL for y in Y}
    # active units are her start count plus integer builds, so integral without being declared so
    act = {(n, y): m.addVar(vtype=vt if ACT_INTEGER else GRB.CONTINUOUS) for n in ALL for y in Y}
    every = p.get("build_every", 1)                # calibration: build decisions every `every` years
    for (n, y), v in inv.items():                  # (not mines: their capacity is fixed by year)
        if (y - min(Y)) % every and n not in fixed_cap:
            v.ub = 0.0
    if fix_int is not None:
        for key, v in inv.items(): v.lb = v.ub = fix_int["inv"][key]
        for key, v in act.items(): v.lb = v.ub = fix_int["act"][key]
    cons = {(n, g, y): m.addVar() for n in ALL for g in RCP[n[:-1]] for y in Y}   # input g taken by node n
    buy = {(g, r, y): m.addVar() for g in BASE for r in R for y in Y}             # base goods bought
    sp = None if stockpile is None else {**STOCKPILE, **stockpile}
    stock = {}                                     # (stage, good, region, year): stock held at the year's end
    if sp is not None:
        if set(sp) != set(STOCKPILE):
            raise ValueError(f"stockpile: unknown options {sorted(set(sp) - set(STOCKPILE))}")
        if not set(sp["stages"]) <= set(STG) - {'rec'}:
            raise ValueError(f"stockpile: stages must be among {STOCKPILE['stages']} (recycling output is not stocked)")
        sp_r = R if sp["regions"] == 'all' else list(sp["regions"])
        if not set(sp_r) <= set(R):
            raise ValueError(f"stockpile: regions {sorted(set(sp_r) - set(R))} are not in the model ({R})")
        stock = {(st, g, r, y): m.addVar() for st in sp["stages"] for g in OUTT[st] for r in sp_r for y in Y}
    m.update()

    def draw(st, g, r, y):                         # stock drawn down in year y (negative when built up)
        if (st, g, r, y) not in stock:
            return 0.0
        prev = stock[st, g, r, y - 1] if y > min(Y) else sp["initial"].get((st, g, r), 0.0)
        return prev - stock[st, g, r, y]

    cell_bal, short_cap = {}, {}
    bal_all, short_cap_all = {}, {}                # every good's balance and shortage cap, for price()
    # unmet demand, where it is consumed: each region's grid cells (its storage, and ERCOT's) and its packs,
    # each at most that demand. A shortfall cannot become cells that are packed and shipped elsewhere.
    # Not in the last year: capacity for it serves one year, so the horizon's end would read as a shortage.
    short_stage = {name: st for st in nt["short_stages"] if st in STG for name in OUTT[st]}
    short = ({(to, r, y): m.addVar() for to in short_stage for r in R for y in Y if y < max(Y)}
             if short_mult else {})
    eol_of = {}                                    # end-of-life good: the processes whose output retires into it
    for q, (eol, _) in LIFE.items():
        eol_of.setdefault(eol, []).append(q)
    hist = nt.get("history", {})                   # {(process, region, year placed): units}, before the horizon

    def retiring(g, r, y):                         # what retires into end-of-life good g in region r in year y
        tot = 0.0
        for q in eol_of.get(g, []):
            spec = LIFE[q][1]
            tot += quicksum(retire_share(spec, y - v) * prod[q + (r,), v] for v in Y if v < y)
            tot += sum(retire_share(spec, y - v) * u for (qq, rr, v), u in hist.items() if qq == q and rr == r and v < y)
        return tot

    scrap_from = {}                                # scrap good: the nodes whose losses become it
    for s, sc in SCRAP.items():
        for n in N[s]:
            scrap_from.setdefault(((sc, output(n[:-1])[1]), n[-1]), []).append(n)
    co_in = {}                                     # good: (node, units per unit output) of processes that co-produce it
    for q, outs in COPROD.items():
        for g, k in outs.items():
            for r in R:
                co_in.setdefault((g, r), []).append((q + (r,), k))
    dispose = set(nt.get("dispose", ())) | {g for g, _ in co_in}    # goods whose surplus may go unused
    retire = {}                                    # (eol good, region, year): expression, for route caps and results
    for g in GDS:                                # every good, region and year: made + imported + drawn from stock
        s, name = g                                # == exported + taken by recipes + final demand
        for r in R:
            for y in Y:
                supply = (quicksum(prod[n, y] for n in makers[g, r])
                          + quicksum(flow[s][k, y] for n in makers[g, r] for k in t_in[s][n])
                          + draw(s, name, r, y))
                if g in eol_of:
                    retire[g, r, y] = retiring(g, r, y)
                    supply += retire[g, r, y]
                for n in scrap_from.get((g, r), []):
                    lo = loss(n, y)
                    if lo:
                        supply += lo / (1.0 - lo) * prod[n, y]   # lost, in units of the output it would have been
                for n, k in co_in.get((g, r), []):
                    supply += by_year(k, y) * prod[n, y]
                if g in BASE:
                    supply += buy[g, r, y]
                use = (quicksum(flow[s][k, y] for n in makers[g, r] for k in t_out[s][n])
                       + quicksum(cons[n, g, y] for n in users[g, r]))
                demand = final_demand(g, r, y)
                use += demand
                if short_stage.get(name) == s and (name, r, y) in short:   # demanded, not supplied: unmet, at a penalty
                    supply += short[name, r, y]
                    c = m.addConstr(short[name, r, y] <= demand)
                    short_cap_all[g, r, y] = c
                    if s == 'cell': short_cap[name, r, y] = c
                if g in eol_of:                    # what retires is taken, at least the collected share; the rest
                    m.addConstr(use <= supply)     # stays in place (in use, stored or landfilled)
                    bal = m.addConstr(use >= by_year(COLLECT, y) * supply)
                elif g in dispose:                 # co-products and the like: surplus may go unused
                    bal = m.addConstr(supply >= use)
                else:
                    bal = m.addConstr(supply == use)
                bal_all[g, r, y] = bal
                if s == 'cell': cell_bal[name, r, y] = bal
    for n in ALL:                                  # each input in its recipe's proportion
        for g, out_per_in in RCP[n[:-1]].items():
            for y in Y:
                m.addConstr(prod[n, y] == (1.0 - loss(n, y)) * by_year(out_per_in, y) * cons[n, g, y])
    for q, shr in ROUTE_CAP.items():               # e.g. repurposing: at most a share of what retires
        (g,) = RCP[q]
        for r in R:
            for y in Y:
                m.addConstr(cons[q + (r,), g, y] <= by_year(shr, y) * retire[g, r, y])
    for q, spec in RSHARE.items():                 # a route's share of its good's output, within bounds
        g = output(q)
        scopes = [[r] for r in R] if spec.get("scope", "region") == "region" else [list(R)]
        for rs in scopes:
            for y in Y:
                mine_q = quicksum(prod[q + (r,), y] for r in rs)
                every_q = quicksum(prod[n, y] for r in rs for n in makers[g, r])
                if "min" in spec:
                    m.addConstr(mine_q >= by_year(spec["min"], y) * every_q)
                if "max" in spec:
                    m.addConstr(mine_q <= by_year(spec["max"], y) * every_q)
    for g, spec in BASE.items():                   # optional ceilings on what is bought
        for r, c in spec.get("cap", {}).items():
            for y in Y:
                m.addConstr(buy[g, r, y] <= by_year(c, y))
        if "world_cap" in spec:
            for y in Y:
                m.addConstr(quicksum(buy[g, r, y] for r in R) <= by_year(spec["world_cap"], y))
    for n, spec in RES.items():                    # extraction to date within what is extractable by then
        if n not in prod_nodes:
            raise ValueError(f"reserves: {n!r} is not a node")
        for y in Y:
            m.addConstr(quicksum(prod[n, v] for v in Y if v <= y) <= reserves_available(spec, y - min(Y)))
    if alavi:                                      # Alavi's recycling: exactly her recycling demand, world-wide
        for tg in REC_T:
            for y in Y:
                m.addConstr(quicksum(prod[('rec', tk, tg, r), y] for tk in PACK_T for r in R)
                            == quicksum(demand_rec[(tg, r, y)] for r in R))
    for n in ALL:
        mc = nt["max_cap"][n[0]]
        for y in Y:
            yl = yields.get((n[1], n[2]), 1.0) if n[0] == 'mine' else 1.0
            m.addConstr(prod[n, y] <= yl * cap[n, y])
            m.addConstr(newc[n, y] <= mc * inv[n, y])
            m.addConstr(cap[n, y] <= mc * act[n, y])
        L = int(LEAD.get(n[0], 5))                 # years from a build decision to capacity
        ys_n = [y for y in Y if y < min(Y) + max(L, 1)]; yw_n = [y for y in Y if y >= min(Y) + max(L, 1)]
        for y in yw_n:
            m.addConstr(act[n, y] == act[n, y - 1] + inv[n, y - L])
            m.addConstr(cap[n, y] <= newc[n, y - L] + cap[n, y - 1])
        if n in fixed_cap:                         # calibration: capacity fixed (a number, or by year)
            for y in Y: m.addConstr(cap[n, y] == by_year(fixed_cap[n], y))
        for y in ys_n:
            m.addConstr(act[n, y] == nt["init_active"])
            if n not in fixed_cap:
                m.addConstr(cap[n, y] == (nt["init_capacity"][n[0]] if init_cap is None
                                          else by_year(init_cap.get(n, 0.0), y)))
    for s in STG:
        for y in Y:
            m.addConstr(quicksum(inv[n, y] for n in N[s]) <= nt["max_new_units"] * every)   # her yearly limit, per build year
    # calibration: from 2031 each region's capacity at a stage (by chemistry for cathode) grows by at most
    # its ramp plus a floor, over each build period; no ceiling. `over` keeps capacity against IEA's path.
    over = {}
    for (s, chem, r), by_y in pipeline.items():
        nodes = [n for n in N[s] if n[-1] == r and (chem is None or n[2] == chem)]
        tot = {y: quicksum(cap[n, y] for n in nodes) for y in Y}
        for y in Y:
            over[s, chem, r, y] = (tot[y], by_y[y])
        if ramp is None:                           # no growth rule given: hold IEA's path
            for y in Y: m.addConstr(tot[y] <= by_y[y])
            continue
        g = ramp.get((s, r), 0.0) if isinstance(ramp, dict) else ramp
        for y in Y:
            if y not in Y_start and y - every >= min(Y):
                m.addConstr(tot[y] <= (1 + g) ** every * tot[y - every] + every * ramp_floor.get((s, chem), 0.0))
    for (s, r), by_y in limits.items():            # output ceiling on one stage in one region
        for y, lim in by_y.items():
            m.addConstr(quicksum(prod[n, y] for n in N[s] if n[-1] == r) <= lim)
    if sp is not None:                             # the stockpile: no free drawdown at the end; optional ceilings
        if sp["end_at_least_start"]:
            for (st, g, r, y), v in stock.items():
                if y == max(Y):
                    m.addConstr(v >= sp["initial"].get((st, g, r), 0.0))
                    if y > min(Y): m.addConstr(v >= stock[st, g, r, y - 1])
        for (st, r), cap_s in sp["max"].items():
            for y in Y:
                m.addConstr(quicksum(stock[st, g, r, y] for g in OUTT[st] if (st, g, r, y) in stock) <= cap_s)

    # ---- LLNL-TR-859392 levers on CHN -> US arcs
    # Targets: the US alone, or the US and its allies (ALLY; AUS in her three regions). LLNL-TR-859392
    # Finding 3 is that coercion must hit both together; a lever on CHN->US alone is routed around.
    targets = set(tactics.get("targets", ["US"]))
    y_from = tactics.get("from_year", min(Y))      # closures act from this year on
    tariff = tactics.get("tariff", {})            # {stage: tau}: x(1 + tau) on shipping; calibrated, tau of value

    def coerced(i, j):
        return i == 'CHN' and j in targets

    for s in STG:
        for k, a in enumerate(trade[s]):
            i, j = a[-2], a[-1]
            if coerced(i, j) and (tactics.get("friendshore") or s in tactics.get("embargo", ())):
                for y in Y:
                    if y >= y_from: flow[s][k, y].ub = 0.0
    if no_transship:                               # calibration: exports of a good <= own production of it
        for s in STG:
            for r in R:
                for b in OUTT[s]:
                    src = [n for n in N[s] if n[-1] == r and n[-2] == b]
                    for y in Y:
                        m.addConstr(quicksum(flow[s][k, y] for n in src for k in t_out[s][n])
                                    <= quicksum(prod[n, y] for n in src))
    for s, q in tactics.get("quota", {}).items():   # {stage: units per year, each target}
        for j in targets:
            for y in Y:
                m.addConstr(quicksum(flow[s][k, y] for k, a in enumerate(trade[s])
                                     if a[-2:] == ('CHN', j)) <= q)

    # ---- objective, exactly as in her notebook (plus the hooks)
    def stage_cost(s, r):                          # costs keyed node[1:] + (year,): (ore, region, year) for mines
        if not N[s]:                               # a stage with no processes (base materials): nothing made
            return 0
        pc, vc, fc = cost[s]
        ns = [n for n in N[s] if n[-1] == r]
        if s == 'mine':
            return a_(s, r) * (quicksum(prod[n, y] * pc[n[1:] + (y,)] / yields.get((n[1], r), 1.0) for y in Y for n in ns)
                               + quicksum(newc[n, y] * vc[n[1:] + (y,)] for y in Y for n in ns)
                               + quicksum(inv[n, y] * fc[n[1:] + (y,)] for y in Y for n in ns))
        return a_(s, r) * (quicksum(prod[n, y] * pc[n[1:] + (y,)] for y in Y for n in ns)
                           + quicksum(newc[n, y] * vc[n[1:] + (y,)] for y in Y for n in ns)
                           + quicksum(inv[n, y] * fc[n[1:] + (y,)] for y in Y for n in ns))

    def import_cost(r):
        tot = 0
        for s in STG:
            for k, a in enumerate(trade[s]):
                i, j = a[-2], a[-1]
                if j != r:
                    continue
                tau = tariff.get(s, 0.0) if coerced(i, j) else 0.0
                if kappa is None:                  # hers: tariff multiplies the shipping cost
                    tot += quicksum((1.0 + tau) * SHIP_COST[r] * flow[s][k, y] for y in Y)
                else:                              # calibrated: trade cost and tariff, shares of value
                    tot += quicksum((kappa + tau) * value(s, a, y) * flow[s][k, y] for y in Y)
        return import_coef[r] * tot + advalorem_cost(r)

    cv = {}
    made_by = {g: [q for q in nt["processes"] if output(q) == g] for g in GDS}
    # Waste and what is made only from waste (retired products, scrap, black mass) is valued at nothing, so a route
    # fed by it (repurposing, recycling) would make its good look nearly free. A good's value is what it costs made
    # new: routes taking waste count only where a good has no other route.
    waste = {g for g in GDS if not made_by[g] and g not in BASE}
    while True:
        more = {g for g in GDS if g not in waste and made_by[g]
                and all(RCP[q] and all(i in waste for i in RCP[q]) for q in made_by[g])}
        if not more:
            break
        waste |= more
    new_route = {g: ([q for q in made_by[g] if not any(i in waste for i in RCP[q])] or made_by[g]) for g in GDS}

    def embedded(s, b, y):                         # China's unit cost of good b, with everything inside it: the
        if (s, b, y) not in cv:                    # cheapest process's cost plus its inputs' values, per unit made
            pc = cost[s][0] if made_by[s, b] else None
            if (s, b) in BASE and "value" in BASE[s, b]:   # base goods: the value given, else China's price
                cv[s, b, y] = float(by_year(BASE[s, b]["value"], y))
            elif (s, b) in BASE and not made_by[s, b]:
                cv[s, b, y] = base_price((s, b), 'CHN', y)
            elif not made_by[s, b]:                # end-of-life and scrap goods: waste, valued at nothing
                cv[s, b, y] = 0.0
            elif s in nt["value_alone"]:             # recycled chemicals: the recycling stage only
                cv[s, b, y] = min(pc[q[1:] + ('CHN', y)] for q in made_by[s, b])
            else:
                cv[s, b, y] = min(pc[q[1:] + ('CHN', y)] + sum(embedded(*g, y) / ((1.0 - loss(q + ('CHN',), y)) * by_year(k, y))
                                                               for g, k in RCP[q].items())
                                  for q in new_route[s, b])
                if (s, b) in BASE:
                    cv[s, b, y] = min(cv[s, b, y], base_price((s, b), 'CHN', y))   # bought where dearer to make
        return cv[s, b, y]

    def value(s, a, y):                            # the traded good's embedded value (at China's cost)
        return embedded(s, a[-3], y)

    def advalorem_cost(r):                         # tariff on the goods' embedded value
        if r not in adv["targets"]:
            return 0
        return quicksum(adv["rates"][s] * value(s, a, y) * flow[s][k, y]
                        for s in adv["rates"] for k, a in enumerate(trade[s]) if a[-2] == 'CHN' and a[-1] == r
                        for y in Y)

    region_cost = {r: quicksum(stage_cost(s, r) for s in STG) + import_cost(r)
                   + quicksum(base_price(g, r, y) * buy[g, r, y] for g in BASE for y in Y) for r in R}

    co_cost = 0
    if cobalt:                                     # refined Co into NMC cathode, by region
        drc = m.addVars(R, Y); spot = m.addVars(R, Y)
        co_y = yields.get(('co', 'DRC'), 1.0)
        for y in Y:
            m.addConstr(quicksum(drc[r, y] for r in R) <= co_y * CO_MINE["cap"])
            for r in R:
                m.addConstr(drc[r, y] + spot[r, y] ==
                            CO_PER_NMC * quicksum(prod[('cath', tp, 'nmc', r), y] for tp in PROC_T))
        co_cost = quicksum(a_('proc', r) * CO_REFINE[r] * (drc[r, y] + spot[r, y])
                           + CO_MINE["cost"] / co_y * drc[r, y] + CO_SPOT * spot[r, y]
                           for r in R for y in Y)
    short_by_r = p.get("shortage_mult_region", {})
    short_cost = quicksum(short_by_r.get(r, short_mult) * embedded(short_stage[to], to, y) * v
                          for (to, r, y), v in short.items())
    hold_cost = (quicksum(sp["hold_share"] * embedded(st, g, y) * v for (st, g, r, y), v in stock.items())
                 if stock else 0)
    obj = quicksum(region_cost.values()) + co_cost + short_cost + hold_cost
    h = dict(Y=Y, R=R, region_cost=region_cost, flow=flow, trade=trade, inv=inv, act=act, prod=prod,
             ALL=ALL, cell_bal=cell_bal, short=short, short_cap=short_cap, over=over, stock=stock,
             hold_cost=hold_cost, net=nt, N=N, cons=cons, losses=LOSS, retire=retire,
             bal_all=bal_all, short_cap_all=short_cap_all, buy=buy, value=embedded)
    return obj, h


def results(h, obj_val, want_duals=False):
    Y, R, region_cost, flow, trade, inv, act, prod, ALL, cell_bal = (h[k] for k in
        ("Y", "R", "region_cost", "flow", "trade", "inv", "act", "prod", "ALL", "cell_bal"))
    nt, N = h["net"], h["N"]
    cells = nt["out_t"].get('cell', [])
    out = dict(status=GRB.OPTIMAL, obj=obj_val, Y=Y, R=R,
               region_cost={r: region_cost[r].getValue() for r in R},
               us_imports=sum(flow[s][k, y].X for s in nt["stages"] for k, a in enumerate(trade[s])
                              for y in Y if a[-1] == 'US'),
               fix_int=dict(inv={k: round(v.X) for k, v in inv.items()},
                            act={k: round(v.X) for k, v in act.items()}))
    # production share by region, cell stage, final year (a compact "where it's made" summary)
    yl = max(Y)
    cell_by_r = {r: sum(prod[n, yl].X for n in N.get('cell', []) if n[-1] == r) for r in R}
    tot = sum(cell_by_r.values()) or 1.0
    out["cell_share"] = {r: v / tot for r, v in cell_by_r.items()}
    out["short"] = {k: v.X * nt["short_gwh"].get(k[0], 1.0) for k, v in h["short"].items() if v.X > 1e-6}   # unmet, GWh
    out["beyond"] = {k: e.getValue() - c for k, (e, c) in h["over"].items() if e.getValue() - c > 1e-6}  # past IEA's path
    out["stock"] = {k: v.X for k, v in h.get("stock", {}).items() if v.X > 1e-6}   # (stage, good, region, year): held
    hc = h.get("hold_cost", 0)
    out["hold_cost"] = hc.getValue() if hasattr(hc, "getValue") else 0.0
    out["bought"] = {k: v.X for k, v in h.get("buy", {}).items() if v.X > 1e-9}   # (good, region, year): base goods
    out["stage_output"] = {}                       # (stage, region, year): output, every node summed
    for (n, y), v in prod.items():
        k = (n[0], n[-1], y); out["stage_output"][k] = out["stage_output"].get(k, 0.0) + v.X
    # where US-bound cells are made over the coupled years, by chemistry
    yc = [y for y in COUPLED_YEARS if y in Y]
    out["cell_prod"] = {(b, r): sum(prod[n, y].X for n in N.get('cell', []) if n[-2:] == (b, r) for y in yc)
                        for b in cells for r in R}
    # binding pattern: which (stage, region) nodes invest anywhere, and which arcs carry flow
    out["pattern"] = frozenset([f"inv:{n[0]}:{n[-1]}" for n in ALL if any(inv[n, y].X > 0.5 for y in Y)]
                               + [f"arc:{s}:{a[-2]}>{a[-1]}" for s in nt["stages"] for k, a in enumerate(trade[s])
                                  if any(flow[s][k, y].X > 1e-3 for y in Y)])
    if want_duals:
        out["cell_dual"] = {(to, y): cell_bal[to, 'US', y].Pi for to in cells for y in Y}
        # The price of extra US grid-cell demand: it is on the right of the cell balance AND caps the shortage
        # (short <= grid demand), so its price is the sum of both duals. They differ only where the cap binds:
        # every US grid cell of that chemistry unmet that year. See scripts/dual_diagnosis.py.
        cap = h.get("short_cap", {})
        out["cell_dual_total"] = {(to, y): cell_bal[to, 'US', y].Pi + (cap[to, 'US', y].Pi if (to, 'US', y) in cap else 0.0)
                                  for to in cells for y in Y}
        cap_all = h.get("short_cap_all", {})
        out["dual"] = {k: c.Pi for k, c in h.get("bal_all", {}).items()}
        out["dual_total"] = {k: v + (cap_all[k].Pi if k in cap_all else 0.0) for k, v in out["dual"].items()}
    return out


def solve(params=None, env=None, want_duals=False, **kw):
    """Solve the network alone. kw: build() options."""
    m = gp.Model('lithium_network', env=env); m.Params.OutputFlag = 0
    obj, h = build(m, params, **kw)
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()
    if m.SolCount == 0:
        return dict(status=m.Status)
    return results(h, m.ObjVal, want_duals and kw.get("fix_int") is not None)


def calibrated(env=None, regions=None, row_priced_as=None, ramp=None):
    """Her published track on LLNL's regions, calibrated from data/calibration/ (module docstring).

    Stage costs: China 1.0; the US and its allies at the Stanford GSB US/China ratio; the rest of
    the world priced as `row_priced_as` (default ROW_PRICED_AS): 'CHN', 'US', or 'MID' (halfway).
    Demand: her world EV total split by 2024 EV battery demand by region, plus every region's grid
    storage (grid_demand()). Capacity follows each region's share of IEA's base case
    (pipeline_share()) of the world's throughput in one solve where every region costs the same,
    times HEADROOM: mines fixed at it every year; refining, cathode and cells start at it (2026-2030)
    and from 2031 grow by at most `ramp` a year (default RAMP: ramp_rates(), each region's IEA growth)
    plus RAMP_FLOOR of the world's 2030 capacity a year, with no ceiling. Grid-cell and pack demand it cannot supply goes unmet, at SHORTAGE_MULT x
    China's cost of the cell or pack (SHORTAGE_MULT_REGION for the regions listed there).
    """
    regions = list(regions or LLNL_REGIONS)
    row = row_priced_as or ROW_PRICED_AS
    ramp = RAMP if ramp is None else ramp
    key = ("cal", tuple(regions), row, ramp)
    rates = ramp_rates(regions) if ramp is None else ramp
    if key in DATA_CACHE:
        return DATA_CACHE[key]
    cost = pd.read_csv(CAL / "stage_costs_us_china.csv").pivot(index="stage", columns="region", values="usd")
    ratio = {s: float(cost.loc[s, 'US'] / cost.loc[s, 'CHN']) for s in cost.index}
    row_alpha = {'CHN': lambda q: 1.0, 'US': lambda q: q, 'MID': lambda q: (1.0 + q) / 2}[row]
    alpha_stage = {s: {'CHN': 1.0, 'US': ratio[s], 'ALLY': ratio[s], 'ROW': row_alpha(ratio[s])} for s in cost.index}
    sh = shares_2024()
    world = sum(PUBLISHED["region_share"].values())          # her world demand, as a multiple of her US curve
    region_share = {r: world * sh[("demand", None)].get(r, 0.0) for r in regions}
    D = data(regions)
    pk = D["pack_demand"][D["pack_demand"].Technology.isin(PACK_T) & (D["pack_demand"].Region == 'US')]
    ev_gwh = {y: world * sum(r.Demand / RATIO['pack'][r.Technology] for r in pk[pk.Year == y].itertuples())
              for y in D["Y"]}                                # her world EV cells, GWh a year
    grid = grid_demand(regions, ev_gwh)
    tar = pd.read_csv(CAL / "us_tariffs_2024.csv")

    m = gp.Model(env=env); m.Params.OutputFlag = 0
    eq = dict(PUBLISHED, regions=regions, alpha={r: 1.0 for r in regions}, import_coef={r: 1.0 for r in regions},
              region_share=region_share, ship_value_share=SHIP_VALUE_SHARE,  # her ship costs exist for her regions only
              grid_demand=grid)
    obj, h = build(m, eq)
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()
    Y = h["Y"]; ys = [y for y in Y if y < min(Y) + 5]
    by = {}                                                   # (node type without region, year): output
    for (n, y), x in h["prod"].items():
        by[n[:-1], y] = by.get((n[:-1], y), 0.0) + x.X

    def chem(n):
        return n[2] if n[0] == 'cath' else None
    fixed_cap = {('mine', tm, r): {y: HEADROOM * pipeline_share('mine', None, r, y) * by[('mine', tm), y] for y in Y}
                 for tm in MINE_T for r in regions}
    init_cap, pipeline = {}, {}
    for n in h["ALL"]:
        s, r = n[0], n[-1]
        if s not in ('proc', 'cath', 'cell'):
            init_cap[n] = float(INIT_CAPACITY[s]); continue
        init_cap[n] = {y: HEADROOM * pipeline_share(s, chem(n), r, y) * by[n[:-1], y] for y in ys}
        g = (s, chem(n), r)
        if g not in pipeline:
            pipeline[g] = {y: HEADROOM * pipeline_share(s, chem(n), r, y)
                          * sum(v for (k, yy), v in by.items() if yy == y and k[0] == s and chem(k + (r,)) == chem(n))
                          for y in Y}
    out = dict(PUBLISHED, regions=regions, alpha={r: 1.0 for r in regions}, import_coef={r: 1.0 for r in regions},
               region_share=region_share, alpha_stage=alpha_stage, fixed_cap=fixed_cap, init_cap=init_cap,
               pipeline=pipeline, ramp=rates,
               ramp_floor={(s, c): RAMP_FLOOR * sum(v[2030] for (s2, c2, _), v in pipeline.items() if (s2, c2) == (s, c))
                           for (s, c, _) in pipeline},
               shortage_mult=SHORTAGE_MULT, grid_demand=grid,
               shortage_mult_region=SHORTAGE_MULT_REGION,
               build_every=BUILD_EVERY,
               ship_value_share=SHIP_VALUE_SHARE, no_transship=True,
               tariff_advalorem=dict(targets=['US'], rates=dict(zip(tar.stage, tar.rate))))
    DATA_CACHE[key] = out
    return out


PIPE = {}


def pipeline_shares():
    """IEA base-case shares by LLNL region, stage (and chemistry, for cathode) and year, from
    data/calibration/capacity_pipeline.csv. Returns {(stage, chemistry or None): {year: {region: share}}};
    Special and Trade Embargoed must hold under 1% of any stage."""
    d = pd.read_csv(CAL / "capacity_pipeline.csv")
    d = d[d.use == "yes"]
    out = {}
    for (stage, chem, year), g in d.groupby(["model_stage", d.chemistry.fillna(""), "year"]):
        v = g.groupby(g.group.map(GROUP)).value.sum()
        v = v / v.sum()
        other = float(v.drop(LLNL_REGIONS, errors="ignore").sum())
        assert other < 0.01, (stage, chem, year, "Special/Embargoed share", other)
        out.setdefault((stage, chem or None), {})[int(year)] = {r: float(v.get(r, 0.0)) for r in LLNL_REGIONS}
    return out


def pipeline_share(stage, chem, r, y):
    """Region r's share of a stage in year y: linear between the source's years, flat outside them."""
    if not PIPE:
        PIPE.update(pipeline_shares())
    by = PIPE.get((stage, chem)) or PIPE[(stage, None)]
    ys = sorted(by)
    return float(np.interp(y, ys, [by[k][r] for k in ys]))


def ramp_rates(regions=None):
    """{(stage, region): growth a year} from IEA's base case, 2024-2030 (capacity_pipeline.csv): each
    region's own growth, at least the world's (a region whose plans are slow can still build as fast as
    the world does). Refining and cells from absolute values (kt Li, GWh); IEA gives cathode as shares
    only, so cathode grows with cells. A region with nothing in 2024 takes the world's rate."""
    d = pd.read_csv(CAL / "capacity_pipeline.csv")
    d = d[(d.use == "yes") & d.year.isin([2024, 2030])]
    out = {}
    for s in ("proc", "cell"):
        g = d[d.model_stage == s]
        v = g.groupby([g.group.map(GROUP), g.year]).value.sum()
        w = g.groupby("year").value.sum()
        world = (w[2030] / w[2024]) ** (1 / 6) - 1
        for r in regions or LLNL_REGIONS:
            a, b = float(v.get((r, 2024), 0.0)), float(v.get((r, 2030), 0.0))
            out[s, r] = float(max((b / a) ** (1 / 6) - 1 if a > 0 else world, world))
    for r in regions or LLNL_REGIONS:
        out["cath", r] = out["cell", r]
    return out


def grid_demand(regions, ev_gwh):
    """Grid storage outside ERCOT: cells, GWh a year by chemistry, region and year, from
    data/calibration/grid_storage.csv. The world's storage is EV cell demand (`ev_gwh`, {year: GWh},
    her curve) times storage's lithium demand over EVs' (IEA GCMO 2025 annex, stated policies), so
    it keeps IEA's proportion; it is split by region at the regions' shares of storage additions; the
    US's less ERCOT's share (ERCOT's own build is the energy model's). LFP at IEA's share of
    stationary storage, the rest NMC. Every value is linear between the source's years, flat outside."""
    d = pd.read_csv(CAL / "grid_storage.csv")
    d = d[d.use == "yes"]
    one = lambda item: float(d[d.item == item].value.iloc[0])
    lfp, ercot = one("lfp_share"), one("ercot_share_of_us")
    li = d[d.item.isin(["storage_li", "ev_li"])].pivot(index="year", columns="item", values="value")
    ratio = (li.storage_li / li.ev_li).sort_index()
    add = d[d.item == "storage_added"]
    sh = add.groupby(["year", add.group.map(GROUP)]).value.sum().unstack(fill_value=0.0)
    sh = sh.div(sh.sum(axis=1), axis=0).sort_index()
    out = {}
    for y, ev in ev_gwh.items():
        world = ev * float(np.interp(y, ratio.index.to_numpy(), ratio.to_numpy()))
        for r in regions:
            v = world * float(np.interp(y, sh.index.to_numpy(), sh[r].to_numpy())) * (1.0 - ercot if r == 'US' else 1.0)
            out['GWh_lfp', r, y] = lfp * v
            out['GWh_nmc', r, y] = (1.0 - lfp) * v
    return out


def shares_2024():
    """2024 shares by LLNL region from data/calibration/country_shares_2024.csv (one row per
    country, stage and source). Returns {(stage, chemistry or None): {region: share}}, lithium regions
    only; Special and Trade Embargoed must hold under 1% of any lithium stage."""
    d = pd.read_csv(CAL / "country_shares_2024.csv")
    d = d[d.use == "yes"]
    out = {}
    for (stage, chem), g in d.groupby(["model_stage", d.chemistry.fillna("")]):
        v = g.groupby(g.group.map(GROUP)).value.sum()
        v = v / v.sum()
        other = float(v.drop(LLNL_REGIONS, errors="ignore").sum())
        assert other < 0.01 or stage == "cobalt", (stage, chem, "Special/Embargoed share", other)
        out[(stage, chem or None)] = {r: float(v.get(r, 0.0)) for r in LLNL_REGIONS}
    return out


def us_cell_price(extra_cell_demand=None, years=None, total=False, **kw):
    """Marginal cost of one more US cell GWh (by chemistry), averaged over `years`.

    Solve the MILP, fix its integers, re-solve the LP and read the duals of the US cell balance. With
    total=True, add the dual of the shortage cap, which extra grid demand also loosens (cell_dual_total in
    results()): the price of the demand itself. The default, the balance alone, is what the committed results
    used; it overstates the price where every US grid cell of a chemistry goes unmet.
    """
    base = solve(extra_cell_demand=extra_cell_demand, **kw)
    if "obj" not in base:
        return None, base
    lp = solve(extra_cell_demand=extra_cell_demand, fix_int=base["fix_int"], want_duals=True, **kw)
    years = years or COUPLED_YEARS
    key = "cell_dual_total" if total else "cell_dual"
    price = {to: float(np.mean([lp[key][to, y] for y in years])) for to in CELL_T}
    return price, base


def price(goods, region='US', years=None, total=False, params=None, **kw):
    """Marginal cost of one more unit of each good demanded in `region`, by year: {(good, year): price}.

    Any good, any network (net=...): solve the MILP, fix its integers, re-solve the LP and read the duals of the
    good's balance; with total=True add its shortage cap's dual, as us_cell_price does for cells. kw: build()
    options (net, extra_demand, ...). Returns (prices, the MILP's results)."""
    base = solve(params, **kw)
    if "obj" not in base:
        return None, base
    lp = solve(params, fix_int=base["fix_int"], want_duals=True, **kw)
    key = "dual_total" if total else "dual"
    return {(g, y): lp[key][g, region, y] for g in goods for y in (years or lp["Y"])}, base


def cut(net, goods):
    """The network with everything upstream of `goods` removed: (net, removed processes, removed goods).

    Upstream is what makes the cut goods and, in turn, what only feeds that: walking back from each cut good, a
    process that makes it goes unless one of its inputs lies downstream of the cut (recycling, which makes refined
    metal from black mass, stays); an input goes with its last user, and its final demand (other uses) with it.
    The cut goods stay, with no maker but what stays: zoom() makes them base goods. No solve; the copy is new.
    """
    import copy
    goods = list(goods)
    G = set(net["goods"])
    if set(goods) - G:
        raise ValueError(f"cut: {sorted(set(goods) - G)} are not goods of the network")
    P, RCP = net["processes"], net["recipe"]
    users = {g: [q for q in P if g in RCP[q]] for g in G}
    makers = {g: [q for q in P if output(q) == g] for g in G}
    life, scrap, co = net.get("life", {}), net.get("scrap", {}), net.get("coproducts", {})

    def after(q):                                  # the goods a process puts into the network
        out = {output(q), *co.get(q, {})}
        if q in life:
            out.add(life[q][0])
        if q[0] in scrap:
            out.add((scrap[q[0]], q[-1]))
        return out & G
    down, todo = set(goods), list(goods)           # everything downstream of the cut
    while todo:
        for q in users[todo.pop()]:
            for g in after(q) - down:
                down.add(g); todo.append(g)
    gone_p, gone_g = set(), set()
    while True:                                    # to a fixed point: a good goes once all its users have
        more_p = {q for g in set(goods) | gone_g for q in makers[g]
                  if q not in gone_p and not any(i in down for i in RCP[q])}
        more_g = {i for q in gone_p | more_p for i in RCP[q]
                  if i not in goods and i not in gone_g and all(u in gone_p | more_p for u in users[i])
                  and not any(j in down for mk in makers[i] for j in RCP[mk])}
        if not more_p and not more_g:
            break
        gone_p |= more_p; gone_g |= more_g
    for g in goods:
        if not any(q in gone_p for q in makers[g]):
            raise ValueError(f"cut: nothing upstream of {g!r} to remove")
    for q in gone_p:
        if q in life or set(co.get(q, {})) - gone_g - set(goods):
            raise ValueError(f"cut: {q!r} would go, but it also puts goods downstream (a lifetime or co-products)")
    z = copy.deepcopy(net)
    z["processes"] = [q for q in P if q not in gone_p]
    z["recipe"] = {q: v for q, v in z["recipe"].items() if q not in gone_p}
    z["goods"] = [g for g in z["goods"] if g not in gone_g]
    z["out_t"] = {s: [b for b in v if (s, b) not in gone_g] for s, v in z["out_t"].items()}
    for k in ("mineral_of", "units", "base"):
        if k in z:
            z[k] = {g: v for g, v in z[k].items() if g not in gone_g}
    z["minerals"] = [x for x in z["minerals"] if x in set(z["mineral_of"].values())]
    for k in ("coproducts", "route_caps", "route_share"):
        if k in z:
            z[k] = {q: v for q, v in z[k].items() if q not in gone_p}
    if "losses" in z:                              # keyed by stage, process or node
        z["losses"] = {k: v for k, v in z["losses"].items() if k not in gone_p and k[:-1] not in gone_p}
    for k in ("reserves",):                        # keyed by node
        if k in z:
            z[k] = {n: v for n, v in z[k].items() if n[:-1] not in gone_p}
    for k in ("demand", "history"):                # keyed (good or process, region, year)
        if k in z:
            z[k] = {key: v for key, v in z[k].items() if key[0] not in gone_g and key[0] not in gone_p}
    if "dispose" in z:
        z["dispose"] = [g for g in z["dispose"] if g not in gone_g]
    return z, sorted(gone_p), sorted(gone_g)


def zoom(goods, params=None, net=None, caps=True, env=None, **kw):
    """Zoom in: the network cut at `goods` (cut()), each cut good bought at what it is worth in the whole network.

    Solve the whole network (MILP, then its LP with the integers fixed), then make each cut good a base good:
      price  by region and year, the dual of its balance: its marginal cost in the whole network;
      value  the whole network's valuation of it (trade costs and penalties downstream are shares of value);
      cap    with caps=True, what each region got from the removed chain (made there, plus imports, less exports).
    Price and value reproduce the whole network's cost and keep its plan optimal in the zoomed one; at exactly
    the marginal price a buyer is indifferent to how much it buys, so where plans tie, the caps pin the quantities.
    With all three the zoomed network reproduces the whole one's plan (tested on the lithium network as the
    working repository runs it and on the battery network: tests/test_solver.py). The prices hold for the case
    they came from: a change near the cut (a tariff, a demand shock) moves them, so check such a case against
    the whole network.

    kw: build() options, for both solves; solve the zoomed network with the same ones (leaving out any that name
    a removed process or good). Returns (zoomed net, info): info has the removed processes and goods, each cut
    good's price, value and cap, and the whole network's LP results.
    """
    goods = list(goods)
    nt = LITHIUM if net is None else net
    m = gp.Model(env=env); m.Params.OutputFlag = 0
    obj, h = build(m, params, net=nt, **kw)
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()
    if m.SolCount == 0:
        raise RuntimeError(f"zoom: the whole network did not solve (status {m.Status})")
    fix = dict(inv={k: round(v.X) for k, v in h["inv"].items()}, act={k: round(v.X) for k, v in h["act"].items()})
    lp = gp.Model(env=env); lp.Params.OutputFlag = 0
    obj, h = build(lp, params, net=nt, **{**kw, "fix_int": fix})
    lp.setObjective(obj, GRB.MINIMIZE); lp.optimize()
    if lp.Status != GRB.OPTIMAL:
        raise RuntimeError(f"zoom: the whole network's LP did not solve (status {lp.Status})")
    z, gone_p, gone_g = cut(nt, goods)
    Y, R, gp_ = h["Y"], h["R"], set(gone_p)
    got = {(g, r, y): 0.0 for g in goods for r in R for y in Y}
    for n in h["ALL"]:                             # what each region got from the removed chain
        if n[:-1] in gp_ and output(n[:-1]) in goods:
            for y in Y:
                got[output(n[:-1]), n[-1], y] += h["prod"][n, y].X
    for s, arcs in h["trade"].items():
        for k, a in enumerate(arcs):
            if a[:-2] in gp_ and output(a[:-2]) in goods:
                for y in Y:
                    x = h["flow"][s][k, y].X
                    got[output(a[:-2]), a[-1], y] += x; got[output(a[:-2]), a[-2], y] -= x
    info = dict(processes=gone_p, goods=gone_g, price={}, value={}, cap={}, whole=results(h, lp.ObjVal))
    z.setdefault("base", {})
    for g in goods:
        info["price"][g] = {r: {y: h["bal_all"][g, r, y].Pi for y in Y} for r in R}
        info["value"][g] = {y: h["value"](*g, y) for y in Y}
        info["cap"][g] = {r: {y: max(got[g, r, y], 0.0) for y in Y} for r in R}
        z["base"][g] = {"price": info["price"][g], "value": info["value"][g]}
        if caps:
            z["base"][g]["cap"] = info["cap"][g]
    return z, info


def us_cell_prices(periods, extra_cell_demand=None, total=False, **kw):
    """us_cell_price for several periods from one solve: {name: {chemistry: mean dual over that period's years}}.

    periods: {name: years}. For the multi-period testbed (multiperiod.py), where ERCOT buys in each period."""
    base = solve(extra_cell_demand=extra_cell_demand, **kw)
    if "obj" not in base:
        return None, base
    lp = solve(extra_cell_demand=extra_cell_demand, fix_int=base["fix_int"], want_duals=True, **kw)
    key = "cell_dual_total" if total else "cell_dual"
    return {t: {to: float(np.mean([lp[key][to, y] for y in ys])) for to in CELL_T} for t, ys in periods.items()}, base


def check_agreement(tol=1e-6):
    """Port vs her notebook (data/reference/sara_network_meta.json): same objective."""
    import json
    ref = json.loads((RAW / "reference" / "sara_network_meta.json").read_text())
    got = solve(NOTEBOOK)["obj"]
    rel = abs(got - ref["objective"]) / abs(ref["objective"])
    assert rel <= tol, f"port {got:.6f} vs notebook {ref['objective']:.6f} (rel {rel:.2e})"
    return got, ref["objective"], rel


if __name__ == "__main__":
    print("agreement (port, notebook, rel):", check_agreement())
    r = solve(PUBLISHED)
    print("published multipliers:", round(r["obj"], 2), {k: round(v, 1) for k, v in r["region_cost"].items()},
          "cell share", {k: round(v, 2) for k, v in r["cell_share"].items()})

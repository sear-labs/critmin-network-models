"""critmin-net's engine: build() adds a supply-chain network to a gurobipy model, from the network's own sets and data.

A network (a dict: see the notes above build()) names its minerals, stages, goods, processes and recipes, and carries
its years, costs and demand; params name its regions and starting capacity. build() makes every balance, trade arc,
capacity and build decision from those, so a new mineral, stage or input is new entries in a network, not new
constraints. The battery network (battery.py) and its horizon (horizon.py) are built this way.

The engine began as a port of Sara Alavi's six-stage lithium network (SEAR Lab; sear-labs/mineralnet-optsc). That
network, its inputs and the calibration that moved it to LLNL's regions were retired in 0.16.0 and remain in this
repository's history (0.15.x).

Hooks (all off by default):
  * losses             material lost in a process, as a share of what goes in, by stage, process or node
                       (process + region), optionally by year: output = (1 - loss) x recipe x input. A network
                       may carry its own defaults (net["losses"]); the argument overrides them key by key
  * reserves           extraction to date within what is extractable, per mine node: a fixed total, or reserves
                       that grow (discoveries and reclassification) up to identified resources, also growing
                       (reserves_available)
  * lead               build lead time by stage, years from a build decision to capacity (5 for all stages unless a
                       network or the argument says otherwise)
  * route_share        bounds on a route's share of its good's output, per region or world-wide, optionally by year
                       (technology or chemistry choice within limits)
  * extra_demand       demand added on any good, region and year, numbers or linear expressions (an energy model's
                       purchases); price() reads back any good's marginal cost
  * base               goods bought at a price, with no chain behind them (see the base-materials notes); zoom()
                       cuts a network at some goods and buys them at their whole-network price, value and quantity,
                       which reproduces the whole network's plan (cut() is the cut alone)
  * life               product lifetimes, over a network's own (net["life"]): what a process places in a region
                       (an end use) retires there over the following years, by a lifetime distribution, into an
                       end-of-life good that repurposing and recycling take (see the lifecycle notes)
  * limits             output ceiling per (stage, region) and year, e.g. a region's refining cut to a share of
                       its usual output (a shock)
  * stockpile          stock carried between years, by stage, good and region, built up and drawn down as
                       the model chooses, at a holding cost; none is drawn in the last year, and it ends
                       with at least what it started with (STOCKPILE: options, defaults)
  * tariffs            ad valorem, by arc and stage or good, on the traded good's embedded value
  * quad_cost, cost_curve, demand_curve, pools   rising costs, stepped supply and demand curves, shared capacity
params also take: ship_value_share (trade cost as a share of the goods' value, the same at every stage; default
SHIP_VALUE_SHARE), no_transship (rules of origin: a region exports only what it makes; True: every year, a year: from
that year on), shortage_mult (unmet final demand at the network's short_stages, at that multiple of China's cost of
the good; None: none allowed), alpha and alpha_stage (cost multipliers by region, and by stage and region),
import_coef (a multiplier on each region's trade costs), and the capacity options in build()'s docstring.
"""
import math
import os
from pathlib import Path

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

# ---- a network as sets: minerals, goods, processes and their recipes
# A good is (the stage that makes it, its name). A process makes one good: a mine is (stage, ore), every other
# process (stage, input, ..., output), and recipe[process] = {input good: output per unit of that input} (empty for
# mines). A node is a process in a region: process + (region,).


def output(p):
    """The good process p makes."""
    return (p[0], p[-1])


# LLNL's regions (Yao et al., LLNL/CMU interdiction model, 2026; LLNL-TR-859392 had the first four): USA, US allies
# (active US defense treaty), China, rest of world, plus "Special" (the DRC) and "Trade Embargoed" in mining only.
LLNL_REGIONS = ['US', 'ALLY', 'CHN', 'ROW']
CAL = RAW / "calibration"                         # 2024 shares by country (country_shares_2024.csv)
ACT_INTEGER = False
SHORTAGE_MULT = 5.0                               # unmet demand costs 5x China's cost of the good
SHIP_VALUE_SHARE = 0.02                           # assumption: trade costs 2% of the goods' value

# The stockpile hook (build(stockpile=...)): defaults, each overridable per call.
# Stock of a good is carried from year to year in a region; what is drawn down supplies that year's balance
# like production, and what is built up leaves it like demand. It is not production, so under rules of origin
# (no_transship) stock is not re-exported: a reserve serves the region that holds it.
STOCKPILE = dict(
    regions=['US'],                               # who holds stock: a US strategic reserve; 'all' for any region
    stages=None,                                  # whose outputs can be stocked: None, every stage of the network
    hold_share=0.10,                              # PLACEHOLDER, no source yet: holding cost a year, as a share of
                                                  # the good's value (China's embedded cost, the trade-cost basis)
    initial={},                                   # {(stage, good, region): stock at the start}; none by default
    max={},                                       # {(stage, region): ceiling on that stage's stock, every good
                                                  # summed, each year}; none by default
    from_year=None,                               # 0.13.0: no stock held before this year (None: from the first)
    hold_unit={},                                 # 0.15.0: {stage: cost per unit held a year}, on top of hold_share
                                                  # (goods whose value is nil, such as retired packs, still cost to
                                                  # store); none by default
    end_at_least_start=True)                      # no stock drawn in the horizon's last year, and each good ends at
                                                  # least where it started. Otherwise the end reads as a free
                                                  # drawdown, and stock stands in for capacity the last year lacks
                                                  # only because it serves one year (as unmet demand is not allowed
                                                  # there either)


# A network for build(): a dict of its sets, per-stage capacity settings and data.
#   minerals, stages, goods, mineral_of, processes, recipe, out_t   the sets (check_net() checks they hang together)
#   max_cap, init_capacity   {stage: units}: a plant's size, and capacity at the start where params give no init_cap
#   init_active, max_new_units   plants active at the start, and plants built per stage per build year (lumpy builds)
#   short_stages   stages whose final demand may go unmet, at a penalty (params["shortage_mult"])
#   value_alone    stages whose goods are valued at their own stage's cost only
#   short_gwh      {good name: GWh per unit unmet}, for reporting
#   years   [year, ...]
#   cost    {stage: (prod, var, fixed)}, each {node[1:] + (year,): cost}: per unit made, per unit of capacity
#           added, per unit (plant) built
#   demand  {(good, region, year): final demand}
# It takes its regions from params["regions"] and its starting capacity from params["init_cap"]. Optionally:
#   lead    {stage: years, or {region: years}}: from a build decision to capacity (build(lead=) overrides a stage)
#   lumpy   False: capacity is built in any amount (newc, priced by cost's `var`), not in whole plants; inv stays 0
# params["observed_to"] (default none) keeps capacity at the starting capacity through that year whatever the lead,
# so the years to it can be observed ones; builds are still decided from the first year (a plant decided in the first
# year with a two-year lead serves from the third).


# Lifecycle, for a network that carries it:
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
#   trade_only  processes kept only for their trade routes, with no recipe: they make nothing. A good is traded on
#               its makers' arcs, so zoom() keeps a cut good's removed makers this way and the good moves as before
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
    for q in net.get("trade_only", ()):
        if q not in net["processes"] or net["recipe"][q]:
            raise ValueError(f"trade_only: {q!r} must be a process with no recipe")
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
                raise ValueError(f"losses: no process at stage {k!r} has inputs (mines have none)")
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


def build(m, params=None, fix_int=None, limits=None, stockpile=None, net=None, losses=None, reserves=None, life=None,
          lead=None, route_share=None, extra_demand=None, base=None, quad_cost=None, cost_curve=None,
          demand_curve=None, tariffs=None, pools=None):
    """Add the network to model m; returns (objective expression, handles).

    fix_int: integer solution from a previous solve; fixes the integers so the LP gives duals.
    stockpile: None (off), or a dict overriding STOCKPILE's defaults ({} for the defaults as they are).
    params, net: required; the network's sets and data, and its regions and settings (see the notes above).
    losses: {stage | process | node: share lost, or {year: share}}, over the network's own (net["losses"]); the
      most specific key wins. Applies to processes with inputs.
    reserves: {mine node: a number (a fixed total), or {"reserve", "growth", "resources", "resource_growth"}},
      over the network's own (net["reserves"]); see reserves_available.
    life: {process: lifetime spec}, replacing the network's spec for that process (net["life"]; see LIFECYCLE).
    lead: {stage: years, or {region: years}}, over the network's (net["lead"]), a stage's entry replacing the
      network's whole; 5 where neither says (for a stage or a region). A process may have its own entry (0.13.0:
      a mine's expansion faster than a new mine), which wins over its stage's. A region's own lead (US and allied plants
      taking longer to permit and build than China's) is off unless a network or a run gives one.
    route_share: {process: {"min": share, "max": share, "scope": "region" or "world"}}, shares a number or by year,
      over the network's (net["route_share"]).
    extra_demand: {(good, region, year): units}, numbers or linear expressions, added to final demand.
    base: {good: spec}, replacing the network's spec for that good (net["base"]; see the base-materials notes).
    quad_cost: [(nodes, year, gamma)], each adding 0.5 * gamma * (the nodes' production that year)^2 to the objective:
      a cost that rises with output, as a calibration sets it (battery.calibrate()). Nodes not in the network are
      left out, and a term with none left is dropped. None (the default) adds nothing.
    cost_curve: [(nodes, year, [(size, adder), ...])], a stepped supply curve on the nodes' output that year: the
      output is split into blocks of at most `size` (None: no limit; the last block should have none), each costing
      `adder` per unit on top of the nodes' own costs. Adders should rise block by block (a convex curve), so the
      cheapest blocks fill first. None adds nothing.
    demand_curve: {(good, region, year): [(size, value), ...]}, a stepped demand curve on top of final demand: up
      to `size` more units are taken in each block, each worth `value` per unit (subtracted from the objective).
      Values should fall block by block. None adds nothing.
    tariffs: {(stage, exporter, importer) or (stage, good, exporter, importer): rate or {year: rate}}, ad valorem
      on the traded good's embedded value (a good's own key over its stage's).
      None adds nothing.
    pools: [{node: coef}], capacity shared by nodes of one region (routes to one good, or chemistries on one line):
      sum coef x output <= sum coef x capacity, in place of each node's own limit. coef puts the nodes' units on one
      basis (1 for nodes making the same good). A cost curve's nodes may include ("buy", good, region) for a base
      material's purchases. None: every node has its own capacity, as before.
    params["discount"]: a rate; every year's costs (and demand curves' values) are weighted by
      (1 + rate) ** -(year - params.get("discount_base", first year)). None (the default): undiscounted.
    params["capacity_rule"]: "cumulative" makes capacity after the starting years the starting capacity that year
      (init_cap by year, so it can retire) plus what was built and is still within params["build_life"] ({stage:
      years}, 25 where not given); otherwise (the default) last year's capacity plus this year's arrivals.
    route_share's shares may also be {region: share or {year: share}} (a region left out is not bounded).
    params["cap_max"]: {node: number or {year: number}}, a ceiling on a node's capacity (0.13.0). reserves' keys may be
      a tuple of nodes drawing on one deposit (a mine and its expansion), whose extraction is summed (0.13.0).
    Recipe and co-product coefficients may be numbers or {year: number} (intensities that change over time).
    """
    if params is None or net is None or "cost" not in net:
        raise ValueError("build: a network carrying its own data (net=) and its params are required")
    p, nt = params, net
    STG, GDS, RCP, OUTT = nt["stages"], nt["goods"], nt["recipe"], nt["out_t"]
    check_net(nt)
    alpha, import_coef = p["alpha"], p["import_coef"]
    alpha_stage, init_cap = p.get("alpha_stage", {}), p.get("init_cap")
    kappa, no_transship = p.get("ship_value_share", SHIP_VALUE_SHARE), p.get("no_transship", False)
    short_mult = p.get("shortage_mult")

    def a_(s, r):                                  # the region's cost multiplier, unless a stage-specific one is given
        return alpha_stage.get(s, {}).get(r, alpha[r])
    R, Y = list(p["regions"]), list(nt["years"])
    disc, d_base = p.get("discount"), p.get("discount_base", min(Y))

    def w(y):                                      # the year's weight in the objective (1.0 undiscounted)
        return 1.0 if disc is None else (1.0 + disc) ** -(y - d_base)
    limits = limits or {}
    LOSS = check_losses({**nt.get("losses", {}), **(losses or {})}, nt, R)
    RES = {**nt.get("reserves", {}), **(reserves or {})}
    LIFE = {q: (eol, (life or {}).get(q, spec)) for q, (eol, spec) in nt.get("life", {}).items()}
    if set(life or {}) - set(LIFE):
        raise ValueError(f"life: {sorted(set(life) - set(LIFE))} have no lifetime in the network")
    COPROD = nt.get("coproducts", {})              # {process: {good: units per unit of the process's output}}
    SCRAP = nt.get("scrap", {})                    # {stage: scrap stage}: what a stage loses becomes scrap there
    NO_TRADE = set(nt.get("no_trade", ()))         # stages whose goods stay where they are made or retire
    TRADE_ONLY = set(nt.get("trade_only", ()))     # processes kept for their trade routes only (zoom())
    ROUTE_CAP = nt.get("route_caps", {})           # {process: share}: its input <= share x that good's retirement
    COLLECT = nt.get("collect", 1.0)               # share of what retires that must be taken (repurposed or recycled)
    LEAD = {**nt.get("lead", {}), **(lead or {})}  # {stage or process: years, or {region: years}}
    if not all((s in STG or s in nt["processes"])
               and all(int(v) == v and v >= 0 for v in (y.values() if isinstance(y, dict) else [y]))
               for s, y in LEAD.items()):
        raise ValueError(f"lead: keys must be the network's stages or processes and years whole and >= 0, got {LEAD!r}")

    def lead_of(n):                                # node n's lead: its process's, else its stage's; by region or not
        v = LEAD.get(n[:-1], LEAD.get(n[0], 5))
        return int(v.get(n[-1], 5) if isinstance(v, dict) else v)
    LUMPY = nt.get("lumpy", True)                  # builds in whole plants (her model); False: any amount
    CUMULATIVE = p.get("capacity_rule") == "cumulative"
    CAP_MAX = p.get("cap_max", {})                 # {node: ceiling on its capacity, or by year}
    BUILD_LIFE = p.get("build_life", {})           # {stage: years a built plant serves} (cumulative rule)
    RSHARE = {**nt.get("route_share", {}), **(route_share or {})}
    if set(RSHARE) - set(nt["processes"]):
        raise ValueError(f"route_share: {sorted(set(RSHARE) - set(nt['processes']))} are not processes")
    XD = dict(extra_demand or {})                  # {(good, region, year): units} on top of final demand
    TARIFFS = dict(tariffs or {})                  # {(stage, exporter, importer): ad valorem rate, or by year}
    if {k[0] for k in TARIFFS} - set(STG):
        raise ValueError(f"tariffs: stages {sorted({k[0] for k in TARIFFS} - set(STG))} are not the network's")
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
    cost = nt["cost"]

    def final_demand(g, r, y):                     # a good's final demand, plus extra_demand
        d = nt["demand"].get((g, r, y), 0.0)
        return d + XD[g, r, y] if (g, r, y) in XD else d

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
    vt = GRB.CONTINUOUS if fix_int is not None or not LUMPY else GRB.INTEGER
    prod = {(n, y): m.addVar() for n in ALL for y in Y}
    prod_nodes = set(ALL)
    for (n, y), v in prod.items():                 # trade-only processes make nothing
        if n[:-1] in TRADE_ONLY:
            v.ub = 0.0
    cap = {(n, y): m.addVar() for n in ALL for y in Y}
    newc = {(n, y): m.addVar() for n in ALL for y in Y}
    inv = {(n, y): m.addVar(vtype=vt) for n in ALL for y in Y}
    # active units are the starting count plus integer builds, so integral without being declared so
    act = {(n, y): m.addVar(vtype=vt if ACT_INTEGER else GRB.CONTINUOUS) for n in ALL for y in Y}
    every = p.get("build_every", 1)                # calibration: build decisions every `every` years
    observed_to = p.get("observed_to", min(Y) - 1)  # capacity is the starting capacity through this year
    if observed_to != min(Y) - 1 and observed_to not in Y:
        raise ValueError(f"observed_to: {observed_to!r} is not a year of the model")
    for (n, y), v in inv.items():
        if (y - min(Y)) % every or not LUMPY:
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
        sp["stages"] = list(STG) if sp["stages"] is None else list(sp["stages"])
        if not set(sp["stages"]) <= set(STG):
            raise ValueError(f"stockpile: stages must be among the network's ({STG})")
        sp_r = R if sp["regions"] == 'all' else list(sp["regions"])
        if not set(sp_r) <= set(R):
            raise ValueError(f"stockpile: regions {sorted(set(sp_r) - set(R))} are not in the model ({R})")
        stock = {(st, g, r, y): (m.addVar(ub=0.0) if sp["from_year"] is not None and y < sp["from_year"] else m.addVar())
                 for st in sp["stages"] for g in OUTT[st] for r in sp_r for y in Y}
    m.update()

    def draw(st, g, r, y):                         # stock drawn down in year y (negative when built up)
        if (st, g, r, y) not in stock:
            return 0.0
        prev = stock[st, g, r, y - 1] if y > min(Y) else sp["initial"].get((st, g, r), 0.0)
        return prev - stock[st, g, r, y]

    bal_all, short_cap_all = {}, {}                # every good's balance and shortage cap, for price()
    # unmet demand, where it is consumed: final demand at the network's short_stages, each at most that demand.
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
    served = {}                                    # demand curves: (good, region, year, block) -> units taken
    for (g, r, y), blocks in (demand_curve or {}).items():
        if g not in GDS or r not in R or y not in Y:
            raise ValueError(f"demand_curve: {(g, r, y)!r} is not a good, region and year of the model")
        for k, (size, _) in enumerate(blocks):
            served[g, r, y, k] = m.addVar(ub=GRB.INFINITY if size is None else float(size))
    served_at = {}
    for (g, r, y, k), v in served.items():
        served_at.setdefault((g, r, y), []).append(v)
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
                if (g, r, y) in served_at:
                    use += quicksum(served_at[g, r, y])
                if short_stage.get(name) == s and (name, r, y) in short:   # demanded, not supplied: unmet, at a penalty
                    supply += short[name, r, y]
                    c = m.addConstr(short[name, r, y] <= demand)
                    short_cap_all[g, r, y] = c
                if g in eol_of:                    # what retires is taken, at least the collected share; the rest
                    m.addConstr(use <= supply)     # stays in place (in use, stored or landfilled)
                    bal = m.addConstr(use >= by_year(COLLECT, y) * supply)
                elif g in dispose:                 # co-products and the like: surplus may go unused
                    bal = m.addConstr(supply >= use)
                else:
                    bal = m.addConstr(supply == use)
                bal_all[g, r, y] = bal
    for n in ALL:                                  # each input in its recipe's proportion
        for g, out_per_in in RCP[n[:-1]].items():
            for y in Y:
                m.addConstr(prod[n, y] == (1.0 - loss(n, y)) * by_year(out_per_in, y) * cons[n, g, y])
    for q, shr in ROUTE_CAP.items():               # e.g. repurposing: at most a share of what retires
        (g,) = RCP[q]
        for r in R:
            for y in Y:
                m.addConstr(cons[q + (r,), g, y] <= by_year(shr, y) * retire[g, r, y])
    def share_in(v, rs, y):                        # a share, by year, or {region: share or by year}
        if isinstance(v, dict) and v and all(isinstance(k, str) for k in v):
            return by_year(v[rs[0]], y) if len(rs) == 1 and rs[0] in v else None
        return by_year(v, y)
    for q, spec in RSHARE.items():                 # a route's share of its good's output, within bounds
        g = output(q)
        scopes = [[r] for r in R] if spec.get("scope", "region") == "region" else [list(R)]
        for rs in scopes:
            for y in Y:
                mine_q = quicksum(prod[q + (r,), y] for r in rs)
                every_q = quicksum(prod[n, y] for r in rs for n in makers[g, r])
                lo = share_in(spec["min"], rs, y) if "min" in spec else None
                hi = share_in(spec["max"], rs, y) if "max" in spec else None
                if lo is not None:
                    m.addConstr(mine_q >= lo * every_q)
                if hi is not None:
                    m.addConstr(mine_q <= hi * every_q)
    for g, spec in BASE.items():                   # optional ceilings on what is bought
        for r, c in spec.get("cap", {}).items():
            for y in Y:
                m.addConstr(buy[g, r, y] <= by_year(c, y))
        if "world_cap" in spec:
            for y in Y:
                m.addConstr(quicksum(buy[g, r, y] for r in R) <= by_year(spec["world_cap"], y))
    for n, spec in RES.items():                    # extraction to date within what is extractable by then
        nodes = list(n) if n and isinstance(n[0], tuple) else [n]   # a node, or a tuple of nodes on one deposit
        if set(nodes) - prod_nodes:
            raise ValueError(f"reserves: {n!r} is not a node or a tuple of nodes")
        for y in Y:
            m.addConstr(quicksum(prod[q, v] for q in nodes for v in Y if v <= y)
                        <= reserves_available(spec, y - min(Y)))
    POOLED = {}
    for pool in pools or ():
        if len({n[-1] for n in pool}) != 1 or set(pool) - set(ALL):
            raise ValueError(f"pools: a pool's nodes must be nodes of one region, got {sorted(pool)!r}")
        for n in pool:
            POOLED[n] = pool
    for pool in pools or ():
        for y in Y:
            m.addConstr(quicksum(c * prod[n, y] for n, c in pool.items())
                        <= quicksum(c * cap[n, y] for n, c in pool.items()))
    for n in ALL:
        mc = nt["max_cap"][n[0]]
        for y in Y:
            if n not in POOLED:
                m.addConstr(prod[n, y] <= cap[n, y])
            if LUMPY:                              # whole plants; otherwise newc alone is the build
                m.addConstr(newc[n, y] <= mc * inv[n, y])
                m.addConstr(cap[n, y] <= mc * act[n, y])
        L = lead_of(n)                             # years from a build decision to capacity
        ys_n = [y for y in Y if y < min(Y) + max(L, 1) or y <= observed_to]; yw_n = [y for y in Y if y not in ys_n]
        for y in yw_n:
            m.addConstr(act[n, y] == act[n, y - 1] + inv[n, y - L])
            if CUMULATIVE:                         # starting capacity that year (it may retire) plus live builds
                life_n = BUILD_LIFE.get(n[0], 25)
                m.addConstr(cap[n, y] <= (by_year(init_cap.get(n, 0.0), y) if init_cap is not None
                                          else nt["init_capacity"][n[0]])
                            + quicksum(newc[n, v] for v in Y if v + L <= y < v + L + life_n))
            else:
                m.addConstr(cap[n, y] <= newc[n, y - L] + cap[n, y - 1])
        if n in CAP_MAX:                           # a ceiling on capacity (an expansion's potential)
            for y in Y: m.addConstr(cap[n, y] <= by_year(CAP_MAX[n], y))
        for y in ys_n:
            m.addConstr(act[n, y] == nt["init_active"])
            m.addConstr(cap[n, y] == (nt["init_capacity"][n[0]] if init_cap is None
                                      else by_year(init_cap.get(n, 0.0), y)))
    for s in STG if LUMPY else ():
        for y in Y:
            m.addConstr(quicksum(inv[n, y] for n in N[s]) <= nt["max_new_units"] * every)   # plants a stage may add, per build year
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

    if no_transship:                               # rules of origin: exports of a good <= own production of it
        for s in STG:                              # (a base good: production plus what the region buys)
            for r in R:
                for b in OUTT[s]:
                    src = [n for n in N[s] if n[-1] == r and n[-2] == b]
                    for y in Y:
                        if no_transship is not True and y < no_transship:
                            continue
                        own = quicksum(prod[n, y] for n in src)
                        if (s, b) in BASE:
                            own += buy[(s, b), r, y]
                        m.addConstr(quicksum(flow[s][k, y] for n in src for k in t_out[s][n]) <= own)
    # ---- objective
    def stage_cost(s, r):                          # costs keyed node[1:] + (year,): (ore, region, year) for mines
        if not N[s]:                               # a stage with no processes (base materials): nothing made
            return 0
        pc, vc, fc = cost[s]
        ns = [n for n in N[s] if n[-1] == r]
        return a_(s, r) * (quicksum(prod[n, y] * (pc[n[1:] + (y,)] * w(y)) for y in Y for n in ns)
                           + quicksum(newc[n, y] * (vc[n[1:] + (y,)] * w(y)) for y in Y for n in ns)
                           + quicksum(inv[n, y] * (fc[n[1:] + (y,)] * w(y)) for y in Y for n in ns))

    def import_cost(r):
        tot = 0
        for s in STG:
            for k, a in enumerate(trade[s]):
                i, j = a[-2], a[-1]
                if j != r:
                    continue
                tot += quicksum((kappa * value(s, a, y) * w(y)) * flow[s][k, y] for y in Y)   # trade cost
                tk = (s, a[-3], i, j) if (s, a[-3], i, j) in TARIFFS else (s, i, j)
                if tk in TARIFFS:
                    tot += quicksum((by_year(TARIFFS[tk], y) * value(s, a, y) * w(y)) * flow[s][k, y]
                                    for y in Y if by_year(TARIFFS[tk], y))
        return import_coef[r] * tot

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

    region_cost = {r: quicksum(stage_cost(s, r) for s in STG) + import_cost(r)
                   + quicksum((base_price(g, r, y) * w(y)) * buy[g, r, y] for g in BASE for y in Y) for r in R}

    short_cost = quicksum((short_mult * embedded(short_stage[to], to, y) * w(y)) * v
                          for (to, r, y), v in short.items())
    hold_cost = (quicksum((sp["hold_share"] * embedded(st, g, y) * w(y)) * v for (st, g, r, y), v in stock.items())
                 if stock else 0)
    if stock and sp["hold_unit"]:                  # a cost per unit held, whatever the good's value
        hold_cost = hold_cost + quicksum(sp["hold_unit"][st] * w(y) * v for (st, g, r, y), v in stock.items()
                                         if sp["hold_unit"].get(st))
    obj = quicksum(region_cost.values()) + short_cost + hold_cost
    for nodes, y, gamma in quad_cost or ():
        q = quicksum(prod[n, y] for n in nodes if (n, y) in prod)
        if q.size():
            obj = obj + (0.5 * gamma * w(y)) * q * q
    curve_x = {}                                   # cost curves: (term, block) -> units in the block
    for t, (nodes, y, blocks) in enumerate(cost_curve or ()):
        q = quicksum(prod[n, y] for n in nodes if (n, y) in prod)
        q += quicksum(buy[n[1], n[2], y] for n in nodes if n[0] == "buy" and (n[1], n[2], y) in buy)
        if not q.size():
            continue
        xs = [m.addVar(ub=GRB.INFINITY if size is None else float(size)) for size, _ in blocks]
        m.addConstr(quicksum(xs) == q)
        for k, ((_, adder), x) in enumerate(zip(blocks, xs)):
            curve_x[t, k] = x
            if adder:
                obj = obj + (float(adder) * w(y)) * x
    if served:
        obj = obj - quicksum((float(demand_curve[g, r, y][k][1]) * w(y)) * v for (g, r, y, k), v in served.items())
    h = dict(Y=Y, R=R, region_cost=region_cost, flow=flow, trade=trade, inv=inv, act=act, prod=prod,
             ALL=ALL, short=short, stock=stock, cap=cap, newc=newc,
             hold_cost=hold_cost, net=nt, N=N, cons=cons, losses=LOSS, retire=retire,
             bal_all=bal_all, short_cap_all=short_cap_all, buy=buy, value=embedded, served=served,
             curve_x=curve_x, weight=w)
    return obj, h


def results(h, obj_val, want_duals=False):
    Y, R, region_cost, inv, act, prod = (h[k] for k in ("Y", "R", "region_cost", "inv", "act", "prod"))
    nt = h["net"]
    out = dict(status=GRB.OPTIMAL, obj=obj_val, Y=Y, R=R,
               region_cost={r: region_cost[r].getValue() for r in R},
               fix_int=dict(inv={k: round(v.X) for k, v in inv.items()},
                            act={k: round(v.X) for k, v in act.items()}))
    out["short"] = {k: v.X * nt["short_gwh"].get(k[0], 1.0) for k, v in h["short"].items() if v.X > 1e-6}   # unmet
    out["stock"] = {k: v.X for k, v in h.get("stock", {}).items() if v.X > 1e-6}   # (stage, good, region, year): held
    hc = h.get("hold_cost", 0)
    out["hold_cost"] = hc.getValue() if hasattr(hc, "getValue") else 0.0
    out["bought"] = {k: v.X for k, v in h.get("buy", {}).items() if v.X > 1e-9}   # (good, region, year): base goods
    out["stage_output"] = {}                       # (stage, region, year): output, every node summed
    for (n, y), v in prod.items():
        k = (n[0], n[-1], y); out["stage_output"][k] = out["stage_output"].get(k, 0.0) + v.X
    if want_duals:
        # A good's price: the dual of its balance; with its shortage cap's dual added (dual_total), the price of the
        # demand itself, which also loosens the cap. They differ only where the cap binds (all of that demand unmet).
        cap_all = h.get("short_cap_all", {})
        out["dual"] = {k: c.Pi for k, c in h.get("bal_all", {}).items()}
        out["dual_total"] = {k: v + (cap_all[k].Pi if k in cap_all else 0.0) for k, v in out["dual"].items()}
    return out


def solve(params=None, env=None, want_duals=False, **kw):
    """Solve a network alone. kw: build() options (net= among them)."""
    m = gp.Model('critmin_net', env=env); m.Params.OutputFlag = 0
    obj, h = build(m, params, **kw)
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()
    if m.SolCount == 0:
        return dict(status=m.Status)
    return results(h, m.ObjVal, want_duals and kw.get("fix_int") is not None)


def price(goods, region='US', years=None, total=False, params=None, **kw):
    """Marginal cost of one more unit of each good demanded in `region`, by year: {(good, year): price}.

    Any good, any network (net=...): solve the MILP, fix its integers, re-solve the LP and read the duals of the
    good's balance; with total=True add its shortage cap's dual (results()' dual_total). kw: build()
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
    The cut goods stay, with no maker but what stays: zoom() makes them base goods. Their removed makers stay as
    trade-only processes (no recipe, nothing made: net["trade_only"]), since a good is traded on its makers' arcs:
    without them a cut good with no other maker, or a co-product such as recycled cobalt, could not leave the
    region it is in. "removed processes" lists them too. No solve; the copy is new.
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
    carry = {q for q in gone_p if output(q) in goods}  # kept for their trade routes
    z["processes"] = [q for q in P if q not in gone_p or q in carry]
    z["recipe"] = {q: ({} if q in carry else v) for q, v in z["recipe"].items() if q not in gone_p or q in carry}
    z["trade_only"] = sorted(set(z.get("trade_only", ())) | carry)
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
      cap    with caps=True, what each region made in the removed chain. The removed makers stay as trade routes
             (cut()), so what was made moves as it did in the whole network.
    Price and value reproduce the whole network's cost and keep its plan optimal in the zoomed one; at exactly
    the marginal price a buyer is indifferent to how much it buys, so where plans tie, the caps pin the quantities.
    With all three the zoomed network reproduces the whole one's plan (tested on a toy network,
    tests/test_lifecycle.py, and on the battery network, tests/test_solver.py). The prices hold for the case
    they came from: a change near the cut (a tariff, a demand shock) moves them, so check such a case against
    the whole network.

    kw: build() options, for both solves; solve the zoomed network with the same ones (leaving out any that name
    a removed process or good). Returns (zoomed net, info): info has the removed processes and goods, each cut
    good's price, value and cap, and the whole network's LP results.
    """
    goods = list(goods)
    nt = net
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
    for n in h["ALL"]:                             # what each region made in the removed chain
        if n[:-1] in gp_ and output(n[:-1]) in goods:
            for y in Y:
                got[output(n[:-1]), n[-1], y] += h["prod"][n, y].X
    info = dict(processes=gone_p, goods=gone_g, price={}, value={}, cap={}, whole=results(h, lp.ObjVal))
    z.setdefault("base", {})
    for g in goods:
        info["price"][g] = {r: {y: h["bal_all"][g, r, y].Pi for y in Y} for r in R}
        info["value"][g] = {y: h["value"](*g, y) for y in Y}
        info["cap"][g] = {r: {y: got[g, r, y] for y in Y} for r in R}
        z["base"][g] = {"price": info["price"][g], "value": info["value"][g]}
        if caps:
            z["base"][g]["cap"] = info["cap"][g]
    return z, info


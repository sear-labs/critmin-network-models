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
  * limits             output ceiling per (stage, region) and year, e.g. China's refining cut to a
                       share of its business-as-usual output (the refining shock)
  * cobalt             a Co add-on: NMC cathode needs refined Co, mined in DRC (stylized)

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
          ev_scale=1.0, fix_int=None, limits=None):
    """Add the network to model m; returns (objective expression, handles).

    extra_cell_demand: {(cell tech, region, year): GWh}, numbers or linear expressions.
    fix_int: integer solution from a previous solve; fixes the integers so the LP gives duals.
    """
    p = params or NOTEBOOK
    alpha, import_coef, region_share = p["alpha"], p["import_coef"], p["region_share"]
    alpha_stage, init_cap, fixed_cap = p.get("alpha_stage", {}), p.get("init_cap"), p.get("fixed_cap", {})
    adv = p.get("tariff_advalorem", {"targets": [], "rates": {}})
    kappa, no_transship = p.get("ship_value_share"), p.get("no_transship", False)
    pipeline, ramp, short_mult = p.get("pipeline", {}), p.get("ramp"), p.get("shortage_mult")
    ramp_floor = p.get("ramp_floor", {})

    def a_(s, r):                                  # her alpha, unless a stage-specific one is given
        return alpha_stage.get(s, {}).get(r, alpha[r])
    D = data(p.get("regions")); R, Y = D["R"], D["Y"]
    Y_start = [y for y in Y if y < min(Y) + 5]; Y_warm = [y for y in Y if y >= min(Y) + 5]
    tactics = tactics or {}; yields = yields or {}; limits = limits or {}
    extra = dict(extra_cell_demand or {})
    for k, v in p.get("grid_demand", {}).items():  # calibration: other grids' storage, exogenous
        extra[k] = extra.get(k, 0.0) + v

    def io(df, ins, outs):
        w = df[df.Year.isin(Y) & df.Input.isin(ins) & df.Output.isin(outs)]
        return {(r.Input, r.Output, r.Region, int(r.Year)): r.Cost for r in w.itertuples()}

    def mine_d(df):
        w = df[df.Year.isin(Y) & df.Technology.isin(MINE_T)]
        return {(r.Technology, r.Region, int(r.Year)): r.Cost for r in w.itertuples()}

    cost = {'mine': tuple(mine_d(D[f"mine_{k}"]) for k in ("prod", "var", "fixed"))}
    for s, (ins, outs) in {'proc': (MINE_T, PROC_T), 'cath': (PROC_T, CATH_T),
                           'cell': (CATH_T, CELL_T), 'pack': (CELL_T, PACK_T),
                           'rec': (PACK_T, REC_T)}.items():
        cost[s] = tuple(io(D[f"{s}_{k}"], ins, outs) for k in ("prod", "var", "fixed"))

    def share(df, techs, scale=1.0):
        w = df[df.Year.isin(Y) & df.Technology.isin(techs) & (df.Region == 'US')]
        return {(r.Technology, rg, int(r.Year)): scale * region_share[rg] * r.Demand
                for r in w.itertuples() for rg in R}

    demand_pack = share(D["pack_demand"], PACK_T, ev_scale)
    demand_rec = share(D["rec_demand"], REC_T)

    N = {'mine': [('mine', t, r) for t in MINE_T for r in R],
         'proc': [('proc', a, b, r) for a in MINE_T for b in PROC_T for r in R],
         'cath': [('cath', a, b, r) for a in PROC_T for b in CATH_T for r in R],
         'cell': [('cell', a, b, r) for a in CATH_T for b in CELL_T for r in R],
         'pack': [('pack', a, b, r) for a in CELL_T for b in PACK_T for r in R],
         'rec': [('rec', a, b, r) for a in PACK_T for b in REC_T for r in R]}
    ALL = [n for s in STAGES for n in N[s]]
    IN_T = {'proc': MINE_T, 'cath': PROC_T, 'cell': CATH_T, 'pack': CELL_T, 'rec': PACK_T}
    OUT_T = {'mine': MINE_T, 'proc': PROC_T, 'cath': CATH_T, 'cell': CELL_T, 'pack': PACK_T, 'rec': REC_T}
    trade = {'mine': [('mine', t, i, j) for t in MINE_T for i in R for j in R if i != j]}
    for s in STAGES[1:]:
        trade[s] = [(s, a, b, i, j) for a in IN_T[s] for b in OUT_T[s] for i in R for j in R if i != j]
    t_in = {s: {n: [] for n in N[s]} for s in STAGES}; t_out = {s: {n: [] for n in N[s]} for s in STAGES}
    for s in STAGES:
        for k, a in enumerate(trade[s]):
            src = (s, a[1], a[2]) if s == 'mine' else (s, a[1], a[2], a[3])
            dst = (s, a[1], a[3]) if s == 'mine' else (s, a[1], a[2], a[4])
            t_out[s][src].append(k); t_in[s][dst].append(k)

    flow = {s: {(k, y): m.addVar() for k in range(len(trade[s])) for y in Y} for s in STAGES}
    vt = GRB.CONTINUOUS if fix_int is not None else GRB.INTEGER
    prod = {(n, y): m.addVar() for n in ALL for y in Y}
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
    cons = {s: {(a, b, r, y): m.addVar() for a in IN_T[s] for b in OUT_T[s] for r in R for y in Y}
            for s in STAGES[1:]}
    m.update()

    def fin(s, n, y):
        return quicksum(flow[s][k, y] for k in t_in[s][n])

    def fout(s, n, y):
        return quicksum(flow[s][k, y] for k in t_out[s][n])

    for tm in MINE_T:
        for r in R:
            for y in Y:
                n = ('mine', tm, r)
                m.addConstr(prod[n, y] + fin('mine', n, y) == fout('mine', n, y)
                            + quicksum(cons['proc'][tm, tp, r, y] for tp in PROC_T))
    nxt = {'proc': 'cath', 'cath': 'cell', 'cell': 'pack'}
    cell_bal, short_cap = {}, {}
    # unmet demand, where it is consumed: each region's grid cells (its storage, and ERCOT's) and its packs,
    # each at most that demand. A shortfall cannot become cells that are packed and shipped elsewhere.
    # Not in the last year: capacity for it serves one year, so the horizon's end would read as a shortage.
    short = ({(to, r, y): m.addVar() for to in CELL_T + PACK_T for r in R for y in Y if y < max(Y)}
             if short_mult else {})
    for s in ('proc', 'cath', 'cell'):
        for to in OUT_T[s]:
            for r in R:
                for y in Y:
                    lhs = (quicksum(prod[(s, ti, to, r), y] for ti in IN_T[s])
                           + quicksum(flow[s][k, y] for ti in IN_T[s] for k in t_in[s][(s, ti, to, r)]))
                    rhs = (quicksum(flow[s][k, y] for ti in IN_T[s] for k in t_out[s][(s, ti, to, r)])
                           + quicksum(cons[nxt[s]][to, tn, r, y] for tn in OUT_T[nxt[s]]))
                    if s == 'cell':
                        rhs += extra.get((to, r, y), 0.0)
                        if (to, r, y) in short:    # grid cells demanded but not supplied: unmet, at a penalty
                            lhs += short[to, r, y]
                            short_cap[to, r, y] = m.addConstr(short[to, r, y] <= extra.get((to, r, y), 0.0))
                        cell_bal[to, r, y] = m.addConstr(lhs == rhs)
                    else:
                        m.addConstr(lhs == rhs)
    for to in PACK_T:
        for r in R:
            for y in Y:
                sp = 0.0
                if (to, r, y) in short:                    # packs demanded but not supplied: unmet, at a penalty
                    sp = short[to, r, y]
                    m.addConstr(sp <= demand_pack[(to, r, y)])
                m.addConstr(quicksum(prod[('pack', ti, to, r), y] for ti in CELL_T) + sp
                            + quicksum(flow['pack'][k, y] for ti in CELL_T for k in t_in['pack'][('pack', ti, to, r)])
                            == quicksum(flow['pack'][k, y] for ti in CELL_T for k in t_out['pack'][('pack', ti, to, r)])
                            + demand_pack[(to, r, y)]
                            + quicksum(cons['rec'][to, tg, r, y] for tg in REC_T))
    for tg in REC_T:
        for r in R:
            for y in Y:
                m.addConstr(quicksum(prod[('rec', tk, tg, r), y] for tk in PACK_T)
                            + quicksum(flow['rec'][k, y] for tk in PACK_T for k in t_in['rec'][('rec', tk, tg, r)])
                            == quicksum(flow['rec'][k, y] for tk in PACK_T for k in t_out['rec'][('rec', tk, tg, r)])
                            + demand_rec[(tg, r, y)])
    for s in STAGES[1:]:
        for a in IN_T[s]:
            for b in OUT_T[s]:
                for r in R:
                    for y in Y:
                        m.addConstr(prod[(s, a, b, r), y] == RATIO[s][b] * cons[s][a, b, r, y])
    for tg in REC_T:
        for y in Y:
            m.addConstr(quicksum(prod[('rec', tk, tg, r), y] for tk in PACK_T for r in R)
                        == quicksum(demand_rec[(tg, r, y)] for r in R))
    for n in ALL:
        mc = MAX_CAP[n[0]]
        for y in Y:
            yl = yields.get((n[1], n[2]), 1.0) if n[0] == 'mine' else 1.0
            m.addConstr(prod[n, y] <= yl * cap[n, y])
            m.addConstr(newc[n, y] <= mc * inv[n, y])
            m.addConstr(cap[n, y] <= mc * act[n, y])
        for y in Y_warm:
            m.addConstr(act[n, y] == act[n, y - 1] + inv[n, y - 5])
            m.addConstr(cap[n, y] <= newc[n, y - 5] + cap[n, y - 1])
        if n in fixed_cap:                         # calibration: capacity fixed (a number, or by year)
            for y in Y: m.addConstr(cap[n, y] == by_year(fixed_cap[n], y))
        for y in Y_start:
            m.addConstr(act[n, y] == INIT_ACTIVE)
            if n not in fixed_cap:
                m.addConstr(cap[n, y] == (INIT_CAPACITY[n[0]] if init_cap is None else by_year(init_cap.get(n, 0.0), y)))
    for s in STAGES:
        for y in Y:
            m.addConstr(quicksum(inv[n, y] for n in N[s]) <= MAX_NEW_UNITS * every)   # her yearly limit, per build year
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

    # ---- LLNL-TR-859392 levers on CHN -> US arcs
    # Targets: the US alone, or the US and its allies (ALLY; AUS in her three regions). LLNL-TR-859392
    # Finding 3 is that coercion must hit both together; a lever on CHN->US alone is routed around.
    targets = set(tactics.get("targets", ["US"]))
    y_from = tactics.get("from_year", min(Y))      # closures act from this year on
    tariff = tactics.get("tariff", {})            # {stage: tau}: x(1 + tau) on shipping; calibrated, tau of value

    def coerced(i, j):
        return i == 'CHN' and j in targets

    for s in STAGES:
        for k, a in enumerate(trade[s]):
            i, j = (a[2], a[3]) if s == 'mine' else (a[3], a[4])
            if coerced(i, j) and (tactics.get("friendshore") or s in tactics.get("embargo", ())):
                for y in Y:
                    if y >= y_from: flow[s][k, y].ub = 0.0
    if no_transship:                               # calibration: exports of a good <= own production of it
        for s in STAGES:
            for r in R:
                for b in OUT_T[s]:
                    src = [n for n in N[s] if n[-1] == r and (n[1] if s == 'mine' else n[2]) == b]
                    for y in Y:
                        m.addConstr(quicksum(flow[s][k, y] for n in src for k in t_out[s][n])
                                    <= quicksum(prod[n, y] for n in src))
    for s, q in tactics.get("quota", {}).items():   # {stage: units per year, each target}
        for j in targets:
            for y in Y:
                m.addConstr(quicksum(flow[s][k, y] for k, a in enumerate(trade[s])
                                     if a[-2:] == ('CHN', j)) <= q)

    # ---- objective, exactly as in her notebook (plus the hooks)
    def stage_cost(s, r):
        pc, vc, fc = cost[s]
        if s == 'mine':
            return a_(s, r) * (quicksum(prod[('mine', t, r), y] * pc[(t, r, y)] / yields.get((t, r), 1.0)
                                        for y in Y for t in MINE_T)
                               + quicksum(newc[('mine', t, r), y] * vc[(t, r, y)] for y in Y for t in MINE_T)
                               + quicksum(inv[('mine', t, r), y] * fc[(t, r, y)] for y in Y for t in MINE_T))
        return a_(s, r) * (quicksum(prod[(s, a, b, r), y] * pc[(a, b, r, y)] for y in Y for a in IN_T[s] for b in OUT_T[s])
                           + quicksum(newc[(s, a, b, r), y] * vc[(a, b, r, y)] for y in Y for a in IN_T[s] for b in OUT_T[s])
                           + quicksum(inv[(s, a, b, r), y] * fc[(a, b, r, y)] for y in Y for a in IN_T[s] for b in OUT_T[s]))

    def import_cost(r):
        tot = 0
        for s in STAGES:
            for k, a in enumerate(trade[s]):
                i, j = (a[2], a[3]) if s == 'mine' else (a[3], a[4])
                if j != r:
                    continue
                tau = tariff.get(s, 0.0) if coerced(i, j) else 0.0
                if kappa is None:                  # hers: tariff multiplies the shipping cost
                    tot += quicksum((1.0 + tau) * SHIP_COST[r] * flow[s][k, y] for y in Y)
                else:                              # calibrated: trade cost and tariff, shares of value
                    tot += quicksum((kappa + tau) * value(s, a, y) * flow[s][k, y] for y in Y)
        return import_coef[r] * tot + advalorem_cost(r)

    PREV = {'proc': 'mine', 'cath': 'proc', 'cell': 'cath', 'pack': 'cell'}
    cv = {}

    def embedded(s, b, y):                         # China's unit cost of good b, with everything inside it
        if (s, b, y) not in cv:
            if s == 'mine':
                cv[s, b, y] = cost['mine'][0][(b, 'CHN', y)]
            elif s == 'rec':                       # recycled chemicals: the recycling stage only
                cv[s, b, y] = min(cost['rec'][0][(a, b, 'CHN', y)] for a in IN_T['rec'])
            else:
                cv[s, b, y] = min(cost[s][0][(a, b, 'CHN', y)] + embedded(PREV[s], a, y) / RATIO[s][b]
                                  for a in IN_T[s])
        return cv[s, b, y]

    def value(s, a, y):                            # the traded good's embedded value (at China's cost)
        return embedded(s, a[1] if s == 'mine' else a[2], y)

    def advalorem_cost(r):                         # tariff on the goods' embedded value
        if r not in adv["targets"]:
            return 0
        return quicksum(adv["rates"][s] * value(s, a, y) * flow[s][k, y]
                        for s in adv["rates"] for k, a in enumerate(trade[s]) if a[3] == 'CHN' and a[4] == r
                        for y in Y)

    region_cost = {r: quicksum(stage_cost(s, r) for s in STAGES) + import_cost(r) for r in R}

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
    short_cost = quicksum(short_by_r.get(r, short_mult) * embedded('cell' if to in CELL_T else 'pack', to, y) * v
                          for (to, r, y), v in short.items())
    obj = quicksum(region_cost.values()) + co_cost + short_cost
    h = dict(Y=Y, R=R, region_cost=region_cost, flow=flow, trade=trade, inv=inv, act=act, prod=prod,
             ALL=ALL, cell_bal=cell_bal, short=short, short_cap=short_cap, over=over)
    return obj, h


def results(h, obj_val, want_duals=False):
    Y, R, region_cost, flow, trade, inv, act, prod, ALL, cell_bal = (h[k] for k in
        ("Y", "R", "region_cost", "flow", "trade", "inv", "act", "prod", "ALL", "cell_bal"))
    out = dict(status=GRB.OPTIMAL, obj=obj_val, Y=Y, R=R,
               region_cost={r: region_cost[r].getValue() for r in R},
               us_imports=sum(flow[s][k, y].X for s in STAGES for k, a in enumerate(trade[s])
                              for y in Y if a[-1] == 'US'),
               fix_int=dict(inv={k: round(v.X) for k, v in inv.items()},
                            act={k: round(v.X) for k, v in act.items()}))
    # production share by region, cell stage, final year (a compact "where it's made" summary)
    yl = max(Y)
    cell_by_r = {r: sum(prod[('cell', a, b, r), yl].X for a in CATH_T for b in CELL_T) for r in R}
    tot = sum(cell_by_r.values()) or 1.0
    out["cell_share"] = {r: v / tot for r, v in cell_by_r.items()}
    out["short"] = {k: v.X * SHORT_GWH[k[0]] for k, v in h["short"].items() if v.X > 1e-6}   # unmet, cell GWh
    out["beyond"] = {k: e.getValue() - c for k, (e, c) in h["over"].items() if e.getValue() - c > 1e-6}  # past IEA's path
    out["stage_output"] = {}                       # (stage, region, year): output, every node summed
    for (n, y), v in prod.items():
        k = (n[0], n[-1], y); out["stage_output"][k] = out["stage_output"].get(k, 0.0) + v.X
    # where US-bound cells are made over the coupled years, by chemistry
    out["cell_prod"] = {(b, r): sum(prod[('cell', a, b, r), y].X for a in CATH_T for y in COUPLED_YEARS)
                        for b in CELL_T for r in R}
    # binding pattern: which (stage, region) nodes invest anywhere, and which arcs carry flow
    out["pattern"] = frozenset([f"inv:{n[0]}:{n[-1]}" for n in ALL if any(inv[n, y].X > 0.5 for y in Y)]
                               + [f"arc:{s}:{a[-2]}>{a[-1]}" for s in STAGES for k, a in enumerate(trade[s])
                                  if any(flow[s][k, y].X > 1e-3 for y in Y)])
    if want_duals:
        out["cell_dual"] = {(to, y): cell_bal[to, 'US', y].Pi for to in CELL_T for y in Y}
        # The price of extra US grid-cell demand: it is on the right of the cell balance AND caps the shortage
        # (short <= grid demand), so its price is the sum of both duals. They differ only where the cap binds:
        # every US grid cell of that chemistry unmet that year. See scripts/dual_diagnosis.py.
        cap = h.get("short_cap", {})
        out["cell_dual_total"] = {(to, y): cell_bal[to, 'US', y].Pi + (cap[to, 'US', y].Pi if (to, 'US', y) in cap else 0.0)
                                  for to in CELL_T for y in Y}
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

"""The battery network (battery.py) projected to 2040: demand from IEA's outlooks, capacity built where it is cheapest
once each region's lead time allows, and an onshoring scenario. PRELIMINARY.

2023 and 2024 are battery.py's observed years, calibrated to the observed regional shares (battery.calibrate()). From
2025 nothing is imposed: the calibration's costs apply to 2023 and 2024 only, and where each stage is made after that
is the model's decision (Jones, 2026-11-23), at the sourced operating costs (battery.costs(), 2024's held), the capital
costs below and the lead times below. Capacity observed in 2024 stays (no plant retires before 2040); new capacity
is built in any amount and serves from its decision year plus its region's lead time; decisions start in 2023, so
what came online in 2025 and 2026 is the model's choice too (it was decided before them), while capacity in 2023 and
2024 stays as observed.

Data: data/battery_horizon/ (one row per number with its source; ids D, P and T; verification.csv is an independent
check of 188 rows against the sources, 4 corrected, the corrections applied in the rows).

Demand (load()), GWh of lithium-ion cells placed, by end use, chemistry and region:
  EVs     IEA Global EV Outlook 2026, Figure 9.16: world EV battery deployment by mode, 2025 (D0-D3), and 2030 and
          2035 in the stated policies scenario (STEPS, D8-D11, D16-D19) or current policies (CPS, D4-D7, D12-D15);
          2040 continues 2030-35's increase (IEA gives no 2040 EV deployment; its 2040 lithium demand, D259, is the
          check). By region at the figure's shares (D20-D44), as battery.load() maps them: China; the EU and other
          advanced economies -> ALLY; the US; other emerging economies -> ROW. 2040 at 2035's shares.
          Chemistry: each region's 2025 mix (D49-D60), moved as IEA's world mix for electric cars moves (D279-D294:
          high-nickel falls, high-manganese and sodium-ion rise, LFP stays at 54%), high-manganese counted as
          low-nickel NMC. Sodium-ion uses no lithium and is not in this network: its share is left out.
  Storage 2025: at least 15% of lithium-ion deployment against EVs' 70% (D383, D384), so EV GWh x 15/70; 2030: IEA's
          lithium-ion additions (D343, D344: 92% LFP); 2035 and 2040: IEA's installed power (D297, D298; CPS D295,
          D296) added each year at STORAGE_HOURS, sodium-ion and other chemistries left out at 2030's share, plus
          the replacement of what retires (IEA's installed power is net; retirement by battery.LIFECYCLE). By
          region at IEA's 2030 installed shares (D301-D304) and its 2030-35 additions (D305-D308).
  Electronics and other uses: held at 2024 (no projection found). The minerals' other uses: held at 2024.
  Between the anchor years, straight lines. Manufacturing scrap falls from 10% (2023) to 6% in 2030 and stays (IEA
  GEVO 2024, as battery.LOSSES).

Building (CAPEX, LEAD): CAPEX is per unit of yearly capacity, annualised at CRF (8% over 25 years, IEA's convention for
clean-technology plants, T89) for each year a plant serves to 2040; undiscounted, as the model's operating costs are.
Recycling, shredding and the end uses have open capacity, as in battery.py. Lead times differ by region (Jones,
2026-11-23: US and allied long, China short, the rest of the world shorter still for mines).

Scenarios (run()): "cost" (the model's decision) and "onshore": the US and its allies make at least a floor share of
their own demand at each processing and manufacturing stage (refining, precursor, anode, cathode, cells): 40% from
2030 (the EU's 2030 benchmarks: the Critical Raw Materials Act for processing, the Net-Zero Industry Act for
manufacturing), rising to 60% in 2040 (ours). Mines have no floor: they go where they are cheapest.
"""
import pandas as pd

from . import battery as B
from . import network as N

YEARS = list(range(2023, 2041))
DATA = N.RAW / "battery_horizon"
RATE, LIFE_YEARS = 0.08, 25
CRF = RATE * (1 + RATE) ** LIFE_YEARS / ((1 + RATE) ** LIFE_YEARS - 1)
STORAGE_HOURS = 3.0          # IEA 2030: about 382 GWh added (D343-D346) on about 130 GW (D318, D320)
CELL_SCRAP = {2023: 0.10, 2024: 0.094, 2030: 0.06}       # battery.LOSSES, then IEA GEVO 2024's 6% in 2030, held
US_ALLY = ('US', 'ALLY')
ONSHORE = {2030: 0.40, 2040: 0.60}                      # floor on US+ALLY's share of their own demand, straight between

# Capital cost per unit of yearly capacity: USD per kg (M USD per kt) or per kWh (M USD per GWh); SPC as ROW where
# not given. Sources: battery_costs/sources_upstream.csv (U) and sources_midstream.csv (M); battery_horizon's
# pipeline_capex.csv (P).
_ACTM = {  # IEA Advancing Clean Technology Manufacturing (2024), greenfield plants, USD per kWh a year (P197-P208)
    'cath': {'CHN': 9.4, 'ROW': 11.9, 'ALLY': 17.0, 'US': 17.0},
    'anode': {'CHN': 3.8, 'ROW': 4.8, 'ALLY': 6.8, 'US': 6.8},
    'cell': {'CHN': 60.0, 'ROW': 74.3, 'ALLY': 98.9, 'US': 106.8}}
PCAM_TO_CAM = 8982.4 / 19162.5     # pCAM over cathode plant capex per tonne, China (Stanford GSB model, M2, M17; the
                                   # same 0.469 in the US, M5/M20, and Korea, M11/M26)
FEPO4_CAPEX = (0.88 + 2.26) / 2    # USD per kg FePO4 a year, China: Lopal 150 kt (P213) and Yunti 500 kt (P214)


def capex(intensity):
    """{(key, region): capital cost per unit of yearly capacity} for battery.network(capex=). intensity: kg per kWh
    (the anode's per-kWh cost is per kg of graphite at the chemistries' mean graphite intensity)."""
    hard, top = 55.0, 28.0         # lithium hard rock, IEA GCMO 2025: rest of world (U25), top producer Australia (U24)
    c = {('mine_Li', r): hard for r in B.REGIONS}                # (brine costs more per capacity: U7, U8)
    c['mine_Li', 'ALLY'] = top
    for r in B.REGIONS:
        c['refine_Li', r] = 60.0 if r == 'CHN' else 103.0       # IEA: top refiner China (U90), the rest (U91)
        c['mine_Ni', r] = 38.5 if r == 'ROW' else 68.5          # IEA: top producer Indonesia (U50), the rest (U34)
        c['refine_Ni', r] = 37.5 if r == 'ROW' else 56.0        # IEA: top refiner Indonesia (U93), the rest (U92)
        c['mine_Co', r] = 40.94                                 # a primary cobalt mine, US (U55); one source
        c['refine_Co', r] = 13.156                              # hydroxide to sulphate, Kwinana (U105); one source
    c.update({('mine_graphite', 'CHN'): 2.1125, ('mine_graphite', 'ROW'): 2.1125,       # Tanzania (U62)
              ('mine_graphite', 'SPC'): 2.1125, ('mine_graphite', 'ALLY'): 3.5561,      # Canada (U58)
              ('mine_graphite', 'US'): 6.7669})                                         # Alaska (U71)
    mn = {'CHN': 3.5676, 'US': 13.6954, 'ALLY': 16.1816}        # U114, U117, U111 (whole site, tailings included)
    mn['ROW'] = mn['SPC'] = (mn['CHN'] + mn['US']) / 2          # as battery.costs() fills the rest of the world
    c.update({('refine_Mn', r): v for r, v in mn.items()})
    g = sum(i['graphite'] for i in intensity.values()) / len(intensity)
    fepo4 = B.FEPO4_PER_LI * intensity['lfp']['Li']             # kg FePO4 per kWh
    for r in B.REGIONS:
        a = r if r in _ACTM['cell'] else 'ROW'
        c['cell', r] = _ACTM['cell'][a]
        c['cath', r] = _ACTM['cath'][a]
        c['anode', r] = _ACTM['anode'][a] / g
        c['pcam_nmc', r] = PCAM_TO_CAM * _ACTM['cath'][a]
        c['pcam_lfp', r] = FEPO4_CAPEX * fepo4 * _ACTM['cath'][a] / _ACTM['cath']['CHN']
    return c


# Years from a build decision to capacity, by stage and region (lead_times.csv, T).
LEAD = {
    'mine': {'CHN': 5,             # T48: equity (2018) to first concentrate (2023), a Chinese miner abroad
             'ROW': 2,             # T50, T51, T54: 9-18 months to build a concentrator or ponds (Africa, Argentina)
             'SPC': 3,             # T46, T47: 2.5-5 years in the DRC's copper-cobalt belt
             'US': 10,             # T31, T33: 7-10 years to permit, then building (T38: 2-3)
             'ALLY': 5},           # T32, T34: 2-3 years to permit, plus T38's 2-3 to build
    'refine': {'CHN': 2,           # T61: a hydroxide plant, announcement to commissioning
               'ROW': 2, 'SPC': 2,  # T55, T56: 18-28 months (nickel sulphate, HPAL)
               'US': 5,            # ours: between T63's 4 (a US pCAM plant) and the allies' 6
               'ALLY': 6},         # T60: a hydroxide refinery in Australia, announcement to first output
    'pcam': {'CHN': 1, 'ROW': 2, 'SPC': 2, 'US': 4, 'ALLY': 4},
    'cath': {'CHN': 1,             # T64, T65: 8 months, groundbreaking to commissioning
             'ROW': 2, 'SPC': 2,   # T80, T81: 1-3 years for battery and component plants (IEA)
             'US': 4,              # T63: a US pCAM plant, groundbreaking to planned operation
             'ALLY': 4},           # T62: a European pCAM plant, still without a final permit after 4 years
    'anode': {'CHN': 2,            # T68: 19 months, construction to production
              'ROW': 2, 'SPC': 2, 'US': 3, 'ALLY': 3},    # ours, between components' and refining's
    'cell': {'CHN': 1,             # T70, T71: 6-18 months
             'ROW': 2, 'SPC': 2,   # T80, T81
             'US': 3,              # T75, T77, T78: about 3 years
             'ALLY': 4}}           # T72, T73, T74: 3.2-4.1 years


def _rows():
    d = pd.read_csv(DATA / "demand.csv", dtype=str).set_index("id")

    def val(i):
        return float(str(d.loc[i, "value"]).lstrip("<>~"))
    return val


def _line(anchors, y):
    """Straight lines between {year: value} anchors; held after the last."""
    ks = sorted(anchors)
    if y <= ks[0]:
        return anchors[ks[0]]
    if y >= ks[-1]:
        return anchors[ks[-1]]
    lo = max(k for k in ks if k <= y); hi = min(k for k in ks if k > y)
    return anchors[lo] + (anchors[hi] - anchors[lo]) * (y - lo) / (hi - lo)


def load(scenario="STEPS"):
    """battery.load()'s inputs with demand and the minerals' other uses to 2040 (the module docstring says how)."""
    if scenario not in ("STEPS", "CPS"):
        raise ValueError(f"scenario: 'STEPS' or 'CPS', got {scenario!r}")
    inp = B.load()
    val = _rows()
    assert (val("D0"), val("D11"), val("D16"), val("D20"), val("D51"), val("D282"), val("D344"), val("D298")) == \
        (1.06, 0.277, 3.94, 60.1, 81.2, 1.0, 313.0, 2327.0), "demand.csv ids have moved"
    stp = scenario == "STEPS"
    later = [y for y in YEARS if y not in B.YEARS]
    D = dict(inp["demand"])

    # ---- EVs: world total (TWh), regional shares, chemistry
    tot = {2025: sum(val(f"D{i}") for i in range(0, 4)),
           2030: sum(val(f"D{i}") for i in (range(8, 12) if stp else range(4, 8))),
           2035: sum(val(f"D{i}") for i in (range(16, 20) if stp else range(12, 16)))}
    tot[2040] = 2 * tot[2035] - tot[2030]
    reg = ['CHN', 'ALLY', 'US', 'ROW', 'ALLY']              # China, EU, US, other EMDEs, other AEs (as battery.load())
    first = {2025: 20, 2030: 30 if stp else 25, 2035: 40 if stp else 35}
    share = {}
    for y, i0 in first.items():
        s = {}
        for k, r in enumerate(reg):
            s[r] = s.get(r, 0.0) + val(f"D{i0 + k}")
        t = sum(s.values())
        share[y] = {r: v / t for r, v in s.items()}
    share[2040] = share[2035]
    mix25 = {}
    for r, i0 in (('CHN', 49), ('ROW', 52), ('ALLY', 55), ('US', 58)):   # low-nickel, mid/high-nickel, LFP
        mix25[r] = {'nmc_lo': val(f"D{i0}"), 'nmc_hi': val(f"D{i0 + 1}"), 'lfp': val(f"D{i0 + 2}")}
    world = {2024: dict(lo=val("D279"), hi=val("D280"), lfp=val("D281"), mn=0.0, na=0.0),
             2030: dict(lo=val("D282"), hi=val("D283"), mn=val("D284"), lfp=val("D285"), na=val("D286")),
             2035: dict(lo=0.0, hi=val("D287"), mn=val("D288"), lfp=val("D289"), na=val("D290")),
             2040: dict(lo=0.0, hi=val("D291"), mn=val("D292"), lfp=val("D293"), na=val("D294"))}

    def wsh(k, y):
        return _line({a: v[k] / sum(v.values()) for a, v in world.items()}, y)

    def ev_mix(r, y):                                    # the region's 2025 mix, moved as the world's moves
        f = {'nmc_hi': wsh('hi', y) / wsh('hi', 2025), 'lfp': wsh('lfp', y) / wsh('lfp', 2025),
             'nmc_lo': (wsh('lo', y) + wsh('mn', y)) / (wsh('lo', 2025) + wsh('mn', 2025))}
        m = {c: mix25[r][c] * f[c] for c in f}
        t = sum(m.values())
        return {c: v / t * (1.0 - wsh('na', y)) for c, v in m.items()}   # sodium-ion left out
    for y in later:
        T = 1000.0 * _line(tot, y)
        for r, s in _line_d(share, y).items():
            for c, f in ev_mix(r if r in mix25 else 'ROW', y).items():
                D['ev', c, r, y] = T * s * f

    # ---- storage: lithium-ion GWh a year
    ev25 = 1000.0 * tot[2025]
    st_li = {2024: sum(v for (u, c, r, y), v in inp["demand"].items() if u == 'storage' and y == 2024),
             2025: ev25 * val("D384") / val("D383"),
             2030: val("D343") + val("D344")}
    li_frac = (val("D343") + val("D344")) / sum(val(f"D{i}") for i in range(343, 347))
    gw = {2030: sum(val(f"D{i}") for i in range(301, 305)),
          2035: val("D297") if stp else val("D295"), 2040: val("D298") if stp else val("D296")}
    spec = B.LIFECYCLE["life"]["storage"]
    placed = {}
    for (u, c, r, y), v in list(inp["history"].items()) + list(inp["demand"].items()):
        if u == 'storage':
            placed[y] = placed.get(y, 0.0) + v

    def replaced(y, path):                               # what retires in y of what was placed before
        return sum(v * N.retire_share(spec, y - a) for a, v in path.items() if a < y)
    anchors = dict(st_li)
    for _ in range(5):                                   # 2035's and 2040's replacements depend on the path to them
        path = {**placed, **{y: _line(anchors, y) for y in later}}
        for y, y0 in ((2035, 2030), (2040, 2035)):
            anchors[y] = STORAGE_HOURS * (gw[y] - gw[y0]) / (y - y0) * li_frac + replaced(y, path)
    st_share = {2024: {r: sum(v for (u, c, rr, y), v in inp["demand"].items() if u == 'storage' and y == 2024
                              and rr == r) / st_li[2024] for r in B.REGIONS}}
    for y, i0, prev in ((2030, 301, None), (2035, 305, 301)):
        s = {}
        for k, r in enumerate(['CHN', 'US', 'ALLY', 'ROW']):
            s[r] = val(f"D{i0 + k}") - (val(f"D{prev + k}") if prev else 0.0)
        t = sum(s.values())
        st_share[y] = {r: s.get(r, 0.0) / t for r in B.REGIONS}
    lfp = val("D344") / (val("D343") + val("D344"))
    for y in later:
        T = _line(anchors, y)
        for r, s in _line_d(st_share, y).items():
            D['storage', 'lfp', r, y] = T * s * lfp
            D['storage', 'nmc_hi', r, y] = T * s * (1 - lfp)

    # ---- electronics, other applications, and the minerals' other uses: held at 2024
    for (u, c, r, y), v in inp["demand"].items():
        if u in ('electronics', 'other') and y == 2024:
            for yy in later:
                D[u, c, r, yy] = v
    other = dict(inp["other"])
    for (g, r, y), v in inp["other"].items():
        if y == 2024:
            for yy in later:
                other[g, r, yy] = v
    losses = dict(inp["losses"])
    losses['cell'] = {y: _line(CELL_SCRAP, y) for y in YEARS}
    return dict(inp, demand=D, other=other, losses=losses, scenario=scenario,
                storage_anchors=anchors, ev_total=tot)


def _line_d(anchors, y):
    """_line for {year: {key: value}}."""
    keys = set().union(*anchors.values())
    return {k: _line({a: v.get(k, 0.0) for a, v in anchors.items()}, y) for k in keys}


def network(inputs, quad=None, **kw):
    """(net, params, build options, need) for the horizon: battery.network() over YEARS with CAPEX and LEAD. The
    anode's 2024 capacity, which battery.py lets either route use whole (with a ceiling on the two), is split
    between the routes in later years as the observed (calibrated) 2024 solve uses them, so it is not counted twice.
    kw: battery.network()'s overrides."""
    import gurobipy as gp
    from gurobipy import GRB
    net, params, bkw, need = B.network(inputs, quad=quad, years=YEARS, capex=capex(inputs["intensity"]), lead=LEAD,
                                       crf=CRF, **kw)
    base = {k: v for k, v in inputs.items()}
    base["demand"] = {k: v for k, v in inputs["demand"].items() if k[3] in B.YEARS}
    base["other"] = {k: v for k, v in inputs["other"].items() if k[2] in B.YEARS}
    bn, bp, bb, _ = B.network(base, quad=quad, **kw)
    m = gp.Model(); m.Params.OutputFlag = 0
    obj, h = N.build(m, bp, net=bn, **bb)
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()
    y0 = max(B.YEARS)
    for r in B.REGIONS:
        nodes = [p + (r,) for p in net["processes"] if p[0] == 'anode']
        out = {n: h["prod"][n, y0].X for n in nodes}
        t = sum(out.values())
        cap = bb["limits"][('anode', r)][y0]
        for n in nodes:
            f = out[n] / t if t > 1e-9 else 1.0 / len(nodes)
            for y in YEARS:
                if y not in B.YEARS:
                    params["init_cap"][n][y] = cap * f
    return net, params, bkw, need


def onshore_floor(m, h, inputs, floor=None):
    """The onshoring scenario's constraints on model m (build()'s handles h): at each processing and manufacturing
    group (battery._group(): refining by metal, precursor and cathode by chemistry, anode, cells), the US and allies
    make at least floor(y) x their share of the world's cells placed x the world's output. floor: {year: share}
    anchors (ONSHORE by default), none before the first."""
    from gurobipy import quicksum
    fl = ONSHORE if floor is None else floor
    D = inputs["demand"]
    out = {}
    for y in YEARS:
        if y < min(fl):
            continue
        world = sum(v for k, v in D.items() if k[3] == y)
        mine = sum(v for k, v in D.items() if k[3] == y and k[2] in US_ALLY)
        f = _line(fl, y) * mine / world
        groups = {}
        for (n, yy), v in h["prod"].items():
            g = B._group(n)
            if yy == y and g and g[0] != 'mine':
                groups.setdefault(g, []).append((n, v))
        for g, nv in groups.items():
            out[g, y] = m.addConstr(quicksum(v for n, v in nv if n[-1] in US_ALLY) >= f * quicksum(v for _, v in nv))
    return out


def run(scenario="cost", demand="STEPS", env=None, inputs=None, cal=None, floor=None, **kw):
    """Solve the horizon and summarise. scenario: "cost" or "onshore"; demand: "STEPS" or "CPS". cal: battery.calibrate()
    of the observed years (computed if not given; the same in every scenario). Returns dict(status, obj, prod and cap
    {(stage, key, region, year): units}, built {(stage, key, region, year online): units}, short, need, floors' duals)."""
    import gurobipy as gp
    from gurobipy import GRB
    if scenario not in ("cost", "onshore"):
        raise ValueError(f"scenario: 'cost' or 'onshore', got {scenario!r}")
    inputs = inputs or load(demand)
    cal = cal or B.calibrate(None, env)
    net, params, bkw, need = network(inputs, quad=cal["quad"], **kw)
    m = gp.Model(env=env); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **bkw)
    fl = onshore_floor(m, h, inputs, floor) if scenario == "onshore" else {}
    m.Params.Method = 1                            # dual simplex: barrier stalls on the open capacities (1e9) beside
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()   # retirement tails (1e-12); simplex solves it in a second
    if m.Status != GRB.OPTIMAL:
        return dict(status=m.Status)
    out = dict(status=m.Status, obj=m.ObjVal, need=need, prod={}, cap={}, built={},
               short={k: v.X for k, v in h["short"].items() if v.X > 1e-6},
               floor={k: c.Pi for k, c in fl.items()} if m.IsMIP == 0 else {})
    for (n, y), v in h["prod"].items():
        g = B._group(n)
        if g:
            k = g + (n[-1], y)
            out["prod"][k] = out["prod"].get(k, 0.0) + v.X
            out["cap"][k] = out["cap"].get(k, 0.0) + h["cap"][n, y].X
    for (n, y), v in h["newc"].items():
        g = B._group(n)
        L = B._lead(LEAD, n[0], n[-1])
        if g and v.X > 1e-6 and max(B.YEARS) < y + L <= max(YEARS):
            k = g + (n[-1], y + L)
            out["built"][k] = out["built"].get(k, 0.0) + v.X
    return out

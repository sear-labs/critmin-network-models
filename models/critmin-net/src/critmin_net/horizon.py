"""The battery network (battery.py) projected to 2040: demand from IEA's outlooks, capacity built where it is cheapest
once each region's lead time allows, and an onshoring scenario. PRELIMINARY.

0.12.0: every market is a curve (curves.py; KNOBS turns them). Every stage in every region and year has a supply
(cost) curve anchored at its observed output, growing with the world's need (plus an entry share), with known
operations below the anchor at their own costs (OPERATIONS); every end use, the minerals' other uses and the base
materials have demand or supply curves; operating and capital costs move on low, mid or high cost curves over time
(COST_PATHS). 2023 and 2024 are battery.py's observed years: calibrate() sets each curve's offset there so the network
makes the observed regional shares; after 2024 the offsets are dropped by default (KNOBS["wedge_carry"]) and where
each stage is made is the model's decision (Jones, 2026-11-23). Costs are discounted (8%). Existing capacity is
nameplate where known (cells) and retires (mines and refining, KNOBS["retire"]); new capacity is built in any amount,
serves from its decision year plus its region's lead time for 25 years, and is shared where plants are (anode routes,
cell chemistries, NMC precursor and cathode, hydromet). Decisions start in 2023, so what came online in 2025 and 2026
is the model's choice too, while capacity in 2023 and 2024 stays as observed. Chemistry is a choice within a band of
IEA's mix by region; cobalt is mined as a co-product of nickel (the DRC's copper-cobalt mines primary). Shredding is
open but costed; hydromet starts from IEA's 2023 capacity and is built only where it pays. policy.py: tariffs and
45X, always in the observed years, after them by scenario. audit() lists what is still fixed or flat.

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
clean-technology plants, T89) for each year a plant serves to 2040, and discounted as every cost is. Shredding and the
end uses have open capacity; hydromet has HYDROMET_CAP and HYDROMET_CAPEX. Lead times differ by region (Jones,
2026-11-23: US and allied long, China short, the rest of the world shorter still for mines).

Scenarios (run()): policy None (none after 2024) or {} (current law kept), foresight None (perfect) or a number of years
(myopic); "cost" (the model's decision) and "onshore": the US and its allies make at least a floor share of
their own demand at each processing and manufacturing stage (refining, precursor, anode, cathode, cells): 40% from
2030 (the EU's 2030 benchmarks: the Critical Raw Materials Act for processing, the Net-Zero Industry Act for
manufacturing), rising to 60% in 2040 (ours). Mines have no floor: they go where they are cheapest.
"""
import pandas as pd

from . import battery as B
from . import curves as C
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


# ---- 0.12.0: curves (curves.py), and what they are anchored at. Sources: data/battery_horizon/curves/
# (paths_elasticities.csv, ids E; operations_capacity.csv, ids S); "ours" where nothing was found.
KNOBS = dict(
    discount=0.08,                 # real, per year, on every year's costs (the same 8% the capital costs are annualised at)
    cost_path="mid",               # which cost curves over time: low, mid, high (COST_PATHS)
    cost_paths=None,               # set below
    # supply elasticities: a group's own, else its stage's. Mines: 20-year elasticities from a Bayesian SVAR, 1900-2020
    # (Boer, Pescatori and Stuermer: E241 lithium, E235 nickel, E238 cobalt); graphite none found (ours). Refining,
    # components and cells: none found; plants replicate at a small minimum scale (E136: under 2 GWh for cells), so
    # their curves are flatter (ours)
    supply_elasticity={('mine', 'Li'): 2.55, ('mine', 'Ni'): 1.30, ('mine', 'Co'): 0.86, ('mine', 'graphite'): 1.0,
                       'refine': 2.0, 'pcam': 5.0, 'anode': 5.0, 'cath': 5.0, 'cell': 5.0},
    # demand elasticities. EVs: the aggregate US EV price elasticity, -1.29 (E249: Li, Tong, Xing and Zhou 2017), times the
    # cells' share of an EV's price, about 0.15 (ours), so about -0.2 with respect to the cell price; storage,
    # electronics, other applications: none found (ours). The minerals' other uses: 2SLS estimates after the
    # structural break (Shojaeddini, Alonso and Nassar: E270 lithium, E272 nickel, E271 cobalt, E275 flake graphite)
    demand_elasticity={'ev': -0.2, 'storage': -0.5, 'electronics': -0.1, 'other': -0.3,
                       ('refine', 'Li'): -0.11, ('refine', 'Ni'): -0.09, ('refine', 'Co'): -0.45,
                       ('mine', 'graphite'): -0.58},
    entry=0.02,                    # every region's curve is also anchored at this share of the world's output, so a
                                   # region that makes nothing today can start (ours)
    wedge_carry={2024: 1.0, 2025: 0.0},   # share of the calibrated offset kept after 2024 (none: the model's decision,
                                          # Jones 2026-11-23); 1.0 keeps today's unexplained costs
    chem_band=0.10,                # each chemistry's share of an end use within this of IEA's path, by region (ours)
    chem_band_base=0.02,           # in the observed years (room for repurposed packs)
    retire={'mine': 0.04, 'refine': 0.04},   # share of 2024's capacity retiring each year: 1/25 (plant lives of 25
                                   # years, E/T89; refinery and most mine lives not found, S rows); components and cells
                                   # are young (cell capacity tripled since 2021, S rows) and do not retire before 2040
    operations_later=True,         # known operations keep their own costs in later years
    other_growth=0.0,              # the minerals' other uses: growth per year of the demand curve's anchor
    base_share={'Mn': 0.01, 'Fe': 0.001, 'P': 0.05},   # batteries' share of each base material's market, which
                                   # anchors its supply curve (Mn: IEA, 1% for energy technologies; Fe, P: ours)
    base_elasticity={'Mn': 0.316, 'Fe': 0.539, 'P': 0.5},   # long run: manganese ore (E295), iron ore (E298), Dahl's
                                                            # MEDS averages; phosphorus none found (ours)
    price_mult={},                 # {(group, region): multiplier or {year: multiplier}} on a curve's price
    strict=True,                   # audit(): refuse to solve while a fixed or flat piece has no reason in ALLOW
)
# Cost curves over time: {(opex|capex, stage): {year: index over 2024}}, straight between, held after 2040.
#   cells, mid: Argonne BatPaC's pack paths, NMC and LFP averaged (E30-E45; the depreciation line for capital; its
#     NMC pack moves from NMC622 to NMC811, NMC95 and LMNO with more silicon, so the path includes that), to
#     2035, then NREL's mid storage path 2035-40 (E25, E28); low: BNEF's 2030 pack forecast (E9, E11), then NREL's
#     low path (E21, E24, E27); high: NREL's high path, about flat (E20, E23, E26, E29)
#   cathode and precursor processing: no learning (E123), low at Argonne's LFP cathode price path (E104-E113, which
#     includes materials: an upper bound on processing's fall); anode likewise (E106-E115)
#   refining and mining: no projection found (E165, E170-E173), flat; high: mining 15% dearer by 2040 as grades fall
#     (IEA's qualitative statement, E167; the number is ours)
_CELL_MID = {2030: 0.758, 2035: 0.638, 2040: 0.580}
_CELL_MID_CAPEX = {2030: 0.754, 2035: 0.680, 2040: 0.618}
_CELL_LOW = {2030: 0.602, 2035: 0.427, 2040: 0.389}
_CELL_HIGH = {2030: 1.060, 2035: 1.015, 2040: 0.985}
COST_PATHS = {
    "mid": {('opex', 'cell'): _CELL_MID, ('capex', 'cell'): _CELL_MID_CAPEX},
    "low": {('opex', 'cell'): _CELL_LOW, ('capex', 'cell'): _CELL_LOW,
            ('opex', 'cath'): {2030: 0.80, 2035: 0.76}, ('opex', 'pcam'): {2030: 0.80, 2035: 0.76},
            ('opex', 'anode'): {2030: 0.83, 2035: 0.83}},
    "high": {('opex', 'cell'): _CELL_HIGH, ('capex', 'cell'): _CELL_HIGH, ('opex', 'mine'): {2040: 1.15}},
}
KNOBS["cost_paths"] = COST_PATHS
# Nameplate cell capacity in 2024 (IEA, battery_2023_2024/cell_production.csv): China 2.8 TWh, the EU 0.2, the US
# 0.2, the rest of the world 0.1, of which India and Indonesia 15 GWh (the same file) and the rest (Japan, Korea)
# allied. Used from 2025, when existing capacity is nameplate, not observed output plus headroom.
NAMEPLATE = {('cell', 'CHN'): 2800.0, ('cell', 'ALLY'): 285.0, ('cell', 'US'): 200.0, ('cell', 'ROW'): 15.0}
# cell-equivalent mass per kWh, for recycling capacity in tonnes: 1000 / Wh per kg, LFP about 160 (6.25 kg) and
# high-nickel over 270 (3.7 kg), the mean (E221, E222)
KG_CELL_PER_KWH = 4.98
# Hydromet (material recovery) capacity, IEA Recycling of Critical Minerals 2024, 2023 (P168-P172), Mt of
# cell-equivalent mass: China 1.78, Europe 0.04 and Korea 0.12 (ALLY), North America 0.04 (US), other 0.18 (ROW)
HYDROMET_MT = {'CHN': 1.78, 'ALLY': 0.16, 'US': 0.04, 'ROW': 0.18, 'SPC': 0.0}
HYDROMET_CAP = {r: mt * 1000.0 / KG_CELL_PER_KWH for r, mt in HYDROMET_MT.items()}
# Hydromet capital cost, USD per kWh of black-mass feed a year: the US, Li-Cycle Rochester's 2021 study (M138; its
# note: 26.9 per kWh); the allies, a European mechanical-thermal and hydrometallurgical plant, about 3,350 USD per t
# of batteries a year (E194's total investment over its 1,314 kg/h, per the check of 2026-11-24), at KG_CELL_PER_KWH; China, Brunp Yichang (P222, 0.5 USD per kg of spent LFP
# battery a year); the rest of the world between the US and China. No capital cost per GWh by region was found (E198).
HYDROMET_CAPEX = {'US': 26.9, 'ALLY': 3.35 * KG_CELL_PER_KWH, 'CHN': 0.5 * KG_CELL_PER_KWH}
HYDROMET_CAPEX['ROW'] = HYDROMET_CAPEX['SPC'] = (HYDROMET_CAPEX['US'] + HYDROMET_CAPEX['CHN']) / 2
# Known operations, 2024, for the supply curve below each region's observed output: {(group, region): [(kt
# contained, USD per kg contained)]}, scaled to the region's output. Mine-gate costs; an integrated (brine or
# lepidolite to carbonate) cost less the region's conversion (battery_costs selected.csv: China 16.36, the rest of the
# world 16.69), as battery.costs() splits them.
#   Australia's lithium (S1, S7, S14, S19/S20): Greenbushes, Pilgangoora (17.76, corrected by the check of
#     2026-11-24), Mt Marion, Wodgina (cash or FOB costs).
#     North American Lithium (S116, 37.29 in a restart year) is left out; Mt Cattlin and Bald Hill have no 2024 cost.
#   The rest of the world's lithium (S45 with U231, S40, S50 with S51's 2023 cost, S54, S57 with S58's 2023 cost, S67):
#     Albemarle Atacama (salar costs 7.55), SQM Atacama (excluding CORFO lease payments, as Australia's exclude
#     royalties; 43.28 integrated with them), Olaroz, Cauchari-Olaroz, Fenix, Grota do Cirilo. Zimbabwe has no
#     cost (S101).
#   China's lithium (S76, S82, S84, S88, S91): Jiajika, Huashan lepidolite, Jiangte lepidolite, Qarhan (Salt Lake),
#     Qarhan (Zangge).
#   Nickel (S196, S197, S209, S216, S229; S171, S173): Indonesian HPAL and RKEF complexes to MHP, NPI or matte
#     (Harita, Huayue, Nickel Industries, PT Vale); Vale's Sudbury and Voisey's Bay (ALLY).
OPERATIONS = {
    (('mine', 'Li'), 'ALLY'): [(38.59, 7.81), (17.52, 17.76), (12.49, 17.74), (11.29, 23.04)],
    (('mine', 'Li'), 'ROW'): [(13.0, 7.55), (33.75, 32.96 - 16.69), (4.405, 26.68 - 16.69), (4.773, 37.95 - 16.69),
                              (4.626, 25.01 - 16.69), (5.929, 14.78)],
    (('mine', 'Li'), 'CHN'): [(1.884, 10.37), (4.894, 34.82 - 16.36), (2.91, 59.97 - 16.36), (7.516, 27.01 - 16.36),
                              (2.173, 30.35 - 16.36)],
    (('mine', 'Ni'), 'ROW'): [(126.3, 8.38), (67.05, 5.7), (83.41, 7.115), (127.3, 10.223), (71.31, 9.374)],
    (('mine', 'Ni'), 'ALLY'): [(36.6, 13.18), (19.2, 23.18)],
}
CAL_ROUNDS = 8                     # calibrate(): refinement rounds, and the miss allowed, a share of the stage's output
CAL_TOL = {None: 0.005, ('mine', 'graphite'): 0.02}   # graphite mining misses by up to 1.6%: the split of anode
                                                      # between natural and synthetic graphite is not observed


def _ref_prices(net, y):
    """{good: value} in year y at China's unit costs with everything inside it, as build() values traded goods
    (retired products, scrap and black mass at nothing; base materials at their price): a good's production cost for
    the 45X credits that are a share of it."""
    memo = {}
    made = {}
    for p in net["processes"]:
        made.setdefault(N.output(p), []).append(p)
    pcs = {s: net["cost"][s][0] for s in net["stages"]}

    def val(g, seen=()):
        if g in memo:
            return memo[g]
        if g in net["base"]:
            v = float(net["base"][g]["price"][y])
        elif g not in made or g in seen or g[0] in ('eol', 'scrap', 'shred'):
            v = 0.0
        else:
            v = min(pcs[g[0]].get(p[1:] + ('CHN', y), 0.0)
                    + sum(val(i, seen + (g,)) / by_year_or(k_, y) for i, k_ in net["recipe"][p].items())
                    for p in made[g])
        memo[g] = v
        return v
    return val


def apply_policy(net, bkw, years, later_policy):
    """Tariffs and 45X on the network: the policy in force in the observed years always (they were calibrated with
    it), and after them `later_policy` (policy.py: dict(law=, s232=, tariffs=, credits=), or None for none)."""
    from . import policy as P
    lp = later_policy or {}
    tf = P.tariffs(years, s232=lp.get("s232", False))
    cr_hist = P.credits(years, "IRA")              # 2023-24: the IRA's 45X (PL 119-21 changed nothing then)
    cr = P.credits(years, lp.get("law", "PL 119-21"))
    on_t = later_policy is not None and lp.get("tariffs", True)
    on_c = later_policy is not None and lp.get("credits", True)
    bkw["tariffs"] = {k: {y: (v if (y in B.YEARS or on_t) else 0.0) for y, v in by.items()} for k, by in tf.items()}
    for y in years:
        if y not in B.YEARS and not on_c:
            continue
        c = cr_hist if y in B.YEARS else cr
        val = _ref_prices(net, y)
        for s in ('refine', 'cath', 'anode', 'cell'):
            pc = net["cost"][s][0]
            for p in net["processes"]:
                if p[0] != s:
                    continue
                key = p[1:] + ('US', y)
                if s == 'cell':
                    credit = c['cell'][y]
                else:
                    inputs = sum(val(i) / by_year_or(k_, y) for i, k_ in net["recipe"][p].items())
                    share = (c['mineral'][y] if s == 'refine' else
                             max(c['eam'][y], c['mineral'][y]) if s == 'anode' else c['eam'][y])
                    credit = share * (pc[key] + inputs)
                pc[key] -= credit
                net.setdefault("credit", {})[p + ('US',), y] = credit


def _co_per_ni(inputs):
    """kt of cobalt mined per kt of nickel mined outside the DRC in 2024 (USGS, battery.load()'s mine table): cobalt
    from nickel ores (Indonesian HPAL, Australian, Russian, Philippine, Canadian sulphide and laterite)."""
    y = max(B.YEARS)
    co = sum(v for (m, r, yy), v in inputs["mine"].items() if m == 'Co' and yy == y and r != 'SPC')
    ni = sum(v for (m, r, yy), v in inputs["mine"].items() if m == 'Ni' and yy == y)
    return co / ni


def _index(path, y):
    """A cost path's index in year y: {year: index} anchors, 1.0 to the last observed year, straight between."""
    if not path or y <= max(B.YEARS):
        return 1.0
    return _line({max(B.YEARS): 1.0, **path}, y)


def _groups(net):
    """{group: [process, ...]} for battery._group()'s groups, cobalt mining left out where it is a co-product."""
    g = {}
    for p in net["processes"]:
        k = B._group(p + ('X',))
        if k and not (k == ('mine', 'Co') and ('mine', 'Ni') in net.get("coproducts", {})):
            g.setdefault(k, []).append(p)
    return g


def _observed(net, params, bkw, groups):
    """{(group, region, year): observed output} in the observed years, as battery.calibrate() reads it: capacity over
    HEADROOM (the anode: its limit over HEADROOM)."""
    cap, lim = params["init_cap"], bkw["limits"]
    obs = {}
    for g, ps in groups.items():
        for r in B.REGIONS:
            for y in B.YEARS:
                obs[g, r, y] = (lim[('anode', r)][y] if g[0] == 'anode'
                                else sum(cap[p + (r,)][y] for p in ps)) / B.HEADROOM
    return obs


def _scale(inputs, net, groups, obs):
    """{(group, year): world output index over 2024} for the curves' anchors: the batteries' need for the group's
    output (and the minerals' other uses, held) relative to 2024."""
    D, I = inputs["demand"], inputs["intensity"]
    other = {}
    for (g, r, y), v in inputs["other"].items():
        other[g, y] = other.get((g, y), 0.0) + v
    out = {}
    for g in groups:
        def amount(y):
            if g[0] == 'cell':
                return sum(v for k, v in D.items() if k[3] == y)
            if g[0] in ('pcam', 'cath'):
                return sum(v for k, v in D.items() if k[3] == y and k[1] == g[1])
            m = 'graphite' if g[0] == 'anode' else g[1]
            batt = sum(v * I[k[1]].get(m, 0.0) for k, v in D.items() if k[3] == y)
            return batt + other.get((('refine', m) if g[0] == 'refine' else ('mine', m), y), 0.0)
        a0 = amount(max(B.YEARS))
        for y in YEARS:
            out[g, y] = amount(y) / a0 if a0 else 1.0
    return out


def network(inputs, years=None, knobs=None, cal=None, policy=None):
    """(net, params, build options, need, info) for the horizon. knobs: KNOBS overrides. cal: calibrate()'s result
    (offsets and reference prices); None builds the curves with no offsets and no demand curves (calibrate() uses
    that). policy: policy() options (tariffs and production credits), or None."""
    k = {**KNOBS, **(knobs or {})}
    Y = list(years or YEARS)
    cx = capex(inputs["intensity"])
    net, params, bkw, need = B.network(inputs, years=Y, capex=cx, lead=LEAD, crf=CRF, chem_choice=True,
                                       co_per_ni=_co_per_ni(inputs))
    groups = _groups(net)
    obs = _observed(net, params, bkw, groups)
    later = [y for y in Y if y not in B.YEARS]
    info = dict(groups=groups, observed=obs)
    params.update(discount=k["discount"], discount_base=max(B.YEARS), capacity_rule="cumulative",
                  build_life={s: LIFE_YEARS for s in net["stages"]})
    ic = params["init_cap"]

    # ---- cost curves over time: operating and capital costs move by their stage's path
    paths = k["cost_paths"][k["cost_path"]]
    pc_all = {}
    for s in net["stages"]:
        pc, vc, fc = net["cost"][s]
        for key in pc:
            y = key[-1]
            pc[key] = pc[key] * _index(paths.get(('opex', s)), y)
            vc[key] = vc[key] * _index(paths.get(('capex', s)), y)
        pc_all[s] = pc

    # ---- existing capacity: nameplate where known, retiring at its stage's rate; pooled where plants are shared
    for (s, r), v in NAMEPLATE.items():
        nodes = [p + (r,) for p in net["processes"] if p[0] == s]
        for n in nodes:
            for y in later:
                ic[n][y] = 0.0
        for y in later:
            ic[nodes[0]][y] = v
    for n, by_y in ic.items():
        rate = k["retire"].get(n[0], 0.0)
        for y in later:
            by_y[y] = by_y[y] * max(0.0, 1.0 - rate * (y - max(B.YEARS)))
    pools = []
    for r in B.REGIONS:
        for members in (['anode'], ['cell'], ['pcam_nmc'], ['cath_nmc'], ['hydromet']):
            nodes = [p + (r,) for p in net["processes"] if _pool_of(p) == members[0]]
            if len(nodes) > 1:
                pools.append({n: _pool_coef(net, n) for n in nodes})
    for pool in pools:                             # the pool's capacity on its first node, in that node's units
        first = next(iter(pool))
        for y in later:
            tot = sum(ic[n][y] * pool[n] for n in pool)
            for n in pool:
                ic[n][y] = 0.0
            ic[first][y] = tot / pool[first]
    # hydromet: IEA's 2023 material-recovery capacity, built further at its capital cost
    for r, gwh in HYDROMET_CAP.items():
        nodes = [p + (r,) for p in net["processes"] if _pool_of(p) == 'hydromet']
        for n in nodes:
            for y in Y:
                ic[n][y] = 0.0
        for y in Y:
            ic[nodes[0]][y] = gwh / _pool_coef(net, nodes[0])
    pc, vc, fc = net["cost"]['refine']
    for p in net["processes"]:
        if _pool_of(p) == 'hydromet':
            for r in B.REGIONS:
                for y in Y:
                    vc[p[1:] + (r, y)] = (HYDROMET_CAPEX[r] / _pool_coef(net, p + (r,)) * CRF
                                          * max(0, max(Y) - (y + LEAD['refine'][r]) + 1)
                                          * _index(paths.get(('capex', 'hydromet')), y))
    # cobalt: mined where it is a co-product of nickel; primary cobalt mines only in the DRC (and built anywhere)
    for p in net["processes"]:
        if p == ('mine', 'Co'):
            for r in B.REGIONS:
                if r != 'SPC':
                    for y in Y:
                        ic[p + (r,)][y] = 0.0

    # ---- chemistry: the observed mix in the observed years, within a band of IEA's path after them
    D = inputs["demand"]
    rshare = {}
    for p in net["processes"]:
        if p[0] == 'use' and p[1].startswith('GWh_'):
            c, u = p[1][4:], p[2]
            lo, hi = {}, {}
            for r in B.REGIONS:
                lo[r], hi[r] = {}, {}
                for y in Y:
                    tot = sum(v for (uu, cc, rr, yy), v in D.items() if (uu, rr, yy) == (u, r, y))
                    sh = D.get((u, c, r, y), 0.0) / tot if tot else 0.0
                    band = k["chem_band_base"] if y in B.YEARS else k["chem_band"]
                    lo[r][y], hi[r][y] = max(0.0, sh - band), min(1.0, sh + band)
            rshare[p] = {"min": lo, "max": hi}
    bkw["route_share"] = rshare

    # ---- supply (cost) curves on every group in every region and year
    scale = _scale(inputs, net, groups, obs)
    world0 = {g: sum(obs[g, r, max(B.YEARS)] for r in B.REGIONS) for g in groups}
    curve = []
    for g, ps in groups.items():
        e = k["supply_elasticity"].get(g, k["supply_elasticity"].get(g[0]))
        for r in B.REGIONS:
            nodes = [p + (r,) for p in ps]
            for y in Y:
                if y in B.YEARS:                   # observed years: anchored where calibrate() holds each region
                    Q0 = cal["target"][g, r, y] if cal else obs[g, r, y]
                else:
                    Q0 = obs[g, r, max(B.YEARS)] * scale[g, y] + k["entry"] * world0[g] * scale[g, y]
                P = sum(pc_all[g[0]][p[1:] + (r, y)] for p in ps) / len(ps)
                P *= by_year_or(k["price_mult"].get((g, r), 1.0), y)
                off = 0.0
                if cal:
                    w = cal["offset"].get((g, r, y if y in B.YEARS else max(B.YEARS)), 0.0)
                    off = w * (1.0 if y in B.YEARS else _line(k["wedge_carry"], y))
                    if y in B.YEARS:               # half a step down, so the anchor sits between two blocks, not on a tie
                        off -= C.HALF_STEP * P
                steps = OPERATIONS.get((g, r)) if y in B.YEARS or k["operations_later"] else None
                curve.append((nodes, y, _supply(Q0, P, e, off, steps)))
    # base materials: supply curves on what each region buys, anchored at the whole market
    if cal:
        for g in net["base"]:
            world_q = sum(v for (gg, _), v in cal["buy"].items() if gg == g)
            for r in B.REGIONS:                    # a region that bought none in 2024 at the entry share of the world's
                Qm = max(cal["buy"].get((g, r), 0.0), k["entry"] * world_q) / k["base_share"][g[1]]
                for y in later:
                    P = net["base"][g]["price"][y]
                    curve.append(([("buy", g, r)], y, _supply(Qm, P, k["base_elasticity"][g[1]], 0.0, None)))
    bkw["cost_curve"] = curve

    # ---- demand curves after the observed years: end uses and the minerals' other uses
    if cal and later:
        dc = {}
        for (g, r, y), q in list(net["demand"].items()):
            if y in B.YEARS or y not in Y or q <= 0:
                continue
            V = cal["price"].get((g, r))
            if V is None or V <= 0:
                continue
            if g[0] == 'use':
                e, V = k["demand_elasticity"][g[1]], V * _index(paths.get(('opex', 'cell')), y)
            else:
                e = k["demand_elasticity"][g]
                q = q * (1.0 + k["other_growth"]) ** (y - max(B.YEARS))
            dc[g, r, y] = C.demand_blocks(q, V, e)
            net["demand"][g, r, y] = 0.0
        bkw["demand_curve"] = dc
    bkw["pools"] = pools
    apply_policy(net, bkw, Y, policy)
    return net, params, bkw, need, info


def by_year_or(v, y):
    return v[y] if isinstance(v, dict) else v


def _supply(Q0, P, e, off, steps):
    return C.supply_blocks(max(Q0, 0.0), max(P, 1e-6), e, off, steps)


def _pool_of(p):
    """The capacity pool a process's plants belong to: one anode plant serves either graphite route, one cell line
    any chemistry, one pCAM or cathode plant either NMC, one hydromet plant any black mass."""
    if p[0] == 'anode':
        return 'anode'
    if p[0] == 'cell':
        return 'cell'
    if p[0] == 'pcam' and p[1] == 'sulfates':
        return 'pcam_nmc'
    if p[0] == 'cath' and p[2].startswith('nmc'):
        return 'cath_nmc'
    if p[0] == 'refine' and p[1].startswith('bm_'):
        return 'hydromet'
    return None


def _pool_coef(net, n):
    """Units on the pool's basis per unit of the node's output: 1, except hydromet (GWh-equivalents of black mass per
    kt of its main metal)."""
    if _pool_of(n[:-1]) == 'hydromet':
        return 1.0 / net["recipe"][n[:-1]][('shred', n[1])]
    return 1.0


def _solve(net, params, bkw, env=None, holds=None, fix=None):
    import gurobipy as gp
    from gurobipy import GRB, quicksum
    m = gp.Model(env=env); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **bkw)
    hc = {}
    for key, (nodes, x) in (holds or {}).items():
        hc[key] = m.addConstr(quicksum(h["prod"][n, key[2]] for n in nodes) <= x * (1 + 1e-9) + 1e-9)
    for (n, y), v in (fix or {}).items():
        h["newc"][n, y].lb = h["newc"][n, y].ub = v
    m.Params.Method = 1                            # dual simplex: barrier stalls on the open capacities (1e9) beside
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()   # retirement tails (1e-12); simplex solves it in seconds
    return m, h, hc


def calibrate(inputs, knobs=None, env=None):
    """The curves' offsets for the observed years (positive mathematical programming on the curves, as the Texas model
    calibrates its markets' offsets): each group's output in each region and observed year is held at or below its
    observed share of the model's total, the totals iterated until they settle; the hold's dual is the offset, added
    to that region's curve, so it makes its observed output at the observed costs. Then the reference prices for the
    demand curves (each good's price in each region in 2024) and what each region bought of the base materials.
    Returns dict(offset, target, price, buy, iterations)."""
    from gurobipy import GRB
    net, params, bkw, _, info = network(inputs, years=B.YEARS, knobs=knobs)
    groups, obs = info["groups"], info["observed"]
    nodes = {(g, r): [p + (r,) for p in ps] for g, ps in groups.items() for r in B.REGIONS}
    otot = {}
    for (g, r, y), v in obs.items():
        otot[g, y] = otot.get((g, y), 0.0) + v

    def totals(h):
        t = {}
        for (g, r, y) in obs:
            t[g, y] = t.get((g, y), 0.0) + sum(h["prod"][n, y].X for n in nodes[g, r])
        return t
    m, h, _ = _solve(net, params, bkw, env)
    if m.Status != GRB.OPTIMAL:
        raise RuntimeError(f"horizon.calibrate: the unheld solve ended with status {m.Status}")
    tot = totals(h)
    for it in range(1, 21):
        target = {key: obs[key] / otot[key[0], key[2]] * tot[key[0], key[2]] if otot[key[0], key[2]] else 0.0
                  for key in obs}
        holds = {key: (nodes[key[0], key[1]], x) for key, x in target.items()}
        m, h, hc = _solve(net, params, bkw, env, holds=holds)
        if m.Status != GRB.OPTIMAL:
            raise RuntimeError(f"horizon.calibrate: a held solve ended with status {m.Status}")
        t1 = totals(h)
        moved = max(abs(t1[x] - tot[x]) / max(tot[x], 1e-9) for x in t1)
        tot = t1
        if moved < 1e-7:
            break
    else:
        raise RuntimeError("horizon.calibrate: the targets did not settle in 20 solves")
    offset = {key: max(0.0, -c.Pi) / h["weight"](key[2]) for key, c in hc.items()}
    cal = dict(offset=offset, target=target, iterations=it, price={}, buy={})
    # the curves step in 1% of price, so the offsets alone land each region within a step of its target; refine them:
    # hold again with the offsets in, and add the holds' duals, until the free solve is within TOL of every target
    gtot = {}
    for (g, r, y), x in target.items():
        gtot[g, y] = gtot.get((g, y), 0.0) + x
    for rounds in range(1, CAL_ROUNDS + 1):
        net, params, bkw, _, _ = network(inputs, years=B.YEARS, knobs=knobs, cal=cal)
        m, h, _ = _solve(net, params, bkw, env)
        miss = max(abs(sum(h["prod"][n, key[2]].X for n in nodes[key[0], key[1]]) - x) / gtot[key[0], key[2]]
                   / CAL_TOL.get(key[0], CAL_TOL[None]) for key, x in target.items() if gtot[key[0], key[2]] > 0)
        if miss < 1.0:                             # every group within its tolerance
            break
        m, h, hc = _solve(net, params, bkw, env, holds={key: (nodes[key[0], key[1]], x) for key, x in target.items()})
        for key, c in hc.items():
            offset[key] = offset.get(key, 0.0) + max(0.0, -c.Pi) / h["weight"](key[2])
    cal["rounds"], cal["miss"] = rounds, miss
    net, params, bkw, _, _ = network(inputs, years=B.YEARS, knobs=knobs, cal=cal)
    m, h, _ = _solve(net, params, bkw, env)        # the calibrated observed years, unheld: prices and purchases
    y0 = max(B.YEARS)
    others = {g for (g, _, _) in inputs["other"]}
    for (g, r, y), c in h["bal_all"].items():
        if y == y0 and (g[0] == 'use' or g in others):
            cal["price"][g, r] = c.Pi / h["weight"](y)
    for (g, r, y), v in h["buy"].items():
        if y == y0 and v.X > 1e-9:
            cal["buy"][g, r] = v.X
    cal["shares"] = {key: sum(h["prod"][n, key[2]].X for n in nodes[key[0], key[1]]) for key in obs}
    return cal


# Pieces that are not curves on purpose, each with its reason, who and when (the Texas model's audit.allow).
ALLOW = {
    "observed years": "2023 and 2024 are observed: demand and capacity as measured, the curves calibrated to them",
    "shred": "shredding is cheap enough to be effectively unlimited, but costed by region (Jones, 2026-11-24)",
    "use": "placing a cell in an end use has no capacity of its own; the end use's demand curve prices it",
    "scrap": "manufacturing scrap: a share of what is made, not a market",
    "trade cost": "a share of the good's value on every arc (network.SHIP_VALUE_SHARE): a cost, not a market",
}


def audit(net, bkw, years, strict=True):
    """Every piece of the horizon that is a fixed amount or a flat price after the observed years (the Texas model's
    markets.audit()): final demand not on a demand curve, base materials bought with no supply curve, and groups
    with no cost curve. Each must be in ALLOW, or the run refuses (strict). Returns [(piece, kind, reason)]."""
    later = [y for y in years if y not in B.YEARS]
    out = [("observed years", "fixed", ALLOW["observed years"])]
    for (g, r, y), q in net["demand"].items():
        if y in later and q > 1e-9 and (g, r, y) not in bkw.get("demand_curve", {}):
            out.append((f"demand {g} {r} {y}", "fixed flow", ALLOW.get(g[0], "")))
    curved = {n for nodes, _, _ in bkw.get("cost_curve", ()) for n in nodes}
    for g in net["base"]:
        for r in B.REGIONS:
            if later and ("buy", g, r) not in curved:
                out.append((f"base {g} {r}", "flat price", ""))
    for s in ("shred", "use", "scrap"):
        out.append((s, "open capacity", ALLOW[s]))
    out.append(("trade cost", "flat share", ALLOW["trade cost"]))
    bad = [x for x in out if not x[2]]
    if strict and bad:
        raise RuntimeError(f"horizon.audit: {len(bad)} pieces are fixed or flat with no reason in ALLOW, e.g. {bad[:3]}")
    return out


def onshore_floor(m, h, inputs, floor=None):
    """The onshoring scenario's constraints on model m (build()'s handles h): at each processing and manufacturing
    group (battery._group(): refining by metal, precursor and cathode by chemistry, anode, cells), the US and allies
    make at least floor(y) x their share of the world's cells placed x the world's output. floor: {year: share}
    anchors (ONSHORE by default), none before the first."""
    from gurobipy import quicksum
    fl = ONSHORE if floor is None else floor
    D = inputs["demand"]
    out = {}
    for y in h["Y"]:
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


def run(scenario="cost", demand="STEPS", env=None, inputs=None, cal=None, floor=None, knobs=None, policy=None,
        foresight=None):
    """Solve the horizon and summarise. scenario: "cost" or "onshore"; demand: "STEPS" or "CPS"; policy: policy()
    options, or None for none. foresight: None (perfect, every year at once) or a number of years: myopic, solving
    from each year with that many years in view and fixing what was built before it. cal: calibrate()'s result
    (computed if not given). Returns dict(status, obj, cost, value, prod and cap {(stage, key, region, year): units},
    built {(stage, key, region, year online): units}, served {(good, region, year): units}, short, floors' duals)."""
    from gurobipy import GRB
    if scenario not in ("cost", "onshore"):
        raise ValueError(f"scenario: 'cost' or 'onshore', got {scenario!r}")
    inputs = inputs or load(demand)
    cal = cal or calibrate(inputs, knobs, env)
    steps = [None] if foresight is None else [y for y in YEARS if y > max(B.YEARS)]
    fixed = {}
    for t in steps:
        years = YEARS if t is None else [y for y in YEARS if y <= min(max(YEARS), t + foresight - 1)]
        net, params, bkw, need, info = network(inputs, years=years, knobs=knobs, cal=cal, policy=policy)
        report = audit(net, bkw, years, strict=(KNOBS | (knobs or {})).get("strict", True))
        import gurobipy as gp
        m = gp.Model(env=env); m.Params.OutputFlag = 0
        obj, h = N.build(m, params, net=net, **bkw)
        for (n, y), v in fixed.items():
            if (n, y) in h["newc"]:
                h["newc"][n, y].lb = h["newc"][n, y].ub = v
        fl = onshore_floor(m, h, inputs, floor) if scenario == "onshore" else {}
        m.Params.Method = 1
        m.setObjective(obj, GRB.MINIMIZE); m.optimize()
        if m.Status != GRB.OPTIMAL:
            return dict(status=m.Status, step=t)
        if t is not None:                          # keep what was decided this year
            for (n, y), v in h["newc"].items():
                if y <= t:
                    fixed[n, y] = v.X
    value = sum(v.X * bkw["demand_curve"][g, r, y][kk][1] * h["weight"](y)
                for (g, r, y, kk), v in h["served"].items()) if h["served"] else 0.0
    out = dict(status=m.Status, obj=m.ObjVal, value=value, cost=m.ObjVal + value, need=need, prod={}, cap={},
               audit=report,
               built={}, served={}, short={k_: v.X for k_, v in h["short"].items() if v.X > 1e-6},
               floor={k_: c.Pi for k_, c in fl.items()} if m.IsMIP == 0 else {})
    for (g, r, y, kk), v in h["served"].items():
        out["served"][g, r, y] = out["served"].get((g, r, y), 0.0) + v.X
    for (n, y), v in h["prod"].items():
        g = B._group(n)
        if g:
            key = g + (n[-1], y)
            out["prod"][key] = out["prod"].get(key, 0.0) + v.X
            out["cap"][key] = out["cap"].get(key, 0.0) + h["cap"][n, y].X
    for (n, y), v in h["newc"].items():
        g = B._group(n) or (('hydromet', 'bm') if _pool_of(n[:-1]) == 'hydromet' else None)
        L = B._lead(net["lead"], n[0], n[-1])
        if g and v.X > 1e-6 and max(B.YEARS) < y + L <= max(YEARS):
            key = g + (n[-1], y + L)
            out["built"][key] = out["built"].get(key, 0.0) + v.X * (_pool_coef(net, n) if g[0] == 'hydromet' else 1)
    w = h["weight"]                                # transfers, discounted as the objective is: tariffs paid
    tf = bkw.get("tariffs", {})                    # (on build()'s embedded values) and 45X credits received
    paid = 0.0
    for s_ in net["stages"]:
        for kk, a in enumerate(h["trade"][s_]):
            tk = (s_, a[-3], a[-2], a[-1]) if (s_, a[-3], a[-2], a[-1]) in tf else (s_, a[-2], a[-1])
            if tk in tf:
                paid += sum(tf[tk].get(y, 0.0) * h["value"](s_, a[-3], y) * w(y) * h["flow"][s_][kk, y].X
                            for y in h["Y"] if tf[tk].get(y, 0.0))
    out["tariffs_paid"] = paid
    out["credits"] = sum(c * h["prod"][n, y].X * w(y) for (n, y), c in net.get("credit", {}).items()
                         if (n, y) in h["prod"])
    out["resource_cost"] = out["cost"] - paid + out["credits"]
    out["recycled"] = {}
    for (n, y), v in h["prod"].items():
        if _pool_of(n[:-1]) == 'hydromet':
            out["recycled"][n[-1], y] = out["recycled"].get((n[-1], y), 0.0) + v.X * _pool_coef(net, n)
    return out

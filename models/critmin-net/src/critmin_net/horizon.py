"""The battery network (battery.py) projected to 2040: demand from IEA's outlooks, capacity built where it is cheapest
once each region's lead time allows, and an onshoring scenario. PRELIMINARY.

0.12.0: every market is a curve (curves.py; KNOBS turns them). Every stage in every region and year has a supply
(cost) curve anchored at its observed output, growing with the world's need (plus an entry share), with known
operations below the anchor at their own costs (OPERATIONS) in the observed years and, after them, a merit order of
existing operations (their own size, retiring), new capacity at the region's cost, and the rising curve (0.12.1); every end use, the minerals' other uses and the base
materials have demand or supply curves; operating and capital costs move on low, mid or high cost curves over time
(COST_PATHS). 2023 and 2024 are battery.py's observed years: calibrate() sets each curve's offset there so the network
makes the observed regional shares; after 2024 the offsets fade to nothing by 2030 (KNOBS["wedge_carry"]), and from
then where each stage is made is the model's decision (Jones, 2026-11-23 and 2026-11-24). Costs are discounted (8%). Existing capacity is
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
              ('mine_graphite', 'SPC'): 2.1125, ('mine_graphite', 'ALLY'): 3.6905,      # Canada (U58)
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
    # share of the calibrated offset kept after 2024, straight between and held after: it fades to none by 2030, so
    # from then where things are made is the model's decision (Jones, 2026-11-23). The fade fits 2025 best (the
    # backcast, scripts/battery_backcast.py: mean miss 2.9 points against observed 2025 shares, 4.3 when dropped at
    # once, 3.4 when kept; Jones, 2026-11-24). {2024: 1.0, 2025: 0.0} drops them at once; 1.0 keeps them.
    wedge_carry={2024: 1.0, 2025: 0.8, 2030: 0.0},
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
    yard=True,                     # retired packs and black mass may be held from year to year (yards) before
                                   # reuse or recycling, or never
    # what holding costs, USD per kWh held a year (0.15.0; without it retired packs piled up for free, 3,200 GWh by
    # 2040): Argonne's reference warehouse cost, 150 USD per tonne a year (Iloeje et al. 2022, X165; an assumption
    # of theirs, for spent hybrid batteries, no dollar year; their range 0-600, X166), per kWh of retired packs at
    # module mass (8.70 kg per kWh, NREL 2015's 115 Wh per kg) and of black mass at cell mass (4.98). Storage limits in
    # law (X172-X178: a year for waste batteries in the US and China, three in the EU before it counts as
    # landfill) are not imposed: the cost does the work. None or {}: free.
    yard_cost={'eol': 0.150 * 8.70, 'shred': 0.150 * 4.98},
    # second life after 2024 (Jones, 2026-11-24: not a hard share, a curve): at most `viable` of retired EV packs can be
    # repurposed (80% of collected packs viable, stakeholder-based, battery_2023_2024/lifecycle.csv row 39; NREL: 80-90%
    # of US packs eligible after 15 years, X137, X138); repurposing costs rise on a supply curve anchored at `anchor` of
    # retired EV packs (the JRC's REP-20 scenario, 20% of removed batteries to second use by 2030, X144; Norway reuses
    # about 60% today, X142, and the EU would need 40% to cover its storage by 2040, X143) with `elasticity` (ours).
    # Repurposing's own cost, 30.09 USD per kWh (battery_costs), sits in NREL's 20-49 (X139-X141). 2023-2024 keep
    # battery.LIFECYCLE's 5% (little was reused).
    second_life={'viable': 0.80, 'anchor': 0.20, 'elasticity': 1.0},
    # rules of origin: a region exports only what it made (and, for base goods, bought), so a good cannot pass
    # through a low-tariff region to dodge a tariff, 45X's foreign-entity rule or an export control (0.13.0: without
    # it the US bought China's cathode and anode through the DRC). Aggregated regions make re-export an artefact.
    # Every year (0.15.0): with it only from 2025, the US bought China's cells and anode through the DRC in 2023-2024
    # too, so it paid no tariff. With it in the observed years graphite mining calibrates within 4% (CAL_TOL). A year:
    # from that year on; False: none.
    rules_of_origin=True,
    # [(stage, region)]: no new capacity there beyond 2024's. Default: the DRC (LLNL's Special region, one country)
    # builds no precursor, cathode, anode or cell plants: it has none and none is announced (pipeline_capex.csv has
    # only its cobalt mining), yet as the one region with no US tariff it would otherwise supply the US from 2030
    # (0.13.0). Refining stays open (it refines cobalt). [] lets it build on its curves like any region.
    no_entry=[('pcam', 'SPC'), ('cath', 'SPC'), ('anode', 'SPC'), ('cell', 'SPC')],
    pyro=True,                     # pyromet+ as a recycling route (PYRO)
    floor_penalty=100.0,           # onshoring floors: USD per kg or kWh short (ours; above their shadow prices, under
                                   # 30, so they are met where they can be; low enough that shrinking the market to
                                   # meet a share never pays). None: hard floors
    quotas=True,                   # operations held at their quotas (QUOTA_OPS: Chile's Atacama); False: they retire
    greenfield=None,               # new mines' operating costs: None takes GREENFIELD; {} prices new capacity at the
                                   # region's own cost (0.12.1's rule), a dict overrides
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
# 0.13.0, from data/battery_horizon/mining/mining_realism.csv (ids X; every row checked against its source,
# verification.csv). USD per kg contained throughout.
#
# Brownfield expansions {(mineral, region): dict(capex=USD per kg a year of capacity added, lead=years from decision,
# share=room to expand, a share of 2024's capacity)}: a separate process beside the region's mines, at their
# operating cost, drawing on the same reserves. Only where an expansion's cost is sourced; elsewhere none.
#   share 0.5 everywhere (ours): sourced steps added 17% (X2), 47% (X4) and 33% (X7) of an operation's capacity.
EXPANSION = {
    # Australia: median of Pilgangoora P680 (77.98, X1), P1000 (47.9 with the A$50M pre-spent, X3) and Greenbushes
    # CGP3 (41.63, X6); FID to first output 1.5 (X0) and 1.8 years (X3). More per unit than IEA's 28 for a new
    # Australian mine (U24, capex()): an expansion's edge here is its lead, 2 years against 5.
    ('Li', 'ALLY'): dict(capex=47.9, lead=2, share=0.5),
    # rest of the world: median of Goulamina Stage 2 (9.37, X54, Mali), Grota do Cirilo Phase 2 (18.49, X49, Brazil;
    # a budget) and Olaroz Stage 2 (90.47, X31, Argentina, brine); Chile's not disclosed. Lead: LEAD's 2 (none sourced)
    ('Li', 'ROW'): dict(capex=18.49, lead=2, share=0.5),
    ('Li', 'CHN'): dict(capex=115.11, lead=5, share=0.5),      # Qarhan brine, 117.66 (X39) and 112.56 (X40); LEAD's 5
    # US: Thacker Pass Phase 2 (309.74, X127), a permitted site: T38's 2-3 years to build
    ('Li', 'US'): dict(capex=309.74, lead=3, share=0.5),
    ('Ni', 'ALLY'): dict(capex=72.73, lead=5, share=0.5),     # Crawford phase 2 (X88, Canada); LEAD's 5
    # rest of the world: HPAL brownfield at 0.71 of greenfield (Ramu expansion against Taganito and Ramu, X93) x
    # IEA's 38.5 for Indonesia (U50); LEAD's 2
    ('Ni', 'ROW'): dict(capex=0.71 * 38.5, lead=2, share=0.5),
}
# Greenfield operating costs {(mineral, region)}: the cost of new capacity on later years' supply curves (in place of
# the region's own cost; royalties excluded, ROYALTY adds them). Lithium at the mine (brine less its carbonate plant,
# 16.69, and Thacker Pass less US conversion, 17.85, as battery_costs/selected.csv splits integrated costs).
GREENFIELD = {
    ('Li', 'ALLY'): 14.52,         # median of Kathleen Valley 11.43 (X10), Moblan 14.52 (X62), Whabouchi 28.13 (X59)
    # median of Goulamina 11.19 (X51), Ewoyaa 14.11 (X63), Grota do Cirilo 21.92 (X50), Sal de Vida 24.10 - 16.69
    # (X36), Cauchari-Olaroz 34.82 - 16.69 (X34)
    ('Li', 'ROW'): 14.11,
    ('Li', 'US'): 33.20 - 17.85,   # Thacker Pass (X57)
}
# Royalties and government lease payments {(mineral, region)}, at 2024 values and held. Ad valorem rates on a value:
# lithium 48.2 per kg Li (Western Australia's 5% came to 2.41 at the FY24 price, X12); nickel 16.812 (IEA's 2024
# price, U154). Cobalt has none added: its cost is priced (hydroxide payables x LME), so it is in the price.
_V_LI, _V_NI = 2.41 / 0.05, 16.812
ROYALTY = {
    ('Li', 'ALLY'): 2.41,          # Western Australia 5% of royalty value (X11, X12)
    # rest of the world, by 2024's output (selected.csv: Chile 0.482, Argentina 0.177, hard rock 0.341): Chile, SQM's
    # CORFO payments in 2025, 6.92 (X16; the line includes some potash); Argentina, 3% provincial royalty and 4.5%
    # export duty (X27, X30) on the value; hard rock, the mean of Brazil's paid 0.91 (X48), Mali's 6% modelled 1.66
    # (X55), Zimbabwe's 7% and 2% levy (X42, X43) and Ghana's 5% (X66) on the value
    ('Li', 'ROW'): 0.482 * 6.92 + 0.177 * 0.075 * _V_LI + 0.341 * (0.91 + 1.66 + 0.09 * _V_LI + 0.05 * _V_LI) / 4,
    # China: the provinces' resource-tax rates by its 2023 mix (battery_costs/selected.csv: lepidolite 0.447, brine
    # 0.435, spodumene 0.118): Jiangxi's lepidolite 6.5% (X149, X150, as its miners report), Qinghai's lithium salts
    # 6% (X151; brine sold as brine pays 15%, X152), Sichuan's concentrate 4.5% (X146)
    ('Li', 'CHN'): (0.447 * 0.065 + 0.435 * 0.06 + 0.118 * 0.045) * _V_LI,
    # the US: none (no federal royalty on hardrock; Nevada taxes net proceeds, 2-5%, X58, a tax on profit)
    ('Ni', 'ALLY'): 0.025 * _V_NI,  # Western Australia 2.5% (X84)
    # rest of the world: Indonesia's 2% on MHP (X76) at its 80.3% payable (U149). The ore royalty (14-19% of the ore's
    # benchmark price, X67-X71; about 3.06 USD per kg Ni at 1.8% in 2025, X160) is not added: the HPAL plants whose
    # costs these are buy ore at that benchmark, so it is in their cost. China: none added (IEA's all-in cost, U51)
    ('Ni', 'ROW'): 0.02 * 0.803 * _V_NI,
    ('graphite', 'ROW'): 0.03 * 0.4947,   # Mozambique 3% (X107) on the flake price (U168)
}
for _m in ('Li', 'Ni', 'graphite'):              # the DRC as the rest of the world (it mines no lithium or graphite)
    if (_m, 'ROW') in ROYALTY:
        ROYALTY[_m, 'SPC'] = ROYALTY[_m, 'ROW']
# Operations held at a quota after the observed years, not retiring: {(group, region): {index in OPERATIONS: {year:
# kt}}}. Chile's Salar de Atacama (CORFO): Albemarle 310.036 kt Li left at mid-2024, to 1 Jan 2044 (X24): 15.9 a
# year; SQM 405.914 kt Li to 2030, about 60% used by the end of 2025 (X18): 32.5 a year over 2026-2030; the SQM-Codelco
# venture (Novandino) 1,859.928 kt Li over 2031-2060 (X19): 62.0 a year. Annual averages of cumulative quotas.
QUOTA_OPS = {
    (('mine', 'Li'), 'ROW'): {
        0: {y: 310.036 / 19.5 for y in range(2025, 2044)},                           # Albemarle Atacama
        1: {**{y: 0.4 * 405.914 / 5 for y in range(2026, 2031)},                   # SQM Atacama
            **{y: 1859.928 / 30 for y in range(2031, 2061)}},
    },
}
# Pyrometallurgy ("pyromet+"): black mass of a nickel chemistry smelted to an alloy that is leached and refined to
# nickel and cobalt compounds, lithium and manganese lost to slag; a refining route beside hydromet+ (one plant serves
# either NMC black mass). Argonne's EverBatt 2019, generic pyro process, NMC622 cells, run with its defaults at each
# location (X128-X134; reproduced by the independent check): the scope includes refining the alloy, so pyromet+ makes
# refined nickel and cobalt. USD per kg of cells, equipment in 2017 dollars:
#   cost without capital charges: US 2.21 (X129); China and Korea (the allies) only as totals, 1.92 and 2.61 (X131,
#   X132), so less the US's capital charges per unit of capital ((3.40 - 2.21) / 5.72 = 0.208, X128-X130; ours)
#   capital per kg of cells a year: US 5.72 (X130), China 3.43 (X131), Korea 4.58 (X132); the rest of the world and the
#   DRC between the US and China, as elsewhere
# Per kWh of black mass at 3.7 kg of high-nickel cells per kWh (over 270 Wh per kg, E222; ours for low-nickel NMC too),
# and to 2024 dollars by US CPI-U annual averages (BLS: 2017 245.120, 2024 313.689). Recoveries 98% nickel and cobalt
# (X115, X116). Existing capacity: Umicore Hoboken's 7,000 t of batteries a year (X123), 1.9 GWh-equivalent. Lead:
# refining's. KNOBS["pyro"] False leaves it out.
_KG_NMC, _CPI_2017 = 3.7, 313.689 / 245.120
_CC = (3.40 - 2.21) / 5.72
_PYRO_CASH = {'US': 2.21, 'CHN': 1.92 - _CC * 3.43, 'ALLY': 2.61 - _CC * 4.58}
_PYRO_CAPEX = {'US': 5.72, 'CHN': 3.43, 'ALLY': 4.58}
for _d in (_PYRO_CASH, _PYRO_CAPEX):
    _d['ROW'] = _d['SPC'] = (_d['US'] + _d['CHN']) / 2
PYRO = dict(recovery={'Ni': 0.98, 'Co': 0.98},
            opex={r: v * _KG_NMC * _CPI_2017 for r, v in _PYRO_CASH.items()},       # USD per kWh of black mass
            capex={r: v * _KG_NMC * _CPI_2017 for r, v in _PYRO_CAPEX.items()},     # USD per kWh of black mass a year
            lead=None,                                                              # None: LEAD['refine']
            capacity={'ALLY': 7000.0 / _KG_NMC / 1000.0})                           # GWh-equivalent a year
CAL_ROUNDS = 8                     # calibrate(): refinement rounds, and the miss allowed, a share of the stage's output
CAL_TOL = {None: 0.005, ('mine', 'graphite'): 0.04}   # graphite mining misses by up to 3.5% with rules of origin in
                                                      # the observed years: the split of anode between natural and
                                                      # synthetic graphite is not observed


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
    it), and after them `later_policy` (policy.py: dict(law=, s232=, tariffs=, credits=, feoc=, china_controls=), or
    None for none). china_controls: dict(targets=, from_year=, goods=) (policy.china_controls()) closes China's
    exports of those goods to the targets from that year (a prohibitive tariff); feoc is applied in run()."""
    from . import policy as P
    lp = later_policy or {}
    tf = P.tariffs(years, s232=lp.get("s232", False))
    cr_hist = P.credits(years, "IRA")              # 2023-24: the IRA's 45X (PL 119-21 changed nothing then)
    cr = P.credits(years, lp.get("law", "PL 119-21"))
    on_t = later_policy is not None and lp.get("tariffs", True)
    on_c = later_policy is not None and lp.get("credits", True)
    bkw["tariffs"] = {k: {y: (v if (y in B.YEARS or on_t) else 0.0) for y, v in by.items()} for k, by in tf.items()}
    if lp.get("china_controls"):
        for key, by in P.china_controls(years, net, **lp["china_controls"]).items():
            old = bkw["tariffs"].get(key, {})
            bkw["tariffs"][key] = {y: max(old.get(y, 0.0), v) for y, v in by.items()}
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
        if p[0] == 'mine' and len(p) == 3:         # expansions and pyrometallurgy: own costs, not on a curve
            continue
        k = B._group(p + ('X',))
        if k and not (k == ('mine', 'Co') and ('mine', 'Ni') in net.get("coproducts", {})):
            g.setdefault(k, []).append(p)
    return g


def _extend(net, params, years, pyro=True):
    """0.13.0: add to the battery network (i) an expansion process beside each region's mines ("mine", "expand", m):
    brownfield capacity, at the region's own operating cost plus royalty, EXPANSION's capital cost and lead, up to a
    share of 2024's capacity, drawing on the same reserves; (ii) pyrometallurgy ("mine", "pyro_<chem>", "Ni"): black
    mass of a nickel chemistry smelted to an alloy that goes to refining as mined nickel (cobalt with it as a
    co-product), lithium and manganese lost to slag (PYRO); (iii) royalties on every mining cost (ROYALTY)."""
    Y = list(years)
    pc, vc, fc = net["cost"]['mine']
    ic = params["init_cap"]
    for (m, r), roy in ROYALTY.items():
        for y in Y:
            if ('Li' if m == 'Li' else m, r, y) in pc and (m, r, y) in pc:
                pc[m, r, y] += roy
    lead = dict(net.get("lead", {}))
    cap_max = dict(params.get("cap_max", {}))
    for m in B.MINED:
        q = ('mine', 'expand', m)
        net["processes"].append(q); net["recipe"][q] = {}
        for r in B.REGIONS:
            ex = EXPANSION.get((m, r)) or EXPANSION.get((m, None)) or {}
            base = ic.get(('mine', m, r), {})
            for y in Y:
                pc[q[1:] + (r, y)] = pc[(m, r, y)]
                vc[q[1:] + (r, y)] = 0.0
                fc[q[1:] + (r, y)] = 0.0
            ic[q + (r,)] = {y: 0.0 for y in Y}
            cap_max[q + (r,)] = ex.get("share", 0.0) * base.get(max(B.YEARS), 0.0)
            if ex:
                L = int(ex["lead"])
                for y in Y:
                    vc[q[1:] + (r, y)] = ex["capex"] * CRF * max(0, max(YEARS) - (y + L) + 1)
        lead[q] = {r: int((EXPANSION.get((m, r)) or EXPANSION.get((m, None)) or {"lead": 5})["lead"]) for r in B.REGIONS}
    res = net.get("reserves", {})
    for (s, m, r), spec in list(res.items()):
        if s == 'mine':
            res[(('mine', m, r), ('mine', 'expand', m, r))] = res.pop((s, m, r))
    if PYRO and pyro:
        rpc, rvc, rfc = net["cost"]['refine']
        plead = PYRO["lead"] or LEAD['refine']
        first = True
        for c in [g[1][3:] for g in net["goods"] if g[0] == 'shred' and g[1].startswith('bm_nmc')]:
            h = ('refine', f"bm_{c}", 'Ni')            # hydromet+'s route for this black mass
            q = ('refine', f"pyro_{c}", 'Ni')
            k = net["recipe"][h][('shred', f"bm_{c}")] / B.LIFECYCLE["recovery"]['Ni'] * PYRO["recovery"]['Ni']
            net["processes"].append(q); net["recipe"][q] = {('shred', f"bm_{c}"): k}   # kt Ni per GWh-eq
            co = net["coproducts"][h].get(('refine', 'Co'))
            if co:                                   # kt Co per kt Ni, at pyrometallurgy's recoveries
                net["coproducts"][q] = {('refine', 'Co'): co / B.LIFECYCLE["recovery"]['Co'] * PYRO["recovery"]['Co']
                                        * B.LIFECYCLE["recovery"]['Ni'] / PYRO["recovery"]['Ni']}
            for r in B.REGIONS:
                for y in Y:
                    rpc[q[1:] + (r, y)] = PYRO["opex"][r] / k
                    rvc[q[1:] + (r, y)] = PYRO["capex"][r] / k * CRF * max(0, max(YEARS) - (y + plead[r]) + 1)
                    rfc[q[1:] + (r, y)] = 0.0
                cap = PYRO["capacity"].get(r, 0.0) if first else 0.0   # pooled: on the first route only
                ic[q + (r,)] = {y: cap * k for y in Y}
            lead[q] = dict(plead)
            first = False
    net["lead"] = lead
    params["cap_max"] = cap_max


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
    output, and for mining and refining the minerals' other uses too (0.12.1: mining had left out the other uses of
    the refined metal, so its anchors grew with the batteries alone, about 6x to 2040 where mining grows about 3.4x),
    relative to 2024."""
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
            # the minerals' other uses (taken as refined metal, or as mined graphite) are in every upstream stage's base
            return batt + other.get((('refine', m), y), 0.0) + other.get((('mine', m), y), 0.0)
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
    # capital is charged to the horizon's end even in a myopic window (charge_to): a plant, once built, is paid for
    # whether or not the window sees the years it serves (0.15.1; charged only to the window's end, a plant built in
    # its last year cost one year's annuity, and the US built half the world's cells for 45X's last year)
    net, params, bkw, need = B.network(inputs, years=Y, capex=cx, lead=LEAD, crf=CRF, chem_choice=True,
                                       charge_to=max(YEARS),
                                       co_per_ni=_co_per_ni(inputs))
    _extend(net, params, Y, pyro=k["pyro"])
    groups = _groups(net)
    obs = _observed(net, params, bkw, groups)
    later = [y for y in Y if y not in B.YEARS]
    info = dict(groups=groups, observed=obs)
    params.update(no_transship=k["rules_of_origin"] if k["rules_of_origin"] in (True, False)
                  else int(k["rules_of_origin"]))
    for (s, r) in k["no_entry"]:                   # regions that cannot build a stage beyond what they have
        for p in net["processes"]:
            if p[0] == s:
                params.setdefault("cap_max", {})[p + (r,)] = max(params["init_cap"].get(p + (r,), {}).get(max(B.YEARS), 0.0), 0.0)
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
    held = {('mine', g[1], r): dict(ic[('mine', g[1], r)]) for (g, r) in QUOTA_OPS} if k["quotas"] else {}
    for n, by_y in ic.items():
        rate = k["retire"].get(n[0], 0.0)
        for y in later:
            by_y[y] = by_y[y] * max(0.0, 1.0 - rate * (y - max(B.YEARS)))
    for (g, r), q in (QUOTA_OPS.items() if k["quotas"] else []):   # capacity held at a quota does not retire: its
        n, ops = ('mine', g[1], r), OPERATIONS[g, r]               # share of the region's capacity is the quota
        tot, rate = sum(sz for sz, _ in ops), k["retire"].get('mine', 0.0)
        for y in later:
            f = max(0.0, 1.0 - rate * (y - max(B.YEARS)))
            for i, by in q.items():
                if y in by:
                    ic[n][y] += by[y] - held[n][y] * ops[i][0] / tot * f
    pools = []
    for r in B.REGIONS:
        for members in (['anode'], ['cell'], ['pcam_nmc'], ['cath_nmc'], ['hydromet'], ['pyro']):
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
                                          * max(0, max(YEARS) - (y + LEAD['refine'][r]) + 1)
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
                if steps and g[0] == 'mine':        # operations' costs exclude royalties; the node's cost has them
                    steps = [(sz, c + ROYALTY.get((g[1], r), 0.0)) for sz, c in steps]
                if steps and y not in B.YEARS and k["quotas"]:   # operations held at their quotas, not retiring
                    q = QUOTA_OPS.get((g, r), {})
                    steps = [(q[n][y], c, sz) if n in q and y in q[n] else (sz, c)
                             for n, (sz, c) in enumerate(steps)]
                gf = ((GREENFIELD if k["greenfield"] is None else k["greenfield"]).get((g[1], r))
                      if g[0] == 'mine' else None)
                if gf is not None:
                    gf = (gf + ROYALTY.get((g[1], r), 0.0)) * _index(paths.get(('opex', 'mine')), y)
                st = None
                if y not in B.YEARS:               # existing operations, retiring
                    st = ((cal["target"][g, r, max(B.YEARS)] if cal else obs[g, r, max(B.YEARS)])
                          * max(0.0, 1.0 - k["retire"].get(g[0], 0.0) * (y - max(B.YEARS))))
                curve.append((nodes, y, _supply(Q0, P, e, off, steps, st, gf)))
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
    if k["yard"]:                                  # yards: retired packs held before reuse or shredding (the
        bkw["stockpile"] = dict(regions="all", stages=["eol", "shred"], hold_share=0.0, initial={}, max={},
                                hold_unit=dict(k["yard_cost"] or {}),
                                end_at_least_start=False,   # retired stage), black mass after shredding; open after
                                from_year=max(B.YEARS) + 1)  # the observed years
    # second life: after the observed years, the viable share of retired EV packs may be repurposed, on a cost curve
    sl = k["second_life"]
    for q in [p for p in net["processes"] if p[0] == 'use' and p[1].startswith('2nd_')]:
        net["route_caps"][q] = {y: (net["route_caps"][q] if y in B.YEARS else sl["viable"]) for y in Y}
    ev_ret = _ev_retirements(inputs, Y)
    for r in B.REGIONS:
        nodes = [p + (r,) for p in net["processes"] if p[0] == 'use' and p[1].startswith('2nd_')]
        for y in later:
            Q0 = sl["anchor"] * B.LIFECYCLE["soh"] * ev_ret.get((r, y), 0.0)
            P = net["cost"]['use'][0][nodes[0][1:] + (y,)]
            if Q0 > 0:
                bkw["cost_curve"].append((nodes, y, C.supply_blocks(Q0, max(P, 1e-6), sl["elasticity"])))
    apply_policy(net, bkw, Y, policy)
    return net, params, bkw, need, info


def _ev_retirements(inputs, years):
    """{(region, year): GWh of EV packs retiring}, from EV placements (history and the demand path) at battery.LIFECYCLE's
    EV lifetimes: the anchor of second life's cost curve."""
    placed = {}
    for src in (inputs.get("history", {}), inputs["demand"]):
        for (u, c, r, y), v in src.items():
            if u == 'ev':
                placed[r, c, y] = placed.get((r, c, y), 0.0) + v
    life = B.LIFECYCLE["life"]
    out = {}
    for (r, c, a), v in placed.items():
        spec = life.get(('ev', c), life['ev'])
        for y in years:
            if y > a:
                out[r, y] = out.get((r, y), 0.0) + v * N.retire_share(spec, y - a)
    return out


def by_year_or(v, y):
    return v[y] if isinstance(v, dict) else v


def _supply(Q0, P, e, off, steps, steps_total=None, growth_cost=None):
    return C.supply_blocks(max(Q0, 0.0), max(P, 1e-6), e, off, steps, steps_total, growth_cost)


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
    if p[0] == 'refine' and p[1].startswith('pyro_'):
        return 'pyro'
    return None


def _pool_coef(net, n):
    """Units on the pool's basis per unit of the node's output: 1, except hydromet+ and pyromet+ (GWh-equivalents of
    black mass per kt of the main metal)."""
    if _pool_of(n[:-1]) in ('hydromet', 'pyro'):
        return 1.0 / next(iter(net["recipe"][n[:-1]].values()))
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


def drc_cobalt_quota(m, h, quota=None):
    """The DRC's cobalt export quota (ARECOMS, from 16 Oct 2025, after the export ban of 22 Feb to 15 Oct 2025): its
    exports of cobalt, mined and refined, at most policy.drc_cobalt_quota() kt a year (96.6 in 2026 and 2027, X98-X100,
    held after). 2025 is not capped: the ban and the quarter's 18.1 kt (X101) need a month's detail. Returns
    {year: constraint}."""
    from gurobipy import quicksum
    from . import policy as P
    q = P.drc_cobalt_quota(h["Y"]) if quota is None else quota
    out = {}
    for y, cap in q.items():
        if y not in h["Y"]:
            continue
        ex = quicksum(h["flow"][s][k, y] for s in ('mine', 'refine') for k, a in enumerate(h["trade"][s])
                      if a[-3] == 'Co' and a[-2] == 'SPC' and a[-1] != 'SPC')
        out[y] = m.addConstr(ex <= cap)
    return out


def feoc_constraints(m, h, net, law="PL 119-21"):
    """45X's prohibited-foreign-entity rules (PL 119-21), as compliance: in every year a credit is paid, US plants at a
    credited stage take at most (1 - threshold) of their inputs from China (policy.feoc_thresholds(): components 60% in
    2026 rising to 85%, critical minerals 25% in 2030 rising to 50%). China stands for "prohibited foreign entity",
    and an input's origin is where it was made (imports from China into the US, against what US plants of that stage
    take). Returns {(stage, year): constraint}."""
    from gurobipy import quicksum
    from . import policy as P
    th = P.feoc_thresholds(h["Y"])
    cr = P.credits(h["Y"], law)
    kind = {'cell': ('component', 'cell'), 'cath': ('component', 'eam'), 'anode': ('component', 'eam'),
            'refine': ('mineral', 'mineral')}
    out = {}
    for s, (k, c) in kind.items():
        for y in h["Y"]:
            if y in B.YEARS or th[k][y] <= 0 or cr[c][y] <= 0:
                continue
            us = [n for n in h["N"][s] if n[-1] == 'US' and (s != 'refine' or n[1] == n[2])]
            goods = {g for n in us for g in net["recipe"][n[:-1]] if g[0] != 'base'}
            take = quicksum(h["cons"][n, g, y] for n in us for g in net["recipe"][n[:-1]] if g in goods)
            imp = quicksum(h["flow"][g[0]][kk, y] for g in goods for kk, a in enumerate(h["trade"][g[0]])
                           if a[-3] == g[1] and a[-2:] == ('CHN', 'US'))
            out[s, y] = m.addConstr(imp <= (1.0 - th[k][y]) * take)
    return out


def onshore_floor(m, h, inputs, floor=None, penalty=None):
    """The onshoring scenario's constraints on model m (build()'s handles h): at each processing and manufacturing
    group (battery._group(): refining by metal, precursor and cathode by chemistry, anode, cells), the US and allies
    make at least floor(y) x their share of the world's cells placed x the world's output. floor: {year: share}
    anchors (ONSHORE by default), none before the first.
    penalty: USD per unit (kg, kWh) the floor falls short, or None for a hard floor. A soft floor is met wherever it
    can be (its shadow prices with perfect foresight are below 30); short of it only where plants cannot arrive in
    time (a myopic run), and the market is not shrunk to meet a share. Returns ({(group, year): constraint},
    penalty expression); the shortfalls are h["floor_short"]."""
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
            s = m.addVar() if penalty else 0.0
            if penalty:
                h.setdefault("floor_short", {})[g, y] = s
            out[g, y] = m.addConstr(quicksum(v for n, v in nv if n[-1] in US_ALLY) + s >= f * quicksum(v for _, v in nv))
    pen = quicksum(penalty * h["weight"](y) * s for (g, y), s in h.get("floor_short", {}).items()) if penalty else 0.0
    return out, pen


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
        fl, fpen = (onshore_floor(m, h, inputs, floor, (KNOBS | (knobs or {}))["floor_penalty"])
                    if scenario == "onshore" else ({}, 0.0))
        obj = obj + fpen
        if policy and policy.get("feoc"):
            feoc_constraints(m, h, net, policy.get("law", "PL 119-21"))
        if policy is not None and policy.get("drc_quota", True):
            drc_cobalt_quota(m, h, policy.get("drc_quota_kt"))
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
               floor={k_: c.Pi for k_, c in fl.items()} if m.IsMIP == 0 else {},
               floor_short={k_: v.X for k_, v in h.get("floor_short", {}).items() if v.X > 1e-6})
    for (g, r, y, kk), v in h["served"].items():
        out["served"][g, r, y] = out["served"].get((g, r, y), 0.0) + v.X
    out["expanded"] = {}                           # {(mineral, region, year): units from brownfield expansions}
    for (n, y), v in h["prod"].items():
        g = B._group(n)
        if n[0] == 'mine' and len(n) == 4:         # an expansion or pyrometallurgy: counted as its mineral's mining
            g = ('mine', n[2])
            if n[1] == 'expand' and v.X > 1e-9:
                out["expanded"][n[2], n[-1], y] = out["expanded"].get((n[2], n[-1], y), 0.0) + v.X
        if g:
            key = g + (n[-1], y)
            out["prod"][key] = out["prod"].get(key, 0.0) + v.X
            out["cap"][key] = out["cap"].get(key, 0.0) + h["cap"][n, y].X
    for (n, y), v in h["newc"].items():
        pl = _pool_of(n[:-1])
        g = B._group(n) or ((pl, 'bm') if pl in ('hydromet', 'pyro') else None)
        if n[0] == 'mine' and len(n) == 4:         # ('expand', mineral) or ('pyro_<chem>', 'Ni')
            g = (n[1], n[2])
        lp = net["lead"].get(n[:-1])               # a process's own lead (expansions), else its stage's
        L = (lp.get(n[-1], 5) if isinstance(lp, dict) else int(lp)) if lp is not None else B._lead(net["lead"], n[0], n[-1])
        if g and v.X > 1e-6 and max(B.YEARS) < y + L <= max(YEARS):
            key = g + (n[-1], y + L)
            out["built"][key] = out["built"].get(key, 0.0) + v.X * (_pool_coef(net, n) if g[0] in ('hydromet', 'pyro')
                                                                   else 1)
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
    out["trade"] = {}                              # {(stage, good, exporter, importer, year): units}, between regions
    for s_ in net["stages"]:
        for kk, a in enumerate(h["trade"][s_]):
            if a[-2] != a[-1]:
                for y in h["Y"]:
                    x = h["flow"][s_][kk, y].X
                    if x > 1e-6:
                        key = (s_, a[-3], a[-2], a[-1], y)
                        out["trade"][key] = out["trade"].get(key, 0.0) + x
    nt = h["net"]                                  # node-level detail for export.write(): what each process made,
    short_stage = {name: st for st in nt["short_stages"] for (s_, name) in nt["goods"] if s_ == st}
    out["detail"] = dict(                          # stocks held, every good's price, the network's units
        prod={(n, y): v.X for (n, y), v in h["prod"].items() if abs(v.X) > 1e-9},
        stock={k_: getattr(v, "X", v) for k_, v in h["stock"].items() if abs(getattr(v, "X", v)) > 1e-9},
        price={(g, r, y): c.Pi / w(y) for (g, r, y), c in h["bal_all"].items()} if m.IsMIP == 0 else {},
        short={(short_stage.get(k_[0], 'use'),) + tuple(k_): v for k_, v in out["short"].items()},
        units=dict(net["units"]), coproducts={p: dict(c) for p, c in net.get("coproducts", {}).items()},
        years=list(h["Y"]))
    out["credits"] = sum(c * h["prod"][n, y].X * w(y) for (n, y), c in net.get("credit", {}).items()
                         if (n, y) in h["prod"])
    out["resource_cost"] = out["cost"] - paid + out["credits"]
    out["recycled"], out["pyro"] = {}, {}           # {(region, year): GWh-equivalents of black mass}, by route
    for (n, y), v in h["prod"].items():
        pl = _pool_of(n[:-1])
        if pl in ('hydromet', 'pyro'):
            d = out["recycled"] if pl == 'hydromet' else out["pyro"]
            d[n[-1], y] = d.get((n[-1], y), 0.0) + v.X * _pool_coef(net, n)
    return out

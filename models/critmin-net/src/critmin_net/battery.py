"""A multi-mineral lithium-ion battery network on critmin-net's sets, 2023-2024: a test that the mechanism works.
PRELIMINARY.

Lithium, nickel, cobalt, manganese and graphite, through mining, refining, precursor (pCAM for NMC, battery-grade
iron phosphate for LFP), anode, cathode and cells, into every lithium-ion end use (EVs, stationary storage,
portable electronics, other), and back: what is placed in an end use retires by age into an end-of-life good,
retired EV packs may be repurposed as stationary storage (up to a share), and the rest, with manufacturing scrap,
is shredded into black mass, which is traded and recycled into refined metals. On LLNL's regions plus "Special"
(the DRC, for cobalt). Built by the same build() as the lithium model, with the network passed as data
(network.LITHIUM and network's lifecycle notes explain the format). It is not a calibration: the quantities are
real, read from public sources (data/battery_2023_2024/, one row per number with its source; load() says how
each is used), and every cost is a placeholder, so where production lands within the regions' capacities follows
those placeholders.

Mines are pulled by refining, refining by precursor and cathode, and so on down to the end uses: each stage only
by the one after it. Mines have their whole output as capacity, and the minerals' other uses (glass, steel,
alloys...) are demand where they leave the battery chain: refined lithium, nickel and cobalt, and mined manganese
and natural graphite (whose other uses do not pass through battery-grade refining). Extraction is within reserves,
which grow at their 2015-2025 rate up to identified resources (network.reserves_available).

Units: mined and refined goods and anode material in kt of contained element (graphite as graphite); precursor,
cathode, cells, end uses, retired products, scrap and black mass in GWh of the cells they serve ("GWh-equivalents").
A recipe's "output per unit input" is then 1 / (kg per kWh), material intensity read directly from the source.

LFP's precursor is battery-grade iron phosphate (FePO4), the pCAM stage's LFP good, with its own capacity and cost
and no mined input (iron ore and phosphate rock are not modelled). 1 kg of lithium in LiFePO4 comes with
FEPO4_PER_LI kg of FePO4, so GREET's 0.08 kg of lithium per kWh is about 1.7 kg of FePO4 per kWh.

Losses (network.build's `losses`): LOSSES, chosen from stage_losses.csv. A cell's loss is manufacturing scrap,
which is recycled. Lifecycle (LIFECYCLE): lifetimes by end use, the second life, the repurposed share, collection
and recycling recovery; each can be changed per run (network(..., life=, repurpose=, collect=)).

Simplifications, each deliberate for a mechanism test: the anode is made from mined natural graphite or synthetic
graphite (petroleum coke, not modelled), sharing each region's anode capacity, and graphite is not recovered by
recycling; portable electronics are at low-nickel NMC's intensity (their LiCoO2 is not modelled) and "other"
applications at the world EV mix; histories before 2023 use 2023's chemistry mix; capacity is fixed in every year
at the observed level times HEADROOM, so nothing is built.
"""
import pandas as pd

from . import network as N

REGIONS = N.LLNL_REGIONS + ['SPC']
YEARS = [2023, 2024]
MINERALS = ['Li', 'Ni', 'Co', 'Mn', 'graphite']
METALS = ['Li', 'Ni', 'Co', 'Mn']                # refined in the model, and recovered by recycling
USES = ['ev', 'storage', 'electronics', 'other']
STAGES = ['mine', 'refine', 'pcam', 'anode', 'cath', 'cell', 'use', 'eol', 'scrap', 'shred']
HEADROOM = 1.20                                  # capacity over observed output, as in network.calibrated()
OPEN = 1e9                                       # capacity where none is modelled (end uses, shredding)
UNIT_COST = 1.0                                  # PLACEHOLDER: every stage's cost per unit in China; regions differ
                                                 # only by the Stanford GSB US/China ratios, as calibrated() uses
SYNTHETIC_COST = 4.0                             # PLACEHOLDER: synthetic anode graphite per unit, above natural's (mined
                                                 # flake through spheronisation's loss, 1 / 0.395, plus processing, 1: 3.5),
                                                 # so mined flake is used first, as it is cheaper
REPURPOSE_COST = 0.5                             # PLACEHOLDER: per GWh of second-life storage
SHRED_COST = 0.1                                 # PLACEHOLDER: per GWh-equivalent shredded
RECYCLE_COST = 1.0                               # PLACEHOLDER: hydrometallurgy, per kt of the black mass's main metal
FEPO4_PER_LI = (55.845 + 30.974 + 4 * 15.999) / 6.94   # kg FePO4 per kg Li in LiFePO4 (standard atomic weights)
DATA = N.RAW / "battery_2023_2024"
# Default losses, share of what goes in (rows of stage_losses.csv). Each can be changed per run (network(losses=)).
LOSSES = {
    ('refine', 'Li', 'Li'): 0.077,   # spodumene concentrate to Li2CO3, 0.923 (Kelly et al. 2021, Table 5; derived).
                                     # Brine's LiCl to carbonate is 0.783 and its pond losses unknown: one route here
    ('refine', 'Ni', 'Ni'): 0.074,   # laterite ore to NiSO4 by HPAL, 0.926 (Sunrise NI 43-101, year 3; one project).
                                     # Sulfide smelting to refining is 0.895 (Wei et al. 2020)
    ('refine', 'Co', 'Co'): 0.004,   # refinery solution to CoSO4, 0.996 (Sunrise): the refinery step only, as nothing
                                     # citable was found for cobalt hydroxide to sulfate
    ('refine', 'Mn', 'Mn'): 0.13,    # ore to high-purity Mn sulphate, 0.87 (Giyani K.Hill DFS 2026; one project,
                                     # read in a news report)
    'pcam': 0.0,                     # GREET assumes 100% material efficiency; no measured yield found
    ('anode', 'natural', 'anode'): 0.605,  # flake concentrate to coated spherical graphite, 0.395 (Argonne 2022,
                                     # Table 3, Engels' data; the fines are a saleable co-product, lost here)
    'cath': 0.0,                     # GREET assumes 100%; no measured yield found
    'cell': {2023: 0.10, 2024: 0.094},     # manufacturing scrap: IEA GEVO 2024, 10% in 2023 falling to 6% in 2030
                                     # (2024 linear between them, ours); recycled as scrap
}
# Lifecycle defaults (rows of lifecycle.csv). Each can be changed per run.
# Weibull shapes marked "ours" are assumptions: only EV cars have a published distribution.
LIFECYCLE = dict(
    life={'ev': {'shape': 6.3, 'scale': 14.4, 'loc': 1.0},      # EV cars, non-LFP (Xu et al. 2020, Supp. Table 3; mode
                                                                # 15 yr); buses, trucks and 2/3-wheelers (a tenth of
                                                                # EV GWh) are at cars' lifetimes here
          ('ev', 'lfp'): {'shape': 8.1, 'scale': 19.3, 'loc': 1.0},   # EV cars, LFP (Xu 2020; mode 20 yr)
          'storage': {'mean': 10.0, 'shape': 3.0},     # 10 yr (Zeng et al. 2022, Supp. Table 7; T&E 2024); shape ours
          'electronics': {'mean': 3.0, 'shape': 3.0},  # 3 yr (Zeng 2022, Supp. Table 5); shape ours
          'other': {'mean': 6.0, 'shape': 3.0}},       # ours: e-bikes and the like, between commercial two-wheelers'
                                                       # 2-4 yr and personal ones' 10-12 (ICCT 2021, Table 8)
    second_life={'mean': 5.0, 'shape': 3.0},           # 5 yr (T&E 2024; RMI 2025; Xu and ICCT use 10); shape ours
    soh=0.75,                                          # GWh of storage per GWh of EV pack retired: 70-80% capacity left
                                                       # (Xu 2020; ICCT 2023); RMI 2025's oversizing implies 0.6
    repurpose=0.05,                                    # low, as Jones asked (2026-11-22). Published assumptions run 0-100%
                                                       # (ICCT 2023: 50%); IEA: today "only a small share"
    collect=1.0,                                       # every retired pack is repurposed or shredded (Jones, 2026-11-21)
    recovery={'Li': 0.9, 'Ni': 0.95, 'Co': 0.95, 'Mn': 0.95})   # hydrometallurgy (BNEF via T&E 2024; Redwood's Li
                                                       # 92% in Machala 2025); EU floors for 2031: Co, Ni 95%, Li 80%
NAME = {'lithium': 'Li', 'nickel': 'Ni', 'cobalt': 'Co', 'manganese': 'Mn', 'graphite': 'graphite'}
CHEMS = {'nmc_hi': ('NMC811', 'High-nickel'),    # IEA's high-nickel group (NMC622/721/811, NCA) at NMC811's intensity
         'nmc_lo': ('NMC532', 'Low-nickel'),     # IEA's low-nickel group (NMC333/442/532) at NMC532's
         'lfp': ('LFP', 'LFP')}                  # (GREET 2022 via ICCT 2024, Table A4; lithium as the element)
MAIN = {'nmc_hi': 'Ni', 'nmc_lo': 'Ni', 'lfp': 'Li'}   # the metal a black mass's recycling is counted in


def sets(intensity, lc=None):
    """The network's sets for these chemistries. intensity: {chemistry: {mineral: kg per kWh}}; lc: LIFECYCLE."""
    lc = {**LIFECYCLE, **(lc or {})}
    chems = list(intensity)
    nmc = [c for c in chems if intensity[c].get('Ni', 0) > 0]          # layered oxides need a Ni/Co/Mn precursor
    use_g = [f"{u}_{c}" for u in USES for c in chems]
    out_t = {'mine': list(MINERALS), 'refine': list(METALS), 'pcam': chems, 'anode': ['anode'],
             'cath': chems, 'cell': [f"GWh_{c}" for c in chems], 'use': use_g, 'eol': list(use_g),
             'scrap': [f"GWh_{c}" for c in chems], 'shred': [f"bm_{c}" for c in chems]}
    procs, recipe, coprod, life, caps = [], {}, {}, {}, {}

    def add(p, r):
        procs.append(p); recipe[p] = r
    for m in MINERALS:
        add(('mine', m), {})
    for m in METALS:
        add(('refine', m, m), {('mine', m): 1.0})
    rec = lc["recovery"]
    for c in chems:                              # hydrometallurgy: black mass to its main metal, the others co-products
        main = MAIN[c]
        k = intensity[c][main] * rec[main]       # kt of main metal per GWh-equivalent of black mass
        add(('refine', f"bm_{c}", main), {('shred', f"bm_{c}"): k})
        coprod[('refine', f"bm_{c}", main)] = {('refine', x): intensity[c][x] * rec[x] / k
                                               for x in METALS if x != main and intensity[c].get(x, 0) > 0}
    for c in chems:
        if c in nmc:
            add(('pcam', 'sulfates', c), {('refine', x): 1.0 / intensity[c][x] for x in ('Ni', 'Co', 'Mn')
                                          if intensity[c].get(x, 0) > 0})
        else:                                    # battery-grade FePO4 from iron and purified phosphoric acid (not modelled)
            add(('pcam', 'fepo4', c), {})
    add(('anode', 'natural', 'anode'), {('mine', 'graphite'): 1.0})
    add(('anode', 'synthetic', 'anode'), {})
    for c in chems:
        add(('cath', 'pcam', c), {('refine', 'Li'): 1.0 / intensity[c]['Li'], ('pcam', c): 1.0})
    for c in chems:
        add(('cell', 'cath_anode', f"GWh_{c}"), {('cath', c): 1.0, ('anode', 'anode'): 1.0 / intensity[c]['graphite']})
    for u in USES:                               # new cells placed in each end use, where they are consumed
        for c in chems:
            q = ('use', f"GWh_{c}", f"{u}_{c}")
            add(q, {('cell', f"GWh_{c}"): 1.0})
            life[q] = (('eol', f"{u}_{c}"), lc["life"].get((u, c), lc["life"][u]))
    for c in chems:                              # repurposed EV packs as storage, at their state of health
        q = ('use', f"2nd_{c}", f"storage_{c}")
        add(q, {('eol', f"ev_{c}"): lc["soh"]})
        life[q] = (('eol', f"storage_{c}"), lc["second_life"])
        caps[q] = lc["repurpose"]
    for g in use_g:                              # retired products shredded where they retire
        add(('shred', g, f"bm_{g.split('_', 1)[1]}"), {('eol', g): 1.0})
    for c in chems:                              # manufacturing scrap, shredded where it is made
        add(('shred', f"scrap_{c}", f"bm_{c}"), {('scrap', f"GWh_{c}"): 1.0})
    goods = [(s, g) for s in STAGES for g in out_t[s]]
    mineral_of = {g: (g[1] if g[0] in ('mine', 'refine') else 'graphite' if g[0] == 'anode' else None) for g in goods}
    units = {g: ('kt contained' if g[0] in ('mine', 'refine') else 'kt graphite' if g[0] == 'anode'
                 else 'GWh' if g[0] in ('cell', 'use', 'eol') else 'GWh-equivalent') for g in goods}
    return dict(minerals=list(MINERALS), stages=list(STAGES), goods=goods, mineral_of=mineral_of, processes=procs,
                recipe=recipe, out_t=out_t, units=units,
                max_cap={s: 1e12 for s in STAGES}, init_capacity={s: 0.0 for s in STAGES}, init_active=1,
                max_new_units=0, short_stages=('use',), value_alone=(), short_gwh={},
                life=life, coproducts=coprod, route_caps=caps, scrap={'cell': 'scrap'},
                no_trade=('use', 'eol', 'scrap'), dispose=[('shred', f"bm_{c}") for c in chems],
                collect=lc["collect"])


def network(inputs, losses=None, life=None, repurpose=None, collect=None):
    """(net, params, build options, need) for build() from the inputs (load() makes them).

    inputs: intensity {chem: {mineral: kg/kWh}}; demand {(use, chem, region, year): GWh}; history {(use, chem,
    region, year): GWh placed before the horizon}; other {(good, region, year): kt, the minerals' other uses};
    mine {(mineral, region, year): kt mined}; refined {(metal, year): kt refined in the world};
    share {(stage, key, region, year): share}, key a metal (refine), a chemistry (pcam, cath), 'anode' or 'cell';
    reserves {(mineral, region): spec}; cost_ratio {stage: US/China cost}; losses; lifecycle (LIFECYCLE's keys).
    losses, life ({use: spec, or 'second_life': spec}), repurpose and collect override the inputs' for one run.
    need is {(mineral, year): kt}, demand x intensity over every end use, before losses.
    """
    lc = {**LIFECYCLE, **inputs.get("lifecycle", {})}
    if life:
        lc["life"] = {**lc["life"], **{u: s for u, s in life.items() if u != 'second_life'}}
        lc["second_life"] = life.get('second_life', lc["second_life"])
    if repurpose is not None:
        lc["repurpose"] = repurpose
    if collect is not None:
        lc["collect"] = collect
    I, D, sh = inputs["intensity"], inputs["demand"], inputs["share"]
    net = sets(I, lc)
    net["losses"] = dict(inputs.get("losses", {}) if losses is None else losses)
    chems = list(I)
    gwh = {(c, y): sum(v for (u, c2, _, y2), v in D.items() if (c2, y2) == (c, y)) for c in chems for y in YEARS}
    need = {(m, y): sum(gwh[c, y] * I[c].get(m, 0.0) for c in chems) for m in MINERALS for y in YEARS}
    init_cap, limits = {}, {}
    for p in net["processes"]:
        s = p[0]
        for r in REGIONS:
            if s == 'mine':
                v = {y: inputs["mine"].get((p[1], r, y), 0.0) for y in YEARS}
            elif s == 'refine' and p[1] == p[2] and p[1] in inputs["refined"]:
                v = {y: sh.get(('refine', p[1], r, y), 0.0) * inputs["refined"][p[1]][y] for y in YEARS}
            elif s == 'refine' and p[1] == p[2]:     # manganese: battery-grade sulphate, scaled to the batteries' need
                v = {y: sh.get(('refine', p[1], r, y), 0.0) * need[p[1], y] for y in YEARS}
            elif s == 'anode':                   # each route may use all of the region's anode capacity; limits caps both
                v = {y: sh.get(('anode', 'anode', r, y), 0.0) * need['graphite', y] for y in YEARS}
                limits[('anode', r)] = {y: HEADROOM * x for y, x in v.items()}
            elif s in ('pcam', 'cath'):
                v = {y: sh.get((s, p[-1], r, y), 0.0) * gwh[p[-1], y] for y in YEARS}
            elif s == 'cell':                    # the region's share of every chemistry
                v = {y: sh.get(('cell', 'cell', r, y), 0.0) * gwh[p[-1][4:], y] for y in YEARS}
            else:                                # recycling, end uses, shredding: not limited here
                v = {y: OPEN / HEADROOM for y in YEARS}
            init_cap[p + (r,)] = {y: HEADROOM * x for y, x in v.items()}
    pcost = {'refine_bm': RECYCLE_COST, 'shred': SHRED_COST, 'use': 0.0}
    cost = {}
    for s in STAGES:
        pc = {}
        for p in net["processes"]:
            if p[0] != s:
                continue
            c = (SYNTHETIC_COST if p[1] == 'synthetic' else REPURPOSE_COST if p[1].startswith('2nd_')
                 else pcost['refine_bm'] if s == 'refine' and p[1].startswith('bm_') else pcost.get(s, UNIT_COST))
            pc.update({p[1:] + (r, y): c for r in REGIONS for y in YEARS})
        cost[s] = (pc, {k: 0.0 for k in pc}, {k: 0.0 for k in pc})
    demand = {(('use', f"{u}_{c}"), r, y): v for (u, c, r, y), v in D.items()}
    for k, v in inputs.get("other", {}).items():
        demand[k] = demand.get(k, 0.0) + v
    hist = {(('use', f"GWh_{c}", f"{u}_{c}"), r, y): v for (u, c, r, y), v in inputs.get("history", {}).items()}
    net.update(years=list(YEARS), cost=cost, demand=demand, history=hist,
               reserves={('mine', m, r): s for (m, r), s in inputs.get("reserves", {}).items()})
    ratio = inputs.get("cost_ratio", {})
    alpha_stage = {s: {'CHN': 1.0, 'SPC': 1.0, 'US': ratio.get(s, 1.0), 'ALLY': ratio.get(s, 1.0),
                       'ROW': (1.0 + ratio.get(s, 1.0)) / 2} for s in STAGES}
    params = dict(regions=list(REGIONS), alpha={r: 1.0 for r in REGIONS}, import_coef={r: 1.0 for r in REGIONS},
                  region_share={r: 0.0 for r in REGIONS}, alpha_stage=alpha_stage, init_cap=init_cap,
                  ship_value_share=N.SHIP_VALUE_SHARE, shortage_mult=N.SHORTAGE_MULT, build_every=1)
    return net, params, dict(limits=limits), need


def _read(name):
    return pd.read_csv(DATA / f"{name}.csv")


def load():
    """The inputs, from data/battery_2023_2024/ (every number there has its source in its row):

    intensity  GREET 2022 via ICCT (2024) Table A4, kg per kWh: NMC811 for IEA's high-nickel group, NMC532
               for low-nickel, LFP.
    demand     IEA, battery demand by end use (EV, stationary storage, portable electronics, other applications),
               GWh. EVs by region at IEA's shares of world EV battery demand (EU and other advanced economies ->
               ALLY, other emerging -> ROW), each region at its own chemistry mix (ALLY at the EU's, ROW at the
               world's). Storage by region at IEA's 2024 deployment shares (China half, US a quarter, Europe a tenth;
               the rest ROW), both years, 80% LFP (IEA, 2023) and the rest high-nickel. Electronics and other
               applications by region at IEA's 2023 EV-plus-storage demand shares (the rest ROW); electronics at
               low-nickel NMC (proxy: LiCoO2 is not modelled), other applications at the world EV mix.
    history    the same, 2015-2022, for what retires in 2023-2024: EV shares from 2018 (2015-2017 at 2018's),
               storage at the world's LFP share by year (33% to 2020, 65% in 2022, 2021 between).
    mine       USGS MCS 2025, mine output by country (US lithium is withheld: none), all of it.
    refined    IEA, world refined output: all lithium chemicals, all refined nickel (incl. NPI and ferronickel),
               all refined cobalt. Manganese's battery-grade sulphate is sized to the batteries' need.
    other      the minerals' other uses, where they leave the battery chain. Lithium, nickel, cobalt (refined):
               IEA's other uses (nickel adds its other clean energy uses), less what the modelled electronics and
               other batteries take, split by region as refining is (proxy). Manganese and natural graphite
               (mined): USGS world mine output times the share not for batteries (IEA: 1% of manganese is for
               energy technologies; graphite, one less its clean-energy share of demand), split as mining is.
    reserves   USGS MCS 2025 reserves by country, growing at the world's 2015-2025 rate (MCS 2015 vs 2025),
               up to identified resources (lithium by country; nickel, cobalt and graphite world totals split by
               reserves; manganese has none published, so no ceiling).
    share      refining and anode: IEA GCMO refined output by country (manganese: battery-grade sulphate
               shares). pCAM and cathode: calibration/'s 2024 cathode capacity shares (pCAM at cathode's).
               Cells: IEA capacity by region (2023 by maker's region of plant, 2024 nameplate).
    losses     LOSSES (stage_losses.csv). lifecycle: LIFECYCLE, chosen from lifecycle.csv (120 published values with
               sources: lifetimes, second life, recovery, recycling utilisation, and the evidence that EV batteries
               outlast early assumptions).
    Countries map to regions by regions.csv.
    """
    reg = _read("regions")
    to_r = {(r.name, r.context if isinstance(r.context, str) else ""): r.region for r in reg.itertuples()}

    def region(name, context=""):
        if (name, context) in to_r:
            return to_r[name, context]
        if (name, "") in to_r:
            return to_r[name, ""]
        raise KeyError(f"no region for {name!r} in regions.csv")

    mi = _read("material_intensity")
    mi = mi[mi.unit.str.startswith("kg per kWh")]
    intensity = {c: {NAME[r.mineral]: float(r.value) for r in mi[mi.chemistry == greet].itertuples() if r.value > 0}
                 for c, (greet, _) in CHEMS.items()}

    # ---- demand and history, by end use, chemistry and region
    bu = _read("battery_demand_by_use")
    gw = bu[(bu.unit == "GWh/year") & (bu.country_or_region == "World")]
    label = {'ev': "EV (all modes)", 'storage': "Stationary storage", 'electronics': "Portable electronics",
             'other': "Other applications (e-bikes, hoverboards, drones etc.)"}
    world = {(u, int(r.year)): float(r.value) for u, lab in label.items() for r in gw[gw.chemistry == lab].itertuples()}
    years_all = sorted({y for (_, y) in world if y <= max(YEARS)})

    def norm(d):
        t = sum(d.values())
        return {k: v / t for k, v in d.items()}

    evs = bu[bu.unit == "% of world EV battery demand"]
    ev_share = {}
    for y, g in evs.groupby("year"):
        acc = {}
        for r in g.itertuples():
            acc[region(r.country_or_region)] = acc.get(region(r.country_or_region), 0.0) + r.value
        ev_share[int(y)] = norm(acc)
    st = bu[bu.chemistry == "Stationary storage: regional share of world storage deployment"]
    st_share = {region(r.country_or_region): r.value / 100 for r in st.itertuples()}
    st_share['ROW'] = st_share.get('ROW', 0.0) + 1.0 - sum(st_share.values())
    es = bu[bu.chemistry == "EV + stationary storage: regional share of world demand"]
    es_share = {region(r.country_or_region): r.value / 100 for r in es.itertuples()}
    es_share['ROW'] = es_share.get('ROW', 0.0) + 1.0 - sum(es_share.values())
    lfp = bu[bu.chemistry == "Stationary storage chemistry share: LFP"]
    lfp_st = {int(r.year): r.value / 100 for r in lfp.itertuples()}

    bd = _read("battery_demand")
    mix_src = {'CHN': 'China', 'ALLY': 'European Union', 'US': 'United States', 'ROW': 'World', 'SPC': 'World'}
    cs = bd[(bd.item == "chemistry_share") & bd.chemistry.str.contains(r"\(") & ~bd.chemistry.eq("LFP")]

    def ev_mix(r, y):                            # an EV region's chemistry mix (2023's before 2023)
        rows = cs[(cs.country_or_region == mix_src[r]) & (cs.year == max(y, 2023))]
        return norm({c: float(rows[rows.chemistry.str.startswith(lab)].value.iloc[0]) for c, (_, lab) in CHEMS.items()})

    def st_lfp(y):
        if y in lfp_st:
            return lfp_st[y]
        if y < min(lfp_st):
            return lfp_st[min(lfp_st)]
        lo = max(k for k in lfp_st if k < y); hi = min((k for k in lfp_st if k > y), default=None)
        return lfp_st[lo] if hi is None else lfp_st[lo] + (lfp_st[hi] - lfp_st[lo]) * (y - lo) / (hi - lo)

    demand, history = {}, {}
    for y in years_all:
        out = demand if y in YEARS else history
        evr = ev_share.get(y, ev_share[min(ev_share)])
        for r, s in evr.items():
            for c, f in ev_mix(r, y).items():
                out['ev', c, r, y] = out.get(('ev', c, r, y), 0.0) + world['ev', y] * s * f
        for r, s in st_share.items():
            out['storage', 'lfp', r, y] = world['storage', y] * s * st_lfp(y)
            out['storage', 'nmc_hi', r, y] = world['storage', y] * s * (1 - st_lfp(y))
        world_mix = ev_mix('ROW', y)
        for r, s in es_share.items():
            out['electronics', 'nmc_lo', r, y] = world['electronics', y] * s
            for c, f in world_mix.items():
                out['other', c, r, y] = world['other', y] * s * f

    # ---- mines, refined output, shares
    mp = _read("mine_production")
    mp = mp[~mp.country_or_region.str.startswith("World")]
    mine, mine_world = {}, {}
    for r in mp.itertuples():
        if pd.isna(r.value):
            continue
        kt = r.value if r.unit.startswith("thousand") else r.value / 1000.0
        k = (NAME[r.mineral], region(r.country_or_region), int(r.year))
        mine[k] = mine.get(k, 0.0) + kt
        mine_world[k[0], k[2]] = mine_world.get((k[0], k[2]), 0.0) + kt
    rp = _read("refined_production")
    rw = rp[rp.country_or_region.str.startswith("World") & rp.mineral.isin(['lithium', 'nickel', 'cobalt'])]
    refined = {}
    for r in rw.itertuples():
        refined.setdefault(NAME[r.mineral], {})[int(r.year)] = float(r.value)

    share = {}
    rf = _read("refining_shares")
    out = rf[(rf.item == "refining_output") & (rf.country_or_region != "World") & (rf.mineral != "manganese")]
    for (m, y), g in out.groupby(["mineral", "year"]):
        tot = g.value.sum()
        for r in g.itertuples():
            stage, key = ('anode', 'anode') if m == 'graphite' else ('refine', NAME[m])
            k = (stage, key, region(r.country_or_region), int(y))
            share[k] = share.get(k, 0.0) + r.value / tot
    mn = rf[(rf.mineral == "manganese") & (rf.item == "refining_share")]
    for r in mn.itertuples():
        k = ('refine', 'Mn', region(r.country_or_region), int(r.year))
        share[k] = share.get(k, 0.0) + r.value / 100
    cal = pd.read_csv(N.CAL / "country_shares_2024.csv")
    cath = cal[(cal.model_stage == "cath") & (cal.use == "yes")]
    for r in cath.itertuples():
        for c in (['nmc_hi', 'nmc_lo'] if r.chemistry == 'nmc' else ['lfp']):
            for s in ('pcam', 'cath'):
                for y in YEARS:
                    k = (s, c, region(r.country), y)
                    share[k] = share.get(k, 0.0) + r.value / 100
    cp = _read("cell_production")
    c23 = cp[(cp.item == "cell_capacity") & (cp.year == 2023) & cp.unit.str.startswith("GWh installed")]
    c24 = cp[(cp.item == "cell_capacity") & (cp.year == 2024) & cp.unit.str.startswith("TWh")]
    for y, g in ((2023, c23), (2024, c24)):
        tot = g.value.sum()
        for r in g.itertuples():
            k = ('cell', 'cell', region(r.country_or_region, "cell"), y)
            share[k] = share.get(k, 0.0) + r.value / tot

    # ---- the minerals' other uses
    md = _read("mineral_demand_by_use")
    other = {}
    mod = {(m, y): sum(v * intensity[c].get(m, 0.0) for (u, c, r, yy), v in demand.items()
                       if u in ('electronics', 'other') and yy == y) for m in MINERALS for y in YEARS}
    for m in ('Li', 'Ni', 'Co'):
        full = {v: k for k, v in NAME.items()}[m]
        for y in YEARS:
            rows = md[(md.mineral == full) & (md.year == y)]
            kt = float(rows[rows.chemistry.str.startswith("Other uses")].value.iloc[0])
            if m == 'Ni':
                kt += float(rows[rows.chemistry.str.startswith("Other clean energy")].value.iloc[0])
            kt = max(0.0, kt - mod[m, y])
            for r in REGIONS:
                if share.get(('refine', m, r, y), 0.0) > 0:
                    other[('refine', m), r, y] = kt * share[('refine', m, r, y)]
    mn_e = md[(md.mineral == "manganese")]
    g_rows = md[md.mineral == "graphite"]
    for m in ('Mn', 'graphite'):
        for y in YEARS:
            if m == 'Mn':
                not_batt = 1.0 - float(mn_e[mn_e.year == y].value.iloc[0]) / 100
            else:
                rows = g_rows[g_rows.year == y]
                not_batt = 1.0 - (float(rows[rows.chemistry == "Clean energy total"].value.iloc[0])
                                  / float(rows[rows.chemistry == "Total demand"].value.iloc[0]))
            for r in REGIONS:
                if mine.get((m, r, y), 0.0) > 0:
                    other[('mine', m), r, y] = not_batt * mine[m, r, y]

    # ---- reserves, growing to resources
    rs = _read("reserves")
    agg = ("World", "Other countries (all non-US)", "Rest of world (excl. United States)")

    def kt_of(r):
        u = r.unit
        return r.value * (1000.0 if u.startswith("million") else 1.0 if u.startswith("thousand") else 0.001)
    res_r, world_res = {}, {}
    for r in rs[(rs.item == "reserves")].itertuples():
        if pd.isna(r.value):
            continue
        m = NAME[r.mineral]
        if r.country_or_region.startswith("World"):
            world_res[m, int(r.year)] = kt_of(r)
        elif int(r.year) == 2025:
            k = (m, region(r.country_or_region))
            res_r[k] = res_r.get(k, 0.0) + kt_of(r)
    growth = {m: (world_res[m, 2025] / world_res[m, 2015]) ** (1 / 10) - 1 for m in MINERALS}
    rsc = rs[(rs.item == "resources") & rs.unit.str.startswith("million")]
    resources = {}
    for r in rsc.itertuples():
        m = NAME[r.mineral]
        if r.country_or_region in agg:
            continue
        k = (m, region(r.country_or_region))
        resources[k] = resources.get(k, 0.0) + kt_of(r)
    for r in rsc[rsc.country_or_region.isin(agg)].itertuples():  # a world total: split as reserves are
        m = NAME[r.mineral]
        if m == 'Li':
            continue                             # lithium's resources are by country
        tot = sum(v for (mm, _), v in res_r.items() if mm == m)
        for (mm, rg), v in res_r.items():
            if mm == m:
                resources[m, rg] = kt_of(r) * v / tot
    reserves = {}
    for (m, rg), v in res_r.items():
        spec = {"reserve": v, "growth": growth[m]}
        if (m, rg) in resources:
            spec["resources"] = max(resources[m, rg], v)
        reserves[m, rg] = spec

    sc = pd.read_csv(N.CAL / "stage_costs_us_china.csv").pivot(index="stage", columns="region", values="usd")
    ratio = {'pcam': sc.loc['proc', 'US'] / sc.loc['proc', 'CHN'], 'cath': sc.loc['cath', 'US'] / sc.loc['cath', 'CHN'],
             'cell': sc.loc['cell', 'US'] / sc.loc['cell', 'CHN']}
    return dict(intensity=intensity, demand=demand, history=history, other=other, mine=mine, refined=refined,
                share=share, reserves=reserves, cost_ratio=ratio, losses=dict(LOSSES), lifecycle=dict(LIFECYCLE))


def run(inputs=None, env=None, **kw):
    """Solve and summarise: per mineral and year, what is mined, refined (primary and recycled) and taken by recipes
    (kt), the batteries' need from demand x intensity, unmet demand, each region's share of each stage, the trade by
    stage, and the lifecycle: retired, repurposed and shredded GWh, by year. kw: network()'s overrides."""
    import gurobipy as gp
    from gurobipy import GRB
    net, params, bkw, need = network(inputs or load(), **kw)
    m = gp.Model(env=env); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **bkw)
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()
    if m.SolCount == 0:
        return dict(status=m.Status)
    prod, cons, flow, trade = h["prod"], h["cons"], h["flow"], h["trade"]
    out = dict(status=m.Status, obj=m.ObjVal, need=need, mined={}, refined={}, recycled={}, used={}, share={},
               trade={}, short={k: v.X for k, v in h["short"].items() if v.X > 1e-6},
               retired={}, repurposed={}, shredded={})
    for (n, y), v in prod.items():
        if n[0] == 'mine':
            out["mined"][n[1], y] = out["mined"].get((n[1], y), 0.0) + v.X
        elif n[0] == 'refine' and n[1] == n[2]:
            out["refined"][n[1], y] = out["refined"].get((n[1], y), 0.0) + v.X
        elif n[0] == 'refine':                   # recycled: the main metal and its co-products
            q = n[:-1]
            for g, k in {('refine', n[2]): 1.0, **net["coproducts"][q]}.items():
                out["recycled"][g[1], y] = out["recycled"].get((g[1], y), 0.0) + k * v.X
    for (n, g, y), v in cons.items():
        if g[0] in ('refine', 'anode') and n[0] in ('pcam', 'cath', 'cell'):   # taken by the battery chain's recipes
            k = (g[1] if g[0] == 'refine' else 'graphite', y)
            out["used"][k] = out["used"].get(k, 0.0) + v.X
        if g[0] == 'eol':
            d = out["repurposed" if n[0] == 'use' else "shredded"]
            d[g[1], y] = d.get((g[1], y), 0.0) + v.X
        if g[0] == 'scrap':
            out["shredded"]['scrap', y] = out["shredded"].get(('scrap', y), 0.0) + v.X
    for (g, r, y), e in h["retire"].items():
        x = e.getValue() if hasattr(e, "getValue") else float(e)
        out["retired"][g[1], y] = out["retired"].get((g[1], y), 0.0) + x
    for s in STAGES:
        for y in YEARS:
            tot = sum(v.X for (n, yy), v in prod.items() if n[0] == s and yy == y) or 1.0
            for r in REGIONS:
                out["share"][s, r, y] = sum(v.X for (n, yy), v in prod.items() if n[0] == s and n[-1] == r and yy == y) / tot
        for k, a in enumerate(trade[s]):
            for y in YEARS:
                x = flow[s][k, y].X
                if x > 1e-6:
                    key = (s, a[-3], a[-2], a[-1], y)
                    out["trade"][key] = out["trade"].get(key, 0.0) + x
    return out


if __name__ == "__main__":
    r = run()
    print("status", r["status"], "unmet", r["short"] or "none")
    for y in YEARS:
        print(y, {m: (round(r["need"][m, y], 1), round(r["used"].get((m, y), 0.0), 1)) for m in MINERALS}, "(need, used) kt")
        print(y, "recycled kt", {m: round(r["recycled"].get((m, y), 0.0), 1) for m in METALS},
              "retired GWh", round(sum(v for (g, yy), v in r["retired"].items() if yy == y), 1),
              "repurposed GWh", round(sum(v for (g, yy), v in r["repurposed"].items() if yy == y), 1))

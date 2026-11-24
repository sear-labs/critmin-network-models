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
each is used). Costs are sourced too (data/battery_costs/, costs()): each stage's own cost per unit made, by region,
in USD per kg (million USD per kt) or per kWh (million USD per GWh), so the objective is in million USD. They are
PRELIMINARY: several are price spreads or single projects, and costs() says which.

Mines are pulled by refining, refining by precursor and cathode, and so on down to the end uses: each stage only
by the one after it. Mines have their whole output as capacity, and the minerals' other uses (glass, steel,
alloys...) are demand where they leave the battery chain: refined lithium, nickel and cobalt, and mined natural
graphite (whose other uses do not pass through battery-grade refining). Extraction is within reserves, which grow
at their 2015-2025 rate up to identified resources (network.reserves_available).

Base materials (network's base-materials notes; critmin_net.base): manganese ore, iron and phosphorus, whose supply
dwarfs the batteries' use (USGS: 20 Mt of manganese mined in 2024, 1.6 Gt of iron), are bought in each region at a
price, with no mines, reserves or other uses behind them. Battery-grade manganese sulphate is refined from bought
manganese; battery-grade iron phosphate is made from bought iron and phosphorus. Manganese and iron are priced at
USGS's prices per tonne contained (base.prices()); phosphorus, which USGS gives no contained price for, at what is
left of iron phosphate's price once its iron and conversion are taken out (base_prices()).

Units: mined and refined goods and anode material in kt of contained element (graphite as graphite); precursor,
cathode, cells, end uses, retired products, scrap and black mass in GWh of the cells they serve ("GWh-equivalents").
A recipe's "output per unit input" is then 1 / (kg per kWh), material intensity read directly from the source.

LFP's precursor is battery-grade iron phosphate (FePO4), the pCAM stage's LFP good, with its own capacity and cost,
made from base iron and phosphorus (by mass, FePO4 is 37% iron and 21% phosphorus). 1 kg of lithium in LiFePO4
comes with FEPO4_PER_LI kg of FePO4, so GREET's 0.08 kg of lithium per kWh is about 1.7 kg of FePO4 per kWh: 0.64 kg
of iron and 0.36 kg of phosphorus.

Losses (network.build's `losses`): LOSSES, chosen from stage_losses.csv. A cell's loss is manufacturing scrap,
which is recycled. Lifecycle (LIFECYCLE): lifetimes by end use, the second life, the repurposed share, collection
and recycling recovery; each can be changed per run (network(..., life=, repurpose=, collect=)).

Simplifications, each deliberate for a mechanism test: the anode is made from mined natural graphite or synthetic
graphite (petroleum coke, not modelled), sharing each region's anode capacity, and graphite is not recovered by
recycling; portable electronics are at low-nickel NMC's intensity (their LiCoO2 is not modelled) and "other"
applications at the world EV mix; histories before 2023 use 2023's chemistry mix; capacity is fixed in every year
at the observed level times HEADROOM, so nothing is built.

Calibration (calibrate(); run(calibrated=True)): at sourced costs the cheapest region fills its headroom (China makes
every cell in 2024). calibrate() adds, by positive mathematical programming, a cost rising with output to each region
at each stage with an observed regional split, so the network reproduces the observed shares; the wedges it finds
are what the sourced costs leave unexplained. Off by default.
"""
import pandas as pd

from . import network as N

REGIONS = N.LLNL_REGIONS + ['SPC']
YEARS = [2023, 2024]
MINERALS = ['Li', 'Ni', 'Co', 'Mn', 'graphite']
METALS = ['Li', 'Ni', 'Co', 'Mn']                # refined in the model, and recovered by recycling
MINED = ['Li', 'Ni', 'Co', 'graphite']           # mined in the model, within reserves
BASE = ['Mn', 'Fe', 'P']                         # base materials, bought at a price (kt contained)
USES = ['ev', 'storage', 'electronics', 'other']
STAGES = ['base', 'mine', 'refine', 'pcam', 'anode', 'cath', 'cell', 'use', 'eol', 'scrap', 'shred']
HEADROOM = 1.20                                  # capacity over observed output, as in network.calibrated()
TIE = 0.001                                      # calibrate()'s slope for regions with no wedge, USD per kg or kWh
OPEN = 1e9                                       # capacity where none is modelled (end uses, shredding)
FEPO4_PER_LI = (55.845 + 30.974 + 4 * 15.999) / 6.94   # kg FePO4 per kg Li in LiFePO4 (standard atomic weights)
IN_FEPO4 = {'Fe': 55.845 / (55.845 + 30.974 + 4 * 15.999),  # mass share of iron and phosphorus in FePO4
            'P': 30.974 / (55.845 + 30.974 + 4 * 15.999)}
CUT = {m: ('refine', m) for m in METALS}         # where zoom() cuts each mineral: its battery-grade good
CUT['graphite'] = ('anode', 'anode')             # (graphite: anode material, so anode plants go with its mines)
DATA = N.RAW / "battery_2023_2024"
COSTS = N.RAW / "battery_costs"
# How costs() fills a region data/battery_costs/selected.csv does not give: the US and allies at China's cost times
# a ratio (these keys: RATIO's; others as given), the rest of the world halfway between China and the US (as
# network.calibrated() prices it), the DRC at China's. Mines are given for every region.
RATIO = dict(refine_Li='chem', refine_Ni='chem', refine_Co='chem', refine_Mn='chem', anode_natural='chem',
             anode_synthetic='chem', fepo4_conv='chem', shred='recycle_nmc', recycle_nmc='recycle_nmc',
             recycle_lfp='recycle_lfp')
SAME_EVERYWHERE = ('cell_materials', 'repurpose', 'fepo4_price', 'fepo4_conversion_share')
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


def costs():
    """{(key, region, year): cost}, from data/battery_costs/selected.csv (one row per number: its value, unit, basis,
    the source rows it comes from in sources_upstream.csv and sources_midstream.csv, and the arithmetic). Every stage's
    own cost per unit made: purchased inputs the network models are counted where they are made, not here.

    mine_<m>         USD per kg contained, by region, from each region's operations (lithium: Chinese lepidolite,
                     Australian operations' median, Brazilian hard rock; nickel: Indonesian HPAL to MHP, Australian and
                     US sulphide, IEA's all-in cost for China; graphite: Mozambique, Canadian and US studies, a Chinese
                     price). Cobalt is a by-product with no cost of its own: priced at hydroxide payables x LME cobalt.
    refine_<m>       conversion to battery grade in China, feed excluded; other regions by the 'chem' ratio.
    pcam_nmc, cath,  the Stanford GSB model's labour and electricity per kWh in China, the US and Korea (the allies),
    cell_proc        excluding capital and materials; NMC811's, used for every chemistry.
    cell_materials   separator, electrolyte, foils and casing per kWh (bought; the same everywhere).
    fepo4_conv       iron phosphate's conversion per kg: fepo4_conversion_share of its price (the rest is iron and
                     phosphorus, priced as base materials).
    anode_<route>    price spreads (natural: anode less the flake in it; synthetic: the anode, feed included), IEA.
    shred, recycle_  shredding per kWh, and hydrometallurgy per kWh of black mass, China; other regions by recycling's
    nmc, recycle_lfp US/China and Europe/China ratios.
    repurpose        per kWh of second-life storage, every region (no regional data).
    Capital costs are in the source tables but not used: capacity is fixed here, so nothing is built.
    """
    d = pd.read_csv(COSTS / "selected.csv")
    raw = {}
    for r in d.itertuples():
        for y in (YEARS if pd.isna(r.year) else [int(r.year)]):
            raw[r.key, r.region, y] = float(r.value)
    for y in YEARS:
        raw['fepo4_conv', 'CHN', y] = raw['fepo4_conversion_share', 'CHN', y] * raw['fepo4_price', 'CHN', y]
    out = {}
    for k in sorted({k for k, _, _ in raw if not k.startswith('ratio_')}):
        for y in YEARS:
            chn = raw[k, 'CHN', y]
            for r in ('CHN', 'US', 'ALLY', 'ROW', 'SPC'):
                if (k, r, y) in raw:
                    v = raw[k, r, y]
                elif k in SAME_EVERYWHERE:
                    v = chn
                elif r in ('US', 'ALLY'):
                    v = chn * raw[f"ratio_{RATIO[k]}", r, y]
                else:
                    v = (chn + out[k, 'US', y]) / 2 if r == 'ROW' else chn
                out[k, r, y] = v
    return out


def base_prices(c=None):
    """{material: {year: USD per kg contained}} for the base materials: manganese and iron at USGS's prices per tonne
    contained (base.prices(): 44% ore CIF China; US iron ore over its grade); phosphorus at iron phosphate's price
    less its conversion and its iron, per kg of phosphorus in it (derived: USGS gives no contained price)."""
    from . import base
    c = costs() if c is None else c
    p = base.prices()
    out = {'Mn': {y: p['manganese', y] / 1000 for y in YEARS}, 'Fe': {y: p['iron_ore', y] / 1000 for y in YEARS}}
    out['P'] = {y: (c['fepo4_price', 'CHN', y] - c['fepo4_conv', 'CHN', y] - out['Fe'][y] * IN_FEPO4['Fe'])
                / IN_FEPO4['P'] for y in YEARS}
    return out


def sets(intensity, lc=None):
    """The network's sets for these chemistries. intensity: {chemistry: {mineral: kg per kWh}}; lc: LIFECYCLE.
    Base materials come with no price; network() prices them."""
    lc = {**LIFECYCLE, **(lc or {})}
    chems = list(intensity)
    nmc = [c for c in chems if intensity[c].get('Ni', 0) > 0]          # layered oxides need a Ni/Co/Mn precursor
    use_g = [f"{u}_{c}" for u in USES for c in chems]
    out_t = {'base': list(BASE), 'mine': list(MINED), 'refine': list(METALS), 'pcam': chems, 'anode': ['anode'],
             'cath': chems, 'cell': [f"GWh_{c}" for c in chems], 'use': use_g, 'eol': list(use_g),
             'scrap': [f"GWh_{c}" for c in chems], 'shred': [f"bm_{c}" for c in chems]}
    procs, recipe, coprod, life, caps = [], {}, {}, {}, {}

    def add(p, r):
        procs.append(p); recipe[p] = r
    for m in MINED:
        add(('mine', m), {})
    for m in METALS:                             # manganese sulphate from bought manganese; the others from mines
        add(('refine', m, m), {(('base' if m in BASE else 'mine'), m): 1.0})
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
        else:                                    # battery-grade FePO4 from bought iron and phosphorus
            fepo4 = FEPO4_PER_LI * intensity[c]['Li']                   # kg FePO4 per kWh
            add(('pcam', 'fepo4', c), {('base', x): 1.0 / (fepo4 * IN_FEPO4[x]) for x in ('Fe', 'P')})
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
    mineral_of = {g: (g[1] if g[0] in ('mine', 'refine') or g == ('base', 'Mn') else 'graphite' if g[0] == 'anode'
                      else None) for g in goods}
    units = {g: ('kt contained' if g[0] in ('base', 'mine', 'refine') else 'kt graphite' if g[0] == 'anode'
                 else 'GWh' if g[0] in ('cell', 'use', 'eol') else 'GWh-equivalent') for g in goods}
    return dict(minerals=list(MINERALS), stages=list(STAGES), goods=goods, mineral_of=mineral_of, processes=procs,
                recipe=recipe, out_t=out_t, units=units,
                max_cap={s: 1e12 for s in STAGES}, init_capacity={s: 0.0 for s in STAGES}, init_active=1,
                max_new_units=0, short_stages=('use',), value_alone=(), short_gwh={},
                life=life, coproducts=coprod, route_caps=caps, scrap={'cell': 'scrap'},
                no_trade=('use', 'eol', 'scrap'), dispose=[('shred', f"bm_{c}") for c in chems],
                collect=lc["collect"], base={('base', x): {} for x in BASE})


def network(inputs, losses=None, life=None, repurpose=None, collect=None, base=None, quad=None):
    """(net, params, build options, need) for build() from the inputs (load() makes them).

    inputs: intensity {chem: {mineral: kg/kWh}}; demand {(use, chem, region, year): GWh}; history {(use, chem,
    region, year): GWh placed before the horizon}; other {(good, region, year): kt, the minerals' other uses};
    mine {(mineral, region, year): kt mined}; refined {(metal, year): kt refined in the world};
    share {(stage, key, region, year): share}, key a metal (refine), a chemistry (pcam, cath), 'anode' or 'cell';
    reserves {(mineral, region): spec}; costs (costs()); losses; lifecycle (LIFECYCLE's keys).
    losses, life ({use: spec, or 'second_life': spec}), repurpose and collect override the inputs' for one run;
    base {material: spec} replaces a base material's spec (network's base-materials notes: a price, caps).
    quad: calibrate()'s quadratic costs (build()'s quad_cost); None for none.
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
    if set(base or {}) - set(BASE):
        raise ValueError(f"base: {sorted(set(base) - set(BASE))} are not base materials here ({BASE})")
    C = inputs["costs"]
    net["base"] = {('base', x): {"price": v} for x, v in base_prices(C).items()}
    net["base"].update({('base', x): s for x, s in (base or {}).items()})
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
    def unit_cost(p, r, y):                      # costs(): per kt, GWh or GWh-equivalent made (million USD)
        s = p[0]
        if s == 'mine':
            return C[f"mine_{p[1]}", r, y]
        if s == 'refine' and p[1] == p[2]:
            return C[f"refine_{p[1]}", r, y]
        if s == 'refine':                        # hydrometallurgy, per kWh of black mass, so per kt of its main metal
            c = p[1][3:]
            return C['recycle_lfp' if MAIN[c] == 'Li' else 'recycle_nmc', r, y] / net["recipe"][p][('shred', p[1])]
        if s == 'pcam':                          # NMC precursor per kWh; iron phosphate per kg, times kg per kWh
            return (C['pcam_nmc', r, y] if p[1] == 'sulfates'
                    else C['fepo4_conv', r, y] * FEPO4_PER_LI * I[p[2]]['Li'])
        if s == 'anode':
            return C[f"anode_{p[1]}", r, y]
        if s == 'cath':
            return C['cath', r, y]
        if s == 'cell':
            return C['cell_proc', r, y] + C['cell_materials', r, y]
        if s == 'use':                           # repurposing; new cells placed in an end use cost nothing more
            return C['repurpose', r, y] if p[1].startswith('2nd_') else 0.0
        return C['shred', r, y]
    cost = {}
    for s in STAGES:
        pc = {p[1:] + (r, y): unit_cost(p, r, y) for p in net["processes"] if p[0] == s for r in REGIONS for y in YEARS}
        cost[s] = (pc, {k: 0.0 for k in pc}, {k: 0.0 for k in pc})
    demand = {(('use', f"{u}_{c}"), r, y): v for (u, c, r, y), v in D.items()}
    for k, v in inputs.get("other", {}).items():
        demand[k] = demand.get(k, 0.0) + v
    hist = {(('use', f"GWh_{c}", f"{u}_{c}"), r, y): v for (u, c, r, y), v in inputs.get("history", {}).items()}
    net.update(years=list(YEARS), cost=cost, demand=demand, history=hist,
               reserves={('mine', m, r): s for (m, r), s in inputs.get("reserves", {}).items() if m in MINED})
    alpha_stage = {s: {r: 1.0 for r in REGIONS} for s in STAGES}     # regions differ in the costs themselves
    params = dict(regions=list(REGIONS), alpha={r: 1.0 for r in REGIONS}, import_coef={r: 1.0 for r in REGIONS},
                  region_share={r: 0.0 for r in REGIONS}, alpha_stage=alpha_stage, init_cap=init_cap,
                  ship_value_share=N.SHIP_VALUE_SHARE, shortage_mult=N.SHORTAGE_MULT, build_every=1)
    bkw = dict(limits=limits)
    if quad:
        bkw["quad_cost"] = quad
    return net, params, bkw, need


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
               Manganese's is not used: manganese is a base material, bought at a price.
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
    g_rows = md[md.mineral == "graphite"]
    for y in YEARS:                              # natural graphite's other uses (manganese's are outside the network)
        rows = g_rows[g_rows.year == y]
        not_batt = 1.0 - (float(rows[rows.chemistry == "Clean energy total"].value.iloc[0])
                          / float(rows[rows.chemistry == "Total demand"].value.iloc[0]))
        for r in REGIONS:
            if mine.get(('graphite', r, y), 0.0) > 0:
                other[('mine', 'graphite'), r, y] = not_batt * mine['graphite', r, y]

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
    growth = {m: (world_res[m, 2025] / world_res[m, 2015]) ** (1 / 10) - 1 for m in MINED}
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
        if m not in MINED:
            continue
        spec = {"reserve": v, "growth": growth[m]}
        if (m, rg) in resources:
            spec["resources"] = max(resources[m, rg], v)
        reserves[m, rg] = spec

    return dict(intensity=intensity, demand=demand, history=history, other=other, mine=mine, refined=refined,
                share=share, reserves=reserves, costs=costs(), losses=dict(LOSSES), lifecycle=dict(LIFECYCLE))


def _group(n):
    """The observed-share group of node n (calibrate()): (stage, key), or None where no regional split is observed."""
    s = n[0]
    if s == 'mine':
        return ('mine', n[1])
    if s == 'refine' and n[1] == n[2]:
        return ('refine', n[1])
    if s == 'anode':
        return ('anode', 'anode')
    if s in ('pcam', 'cath'):
        return (s, n[-2])
    if s == 'cell':
        return ('cell', 'cell')
    return None


def calibrate(inputs=None, env=None, tie=TIE, **kw):
    """Calibrate the network to the observed regional shares, by positive mathematical programming (Howitt 1995).

    Each stage with an observed regional split (mining, primary refining, anode, pCAM and cathode by chemistry, and
    cells: the shares that set capacity in network(); load() gives their sources) has a target in each region and
    year: the region's observed share of what the model makes at that stage. Step 1 solves with each region's output
    held at or below its target (integers fixed from an unheld solve), and the targets are recomputed from that
    solve's totals until they stop moving (they move a little as output shifts between regions). The dual of each
    hold, its wedge, is what the region's sourced costs leave unexplained: how much cheaper per unit it is than its
    observed share implies (policy, contracts, logistics, or a cost wrongly sourced). Step 2 replaces each hold with
    a cost that rises with output, 0.5 * gamma * x^2 with gamma = (wedge + tie) / target, so that each region's
    marginal cost at its target is its sourced cost plus its wedge plus `tie`: step 1's plan, without the holds.
    `tie` (USD per kg or kWh) gives the regions with no wedge a slope too, so regions with equal costs (cobalt
    mines, priced alike everywhere) split in proportion to their targets rather than arbitrarily. Prices are step
    1's plus about `tie`, except where step 1's price is not unique (a region that only imports the good).

    For 2023 and 2024 only: a projection needs a rule for gamma as capacity grows (the horizon work).
    kw: network()'s overrides. Returns dict(quad: network()'s `quad`, target and wedge: {((stage, key), region,
    year): units, and USD per unit}, iterations: step-1 solves).
    """
    import gurobipy as gp
    from gurobipy import GRB, quicksum
    net, params, bkw, _ = network(inputs or load(), **kw)
    cap, lim = params["init_cap"], bkw["limits"]
    G = {}
    for p in net["processes"]:
        for r in REGIONS:
            g = _group(p + (r,))
            if g:
                for y in YEARS:
                    G.setdefault((g, r, y), []).append(p + (r,))
    obs = {k: (lim[('anode', k[1])][k[2]] if k[0][0] == 'anode' else sum(cap[n][k[2]] for n in ns)) / HEADROOM
           for k, ns in G.items()}
    otot = {}
    for (g, r, y), v in obs.items():
        otot[g, y] = otot.get((g, y), 0.0) + v

    def solve(fix=None, target=None):
        m = gp.Model(env=env); m.Params.OutputFlag = 0
        obj, h = N.build(m, params, net=net, fix_int=fix, **bkw)
        hold = {k: m.addConstr(quicksum(h["prod"][n, k[2]] for n in ns) <= target[k] * (1 + 1e-9) + 1e-9)
                for k, ns in G.items()} if target else {}
        m.setObjective(obj, GRB.MINIMIZE); m.optimize()
        if m.Status != GRB.OPTIMAL:
            raise RuntimeError(f"calibrate: a solve ended with status {m.Status}")
        tot = {}
        for (g, r, y), ns in G.items():
            tot[g, y] = tot.get((g, y), 0.0) + sum(h["prod"][n, y].X for n in ns)
        ints = dict(inv={k: round(v.X) for k, v in h["inv"].items()}, act={k: round(v.X) for k, v in h["act"].items()})
        return {k: max(0.0, -c.Pi) for k, c in hold.items()}, tot, ints

    _, tot, fix = solve()
    for it in range(1, 21):
        target = {k: obs[k] / otot[k[0], k[2]] * tot[k[0], k[2]] if otot[k[0], k[2]] else 0.0 for k in G}
        wedge, t1, _ = solve(fix, target)
        moved = max(abs(t1[k] - tot[k]) / max(tot[k], 1e-9) for k in t1)
        tot = t1
        if moved < 1e-7:
            break
    else:
        raise RuntimeError("calibrate: the targets did not settle in 20 solves")
    quad = [(G[k], k[2], (wedge[k] + tie) / target[k]) for k in G if target[k] > 1e-9]
    return dict(quad=quad, target=target, wedge=wedge, iterations=it)


def zoom(focus, inputs=None, env=None, caps=True, calibrated=False, **kw):
    """The network zoomed in on the minerals in `focus`: every other mineral is cut at its battery-grade good (CUT)
    and bought at its price in the whole network (network.zoom: price, value and, with caps, quantities), so the
    focus minerals' chains are the whole network's. calibrated: with calibrate()'s costs (in both).
    kw: network()'s overrides. Returns (net, params, build options, need, info), info from network.zoom."""
    if not focus or set(focus) - set(MINERALS) or set(focus) == set(MINERALS):
        raise ValueError(f"focus: some, not all, of {MINERALS}")
    inputs = inputs or load()
    if calibrated and "quad" not in kw:
        kw["quad"] = calibrate(inputs, env, **kw)["quad"]
    net, params, bkw, need = network(inputs, **kw)
    z, info = N.zoom([CUT[m] for m in MINERALS if m not in focus], params, net=net, caps=caps, env=env, **bkw)
    return z, params, bkw, need, info


def run(inputs=None, env=None, focus=None, calibrated=False, **kw):
    """Solve and summarise: per mineral and year, what is mined, bought (base materials), refined (primary and recycled) and taken by recipes
    (kt), the batteries' need from demand x intensity, unmet demand, each region's share of each stage, the trade by
    stage, and the lifecycle: retired, repurposed and shredded GWh, by year. focus: zoom in on these minerals
    (zoom(); the others' cut goods are reported as bought). calibrated: with calibrate()'s costs, and its wedges
    reported. kw: network()'s overrides."""
    import gurobipy as gp
    from gurobipy import GRB
    inputs = inputs or load()
    cal = None
    if calibrated and "quad" not in kw:
        cal = calibrate(inputs, env, **kw)
        kw["quad"] = cal["quad"]
    if focus:
        net, params, bkw, need, _ = zoom(focus, inputs, env, **kw)
    else:
        net, params, bkw, need = network(inputs or load(), **kw)
    m = gp.Model(env=env); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **bkw)
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()
    if m.SolCount == 0:
        return dict(status=m.Status)
    prod, cons, flow, trade = h["prod"], h["cons"], h["flow"], h["trade"]
    out = dict(status=m.Status, obj=m.ObjVal, need=need, mined={}, bought={}, refined={}, recycled={}, used={}, share={},
               trade={}, short={k: v.X for k, v in h["short"].items() if v.X > 1e-6},
               retired={}, repurposed={}, shredded={}, wedge=cal["wedge"] if cal else {})
    for (n, y), v in prod.items():
        if n[0] == 'mine':
            out["mined"][n[1], y] = out["mined"].get((n[1], y), 0.0) + v.X
        elif n[0] == 'refine' and n[1] == n[2]:
            out["refined"][n[1], y] = out["refined"].get((n[1], y), 0.0) + v.X
        elif n[0] == 'refine':                   # recycled: the main metal and its co-products
            q = n[:-1]
            for g, k in {('refine', n[2]): 1.0, **net["coproducts"][q]}.items():
                out["recycled"][g[1], y] = out["recycled"].get((g[1], y), 0.0) + k * v.X
    for (g, r, y), v in h["buy"].items():
        out["bought"][g[1], y] = out["bought"].get((g[1], y), 0.0) + v.X
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

"""A multi-mineral battery network on critmin-net's sets, 2023-2024: a test that the mechanism works. PRELIMINARY.

Lithium, nickel, cobalt, manganese and graphite, through mining, refining, precursor (pCAM), anode, cathode and
cells, on LLNL's regions plus "Special" (the DRC, for cobalt). Built by the same build() as the lithium model,
with the network passed as data (network.LITHIUM explains the format). It is not a calibration. The quantities
are real, read from public sources (data/battery_2023_2024/, one row per number with its source; load() says
how each is used): mine output, the share of each mineral going to EV batteries, refining and manufacturing
shares, EV battery demand by region and chemistry, and material intensities. Every cost is a placeholder, so
where production lands within the regions' capacities follows those placeholders. What it tests: recipes with
several inputs, several minerals in one network, trade between them, and that the observed years can be
supplied from the observed capacities.

Units: mined and refined goods and anode material in kt of contained element (graphite as graphite); precursor,
cathode and cells in GWh of the cells they serve (pCAM and cathode as "GWh-equivalents"). A recipe's
"output per unit input" is then 1 / (kg per kWh): material intensity read directly from the source.

Simplifications, each deliberate for a mechanism test: refining recovers every unit of contained element; the
anode is made from mined natural graphite one for one or from synthetic graphite (petroleum coke, not modelled
as an input), the two routes sharing each region's anode capacity; LFP cathode takes lithium only (iron
phosphate is not critical); no recycling, no storage batteries; capacity is fixed in every year at the observed
level times HEADROOM, so nothing is built.
"""
import pandas as pd

from . import network as N

REGIONS = N.LLNL_REGIONS + ['SPC']
YEARS = [2023, 2024]
MINERALS = ['Li', 'Ni', 'Co', 'Mn', 'graphite']
STAGES = ['mine', 'refine', 'pcam', 'anode', 'cath', 'cell']
HEADROOM = 1.20                                  # capacity over observed output, as in network.calibrated()
UNIT_COST = 1.0                                  # PLACEHOLDER: every stage's cost per unit in China; regions differ
                                                 # only by the Stanford GSB US/China ratios, as calibrated() uses
SYNTHETIC_COST = 3.0                             # PLACEHOLDER: synthetic anode graphite per unit, above natural's (mined
                                                 # plus processed, 2.0), so mined flake is used first, as it is cheaper
DATA = N.RAW / "battery_2023_2024"
NAME = {'lithium': 'Li', 'nickel': 'Ni', 'cobalt': 'Co', 'manganese': 'Mn', 'graphite': 'graphite'}
CHEMS = {'nmc_hi': ('NMC811', 'High-nickel'),    # IEA's high-nickel group (NMC622/721/811, NCA) at NMC811's intensity
         'nmc_lo': ('NMC532', 'Low-nickel'),     # IEA's low-nickel group (NMC333/442/532) at NMC532's
         'lfp': ('LFP', 'LFP')}                  # (GREET 2022 via ICCT 2024, Table A4; lithium as the element)


def sets(intensity):
    """The network's sets for these chemistries. intensity: {chemistry: {mineral: kg per kWh}}."""
    chems = list(intensity)
    nmc = [c for c in chems if intensity[c].get('Ni', 0) > 0]          # layered oxides need a Ni/Co/Mn precursor
    out_t = {'mine': list(MINERALS), 'refine': ['Li', 'Ni', 'Co', 'Mn'], 'pcam': nmc, 'anode': ['anode'],
             'cath': chems, 'cell': [f"GWh_{c}" for c in chems]}
    procs, recipe = [], {}

    def add(p, r):
        procs.append(p); recipe[p] = r
    for m in MINERALS:
        add(('mine', m), {})
    for m in out_t['refine']:
        add(('refine', m, m), {('mine', m): 1.0})
    for c in nmc:
        add(('pcam', 'sulfates', c), {('refine', x): 1.0 / intensity[c][x] for x in ('Ni', 'Co', 'Mn')
                                      if intensity[c].get(x, 0) > 0})
    add(('anode', 'natural', 'anode'), {('mine', 'graphite'): 1.0})
    add(('anode', 'synthetic', 'anode'), {})
    for c in chems:
        r = {('refine', 'Li'): 1.0 / intensity[c]['Li']}
        if c in nmc:
            r[('pcam', c)] = 1.0
        add(('cath', 'pcam' if c in nmc else 'fepo4', c), r)
    for c in chems:
        add(('cell', 'cath_anode', f"GWh_{c}"), {('cath', c): 1.0, ('anode', 'anode'): 1.0 / intensity[c]['graphite']})
    goods = [(s, g) for s in STAGES for g in out_t[s]]
    mineral_of = {g: (g[1] if g[0] in ('mine', 'refine') else 'graphite' if g[0] == 'anode' else None) for g in goods}
    return dict(minerals=list(MINERALS), stages=list(STAGES), goods=goods, mineral_of=mineral_of, processes=procs,
                recipe=recipe, out_t=out_t,
                max_cap={s: 1e9 for s in STAGES}, init_capacity={s: 0.0 for s in STAGES}, init_active=1,
                max_new_units=0, short_stages=('cell',), value_alone=(), short_gwh={})


def network(inputs):
    """(net, params, build options, need) for build() from the inputs (load() makes them).

    inputs: intensity {chem: {mineral: kg/kWh}}; demand {(chem, region, year): GWh};
    mine {(mineral, region, year): kt available to EV batteries}; share {(stage, key, region, year): share},
    key a mineral (refine), a chemistry (pcam, cath), 'anode' or 'cell'; cost_ratio {stage: US/China cost}.
    need is {(mineral, year): kt}, demand x intensity, the world's requirement.
    """
    net = sets(inputs["intensity"])
    I, D, sh = inputs["intensity"], inputs["demand"], inputs["share"]
    gwh = {(c, y): sum(v for (c2, _, y2), v in D.items() if (c2, y2) == (c, y)) for c in I for y in YEARS}
    need = {(m, y): sum(gwh[c, y] * I[c].get(m, 0.0) for c in I) for m in MINERALS for y in YEARS}
    init_cap, limits = {}, {}
    for p in net["processes"]:
        s = p[0]
        for r in REGIONS:
            if s == 'mine':
                v = {y: inputs["mine"].get((p[1], r, y), 0.0) for y in YEARS}
            elif s == 'refine':
                v = {y: sh.get(('refine', p[1], r, y), 0.0) * need[p[1], y] for y in YEARS}
            elif s == 'anode':                   # each route may use all of the region's anode capacity; limits caps both
                v = {y: sh.get(('anode', 'anode', r, y), 0.0) * need['graphite', y] for y in YEARS}
                limits[('anode', r)] = {y: HEADROOM * x for y, x in v.items()}
            elif s in ('pcam', 'cath'):
                v = {y: sh.get((s, p[-1], r, y), 0.0) * gwh[p[-1], y] for y in YEARS}
            else:                                # cells: the region's share of every chemistry
                v = {y: sh.get(('cell', 'cell', r, y), 0.0) * gwh[p[-1][4:], y] for y in YEARS}
            init_cap[p + (r,)] = {y: HEADROOM * x for y, x in v.items()}
    cost = {}
    for s in STAGES:
        pc = {p[1:] + (r, y): (SYNTHETIC_COST if p[1] == 'synthetic' else UNIT_COST)
              for p in net["processes"] if p[0] == s for r in REGIONS for y in YEARS}
        cost[s] = (pc, {k: 0.0 for k in pc}, {k: 0.0 for k in pc})
    net.update(years=list(YEARS), cost=cost, demand={(('cell', f"GWh_{c}"), r, y): v for (c, r, y), v in D.items()})
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
    demand     IEA GEVO 2025: the world's EV battery demand (750 GWh in 2023; "more than 950" in 2024, taken as
               950) times each region's share (EU and other advanced economies -> ALLY, other emerging -> ROW),
               normalised, times that region's chemistry mix (ALLY at the EU's; ROW at the world's).
    mine       USGS MCS 2025, mine output by country (US lithium is withheld: none), times the share of each
               mineral's demand that is EV batteries (IEA GCMO: EV battery demand over total demand; manganese
               at "energy technologies, about 1%"; natural graphite at graphite's share, synthetic included).
    share      refining and anode: IEA GCMO refined output by country (nickel: all refined products, as no
               battery-grade split is given; manganese: battery-grade sulphate shares; 2023 gives China's only).
               pCAM and cathode: calibration/'s 2024 cathode capacity shares, both years (no pCAM data: pCAM at
               cathode's shares). Cells: IEA capacity by region (2023 by maker's region of plant, 2024 nameplate).
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

    bd = _read("battery_demand")
    world = {2023: float(bd[(bd.item == "battery_demand") & (bd.country_or_region == "World") & (bd.year == 2023)
                            & bd.unit.str.contains("EV batteries")].value.iloc[0]),
             2024: float(bd[(bd.item == "battery_demand") & (bd.country_or_region == "World") & (bd.year == 2024)
                            & bd.unit.str.contains(r"\(EV batteries\)")].value.iloc[0])}
    ds = bd[bd.item == "battery_demand_share"]
    mix_src = {'CHN': 'China', 'ALLY': 'European Union', 'US': 'United States', 'ROW': 'World'}
    cs = bd[(bd.item == "chemistry_share") & bd.chemistry.str.contains(r"\(") & ~bd.chemistry.eq("LFP")]
    demand = {}
    for y in YEARS:
        by_r = {}
        for r in ds[ds.year == y].itertuples():
            k = region(r.country_or_region)
            by_r[k] = by_r.get(k, 0.0) + r.value
        tot = sum(by_r.values())
        for k, v in by_r.items():
            rows = cs[(cs.country_or_region == mix_src[k]) & (cs.year == y)]
            mix = {c: float(rows[rows.chemistry.str.startswith(label)].value.iloc[0]) for c, (_, label) in CHEMS.items()}
            mt = sum(mix.values())
            for c in CHEMS:
                demand[c, k, y] = world[y] * v / tot * mix[c] / mt

    bs = _read("battery_share_of_demand")
    ev = {}
    for m in ('lithium', 'nickel', 'cobalt', 'graphite'):
        for y in YEARS:
            num = bs[(bs.item == "battery_demand_component") & (bs.mineral == m) & (bs.chemistry == "EV batteries")
                     & (bs.year == y)].value.iloc[0]
            den = bs[(bs.item == "total_demand") & (bs.mineral == m) & (bs.year == y)].value.iloc[0]
            ev[NAME[m], y] = float(num) / float(den)
    mn = bs[(bs.mineral == "manganese") & (bs.item == "clean_energy_share")]
    for y in YEARS:
        ev['Mn', y] = float(mn[mn.year == y].value.iloc[0]) / 100
    mp = _read("mine_production")
    mp = mp[~mp.country_or_region.str.startswith("World")]
    mine = {}
    for r in mp.itertuples():
        if pd.isna(r.value):
            continue
        kt = r.value if r.unit.startswith("thousand") else r.value / 1000.0
        k = (NAME[r.mineral], region(r.country_or_region), int(r.year))
        mine[k] = mine.get(k, 0.0) + kt * ev[k[0], k[2]]

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
            for s in (('pcam', 'cath') if c != 'lfp' else ('cath',)):
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

    sc = pd.read_csv(N.CAL / "stage_costs_us_china.csv").pivot(index="stage", columns="region", values="usd")
    ratio = {'pcam': sc.loc['proc', 'US'] / sc.loc['proc', 'CHN'], 'cath': sc.loc['cath', 'US'] / sc.loc['cath', 'CHN'],
             'cell': sc.loc['cell', 'US'] / sc.loc['cell', 'CHN']}
    return dict(intensity=intensity, demand=demand, mine=mine, share=share, cost_ratio=ratio)


def run(inputs=None, env=None):
    """Solve and summarise: per mineral and year, what is mined, refined and taken by recipes (kt), the world's
    need from demand x intensity, unmet cells, each region's share of each stage, and the trade by stage."""
    import gurobipy as gp
    from gurobipy import GRB
    net, params, kw, need = network(inputs or load())
    m = gp.Model(env=env); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **kw)
    m.setObjective(obj, GRB.MINIMIZE); m.optimize()
    if m.SolCount == 0:
        return dict(status=m.Status)
    prod, cons, flow, trade = h["prod"], h["cons"], h["flow"], h["trade"]
    out = dict(status=m.Status, obj=m.ObjVal, need=need, mined={}, refined={}, used={}, share={}, trade={},
               short={k: v.X for k, v in h["short"].items() if v.X > 1e-6})
    for (n, y), v in prod.items():
        if n[0] in ('mine', 'refine'):
            d = out["mined" if n[0] == 'mine' else "refined"]
            d[n[1], y] = d.get((n[1], y), 0.0) + v.X
    for (n, g, y), v in cons.items():             # refined minerals and anode graphite, as recipes took them
        if g[0] in ('refine', 'anode'):
            k = (g[1] if g[0] == 'refine' else 'graphite', y)
            out["used"][k] = out["used"].get(k, 0.0) + v.X
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

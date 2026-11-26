"""Checks that solve the battery network and its horizon, so they need a full Gurobi licence. Skipped without one.

    pytest -q -m solver        # on a licensed machine, a few minutes

The engine's own mechanics are checked on a toy network in tests/test_lifecycle.py, which the pip wheel's licence
solves. The battery model's objectives are compared with tests/baseline/battery_0.16.0.json to 1e-6; a change that
moves them on purpose regenerates that file and says why in the commit and CHANGELOG.md.
"""
import json
from pathlib import Path

import pytest

gp = pytest.importorskip("gurobipy")
BASE = json.loads((Path(__file__).parent / "baseline" / "battery_0.16.0.json").read_text())


def _full_licence():
    """The pip wheel's licence imports and solves small models; it refuses above 2,000 variables.
    Probe by solving, not by declaring: the limit is enforced at optimize()."""
    try:
        env = gp.Env(empty=True); env.setParam("OutputFlag", 0); env.start()
        m = gp.Model(env=env); x = m.addVars(2100); m.setObjective(x.sum()); m.optimize()
        return True
    except gp.GurobiError:
        return False


pytestmark = [pytest.mark.solver,
              pytest.mark.skipif(not _full_licence(), reason="needs a full Gurobi licence")]


@pytest.fixture(scope="module")
def N():
    from critmin_net import network
    return network


@pytest.fixture(scope="module")
def battery():
    from critmin_net import battery as B
    return B, B.run(losses={}, repurpose=0.0)    # no losses and no repurposed packs standing in for new cells:
                                                 # every mineral taken in exactly demand x intensity


@pytest.fixture(scope="module")
def battery_default():
    from critmin_net import battery as B
    return B, B.load(), B.run()                  # the published defaults: losses, lifetimes, repurposing, recovery


def test_battery_network_supplies_2023_and_2024(battery, battery_default):
    """Five minerals, every lithium-ion end use, recipes with several inputs, retirement and recycling: the observed
    years are supplied from the observed capacities, with and without losses."""
    for r in (battery[1], battery_default[2]):
        assert r["status"] == 2 and r["short"] == {}


def test_battery_recipes_take_what_demand_needs(battery):
    """Without losses, every refined metal and anode graphite is taken by the battery chain in exactly demand x
    intensity over every end use."""
    B, r = battery
    for m in B.MINERALS:
        for y in B.YEARS:
            assert r["used"][m, y] == pytest.approx(r["need"][m, y], rel=1e-6)


def test_battery_supply_covers_batteries_and_other_uses(battery_default):
    """Refined lithium, nickel and cobalt, primary plus recycled, cover the batteries and the metals' other uses."""
    B, inp, r = battery_default
    for m in ('Li', 'Ni', 'Co'):
        for y in B.YEARS:
            other = sum(v for (g, rg, yy), v in inp["other"].items() if g == ('refine', m) and yy == y)
            assert other > 0
            assert r["refined"][m, y] + r["recycled"].get((m, y), 0.0) >= r["used"][m, y] + other - 1e-6


def test_battery_china_imports_ore_it_refines(battery):
    """China refines most lithium and cobalt but mines little lithium and no cobalt, so ore must flow to it."""
    B, r = battery
    for m in ('Li', 'Co'):
        for y in B.YEARS:
            into = sum(v for (s, g, i, j, yy), v in r["trade"].items() if (s, g, j, yy) == ('mine', m, 'CHN', y))
            assert into > 1.0, (m, y)


def test_losses_scale_what_goes_in():
    """A 10% loss at cells and 5% at refining: recipes take need / 0.9, lithium, nickel and cobalt mines give
    primary refined / 0.95, and manganese bought (a base material) is primary refined / 0.95 too."""
    from critmin_net import battery as B
    r = B.run(losses={'cell': 0.10, 'refine': 0.05}, repurpose=0.0)
    assert r["status"] == 2 and r["short"] == {}
    for m in ('Li', 'Ni', 'Co', 'Mn'):
        for y in B.YEARS:
            assert r["used"][m, y] == pytest.approx(r["need"][m, y] / 0.9, rel=1e-6)
            src = r["bought"] if m == 'Mn' else r["mined"]
            assert src[m, y] == pytest.approx(r["refined"][m, y] / 0.95, rel=1e-6)


def test_battery_default_losses(battery_default):
    """With the published default losses each mine (and manganese bought) gives what its refinery takes divided by
    the refinery's yield, and the battery chain takes more than demand x intensity."""
    B, inp, r = battery_default
    for m in ('Li', 'Ni', 'Co', 'Mn'):
        for y in B.YEARS:
            src = r["bought"] if m == 'Mn' else r["mined"]
            assert src[m, y] == pytest.approx(r["refined"][m, y] / (1 - B.LOSSES[('refine', m, m)]), rel=1e-6)
            assert r["used"][m, y] > r["need"][m, y]


def test_battery_scrap_and_retirements_are_recycled(battery_default):
    """Manufacturing scrap (the cell loss) and retired products are shredded and recycled into refined metals; with
    long EV lifetimes few EV packs retire yet, so scrap and electronics dominate the feed."""
    B, inp, r = battery_default
    for y in B.YEARS:
        ev = sum(v for (g, yy), v in r["retired"].items() if yy == y and g.startswith('ev_'))
        el = sum(v for (g, yy), v in r["retired"].items() if yy == y and g.startswith('electronics_'))
        assert r["shredded"]['scrap', y] > el > ev > 0
        assert all(r["recycled"][m, y] > 0 for m in B.METALS)


def test_battery_shorter_ev_life_means_more_retired_and_recycled(battery_default):
    """An 8-year EV battery life (the older assumption) retires far more EV packs in 2023-2024 than the published
    longer lifetimes, repurposes more and recycles more lithium."""
    B, inp, r0 = battery_default
    short = {'mean': 8.0, 'shape': 3.0}
    r1 = B.run(inp, life={'ev': short, ('ev', 'lfp'): short})
    for y in B.YEARS:
        ev = [sum(v for (g, yy), v in r["retired"].items() if yy == y and g.startswith('ev_')) for r in (r0, r1)]
        assert ev[1] > 20 * ev[0]
        assert sum(v for (g, yy), v in r1["repurposed"].items() if yy == y) > sum(
            v for (g, yy), v in r0["repurposed"].items() if yy == y)
        assert r1["recycled"]['Li', y] > r0["recycled"]['Li', y]


def test_battery_repurposing_within_its_share(battery_default):
    """At most the repurposing share of retired EV packs is repurposed, by chemistry, region and year."""
    B, inp, r = battery_default
    for y in B.YEARS:
        for c in B.CHEMS:
            assert r["repurposed"].get((f"ev_{c}", y), 0.0) <= B.LIFECYCLE["repurpose"] * r["retired"][f"ev_{c}", y] + 1e-6


def test_battery_price_of_us_storage():
    """price() on the battery network: the marginal cost of one more GWh of US LFP storage in 2023 is positive and
    matches a small step in extra demand."""
    from critmin_net import battery as B, network as N
    net, params, kw, need = B.network(B.load())
    g = ('use', 'storage_lfp')
    pr, base = N.price([g], params=params, net=net, years=[2023], **kw)
    assert pr[g, 2023] > 0
    more = N.solve(params, net=net, extra_demand={(g, 'US', 2023): 0.01}, **kw)
    assert pr[g, 2023] == pytest.approx((more["obj"] - base["obj"]) / 0.01, rel=1e-3)


def test_battery_base_materials(battery_default):
    """Manganese, iron and phosphorus are bought, not mined: iron and phosphorus exactly what LFP's iron phosphate
    takes (37% and 21% of its mass), and manganese a sliver of what the world mines (USGS)."""
    from critmin_net import base
    B, inp, r = battery_default
    assert not any(m == 'Mn' for (m, y) in r["mined"])
    w = base.world()
    for y in B.YEARS:
        lfp = sum(v for (u, c, rg, yy), v in inp["demand"].items() if c == 'lfp' and yy == y)
        fepo4 = B.FEPO4_PER_LI * inp["intensity"]['lfp']['Li']           # kg per kWh, so kt per GWh
        for x in ('Fe', 'P'):
            assert r["bought"][x, y] > lfp * fepo4 * B.IN_FEPO4[x]        # cell scrap means more than demand
        assert r["bought"]['Fe', y] / r["bought"]['P', y] == pytest.approx(B.IN_FEPO4['Fe'] / B.IN_FEPO4['P'])
        assert r["bought"]['Mn', y] < 0.01 * w['manganese', y]


def test_battery_base_price_override():
    """A dearer manganese raises the cost and nothing else changes in what is made."""
    from critmin_net import battery as B
    a = B.run(repurpose=0.0)
    b = B.run(repurpose=0.0, base={'Mn': {"price": 10.0}})
    assert b["obj"] > a["obj"]
    assert b["bought"]['Mn', 2024] == pytest.approx(a["bought"]['Mn', 2024], rel=1e-6)
    with pytest.raises(ValueError):
        B.run(base={'Cu': {"price": 1.0}})


# ---- zoom (0.7.0): the network cut at some goods, bought at what they are worth in the whole network

def _solve_h(N, net, params, **kw):
    m = gp.Model(); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **kw)
    m.setObjective(obj, gp.GRB.MINIMIZE); m.optimize()
    assert m.Status == gp.GRB.OPTIMAL
    return m, h


def test_zoom_battery_on_lithium():
    """The battery network zoomed on lithium: nickel, cobalt, manganese and graphite bought at their whole-network
    prices. Regions that share a cost tie (the DRC is priced at China's), so costs are perturbed by up to 1% (the
    same in both) to make the plan unique; then every remaining node matches, lithium's mines and refineries
    included."""
    import random
    from critmin_net import battery as B, network as N
    net, params, bkw, _ = B.network(B.load())
    rng = random.Random(1)
    for pc, _, _ in net["cost"].values():
        for k in pc:
            pc[k] *= 1 + 0.01 * (2 * rng.random() - 1)
    z, info = N.zoom([B.CUT[m] for m in ('Ni', 'Co', 'Mn', 'graphite')], params, net=net, **bkw)
    assert ('mine', 'Li') not in [q[:2] for q in info["processes"]]
    m0, h0 = _solve_h(N, net, params, **bkw)
    m1, h1 = _solve_h(N, z, params, **bkw)
    for (n, y), v in h1["prod"].items():
        if n[:-1] not in z["trade_only"]:              # the cut goods' removed makers, kept as trade routes
            assert v.X == pytest.approx(h0["prod"][n, y].X, abs=1e-6)
    li = [k for k in h1["prod"] if k[0][:2] in (('mine', 'Li'), ('refine', 'Li'))]
    assert li and sum(h1["prod"][k].X for k in li) > 0
    # price and value alone (no caps): the whole network's plan is still optimal, so the cost is the same
    z2, _ = N.zoom([B.CUT[m] for m in ('Ni', 'Co', 'Mn', 'graphite')], params, net=net, caps=False, **bkw)
    m2, _ = _solve_h(N, z2, params, **bkw)
    assert m2.ObjVal == pytest.approx(m1.ObjVal, rel=1e-9)


@pytest.fixture(scope="module")
def battery_cal():
    from critmin_net import battery as B
    inp = B.load()
    return B, inp, B.calibrate(inp)


def test_battery_calibration_reproduces_observed_shares(battery_cal, battery_default):
    """calibrate(): every stage with an observed regional split matches it in each region and year, to 1e-4 of the
    stage's output, with nothing unmet; uncalibrated, China makes every cell in 2024."""
    from critmin_net import network as N
    B, inp, cal = battery_cal
    assert cal["iterations"] <= 5 and min(cal["wedge"].values()) >= 0.0
    net, params, bkw, _ = B.network(inp, quad=cal["quad"])
    m, h = _solve_h(N, net, params, **bkw)
    assert all(v.X < 1e-6 for v in h["short"].values())
    out, tot, ttot = {}, {}, {}
    for (n, y), v in h["prod"].items():
        g = B._group(n)
        if g:
            out[g, n[-1], y] = out.get((g, n[-1], y), 0.0) + v.X
            tot[g, y] = tot.get((g, y), 0.0) + v.X
    for (g, r, y), x in cal["target"].items():
        ttot[g, y] = ttot.get((g, y), 0.0) + x
    assert set(out) == set(cal["target"])
    for (g, r, y), x in out.items():
        if ttot[g, y] > 0:
            assert x / tot[g, y] == pytest.approx(cal["target"][g, r, y] / ttot[g, y], abs=1e-4)
    assert out[('cell', 'cell'), 'CHN', 2024] / tot[('cell', 'cell'), 2024] < 0.9
    assert battery_default[2]["share"]['cell', 'CHN', 2024] == pytest.approx(1.0)


def test_zoom_battery_calibrated(battery_cal):
    """With calibrate()'s rising costs the plan is unique, so the battery network zoomed on lithium matches the whole
    one node by node with no perturbation, to the solver's tolerance (0.01% at TIE; 0.1% asserted)."""
    from critmin_net import network as N
    B, inp, cal = battery_cal
    net, params, bkw, _ = B.network(inp, quad=cal["quad"])
    z, _ = N.zoom([B.CUT[m] for m in ('Ni', 'Co', 'Mn', 'graphite')], params, net=net, **bkw)
    m0, h0 = _solve_h(N, net, params, **bkw)
    m1, h1 = _solve_h(N, z, params, **bkw)
    top = max(v.X for v in h0["prod"].values())
    for (n, y), v in h1["prod"].items():
        if n[:-1] not in z["trade_only"]:
            assert v.X == pytest.approx(h0["prod"][n, y].X, rel=1e-3, abs=1e-6 * top)


def test_battery_run_with_focus():
    """run(focus=...) zooms: only the focus minerals are mined, the others' battery-grade goods are bought, and the
    lithium mined each year is the whole network's (it may sit in other regions where plans tie)."""
    from critmin_net import battery as B
    whole, li = B.run(), B.run(focus=['Li'])
    assert li["status"] == 2 and li["short"] == {}
    assert {m for m, _ in li["mined"]} == {'Li'}
    assert {'Ni', 'Co', 'Mn', 'anode'} <= {m for m, _ in li["bought"]}
    for y in B.YEARS:
        assert li["mined"]['Li', y] == pytest.approx(whole["mined"]['Li', y], rel=1e-6)
    with pytest.raises(ValueError):
        B.zoom(['Li', 'Ni', 'Co', 'Mn', 'graphite'])


# ---- 0.11.0 and 0.12.0: the battery horizon to 2040, on curves

@pytest.fixture(scope="module")
def horizon():
    from critmin_net import battery as B
    from critmin_net import horizon as H
    inp = H.load("STEPS")
    cal = H.calibrate(inp)
    return H, B, inp, cal, {sc: H.run(sc, inputs=inp, cal=cal) for sc in ("cost", "onshore")}


def test_horizon_calibrates_the_observed_years(horizon):
    """calibrate(): every group's output in every region and observed year within 0.5% of its stage's output of the
    observed share (graphite mining 4%: the anode's natural/synthetic split is not observed), and the full horizon
    reproduces the same regional shares (its totals may move a little: the chemistry band in the observed years)."""
    H, B, inp, cal, res = horizon
    assert cal["miss"] < 1.0
    gt = {}
    for (g, r, y), x in cal["target"].items():
        gt[g, y] = gt.get((g, y), 0.0) + x
    for r in res.values():
        assert r["status"] == 2 and r["short"] == {}
        for (g, rg, y), x in cal["target"].items():
            tot = sum(r["prod"].get(g + (q, y), 0.0) for q in B.REGIONS)
            if gt[g, y] > 0 and tot > 0:
                tol = H.CAL_TOL.get(g, H.CAL_TOL[None])
                assert abs(r["prod"].get(g + (rg, y), 0.0) / tot - x / gt[g, y]) <= tol + 1e-6


def test_horizon_builds_wait_for_their_region_lead(horizon):
    """Nothing built serves before its region's lead allows (an expansion's own lead; decisions from 2023) or in the
    observed years."""
    H, B, inp, cal, res = horizon
    for r in res.values():
        for (s, key, rg, y), v in r["built"].items():
            lead = (H.EXPANSION[key, rg]["lead"] if s == 'expand' else H.LEAD['refine' if s in ('hydromet', 'pyro') else s][rg])
            assert y >= min(H.YEARS) + lead and y > max(B.YEARS)


def test_horizon_demand_answers_to_its_curves(horizon):
    """After 2024 every end use is a demand curve anchored at IEA's projection: what is served is within the curve's
    range (a quarter to four times the anchor's price) and near the anchor, and nothing is a fixed amount."""
    H, B, inp, cal, res = horizon
    D = inp["demand"]
    r = res["cost"]
    for y in (2030, 2040):
        for u in B.USES:
            iea = sum(v for (uu, c, rr, yy), v in D.items() if uu == u and yy == y)
            got = sum(v for (g, rr, yy), v in r["served"].items() if g == ('use', u) and yy == y)
            assert 0.5 * iea <= got <= 2.0 * iea


def test_horizon_onshoring_floors_hold_and_cost_more(horizon):
    """onshore: from 2030 the US and allies make at least the floor share of their own demand at every processing and
    manufacturing group (mines have none), and the plan costs more than the cost-based one."""
    H, B, inp, cal, res = horizon
    D = inp["demand"]
    r = res["onshore"]
    for y in H.YEARS:
        if y < min(H.ONSHORE):
            continue
        f = H._line(H.ONSHORE, y) * (sum(v for k, v in D.items() if k[3] == y and k[2] in H.US_ALLY)
                                     / sum(v for k, v in D.items() if k[3] == y))
        for g in {k[:2] for k in r["prod"] if k[0] != 'mine'}:
            tot = sum(r["prod"].get(g + (q, y), 0.0) for q in B.REGIONS)
            ua = sum(r["prod"].get(g + (q, y), 0.0) for q in H.US_ALLY)
            assert ua >= f * tot - 1e-6 * max(tot, 1.0)
    assert r["cost"] > res["cost"]["cost"]


def test_horizon_myopic_runs_and_costs_no_less(horizon):
    """Myopic (five years in view) solves, and seeing less ahead costs at least as much as perfect foresight."""
    H, B, inp, cal, res = horizon
    r = H.run("cost", inputs=inp, cal=cal, foresight=5)
    assert r["status"] == 2
    assert r["obj"] >= res["cost"]["obj"] - 1e-6 * abs(res["cost"]["obj"])


# ---- 0.13.0: rules of origin, the DRC, export controls and 45X's foreign-entity rule

@pytest.fixture(scope="module")
def horizon_policy(horizon):
    H, B, inp, cal, _ = horizon
    cases = {"policy": {}, "feoc": {"feoc": True}, "controls": {"china_controls": {"from_year": 2027}}}
    return {k: H.run("cost", inputs=inp, cal=cal, policy=v) for k, v in cases.items()}


def _flows(r, stage, y, exp=None, imp=None):
    return sum(v for (s, _, e, i, yy), v in r["trade"].items()
               if s == stage and yy == y and (exp is None or e == exp) and (imp is None or i == imp))


def _made(r, stage, region, y):
    return sum(v for k, v in r["prod"].items() if k[0] == stage and k[-2] == region and k[-1] == y)


def test_horizon_regions_export_only_what_they_make(horizon, horizon_policy):
    """Rules of origin (every year): no region exports more of a stage's goods than it made, so nothing passes
    through a low-tariff region (before 0.13.0 the US bought China's cathode through the DRC; before 0.15.0 its cells
    and anode in 2023-2024)."""
    H, B, inp, cal, res = horizon
    for r in [res["cost"], *horizon_policy.values()]:
        for y in H.YEARS:
            for s in ('mine', 'refine', 'pcam', 'cath', 'anode', 'cell'):
                for g in B.REGIONS:
                    assert _flows(r, s, y, exp=g) <= _made(r, s, g, y) + 1e-4 * max(1.0, _made(r, s, g, y))


def test_horizon_drc_builds_no_midstream_by_default(horizon, horizon_policy):
    """KNOBS no_entry: the DRC makes no precursor, cathode, anode or cells (it has none, none is announced), even with
    the US's tariffs on everyone else."""
    H, B, inp, cal, res = horizon
    for r in [res["cost"], *horizon_policy.values()]:
        for y in H.YEARS:
            for s in ('pcam', 'cath', 'anode', 'cell'):
                assert _made(r, s, 'SPC', y) <= 1e-6


def test_horizon_china_controls_close_its_exports_to_the_us(horizon_policy):
    """china_controls from 2027: China sells the US no graphite, anode, cathode, precursor or cells, and the US is
    still served (from its own plants and other regions)."""
    r = horizon_policy["controls"]
    assert r["status"] == 2 and r["short"] == {}
    for (s, g, e, i, y), v in r["trade"].items():
        if e == 'CHN' and i == 'US' and y >= 2027 and (s in ('anode', 'cath', 'pcam', 'cell') or g == 'graphite'):
            assert v <= 1e-6


def test_horizon_feoc_caps_chinese_inputs_to_us_cells(horizon, horizon_policy):
    """45X's foreign-entity rule (PL 119-21): in each year cells earn the credit, US cell plants take at most
    (1 - threshold) of their cathode and anode from China, and complying costs no less than the policy without it."""
    from critmin_net import policy as P
    H, B, inp, cal, _ = horizon
    r, p = horizon_policy["feoc"], horizon_policy["policy"]
    th, cr = P.feoc_thresholds(H.YEARS)['component'], P.credits(H.YEARS, "PL 119-21")['cell']
    for y in H.YEARS:
        if y in B.YEARS or th[y] <= 0 or cr[y] <= 0:
            continue
        chn = sum(_flows(r, s, y, exp='CHN', imp='US') for s in ('cath', 'anode'))
        take = sum(_made(r, s, 'US', y) + _flows(r, s, y, imp='US') - _flows(r, s, y, exp='US') for s in ('cath', 'anode'))
        assert chn <= (1 - th[y]) * take + 1e-4 * max(1.0, take)
    assert r["obj"] >= p["obj"] - 1e-6 * abs(p["obj"])


def test_horizon_drc_cobalt_quota_and_expansions_hold(horizon, horizon_policy):
    """With policy, the DRC exports at most its quota of cobalt (96.6 kt from 2026); in every case brownfield
    expansions stay within their room (EXPANSION share x 2024's capacity) and only where an expansion is sourced."""
    from critmin_net import policy as P
    H, B, inp, cal, res = horizon
    q = P.drc_cobalt_quota(H.YEARS)
    r = horizon_policy["policy"]
    for y, cap in q.items():
        ex = sum(v for (s, g, e, i, yy), v in r["trade"].items() if g == 'Co' and e == 'SPC' and yy == y)
        assert ex <= cap + 1e-6
    for rr in [res["cost"], *horizon_policy.values()]:
        for (m, rg, y), v in rr["expanded"].items():
            assert (m, rg) in H.EXPANSION
            room = H.EXPANSION[m, rg]["share"] * rr["cap"].get(('mine', m, rg, max(B.YEARS)), 0.0)
            assert v <= room + 1e-6 * max(1.0, room)


def test_horizon_export_is_what_cem_impacts_reads(horizon, tmp_path):
    """export.write(): one folder per run in cem-impacts' critmin-net export format (cem_impacts.adapters.critmin):
    the files and columns it requires, process names that start with their stage code, one unit per good, no
    duplicate keys, and amounts that add up to the run's own production and trade. When cem_impacts is installed,
    its reader accepts the folder and validates it against the Flows contract."""
    import json
    import pandas as pd
    from critmin_net import export as E
    H, B, inp, cal, res = horizon
    r = res["cost"]
    f = E.write(r, tmp_path / "STEPS_cost", scenario="STEPS, no policy")
    cols = {"production": ["stage", "process", "good", "region", "year", "amount", "unit"],
            "trade": ["stage", "good", "origin", "destination", "year", "amount", "unit"],
            "shortfall": ["stage", "good", "region", "year", "amount", "unit"],
            "stock": ["stage", "good", "region", "year", "amount", "unit"],
            "price": ["stage", "good", "region", "year", "price", "unit"]}
    keys = {"production": ["process", "good", "region", "year"], "trade": ["stage", "good", "origin", "destination", "year"],
            "shortfall": ["stage", "good", "region", "year"], "stock": ["stage", "good", "region", "year"],
            "price": ["stage", "good", "region", "year"]}
    meta = json.loads((f / "run.json").read_text(encoding="utf-8"))
    assert meta["model"] == "critmin-net" and meta["status"] == "optimal" and meta["years"] == list(H.YEARS)
    t = {n: pd.read_csv(f / f"{n}.csv", keep_default_na=False, na_values=[""]) for n in cols}
    codes = {'base', 'mine', 'refine', 'pcam', 'anode', 'cath', 'cell', 'use', 'eol', 'scrap', 'shred'}
    for n, df in t.items():
        assert list(df.columns) == cols[n]
        assert not df.duplicated(keys[n]).any()
        if len(df):
            assert set(df["stage"]) <= codes
            assert set(df.get("region", df.get("origin"))) <= set(B.REGIONS)
    p = t["production"]
    assert (p["process"].str.split(":").str[0] == p["stage"]).all()
    units = pd.concat([t[n][["stage", "good", "unit"]] for n in ("production", "trade", "stock")]).drop_duplicates()
    assert not units.duplicated(["stage", "good"]).any()
    for y in (2030, 2040):
        for rg in B.REGIONS:
            got = p[(p.stage == 'cell') & (p.region == rg) & (p.year == y)].amount.sum()
            assert got == pytest.approx(r["prod"].get(('cell', 'cell', rg, y), 0.0), abs=1e-6)
    assert t["trade"].amount.sum() == pytest.approx(sum(v for v in r["trade"].values() if v > 1e-9), rel=1e-9)
    try:
        from cem_impacts.adapters import critmin
    except ImportError:
        return
    fl = critmin.read_export(f)
    assert fl.network == "battery" and len(fl.production) == len(p)


def test_horizon_yards_cost_to_hold(horizon):
    """KNOBS yard_cost (0.15.0): holding retired packs and black mass costs Argonne's 150 USD per tonne a year, so
    yards buffer rather than hoard. With it, little is left in them by 2040; free, thousands of GWh pile up."""
    H, B, inp, cal, res = horizon
    held = lambda r, y: sum(v for k, v in r["detail"]["stock"].items() if k[3] == y)
    assert H.KNOBS["yard_cost"]['eol'] == pytest.approx(0.150 * 8.70)
    free = H.run("cost", inputs=inp, cal=cal, knobs={"yard_cost": None})
    assert held(res["cost"], 2040) < 0.2 * held(free, 2040)
    assert sum(v for (q, y), v in res["cost"]["recycled"].items() if y == 2040) > \
        sum(v for (q, y), v in free["recycled"].items() if y == 2040)


def _cells(r, y, regions=None):
    return sum(v for k, v in r["prod"].items() if k[0] == 'cell' and k[-1] == y and (regions is None or k[-2] in regions))


def test_horizon_myopic_pays_for_plants_past_its_window(horizon, horizon_policy):
    """0.15.1: a myopic window charges a plant's capital to the horizon's end, so it does not build for the last year
    it sees and abandon the plant (before, the US built half the world's cells for 45X's last full year, 2030)."""
    H, B, inp, cal, res = horizon
    r = H.run("cost", inputs=inp, cal=cal, policy={}, foresight=5)
    p = horizon_policy["policy"]
    assert r["status"] == 2
    assert _cells(r, 2030, ('US',)) / _cells(r, 2030) <= _cells(p, 2030, ('US',)) / _cells(p, 2030) + 0.05


def test_horizon_myopic_floors_do_not_shrink_the_market(horizon):
    """0.15.1: onshoring floors are soft (KNOBS floor_penalty), so a myopic run short of plants in time pays for the
    shortfall instead of shrinking world output to meet a share (before, cells in 2040 fell to about a quarter)."""
    H, B, inp, cal, res = horizon
    r = H.run("onshore", inputs=inp, cal=cal, foresight=5)
    assert r["status"] == 2 and r["short"] == {}
    assert _cells(r, 2040) >= 0.9 * _cells(res["onshore"], 2040)
    assert res["onshore"]["floor_short"] == {}         # with perfect foresight every floor is met in full


def test_battery_numbers_unchanged(battery_default, horizon):
    """The battery network (2023-2024, published defaults) and the horizon's cost case (STEPS, no policy) solve to
    the stored objectives."""
    _, _, r = battery_default
    runs = horizon[-1]
    assert r["obj"] == pytest.approx(BASE["battery_run_objective"], rel=1e-6)
    assert runs["cost"]["obj"] == pytest.approx(BASE["horizon_cost_steps_objective"], rel=1e-6)


def test_horizon_build_embeds_in_another_model(horizon):
    """horizon.build() adds the horizon to a model another model can share (0.17.0): built alone it solves to run()'s
    objective, and one more GWh of US LFP cells a year over 2031-2035 (extra_demand) costs what the cell balances'
    duals say, to first order."""
    H, _, inp, cal, runs = horizon
    years = range(2031, 2036)
    out = {}
    for extra in (0.0, 1.0):
        m = gp.Model(); m.Params.OutputFlag = 0; m.Params.Method = 1
        xd = {(('cell', 'GWh_lfp'), 'US', y): extra for y in years} if extra else None
        obj, h, info = H.build(m, inputs=inp, cal=cal, extra_demand=xd)
        m.setObjective(obj, gp.GRB.MINIMIZE); m.optimize()
        assert m.Status == gp.GRB.OPTIMAL
        out[extra] = (m.ObjVal, {y: h["bal_all"][('cell', 'GWh_lfp'), 'US', y].Pi for y in years})
    assert out[0.0][0] == pytest.approx(runs["cost"]["obj"], rel=1e-6)
    by_duals = sum(out[0.0][1].values())                  # duals are already weighted (discounted) as the objective
    assert out[1.0][0] - out[0.0][0] == pytest.approx(by_duals, rel=0.05)
    assert by_duals > 0


def test_horizon_build_merges_its_options(horizon):
    """limits take the lower ceiling, tariffs the higher rate, cap_max replaces a node's ceiling. No solve."""
    H, _, inp, cal, _ = horizon
    m = gp.Model(); m.Params.OutputFlag = 0
    _, _, base = H.build(m, inputs=inp, cal=cal, policy={})
    key = next(iter(base["bkw"]["tariffs"]))
    y = 2030
    m = gp.Model(); m.Params.OutputFlag = 0
    _, _, info = H.build(m, inputs=inp, cal=cal, policy={}, limits={('refine', 'CHN'): {2031: 5.0}},
                         tariffs={key: {y: 100.0}}, cap_max={('refine', 'Li', 'Li', 'CHN'): 1.0})
    assert info["bkw"]["limits"][('refine', 'CHN')][2031] == 5.0
    assert info["bkw"]["tariffs"][key][y] == 100.0
    assert info["params"]["cap_max"][('refine', 'Li', 'Li', 'CHN')] == 1.0
    with pytest.raises(ValueError):
        H.build(gp.Model(), inputs=inp)

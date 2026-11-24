"""Checks that solve the network, so they need a full Gurobi licence. Skipped without one.

    pytest -q -m solver        # on a licensed machine, under a minute

Two guarantees, one each way:
  * the lab model still IS Alavi's model: run with her notebook's parameters and no hooks, it reproduces
    her notebook's objective (src/critmin_net/data/reference/, made by scripts/reference_sara_network.py) to 1e-6;
  * the move here changed nothing: the numbers in tests/baseline/working_repo_5c3616a.json, made by
    the same model in critmin-energy-surrogatecoupling at 5c3616a, come back to 1e-9.
A change to the model that moves the second on purpose regenerates that file and says why in the commit
and CHANGELOG.md. Nothing may move the first.

The stockpile checks (0.3.0) are properties, not stored numbers: it can only lower the cost, it bridges a
refining cut it sees coming, and its accounting holds at the horizon's end.
"""
import json
from pathlib import Path

import pytest

gp = pytest.importorskip("gurobipy")
BASE = json.loads((Path(__file__).parent / "baseline" / "working_repo_5c3616a.json").read_text())


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


def test_reproduces_alavis_notebook(N):
    got, ref, rel = N.check_agreement()
    assert rel <= 1e-6


def test_published_multipliers_unchanged_by_the_move(N):
    assert N.solve(N.PUBLISHED)["obj"] == pytest.approx(BASE["published_objective"], rel=1e-9)


def test_calibrated_model_unchanged_by_the_move(N):
    cal = N.calibrated()
    assert N.solve(cal)["obj"] == pytest.approx(BASE["calibrated_objective"], rel=1e-9)
    for total, key in ((False, "calibrated_us_cell_price"), (True, "calibrated_us_cell_price_total")):
        price, _ = N.us_cell_price(params=cal, total=total)
        assert price == pytest.approx(BASE[key], rel=1e-9)


GAP = 2e-4      # the network is a MILP solved to Gurobi's default 1e-4 gap: two solves compare to twice that


@pytest.fixture(scope="module")
def cut(N):
    """China's refining cut to 70% of its business-as-usual output from 2031, as the shock experiments use."""
    cal = N.calibrated()
    base = N.solve(cal)
    return cal, {('proc', 'CHN'): {y: 0.7 * base["stage_output"][('proc', 'CHN', y)] for y in base["Y"] if y >= 2031}}


def test_stockpile_never_costs_more(N, cut):
    cal, limits = cut
    off = N.solve(cal, limits=limits)["obj"]
    for opts in ({}, {"regions": "all"}):
        assert N.solve(cal, limits=limits, stockpile=opts)["obj"] <= off * (1 + GAP)


def test_stockpile_bridges_a_cut_it_sees_coming(N, cut):
    """The US reserve is built before the cut (2031) and drawn after it."""
    cal, limits = cut
    st = N.solve(cal, limits=limits, stockpile={})["stock"]
    assert all(k[2] == 'US' for k in st)
    assert any(k[3] < 2031 for k in st), "nothing stocked ahead of the cut"
    assert any(k[3] >= 2031 for k in st), "nothing carried into the cut"


def test_stockpile_too_dear_to_hold_is_not_held(N, cut):
    cal, limits = cut
    r = N.solve(cal, limits=limits, stockpile={"hold_share": 100.0})
    assert r["stock"] == {} and r["obj"] == pytest.approx(N.solve(cal, limits=limits)["obj"], rel=GAP)


def test_stockpile_ends_where_it_started(N):
    """A starting stock may be used along the way, but none in the last year, and the end holds at least the start."""
    cal = N.calibrated()
    key = ('proc', 'loh', 'US')
    r = N.solve(cal, stockpile={"initial": {key: 50.0}})
    last = max(r["Y"])
    held = {y: r["stock"].get(key + (y,), 0.0) for y in r["Y"]}
    assert held[last] >= 50.0 - 1e-6
    assert held[last] >= held[last - 1] - 1e-6



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


def test_losses_raise_the_lithium_model_cost():
    """In the lithium network a cell loss costs more: more of everything upstream is made."""
    from critmin_net import network as N
    p = N.calibrated()
    assert N.solve(p, losses={'cell': 0.05})["obj"] > N.solve(p)["obj"]


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


def test_zoom_reproduces_the_lithium_model(N):
    """The lithium model as the working repository runs it (calibrated map, cobalt add-on: a MILP with builds), cut at
    lithium chemicals: mines and chemical refining bought at their whole-network prices. Every remaining node makes
    what it makes in the whole model, and builds the same plants, solving the zoomed MILP afresh."""
    cal = N.calibrated()
    z, info = N.zoom([('proc', b) for b in N.PROC_T], cal, cobalt=True)
    assert {q[0] for q in info["processes"]} == {'mine', 'proc'}
    m0, h0 = _solve_h(N, N.LITHIUM, cal, cobalt=True)
    m1, h1 = _solve_h(N, z, cal, cobalt=True)
    tot = sum(v.X for v in h0["prod"].values())
    for (n, y), v in h1["prod"].items():
        if n[:-1] in z["trade_only"]:                  # the cut goods' removed makers, kept as trade routes
            continue
        assert v.X == pytest.approx(h0["prod"][n, y].X, abs=1e-6 * tot)
        assert round(h1["inv"][n, y].X) == round(h0["inv"][n, y].X)


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


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
    """A 10% loss at cells and 5% at refining: recipes take need / 0.9 and lithium, nickel and cobalt mines give
    primary refined / 0.95 (manganese's mines also serve its other uses)."""
    from critmin_net import battery as B
    r = B.run(losses={'cell': 0.10, 'refine': 0.05}, repurpose=0.0)
    assert r["status"] == 2 and r["short"] == {}
    for m in ('Li', 'Ni', 'Co', 'Mn'):
        for y in B.YEARS:
            assert r["used"][m, y] == pytest.approx(r["need"][m, y] / 0.9, rel=1e-6)
            if m != 'Mn':
                assert r["mined"][m, y] == pytest.approx(r["refined"][m, y] / 0.95, rel=1e-6)


def test_losses_raise_the_lithium_model_cost():
    """In the lithium network a cell loss costs more: more of everything upstream is made."""
    from critmin_net import network as N
    p = N.calibrated()
    assert N.solve(p, losses={'cell': 0.05})["obj"] > N.solve(p)["obj"]


def test_battery_default_losses(battery_default):
    """With the published default losses each lithium, nickel and cobalt mine gives what its refinery takes divided
    by the refinery's yield, and the battery chain takes more than demand x intensity."""
    B, inp, r = battery_default
    for m in ('Li', 'Ni', 'Co', 'Mn'):
        for y in B.YEARS:
            if m != 'Mn':
                assert r["mined"][m, y] == pytest.approx(r["refined"][m, y] / (1 - B.LOSSES[('refine', m, m)]), rel=1e-6)
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

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
    return B, B.run(losses={})                   # no losses: every mineral taken in exactly demand x intensity


def test_battery_network_supplies_2023_and_2024(battery):
    """Five minerals, recipes with several inputs: the observed years are supplied from the observed capacities.
    LFP's cathode takes battery-grade iron phosphate, made in the pCAM stage."""
    B, r = battery
    assert r["status"] == 2 and r["short"] == {}


def test_battery_recipes_take_what_demand_needs(battery):
    """Every refined mineral, and anode graphite, is taken in exactly demand x intensity; refined is mined."""
    B, r = battery
    for m in B.MINERALS:
        for y in B.YEARS:
            assert r["used"][m, y] == pytest.approx(r["need"][m, y], rel=1e-6)
            if m != 'graphite':                  # graphite: natural (mined) plus synthetic
                assert r["mined"][m, y] == pytest.approx(r["need"][m, y], rel=1e-6)
                assert r["refined"][m, y] == pytest.approx(r["need"][m, y], rel=1e-6)
    assert all(r["mined"]['graphite', y] < r["need"]['graphite', y] for y in B.YEARS)


def test_battery_china_imports_ore_it_refines(battery):
    """China refines most lithium and cobalt but mines little lithium and no cobalt, so ore must flow to it."""
    B, r = battery
    for m in ('Li', 'Co'):
        for y in B.YEARS:
            into = sum(v for (s, g, i, j, yy), v in r["trade"].items() if (s, g, j, yy) == ('mine', m, 'CHN', y))
            assert into > 1.0, (m, y)



def test_losses_scale_what_goes_in():
    """A 10% loss at cells and 5% at refining: recipes take need / 0.9 and mines give refined / 0.95."""
    from critmin_net import battery as B
    r = B.run(losses={'cell': 0.10, 'refine': 0.05})
    assert r["status"] == 2 and r["short"] == {}
    for m in ('Li', 'Ni', 'Co', 'Mn'):
        for y in B.YEARS:
            assert r["used"][m, y] == pytest.approx(r["need"][m, y] / 0.9, rel=1e-6)
            assert r["mined"][m, y] == pytest.approx(r["refined"][m, y] / 0.95, rel=1e-6)


def test_losses_raise_the_lithium_model_cost():
    """In the lithium network a cell loss costs more: more of everything upstream is made."""
    from critmin_net import network as N
    p = N.calibrated()
    assert N.solve(p, losses={'cell': 0.05})["obj"] > N.solve(p)["obj"]


def test_battery_default_losses_supply_both_years():
    """With the published default losses the observed years are still supplied, and each mine gives what its
    refinery takes divided by the refinery's yield."""
    from critmin_net import battery as B
    r = B.run()
    assert r["status"] == 2 and r["short"] == {}
    for m in ('Li', 'Ni', 'Co', 'Mn'):
        for y in B.YEARS:
            assert r["mined"][m, y] == pytest.approx(r["refined"][m, y] / (1 - B.LOSSES[('refine', m, m)]), rel=1e-6)
            assert r["used"][m, y] > r["need"][m, y]

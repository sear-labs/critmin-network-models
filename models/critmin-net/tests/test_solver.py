"""Checks that solve the network, so they need a full Gurobi licence. Skipped without one.

    pytest -q -m solver        # on a licensed machine, under a minute

Two guarantees, one each way:
  * the lab model still IS Alavi's model: run with her notebook's parameters and no hooks, it reproduces
    her notebook's objective (data/raw/reference/, made by scripts/reference_sara_network.py) to 1e-6;
  * the move here changed nothing: the numbers in tests/baseline/working_repo_5c3616a.json, made by
    the same model in critmin-energy-surrogatecoupling at 5c3616a, come back to 1e-9.
A change to the model that moves the second on purpose regenerates that file and says why in the commit
and CHANGELOG.md. Nothing may move the first.
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

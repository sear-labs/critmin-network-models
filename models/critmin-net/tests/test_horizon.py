"""The battery horizon's inputs (0.11.0), without solving: the demand path against its sources and IEA's own 2040
lithium demand, and the capital costs and lead times covering every built stage in every region."""
import pytest

from critmin_net import battery as B
from critmin_net import horizon as H


@pytest.fixture(scope="module")
def steps():
    return H.load("STEPS")


def _tot(D, y, uses=B.USES):
    return sum(v for (u, c, r, yy), v in D.items() if yy == y and u in uses)


def test_horizon_demand_follows_its_sources(steps):
    """EVs: IEA's world deployment (GEVO 2026 Figure 9.16, GWh) less sodium-ion's share; storage 340 GWh in 2030 (IEA's
    lithium-ion additions); electronics and other uses held at 2024; the observed years untouched."""
    D = steps["demand"]
    base = B.load()["demand"]
    for k, v in base.items():
        assert D[k] == v
    assert steps["ev_total"][2025] == pytest.approx(1.22)
    assert steps["ev_total"][2030] == pytest.approx(2.48 + 0.11 + 0.08 + 0.277)
    assert steps["ev_total"][2040] == pytest.approx(2 * 4.77 - 2.947)
    assert _tot(D, 2030, ('ev',)) == pytest.approx(2947.0 * (1 - 0.02), rel=1e-9)   # 2% sodium-ion in 2030
    assert _tot(D, 2030, ('storage',)) == pytest.approx(340.0)
    for u in ('electronics', 'other'):
        assert _tot(D, 2040, (u,)) == pytest.approx(_tot(D, 2024, (u,)))
    assert all(v >= 0 for v in D.values())
    assert {y for (_, _, _, y) in D} == set(H.YEARS)


def test_horizon_lithium_grows_as_iea_says(steps):
    """IEA's 2040 lithium demand for EVs and storage (GCMO 2025, STEPS: 809 kt) over its 2030 (369 kt): the horizon's
    need grows by the same factor within 5%, though its level is lower throughout (cell-level intensities)."""
    D, I = steps["demand"], steps["intensity"]

    def li(y):
        return sum(v * I[c]['Li'] for (u, c, r, yy), v in D.items() if yy == y and u in ('ev', 'storage'))
    assert li(2040) / li(2030) == pytest.approx((739 + 70) / (326 + 43), rel=0.05)
    cps = H.load("CPS")["demand"]
    assert _tot(cps, 2040) < _tot(D, 2040)
    with pytest.raises(ValueError):
        H.load("NZE")


def test_horizon_capex_and_lead_cover_every_built_stage(steps):
    """Every process that is built has a capital cost and a lead time in every region; US and allied plants take at
    least as long as China's at every stage, and the rest of the world's mines are the quickest."""
    net = B.sets(steps["intensity"])
    c = H.capex(steps["intensity"])
    for p in net["processes"]:
        k = B.capex_key(p)
        if k is None:
            continue
        for r in B.REGIONS:
            assert c[k, r] > 0
            assert isinstance(H.LEAD[p[0]][r], int)
    for s, by_r in H.LEAD.items():
        assert min(by_r['US'], by_r['ALLY']) >= by_r['CHN']
    assert H.LEAD['mine']['ROW'] == min(H.LEAD['mine'].values())
    assert H.CRF == pytest.approx(0.0936788, rel=1e-6)


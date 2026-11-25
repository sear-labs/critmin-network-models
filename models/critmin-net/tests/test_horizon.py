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


def test_curves_are_convex_and_anchored():
    """0.12.0, curves.py: a supply curve's blocks reach Q0 where the adder is the offset, rise block by block and end
    open; a demand curve takes Q0 at the anchor value and its values fall."""
    from critmin_net import curves as C
    s = C.supply_blocks(100.0, 10.0, 2.0, offset=1.5)
    cum, at = 0.0, None
    for size, adder in s[:-1]:
        cum += size
        if abs(cum - 100.0) < 1e-9:
            at = adder
    assert at == pytest.approx(1.5) and s[-1][0] is None
    assert all(b[1] >= a[1] - 1e-12 for a, b in zip(s, s[1:]))
    d = C.demand_blocks(50.0, 80.0, -0.5)
    cum = 0.0
    for size, value in d:
        cum += size
        if value == pytest.approx(80.0):
            assert cum == pytest.approx(50.0)
    assert all(b[1] <= a[1] for a, b in zip(d, d[1:]))
    with pytest.raises(ValueError):
        C.ladder(1.0, -1.0, "supply")
    ops = C.supply_blocks(10.0, 17.6, 1.0, steps=[(4.0, 7.8), (3.0, 17.4), (3.0, 23.0)])
    assert ops[0] == (pytest.approx(4.0), pytest.approx(7.8 - 17.6))


def test_operations_keep_their_own_size_in_later_years():
    """0.12.1: in a later year (steps_total) known operations keep their own size, new capacity up to the anchor costs
    the region's sourced cost P, and every tranche is in merit order, so the curve stays convex."""
    from critmin_net import curves as C
    b = C.supply_blocks(30.0, 17.6, 2.0, steps=[(4.0, 7.8), (3.0, 17.4), (3.0, 43.0)], steps_total=10.0)
    assert b[0] == (pytest.approx(4.0), pytest.approx(7.8 - 17.6))
    assert (pytest.approx(20.0), pytest.approx(0.0)) in [(x, y) for x, y in b[:-1]]   # the room to Q0 at P
    assert all(q[1] >= p_[1] - 1e-12 for p_, q in zip(b, b[1:]))
    assert sum(x for x, _ in b[:-1]) > 30.0 and b[-1][0] is None


def test_mining_tables_follow_their_rows():
    """0.13.0: EXPANSION, GREENFIELD and ROYALTY take the checked rows of battery_horizon/mining/mining_realism.csv
    (medians and conversions as their comments say), and every row there was checked (verification.csv)."""
    import statistics
    import pandas as pd
    from critmin_net import network as N
    d = pd.read_csv(N.RAW / "battery_horizon" / "mining" / "mining_realism.csv").set_index("id")
    v = pd.read_csv(N.RAW / "battery_horizon" / "mining" / "verification.csv")
    assert set(v.id) == set(d.index) and set(v.verdict) <= {"CONFIRMED", "CORRECTED"}
    cx = lambda *ids: [float(d.loc[i, "capex_usd_per_kg_yr"]) for i in ids]
    op = lambda *ids: [float(d.loc[i, "cost_usd_per_kg_contained"]) for i in ids]
    assert H.EXPANSION['Li', 'ROW']["capex"] == pytest.approx(statistics.median(cx("X54", "X49", "X31")))
    assert H.EXPANSION['Li', 'CHN']["capex"] == pytest.approx(statistics.mean(cx("X39", "X40")), abs=0.01)
    assert H.EXPANSION['Li', 'US']["capex"] == pytest.approx(cx("X127")[0])
    assert H.EXPANSION['Ni', 'ALLY']["capex"] == pytest.approx(cx("X88")[0])
    assert H.GREENFIELD['Li', 'ALLY'] == pytest.approx(statistics.median(op("X10", "X62", "X59")))
    assert H.ROYALTY['Li', 'ALLY'] == pytest.approx(op("X12")[0])
    assert all(e["lead"] >= 1 and 0 < e["share"] <= 1 for e in H.EXPANSION.values())
    assert all(v >= 0 for v in H.ROYALTY.values())


def test_quota_operations_keep_their_size_and_capacity(steps):
    """QUOTA_OPS (Chile's Atacama, 0.13.0): in a later year a step (size, cost, size_2024) keeps its size on the curve
    while the others share the retiring total as in 2024; and the region's existing capacity holds the quota instead
    of retiring that operation's share."""
    from critmin_net import curves as C
    out = C.supply_blocks(100.0, 10.0, 2.0, 0.0, [(30.0, 5.0, 40.0), (60.0, 8.0)], steps_total=50.0)
    sizes = {round(a + 10.0, 6): s for s, a in out if s is not None}
    assert sizes[5.0] == pytest.approx(30.0)                  # held at its quota
    assert sizes[8.0] == pytest.approx(50.0 * 60.0 / 100.0)   # its 2024 share (60 of 100) of the retiring total
    n = ('mine', 'Li', 'ROW')
    ic_q = H.network(steps, knobs={"quotas": True})[1]["init_cap"][n]
    ic_r = H.network(steps, knobs={"quotas": False})[1]["init_cap"][n]
    ops, q = H.OPERATIONS[('mine', 'Li'), 'ROW'], H.QUOTA_OPS[('mine', 'Li'), 'ROW']
    tot, rate = sum(sz for sz, _ in ops), H.KNOBS["retire"]['mine']
    for y in (2030, 2035, 2040):
        f = max(0.0, 1.0 - rate * (y - 2024))
        base = ic_r[y] / f
        extra = sum(by[y] - base * ops[i][0] / tot * f for i, by in q.items() if y in by)
        assert ic_q[y] == pytest.approx(ic_r[y] + extra)
    assert ic_q[2040] > ic_r[2040]                            # SQM-Codelco's 62 kt a year from 2031


def test_pyromet_route_is_a_pooled_refinery(steps):
    """PYRO (0.13.0): each NMC black mass has a pyromet+ route in refining beside hydromet+, recovering nickel and
    cobalt at 98% (lithium and manganese lost), costed per kWh of black mass, pooled into one plant per region with
    Umicore Hoboken's capacity in the allies; KNOBS["pyro"] False leaves it out."""
    from critmin_net import battery as B
    net, params = H.network(steps)[:2]
    routes = [p for p in net["processes"] if p[0] == 'refine' and p[1].startswith('pyro_')]
    assert routes and all(p[2] == 'Ni' for p in routes)
    for q in routes:
        c = q[1][5:]
        h = ('refine', f"bm_{c}", 'Ni')
        kh, kp = net["recipe"][h][('shred', f"bm_{c}")], net["recipe"][q][('shred', f"bm_{c}")]
        assert kp == pytest.approx(kh / B.LIFECYCLE["recovery"]['Ni'] * 0.98)
        assert set(net["coproducts"][q]) == {('refine', 'Co')}       # no lithium or manganese
        assert net["cost"]['refine'][0][q[1:] + ('US', 2030)] == pytest.approx(H.PYRO["opex"]['US'] / kp)
    first = routes[0] + ('ALLY',)
    retiring = 1.0 - H.KNOBS["retire"]['refine'] * (2025 - 2024)    # existing refining retires, as hydromet+ does
    assert params["init_cap"][first][2025] * H._pool_coef(net, first) == pytest.approx(7000.0 / 3.7 / 1000.0 * retiring)
    assert not [p for p in H.network(steps, knobs={"pyro": False})[0]["processes"] if p[1].startswith('pyro_')]

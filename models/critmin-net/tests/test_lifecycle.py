"""The lifecycle mechanics on a toy network with round numbers, solved: retirement by age, repurposing within its
cap, collection, scrap from losses, co-products from recycling, and reserves. Not data; every number is chosen so
the right answer can be worked out by hand. Values are taken at China's cost, so the regions are the US and China."""
import pytest

gp = pytest.importorskip("gurobipy")
from critmin_net import network as N  # noqa: E402

R, Y = ["US", "CHN"], [2023, 2024, 2025, 2026]
EV, ST, REP = ('use', 'GWh', 'ev'), ('use', 'GWh', 'storage'), ('use', 'repurposed', 'storage')
LIFE_EV, LIFE_2ND = {1: 0.5, 2: 0.5}, {2: 1.0}


def toy():
    out_t = {'mine': ['Li', 'Ni'], 'refine': ['Li', 'Ni'], 'cell': ['GWh'], 'use': ['ev', 'storage'],
             'eol': ['ev', 'storage'], 'scrap': ['GWh'], 'shred': ['bm']}
    recipe = {('mine', 'Li'): {}, ('mine', 'Ni'): {},
              ('refine', 'Li', 'Li'): {('mine', 'Li'): 1.0}, ('refine', 'Ni', 'Ni'): {('mine', 'Ni'): 1.0},
              ('refine', 'bm', 'Li'): {('shred', 'bm'): 0.1},          # 0.1 kt Li per GWh of black mass
              ('cell', 'Li', 'GWh'): {('refine', 'Li'): 10.0},          # 10 GWh per kt Li
              EV: {('cell', 'GWh'): 1.0}, ST: {('cell', 'GWh'): 1.0},
              REP: {('eol', 'ev'): 0.8},                               # 0.8 GWh of storage per GWh retired
              ('shred', 'ev', 'bm'): {('eol', 'ev'): 1.0}, ('shred', 'storage', 'bm'): {('eol', 'storage'): 1.0},
              ('shred', 'scrap', 'bm'): {('scrap', 'GWh'): 1.0}}
    stages = list(out_t)
    procs = list(recipe)
    goods = [(s, g) for s in stages for g in out_t[s]]
    pc_of = {'mine': 1.0, 'refine': 1.0, 'cell': 1.0, 'use': 0.0, 'shred': 0.1}
    cost = {}
    for s in stages:
        pc = {p[1:] + (r, y): (0.5 if p == ('refine', 'bm', 'Li') else pc_of.get(s, 0.0))
              for p in procs if p[0] == s for r in R for y in Y}
        cost[s] = (pc, {k: 0.0 for k in pc}, {k: 0.0 for k in pc})
    net = dict(minerals=['Li', 'Ni'], stages=stages, goods=goods,
               mineral_of={g: (g[1] if g[0] in ('mine', 'refine') else None) for g in goods},
               processes=procs, recipe=recipe, out_t=out_t, max_cap={s: 1e9 for s in stages},
               init_capacity={s: 0.0 for s in stages}, init_active=1, max_new_units=0, short_stages=(),
               value_alone=(), short_gwh={}, years=Y, cost=cost,
               demand={(('use', 'ev'), 'US', y): 10.0 for y in Y} | {(('use', 'storage'), 'US', y): 5.0 for y in Y},
               life={EV: (('eol', 'ev'), LIFE_EV), ST: (('eol', 'storage'), LIFE_2ND), REP: (('eol', 'storage'), LIFE_2ND)},
               history={(EV, 'US', 2022): 10.0}, route_caps={REP: 0.2}, scrap={'cell': 'scrap'},
               coproducts={('refine', 'bm', 'Li'): {('refine', 'Ni'): 2.0}},   # 2 kt Ni per kt Li recovered
               losses={'cell': 0.1}, no_trade=('use', 'eol', 'scrap'))
    params = dict(regions=R, alpha={r: 1.0 for r in R}, import_coef={r: 1.0 for r in R},
                  region_share={r: 0.0 for r in R}, init_cap={p + (r,): 1e6 for p in procs for r in R},
                  ship_value_share=N.SHIP_VALUE_SHARE, shortage_mult=None, build_every=1)
    return net, params


def solve(**kw):
    net, params = toy()
    m = gp.Model(); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **kw)
    m.setObjective(obj, gp.GRB.MINIMIZE); m.optimize()
    assert m.Status == gp.GRB.OPTIMAL
    P = {k: v.X for k, v in h["prod"].items()}
    C = {k: v.X for k, v in h["cons"].items()}
    ret = {k: (e.getValue() if hasattr(e, "getValue") else e) for k, e in h["retire"].items()}
    return ret, P, C


def test_retirement_follows_lifetimes():
    """EVs placed 10 a year (and 10 in 2022) retire half after one year and half after two."""
    N.check_net(toy()[0])
    h, P, C = solve()
    ret = {y: h[('eol', 'ev'), 'US', y] for y in Y}
    assert ret == pytest.approx({2023: 5.0, 2024: 10.0, 2025: 10.0, 2026: 10.0})


def test_repurposing_within_its_cap_and_every_retired_pack_taken():
    """Repurposing is cheaper than new cells, so it takes its 20% cap; everything else retired is shredded."""
    h, P, C = solve()
    for y in Y:
        ret = h[('eol', 'ev'), 'US', y]
        rep = C[REP + ('US',), ('eol', 'ev'), y]
        assert rep == pytest.approx(0.2 * ret)
        assert P[REP + ('US',), y] == pytest.approx(0.8 * rep)
        assert C[('shred', 'ev', 'bm', 'US'), ('eol', 'ev'), y] == pytest.approx(ret - rep)


def test_second_life_retires_too():
    """Repurposed storage retires two years after it is placed, into the storage end-of-life good."""
    h, P, C = solve()
    placed = {y: P[REP + ('US',), y] + P[ST + ('US',), y] for y in Y}
    assert h[('eol', 'storage'), 'US', 2026] == pytest.approx(placed[2024])


def test_scrap_from_cell_losses_is_recycled():
    """A 10% cell loss: scrap is output x 0.1 / 0.9, and all of it is shredded (recycling is cheap)."""
    h, P, C = solve()
    for y in Y:
        cells = sum(v for (n, yy), v in P.items() if n[0] == 'cell' and yy == y)
        scrap = sum(v for (n, g, yy), v in C.items() if g == ('scrap', 'GWh') and yy == y)
        assert scrap == pytest.approx(cells * 0.1 / 0.9)


def test_coproducts_and_surplus():
    """Recycling's nickel arrives as a co-product (2 per lithium); with no use for it, it goes unused."""
    h, P, C = solve()
    rec = sum(v for (n, y), v in P.items() if n[:3] == ('refine', 'bm', 'Li'))
    assert rec > 0
    assert sum(v for (n, y), v in P.items() if n[:3] == ('refine', 'Ni', 'Ni')) == pytest.approx(0.0, abs=1e-9)


def test_life_override_and_reserves():
    """A longer life retires less in the horizon; a reserve caps lithium mined over the horizon."""
    h1, _, _ = solve()
    h2, _, _ = solve(life={EV: {'mean': 12, 'shape': 3.0}})
    tot = [sum(h[('eol', 'ev'), 'US', y] for y in Y) for h in (h1, h2)]
    assert tot[1] < 0.2 * tot[0]
    _, P, _ = solve(reserves={('mine', 'Li', 'US'): 1.0, ('mine', 'Li', 'CHN'): 1.0})
    assert sum(v for (n, y), v in P.items() if n[:2] == ('mine', 'Li')) <= 2.0 + 1e-6
    with pytest.raises(ValueError):
        solve(life={('cell', 'Li', 'GWh'): {1: 1.0}})


def test_retire_share():
    """Weibull shares sum to one over a long horizon; an explicit table is read as given."""
    assert sum(N.retire_share({'mean': 12, 'shape': 3.0}, a) for a in range(1, 80)) == pytest.approx(1.0)
    assert N.retire_share({1: 0.5, 2: 0.5}, 0) == 0.0 and N.retire_share({1: 0.5, 2: 0.5}, 2) == 0.5


def test_mine_coproduct_displaces_its_own_mine():
    """Co-production at a mine (the REE and cobalt case): 5 Ni per Li mined arrives with lithium (recycling's
    nickel is switched off here). Refined Ni is demanded at 1 a year. The nickel mine makes only what the co-product
    leaves short, year by year (late on, recycled lithium means little is mined); surplus goes unused."""
    net, params = toy()
    net["coproducts"] = {('mine', 'Li'): {('mine', 'Ni'): 5.0}}
    net["demand"] = {**net["demand"], **{(('refine', 'Ni'), 'US', y): 1.0 for y in Y}}
    N.check_net(net)
    m = gp.Model(); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net)
    m.setObjective(obj, gp.GRB.MINIMIZE); m.optimize()
    assert m.Status == gp.GRB.OPTIMAL
    P = {k: v.X for k, v in h["prod"].items()}
    for y in Y:
        li = sum(v for (n, yy), v in P.items() if n[:2] == ('mine', 'Li') and yy == y)
        ni = sum(v for (n, yy), v in P.items() if n[:2] == ('mine', 'Ni') and yy == y)
        assert ni == pytest.approx(max(0.0, 1.0 - 5.0 * li), abs=1e-6)
    assert sum(v for (n, y), v in P.items() if n[:2] == ('mine', 'Li') and y == 2023) * 5.0 > 1.0   # a surplus year



def test_reserves_grow_up_to_resources():
    """Reserves that grow, capped by resources: the US may have extracted 0.5 by the end of 2023, doubling each
    year, but never more than its 1.2 of resources. China is unconstrained and makes up the rest."""
    assert N.reserves_available(3.0, 5) == 3.0
    assert N.reserves_available({"reserve": 1.0, "growth": 0.1}, 2) == pytest.approx(1.21)
    assert N.reserves_available({"reserve": 1.0, "growth": 0.1, "resources": 1.2}, 3) == pytest.approx(1.2)
    spec = {"reserve": 0.5, "growth": 1.0, "resources": 1.2}       # 0.5, then 1.0, then capped at 1.2
    _, P, _ = solve(reserves={('mine', 'Li', 'US'): spec})
    cum, us = 0.0, []
    for t, y in enumerate(Y):
        cum += sum(v for (n, yy), v in P.items() if n == ('mine', 'Li', 'US') and yy == y)
        us.append(cum)
        assert cum <= N.reserves_available(spec, t) + 1e-6
    assert us[0] == pytest.approx(0.5)                              # binding: the US would mine more

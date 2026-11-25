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
               losses={'cell': 0.1}, no_trade=('use', 'eol', 'scrap'),
               dispose=[('shred', 'bm')])   # black mass may sit unprocessed
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


# ---- 0.6.0: lead times, recipes by year, route shares, extra demand and price() on any good

def _status(net, params, **kw):
    m = gp.Model(); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **kw)
    m.setObjective(obj, gp.GRB.MINIMIZE); m.optimize()
    return m.Status, ({k: v.X for k, v in h["prod"].items()} if m.SolCount else {}), (m.ObjVal if m.SolCount else None)


def test_lead_time_decides_when_capacity_can_grow():
    """Cells start with 20 GWh of capacity (10 in each region) and demand jumps in 2025. With a one-year lead, capacity built in 2024
    serves 2025; with a three-year lead, 2025 is still a start year, capacity is fixed, and the jump cannot be met."""
    net, params = toy()
    net["max_new_units"] = 10
    for p in net["processes"]:
        if p[0] == 'cell':
            for r in R:
                params["init_cap"][p + (r,)] = 10.0
    net["demand"] = {**net["demand"], **{(('use', 'ev'), 'US', y): 35.0 for y in (2025, 2026)}}
    st, P, _ = _status(net, params, lead={'cell': 1})
    assert st == gp.GRB.OPTIMAL
    assert sum(v for (n, y), v in P.items() if n[0] == 'cell' and y == 2025) > 30.0
    st, _, _ = _status(net, params, lead={'cell': 3})
    assert st in (gp.GRB.INFEASIBLE, gp.GRB.INF_OR_UNBD)
    with pytest.raises(ValueError):
        _status(net, params, lead={'cell': 1.5})


def _jump():
    """The toy with 10 GWh of cell capacity in each region and the US's EV demand jumping to 35 GWh in 2025."""
    net, params = toy()
    for p in net["processes"]:
        if p[0] == 'cell':
            for r in R:
                params["init_cap"][p + (r,)] = 10.0
    net["demand"] = {**net["demand"], **{(('use', 'ev'), 'US', y): 35.0 for y in (2025, 2026)}}
    return net, params


def test_lead_time_by_region():
    """0.11.0. The jump in 2025 with cells' lead by region: three years in the US, one in China. The US cannot add
    capacity by 2025 but China can, so the jump is met with China's cells; with three years in both it cannot be. A
    region the dict leaves out takes 5 years."""
    net, params = _jump()
    net["max_new_units"] = 10
    st, P, _ = _status(net, params, lead={'cell': {'US': 3, 'CHN': 1}})
    assert st == gp.GRB.OPTIMAL
    cells = {r: sum(v for (n, y), v in P.items() if n[0] == 'cell' and n[-1] == r and y == 2025) for r in R}
    assert cells['US'] <= 10.0 + 1e-6 and cells['CHN'] > 20.0
    for lead in ({'US': 3, 'CHN': 3}, {'US': 3}):                     # the second: China at the default 5
        st, _, _ = _status(net, params, lead={'cell': lead})
        assert st in (gp.GRB.INFEASIBLE, gp.GRB.INF_OR_UNBD)
    with pytest.raises(ValueError):
        _status(net, params, lead={'cell': {'US': 1.5}})


def _solve_h(net, params, **kw):
    m = gp.Model(); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **kw)
    m.setObjective(obj, gp.GRB.MINIMIZE); m.optimize()
    return m, h


def test_continuous_builds_and_observed_to():
    """0.11.0. With lumpy False, capacity is built in any amount and no plants (max_new_units 0 forbids any build
    otherwise), at cost's `var` per unit added. observed_to 2024 keeps 2023 and 2024 at the starting capacity even
    with a one-year lead: a jump in 2024 cannot be met, while without it it can; the jump in 2025 can be met either
    way (built in 2024 with the one-year lead, or in 2023 with a two-year one)."""
    net, params = _jump()
    st, _, _ = _status(net, params, lead={'cell': 1})                 # whole plants, and none allowed
    assert st in (gp.GRB.INFEASIBLE, gp.GRB.INF_OR_UNBD)
    net["lumpy"] = False
    m0, h0 = _solve_h(net, params, lead={'cell': 1})
    assert m0.Status == gp.GRB.OPTIMAL and m0.IsMIP == 0
    assert all(v.UB == 0.0 for v in h0["inv"].values())
    pc, vc, fc = net["cost"]['cell']
    net["cost"]['cell'] = (pc, {k: 3.0 for k in vc}, fc)
    m3, h3 = _solve_h(net, params, lead={'cell': 1})
    built3 = sum(v.X for (n, y), v in h3["newc"].items() if n[0] == 'cell')
    peak = max(sum(v.X for (n, yy), v in h3["prod"].items() if n[0] == 'cell' and yy == y) for y in Y)
    assert peak > 30.0 and built3 == pytest.approx(peak - 20.0, rel=1e-6)   # priced: only what the peak needs
    built0 = sum(v.X for (n, y), v in h0["newc"].items() if n[0] == 'cell')
    assert m0.ObjVal - 1e-6 <= m3.ObjVal - 3.0 * built3                # the build is charged in the objective
    assert m3.ObjVal <= m0.ObjVal + 3.0 * built0 + 1e-6
    net["demand"] = {**net["demand"], (('use', 'ev'), 'US', 2024): 35.0}
    st, _, _ = _status(net, params, lead={'cell': 1})                 # 2024 can grow
    assert st == gp.GRB.OPTIMAL
    st, _, _ = _status(net, dict(params, observed_to=2024), lead={'cell': 1})
    assert st in (gp.GRB.INFEASIBLE, gp.GRB.INF_OR_UNBD)
    net["demand"].pop((('use', 'ev'), 'US', 2024))
    for L in (1, 2):                                                  # decided in 2024 or in 2023, online in 2025
        st, _, _ = _status(net, dict(params, observed_to=2024), lead={'cell': L})
        assert st == gp.GRB.OPTIMAL
    st, _, _ = _status(net, dict(params, observed_to=2024), lead={'cell': 3})
    assert st in (gp.GRB.INFEASIBLE, gp.GRB.INF_OR_UNBD)
    with pytest.raises(ValueError):
        _status(net, dict(params, observed_to=2030), lead={'cell': 1})


def test_recipes_by_year():
    """Lithium per GWh of cells halves from 2025 (10 GWh per kt, then 20): cells take half as much lithium."""
    net, params = toy()
    net["recipe"][('cell', 'Li', 'GWh')] = {('refine', 'Li'): {2023: 10.0, 2024: 10.0, 2025: 20.0, 2026: 20.0}}
    N.check_net(net)
    m = gp.Model(); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net)
    m.setObjective(obj, gp.GRB.MINIMIZE); m.optimize()
    for y, k in ((2024, 10.0), (2025, 20.0)):
        cells = sum(v.X for (n, yy), v in h["prod"].items() if n[0] == 'cell' and yy == y)
        li = sum(v.X for (n, g, yy), v in h["cons"].items() if n[0] == 'cell' and yy == y)
        assert li == pytest.approx(cells / (0.9 * k))


def test_route_share_bounds():
    """No recycled lithium world-wide (max 0); primary refining at least 90% of each region's lithium (min 0.9)."""
    net, params = toy()
    st, P, _ = _status(net, params, route_share={('refine', 'bm', 'Li'): {'max': 0.0, 'scope': 'world'}})
    assert st == gp.GRB.OPTIMAL
    assert sum(v for (n, y), v in P.items() if n[:3] == ('refine', 'bm', 'Li')) == pytest.approx(0.0, abs=1e-9)
    st, P, _ = _status(net, params, route_share={('refine', 'Li', 'Li'): {'min': 0.9}})
    for r in R:
        for y in Y:
            prim = P[('refine', 'Li', 'Li', r), y]
            rec = P[('refine', 'bm', 'Li', r), y]
            assert prim >= 0.9 * (prim + rec) - 1e-6
    with pytest.raises(ValueError):
        _status(net, params, route_share={('nope',): {'max': 0.5}})


def test_extra_demand_and_price_on_any_good():
    """A little extra EV demand in the US in 2025 raises the cost at the rate price() reads off the EV balance's
    dual (a small step: a large one can cross into another LP basis)."""
    net, params = toy()
    _, _, base = _status(net, params)
    _, _, more = _status(net, params, extra_demand={(('use', 'ev'), 'US', 2025): 0.01})
    pr, res = N.price([('use', 'ev')], params=params, net=net, years=[2025])
    assert pr[('use', 'ev'), 2025] == pytest.approx((more - base) / 0.01, rel=1e-6)
    assert pr[('use', 'ev'), 2025] > 0


# ---- base materials: goods bought at a price, no chain behind them

CU = ('base', 'Cu')


def toy_base(price=None, **spec):
    """The toy with copper in cells (20 GWh per kt), bought at 3 in the US and 2 in China."""
    net, params = toy()
    net["stages"] = net["stages"] + ['base']
    net["out_t"] = {**net["out_t"], 'base': ['Cu']}
    net["goods"] = net["goods"] + [CU]
    net["mineral_of"] = {**net["mineral_of"], CU: None}
    net["recipe"][('cell', 'Li', 'GWh')] = {('refine', 'Li'): 10.0, CU: 20.0}
    net["base"] = {CU: {"price": price or {'US': 3.0, 'CHN': 2.0}, **spec}}
    return net, params


def _solve_h(net, params, **kw):
    m = gp.Model(); m.Params.OutputFlag = 0
    obj, h = N.build(m, params, net=net, **kw)
    m.setObjective(obj, gp.GRB.MINIMIZE); m.optimize()
    return m, h


def test_base_goods_are_bought_where_they_are_used():
    """Every kt of copper the cells take in a region is bought there, at that region's price."""
    net, params = toy_base()
    N.check_net(net)
    m, h = _solve_h(net, params)
    assert m.Status == gp.GRB.OPTIMAL
    for r in R:
        for y in Y:
            took = sum(v.X for (n, g, yy), v in h["cons"].items() if g == CU and n[-1] == r and yy == y)
            assert h["buy"][CU, r, y].X == pytest.approx(took)
    assert sum(v.X for v in h["buy"].values()) > 0
    paid = sum({'US': 3.0, 'CHN': 2.0}[r] * h["buy"][CU, r, y].X for r in R for y in Y)
    assert sum(e.getValue() for e in h["region_cost"].values()) >= paid


def test_base_price_is_the_marginal_cost_and_caps_bind():
    """Uncapped, one more kt of copper demanded costs its price there; a regional cap of 0 moves cells to China; a
    world cap below what the cells need is infeasible (base goods have no shortage)."""
    net, params = toy_base()
    pr, _ = N.price([CU], region='US', params=params, net=net, years=[2024])
    assert pr[CU, 2024] == pytest.approx(3.0)
    pr, _ = N.price([CU], region='CHN', params=params, net=net, years=[2024])
    assert pr[CU, 2024] == pytest.approx(2.0)
    net, params = toy_base(cap={'US': 0.0})
    m, h = _solve_h(net, params)
    assert m.Status == gp.GRB.OPTIMAL
    assert sum(h["buy"][CU, 'US', y].X for y in Y) == pytest.approx(0.0, abs=1e-9)
    assert sum(v.X for (n, y), v in h["prod"].items() if n[0] == 'cell' and n[-1] == 'CHN') > 0
    net, params = toy_base(world_cap=0.1)
    m, _ = _solve_h(net, params)
    assert m.Status in (gp.GRB.INFEASIBLE, gp.GRB.INF_OR_UNBD)


def test_base_override_and_checks():
    """build(base=) replaces a good's spec for one run (a price by year here); bad specs are refused."""
    net, params = toy_base()
    m1, _ = _solve_h(net, params)
    m2, h2 = _solve_h(net, params, base={CU: {"price": {'US': {y: 30.0 for y in Y}, 'CHN': {y: 20.0 for y in Y}}}})
    assert m2.ObjVal > m1.ObjVal
    with pytest.raises(ValueError):
        _solve_h(net, params, base={('base', 'Al'): {"price": 1.0}})
    with pytest.raises(ValueError):
        _solve_h(net, params, base={CU: {"cost": 1.0}})
    del net["base"]
    with pytest.raises(ValueError):
        N.check_net(net)               # copper is now a good nothing makes or supplies


# ---- zoom: cut a network at some goods and buy them at what they are worth in the whole network

LI = ('refine', 'Li')


def test_cut_removes_what_only_feeds_the_cut():
    """Cutting the toy at refined lithium removes lithium's refinery and mines, and keeps recycling (it makes refined
    lithium from black mass, which lies downstream of the cut) and nickel, which the cut does not touch."""
    net, _ = toy()
    z, procs, goods = N.cut(net, [LI])
    assert procs == [('mine', 'Li'), ('refine', 'Li', 'Li')] and goods == [('mine', 'Li')]
    assert ('refine', 'bm', 'Li') in z["processes"] and ('refine', 'Ni', 'Ni') in z["processes"]
    assert ('mine', 'Li') not in z["goods"] and LI in z["goods"] and ('mine', 'Li') not in z["processes"]
    assert z["trade_only"] == [('refine', 'Li', 'Li')] and z["recipe"][('refine', 'Li', 'Li')] == {}  # its routes stay
    N.check_net(z)
    assert N.cut(net, [('mine', 'Li')])[1] == [('mine', 'Li')]     # cut at the ore: buy it, keep the refinery
    bad = {**z, "recipe": {**z["recipe"], ('refine', 'Li', 'Li'): {('refine', 'Ni'): 1.0}}}
    with pytest.raises(ValueError):
        N.check_net(bad)                           # a trade-only process has no recipe
    with pytest.raises(ValueError):
        N.cut(net, [('eol', 'ev')])                # nothing makes it (it retires): nothing upstream to remove
    with pytest.raises(ValueError):
        N.cut(net, [('refine', 'Cu')])             # not a good


def test_zoom_reproduces_the_whole_network():
    """Zoomed at refined lithium (price, value and quantities from the whole network), the toy makes and ships what
    the whole toy does, node by node."""
    net, params = toy()
    z, info = N.zoom([LI], params, net=net)
    assert info["processes"] == [('mine', 'Li'), ('refine', 'Li', 'Li')]
    N.check_net(z)
    m0, h0 = _solve_h(net, params)
    m1, h1 = _solve_h(z, params)
    assert m1.Status == gp.GRB.OPTIMAL
    for (n, y), v in h1["prod"].items():
        if n[:-1] in z["trade_only"]:
            assert v.X == 0.0                      # kept for its trade routes: it makes nothing
        else:
            assert v.X == pytest.approx(h0["prod"][n, y].X, abs=1e-6)
    bought = {(r, y): h1["buy"][LI, r, y].X for r in R for y in Y}
    assert sum(bought.values()) > 0
    assert all(bought[r, y] <= info["cap"][LI][r][y] + 1e-9 for r in R for y in Y)


# ---- 0.12.0: curves, discounting, capacity by vintage, tariffs, route shares by region

def test_cost_curve_fills_cheapest_blocks_first():
    """A two-block curve on US cells: the first 5 GWh at no extra cost, the rest at +100 per GWh. The US makes at most
    5 GWh a year (China's cells are only slightly dearer), and the objective carries the blocks used."""
    net, params = toy()
    for p in net["processes"]:
        if p[0] == 'cell':
            net["cost"]['cell'][0][p[1:] + ('CHN', 2023)] = 1.5
            for y in Y:
                net["cost"]['cell'][0][p[1:] + ('CHN', y)] = 1.5
    nodes = [p + ('US',) for p in net["processes"] if p[0] == 'cell']
    curve = [(nodes, y, [(5.0, 0.0), (None, 100.0)]) for y in Y]
    m, h = _solve_h(net, params, cost_curve=curve)
    assert m.Status == gp.GRB.OPTIMAL
    for y in Y:
        assert sum(h["prod"][n, y].X for n in nodes) <= 5.0 + 1e-6
    assert len(h["curve_x"]) == 2 * len(Y)


def test_demand_curve_takes_more_when_cheap():
    """A demand curve on US EVs: 3 more GWh worth 50 each and 3 worth 0.01 each. Cells cost about 1.1 a GWh in lithium
    and making, so the first block is taken and the second is not."""
    net, params = toy()
    dc = {(('use', 'ev'), 'US', y): [(3.0, 50.0), (3.0, 0.01)] for y in Y}
    m, h = _solve_h(net, params, demand_curve=dc)
    assert m.Status == gp.GRB.OPTIMAL
    for y in Y:
        assert h["served"][('use', 'ev'), 'US', y, 0].X == pytest.approx(3.0)
        assert h["served"][('use', 'ev'), 'US', y, 1].X == pytest.approx(0.0, abs=1e-9)
    with pytest.raises(ValueError):
        _solve_h(net, params, demand_curve={(('use', 'ev'), 'XX', 2023): [(1.0, 1.0)]})


def test_discount_weights_each_year():
    """With a 10% discount rate the objective is each year's cost weighted by 1.1^-(year - 2023): the same plan, so
    the discounted objective is the sum of the undiscounted model's yearly costs so weighted."""
    net, params = toy()
    m0, h0 = _solve_h(net, params)
    m1, h1 = _solve_h(net, dict(params, discount=0.10))
    for y in Y:                                                   # the same plan
        for n in h0["ALL"]:
            assert h1["prod"][n, y].X == pytest.approx(h0["prod"][n, y].X, abs=1e-6)
    assert m1.ObjVal < m0.ObjVal
    assert h1["weight"](2025) == pytest.approx(1.1 ** -2)


def test_cumulative_capacity_retires_the_starting_fleet():
    """capacity_rule cumulative: cell capacity starts at 50 GWh in each region and retires to 5 by 2026 (init_cap by
    year); with a one-year lead and continuous builds, capacity is built to replace it, and a plant built lives
    build_life years."""
    net, params = toy()
    net["lumpy"] = False
    for p in net["processes"]:
        if p[0] == 'cell':
            for r in R:
                params["init_cap"][p + (r,)] = {2023: 50.0, 2024: 50.0, 2025: 30.0, 2026: 5.0}
    pc, vc, fc = net["cost"]['cell']
    net["cost"]['cell'] = (pc, {k: 1.0 for k in vc}, fc)
    params = dict(params, capacity_rule="cumulative")
    m, h = _solve_h(net, params, lead={'cell': 1})
    assert m.Status == gp.GRB.OPTIMAL
    cells = [n for n in h["ALL"] if n[0] == 'cell']
    for y in Y:
        made = sum(h["prod"][n, y].X for n in cells)
        assert sum(h["cap"][n, y].X for n in cells) >= made - 1e-6
    assert sum(h["newc"][n, y].X for n in cells for y in Y) > 0.0     # 2026 needs more than the 10 left
    m2, _ = _solve_h(net, dict(params, build_life={'cell': 1}), lead={'cell': 1})
    assert m2.ObjVal > m.ObjVal - 1e-9                                  # one-year plants: rebuilt every year


def test_tariff_by_arc_and_route_share_by_region():
    """A 1000% tariff on cells from China to the US stops that trade; route shares by region bound one region only."""
    net, params = toy()
    for p in net["processes"]:
        if p[0] == 'cell':
            for y in Y:
                net["cost"]['cell'][0][p[1:] + ('US', y)] = 5.0     # US cells dear: the US would import
    m0, h0 = _solve_h(net, params)
    imp = lambda h: sum(h["flow"]['cell'][k, y].X for k, a in enumerate(h["trade"]['cell']) if a[-2:] == ('CHN', 'US')
                        for y in Y)
    assert imp(h0) > 1.0
    m1, h1 = _solve_h(net, params, tariffs={('cell', 'CHN', 'US'): 10.0})
    assert imp(h1) == pytest.approx(0.0, abs=1e-6)
    with pytest.raises(ValueError):
        _solve_h(net, params, tariffs={('nope', 'CHN', 'US'): 1.0})
    q = ('refine', 'bm', 'Li')
    m2, h2 = _solve_h(net, params, route_share={q: {"max": {'US': 0.0}}})
    assert all(h2["prod"][q + ('US',), y].X < 1e-9 for y in Y)


def test_pools_share_capacity_across_routes():
    """Two refining routes in the US pooled: the 1e6 of capacity each has becomes one limit on both together, and a
    pool with nodes of two regions is refused."""
    net, params = toy()
    a, b = ('refine', 'Li', 'Li', 'US'), ('refine', 'bm', 'Li', 'US')
    params["init_cap"][a] = 2.0; params["init_cap"][b] = 0.0
    m, h = _solve_h(net, params, pools=[{a: 1.0, b: 1.0}])
    assert m.Status == gp.GRB.OPTIMAL
    for y in Y:
        assert h["prod"][a, y].X + h["prod"][b, y].X <= 2.0 + 1e-6
    with pytest.raises(ValueError):
        _solve_h(net, params, pools=[{a: 1.0, ('refine', 'bm', 'Li', 'CHN'): 1.0}])


# ---- 0.13.0: a process's own lead, capacity ceilings, reserves over several nodes

def test_process_lead_ceiling_and_pooled_reserves():
    """A process's own lead wins over its stage's; cap_max bounds a node's capacity; a reserve on a tuple of nodes
    bounds their extraction together."""
    net, params = _jump()
    net["lumpy"] = False
    cell = next(p for p in net["processes"] if p[0] == 'cell')
    st, _, _ = _status(net, params, lead={'cell': 3})
    assert st in (gp.GRB.INFEASIBLE, gp.GRB.INF_OR_UNBD)            # the stage's three years: 2025 cannot grow
    st, _, _ = _status(net, params, lead={'cell': 3, cell: 1})       # the process's one year wins
    assert st == gp.GRB.OPTIMAL
    st, _, _ = _status(net, dict(params, cap_max={cell + (r,): 10.0 for r in R}), lead={cell: 1})
    assert st in (gp.GRB.INFEASIBLE, gp.GRB.INF_OR_UNBD)            # held at 10 + 10: the jump cannot be met
    net2, params2 = toy()
    us, chn = ('mine', 'Li', 'US'), ('mine', 'Li', 'CHN')
    m, h = _solve_h(net2, params2, reserves={(us, chn): 3.0})
    assert m.Status == gp.GRB.OPTIMAL
    assert sum(h["prod"][n, y].X for n in (us, chn) for y in Y) <= 3.0 + 1e-6
    with pytest.raises(ValueError):
        _status(net2, params2, reserves={(us, ('mine', 'Li', 'XX')): 3.0})

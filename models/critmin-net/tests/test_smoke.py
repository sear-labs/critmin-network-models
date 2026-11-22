"""No solver needed: the package imports, and its inputs load and are sane. Runs anywhere."""
import pandas as pd
import pytest


def test_imports():
    from critmin_net import network as N
    assert N.STAGES == ['mine', 'proc', 'cath', 'cell', 'pack', 'rec']
    assert N.LLNL_REGIONS == ['US', 'ALLY', 'CHN', 'ROW']


def test_alavis_tables_load():
    from critmin_net import network as N
    assert not N._read("index").empty
    for stage in N.STAGES:
        for kind in ("demand", "prod_cost", "fixed_cost", "var_cost"):
            df = N._read(f"{stage}_{kind}")
            num = df.select_dtypes("number")
            assert not df.empty and not num.isna().any().any(), f"{stage}_{kind} has blanks"
            assert (num >= 0).all().all(), f"{stage}_{kind} has negative values"


@pytest.mark.parametrize("name", ["capacity_pipeline", "country_shares_2024", "grid_storage",
                                  "stage_costs_us_china", "us_tariffs_2024"])
def test_calibration_tables_load(name):
    from critmin_net import network as N
    df = pd.read_csv(N.CAL / f"{name}.csv")
    assert not df.empty


def test_calibration_shares_cover_llnls_regions():
    from critmin_net import network as N
    sh = N.shares_2024()
    assert set(sh[("demand", None)]) <= set(N.LLNL_REGIONS)
    assert sum(sh[("demand", None)].values()) == pytest.approx(1.0, abs=1e-6)


def test_a_named_data_folder_is_used(tmp_path):
    """Local must win: $CRITMIN_NET_DATA, when set, is the folder read, not the shipped copy."""
    from critmin_net import network as N
    (tmp_path / "MANIFEST.sha256").write_text("")
    assert N.data_dir({"CRITMIN_NET_DATA": str(tmp_path)}) == tmp_path.resolve()


def test_a_named_data_folder_without_a_manifest_is_refused(tmp_path):
    from critmin_net import network as N
    with pytest.raises(FileNotFoundError):
        N.data_dir({"CRITMIN_NET_DATA": str(tmp_path)})


def test_unset_reads_the_shipped_copy():
    from critmin_net import network as N
    assert N.data_dir({}) == N.RAW and (N.RAW / "MANIFEST.sha256").is_file()


@pytest.mark.parametrize("bad", [{"stages": ["rec"]}, {"regions": ["MARS"]}, {"hold": 0.1}])
def test_stockpile_options_are_checked(bad):
    """A misspelt or impossible stockpile option is refused, not ignored. Building needs no licence to solve."""
    gp = pytest.importorskip("gurobipy")
    from critmin_net import network as N
    m = gp.Model(); m.Params.OutputFlag = 0
    with pytest.raises(ValueError):
        N.build(m, N.PUBLISHED, stockpile=bad)


def test_stockpile_off_adds_nothing():
    """Off (the default), the model is the one without the hook: same variables and constraints."""
    gp = pytest.importorskip("gurobipy")
    from critmin_net import network as N
    sizes = []
    for kw in ({}, {"stockpile": None}):
        m = gp.Model(); m.Params.OutputFlag = 0
        N.build(m, N.PUBLISHED, **kw); m.update()
        sizes.append((m.NumVars, m.NumConstrs))
    assert sizes[0] == sizes[1]


def test_the_network_sets():
    """Lithium's chain as sets: one mineral, a good per stage output, one input per process at Alavi's ratios."""
    from critmin_net import network as N
    assert N.MINERALS == ['Li']
    assert len(N.GOODS) == len(set(N.GOODS)) == sum(len(v) for v in N.OUT_T.values())
    assert ('proc', 'lce') in N.GOODS and ('rec', 'lce') in N.GOODS          # same name, different goods
    assert N.MINERAL_OF[('mine', 'spod')] == 'Li' and N.MINERAL_OF[('cell', 'GWh_lfp')] is None
    for p in N.PROCESSES:
        if p[0] == 'mine':
            assert N.RECIPE[p] == {}
        else:
            assert N.RECIPE[p] == {(N.STAGE_IN[p[0]], p[1]): N.RATIO[p[0]][p[2]]}
    N._check_sets()


def test_every_good_has_one_balance_per_region_and_year():
    """build() makes the balances from GOODS: one row per good, region and year (Alavi's notebook regions)."""
    gp = pytest.importorskip("gurobipy")
    from critmin_net import network as N
    m = gp.Model(); m.Params.OutputFlag = 0
    _, h = N.build(m, N.NOTEBOOK)
    cells = [g for g in N.GOODS if g[0] == 'cell']
    assert len(h["cell_bal"]) == len(cells) * len(h["R"]) * len(h["Y"])


def test_battery_inputs_load_and_hang_together():
    """The multi-mineral test network's inputs: every country has a region, demand is the world's, shares sum to
    at most one, and every recipe input is a good. No solver."""
    pytest.importorskip("gurobipy")
    from critmin_net import battery as B, network as N
    inp = B.load()
    for y, world in ((2023, 750.0), (2024, 950.0)):
        assert sum(v for (c, r, yy), v in inp["demand"].items() if yy == y) == pytest.approx(world)
    tot = {}
    for (s, key, r, y), v in inp["share"].items():
        tot[s, key, y] = tot.get((s, key, y), 0.0) + v
    assert all(v <= 1.0 + 1e-9 for v in tot.values()), {k: v for k, v in tot.items() if v > 1}
    assert inp["mine"][('Co', 'SPC', 2024)] > 0              # the DRC mines cobalt, in LLNL's Special region
    net, params, kw, need = B.network(inp)
    N.check_net(net)
    assert need[('Li', 2023)] > 0 and set(params["regions"]) == set(N.LLNL_REGIONS) | {'SPC'}

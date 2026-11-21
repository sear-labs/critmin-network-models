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

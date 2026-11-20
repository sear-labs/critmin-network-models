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

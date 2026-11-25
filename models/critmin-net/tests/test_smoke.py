"""No solver needed: the package imports, and its inputs load and are sane. Runs anywhere."""
import pandas as pd
import pytest


def test_imports():
    from critmin_net import network as N
    assert N.LLNL_REGIONS == ['US', 'ALLY', 'CHN', 'ROW']


def test_build_needs_a_network():
    """The engine has no network of its own (the lithium network was retired in 0.16.0): build() needs one."""
    gp = pytest.importorskip("gurobipy")
    from critmin_net import network as N
    with pytest.raises(ValueError):
        N.build(gp.Model(), {"regions": ["US"]})


def test_calibration_shares_load():
    """The 2024 shares by country the battery network starts its cathode and precursor capacity from."""
    from critmin_net import network as N
    df = pd.read_csv(N.CAL / "country_shares_2024.csv")
    assert not df.empty and {"model_stage", "group", "value", "use"} <= set(df.columns)


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


def test_battery_inputs_load_and_hang_together():
    """The multi-mineral test network's inputs: every country has a region, demand is the world's, shares sum to
    at most one, and every recipe input is a good. No solver."""
    pytest.importorskip("gurobipy")
    from critmin_net import battery as B, network as N
    inp = B.load()
    for y, world in ((2023, 770.0 + 90 + 50 + 80), (2024, 950.0 + 160 + 60 + 90)):   # EV, storage, electronics, other
        assert sum(v for (u, c, r, yy), v in inp["demand"].items() if yy == y) == pytest.approx(world)
    assert min(y for (u, c, r, y) in inp["history"]) == 2015 and max(y for (u, c, r, y) in inp["history"]) == 2022
    assert all(s["reserve"] >= 0 and s["growth"] > 0 for s in inp["reserves"].values())
    assert inp["reserves"][('Li', 'CHN')]["resources"] >= inp["reserves"][('Li', 'CHN')]["reserve"]
    tot = {}
    for (s, key, r, y), v in inp["share"].items():
        tot[s, key, y] = tot.get((s, key, y), 0.0) + v
    assert all(v <= 1.0 + 1e-9 for v in tot.values()), {k: v for k, v in tot.items() if v > 1}
    assert inp["mine"][('Co', 'SPC', 2024)] > 0              # the DRC mines cobalt, in LLNL's Special region
    net, params, kw, need = B.network(inp)
    N.check_net(net)
    assert need[('Li', 2023)] > 0 and set(params["regions"]) == set(N.LLNL_REGIONS) | {'SPC'}

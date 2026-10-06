"""Smoke tests: the repo's data is loadable, sane, and reachable from the notebooks.

Deliberately runs with NO solver and NO licence, so CI can run it on a clean
machine. Nothing here imports gurobipy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "input_data_3region"
NOTEBOOKS = ROOT / "notebooks"

CSVS = sorted(DATA.glob("*.csv"))


def test_instance_tables_exist():
    assert CSVS, f"no instance tables found under {DATA.relative_to(ROOT)}"


@pytest.mark.parametrize("csv", CSVS, ids=lambda p: p.name)
def test_table_parses_and_is_not_empty(csv):
    df = pd.read_csv(csv)
    assert not df.empty, f"{csv.name} parsed to zero rows"
    assert not df.columns.str.contains("^Unnamed").all(), (
        f"{csv.name} has no real header row"
    )


@pytest.mark.parametrize(
    "csv", [c for c in CSVS if c.name != "index.csv"], ids=lambda p: p.name
)
def test_no_negative_quantities(csv):
    """Costs, demands, capacities and CO2 coefficients cannot be negative."""
    df = pd.read_csv(csv)
    num = df.select_dtypes("number")
    bad = num.lt(0).any()
    offenders = sorted(bad[bad].index.tolist())
    assert not offenders, f"{csv.name} has negative values in {offenders}"


# Documented exception. rec_prod_cost.csv and rec_prod_CO2.csv encode
# "this recycling route does not exist" as Cost/CO2 = 9999 with a blank
# Variable name -- the chemistry-mismatched pairs (nmc -> lce, lfp -> loh).
# Real values on those tables span 0.18 .. 10.80, so the sentinel is ~925x
# the largest genuine cost. The test below pins that structure rather than
# tolerating blanks generally: if a blank ever appears anywhere else, or a
# 9999 row acquires a name, this goes red.
SENTINEL = 9999
SENTINEL_TABLES = {"rec_prod_cost.csv": "Cost", "rec_prod_CO2.csv": "CO2"}


def test_no_missing_values_outside_the_documented_sentinel():
    empties = []
    for csv in CSVS:
        if csv.name in SENTINEL_TABLES or csv.name == "index.csv":
            continue
        df = pd.read_csv(csv)
        n = int(df.isna().sum().sum())
        if n:
            empties.append(f"{csv.name}: {n}")
    assert not empties, "unexpected missing values in " + "; ".join(empties)


@pytest.mark.parametrize("name,col", sorted(SENTINEL_TABLES.items()))
def test_sentinel_rows_are_exactly_the_unnamed_rows(name, col):
    df = pd.read_csv(DATA / name)
    unnamed = df["Variable"].isna()
    sentinel = df[col] == SENTINEL

    assert unnamed.equals(sentinel), (
        f"{name}: blank Variable and {col}=={SENTINEL} no longer coincide "
        f"({int(unnamed.sum())} blank vs {int(sentinel.sum())} sentinel). "
        "Either a real row lost its name or a blocked route was priced."
    )
    assert df.loc[~unnamed, col].max() < SENTINEL, (
        f"{name}: a named route costs >= the sentinel, so the sentinel no "
        "longer reads as prohibitive"
    )
    assert set(map(tuple, df.loc[unnamed, ["Input", "Output"]].drop_duplicates().values)) == {
        ("bev_nmc", "lce"), ("phev_nmc", "lce"),
        ("bev_lfp", "loh"), ("phev_lfp", "loh"),
    }, f"{name}: the set of blocked recycling routes changed"


def test_index_horizon_is_covered_by_the_tables():
    """index.csv selects a window; every table must actually span it."""
    index = pd.read_csv(DATA / "index.csv")
    year_col = next(
        (c for c in index.columns if re.search(r"year|time|period", c, re.IGNORECASE)), None
    )
    if year_col is None:
        pytest.skip("index.csv carries no recognisable year column")

    years = pd.to_numeric(index[year_col], errors="coerce").dropna()
    assert not years.empty, "index.csv year column parsed to nothing"
    lo, hi = int(years.min()), int(years.max())
    assert lo <= hi, f"index.csv horizon runs backwards: {lo}..{hi}"

    for csv in CSVS:
        if csv.name == "index.csv":
            continue
        cols = pd.read_csv(csv, nrows=0).columns
        year_cols = [c for c in cols if re.fullmatch(r"\s*\d{4}\s*", str(c))]
        if not year_cols:
            continue
        have = {int(str(c).strip()) for c in year_cols}
        missing = sorted(set(range(lo, hi + 1)) - have)
        assert not missing, f"{csv.name} does not cover index years {missing}"


def _notebook_reads(nb_path: Path) -> list[str]:
    """Filenames the notebook loads via read_csv(DATA_DIR + '...')."""
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    src = "\n".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"
    )
    return re.findall(r"read_csv\(\s*DATA_DIR\s*\+\s*['\"]([^'\"]+)['\"]", src)


@pytest.mark.parametrize(
    "nb", sorted(NOTEBOOKS.glob("*.ipynb")), ids=lambda p: p.name
)
def test_every_notebook_read_resolves_to_a_real_file(nb):
    reads = _notebook_reads(nb)
    if not reads:
        pytest.skip("no DATA_DIR reads in this notebook")
    missing = sorted({r for r in reads if not (DATA / r).is_file()})
    assert not missing, f"{nb.name} reads files that do not exist: {missing}"


@pytest.mark.parametrize(
    "nb", sorted(NOTEBOOKS.glob("*.ipynb")), ids=lambda p: p.name
)
def test_no_hardcoded_absolute_paths(nb):
    """The failure mode this batch already has: C:\\Users\\... baked into a notebook."""
    text = nb.read_text(encoding="utf-8")
    hits = re.findall(r"[A-Za-z]:\\\\+Users[^\"']{0,80}", text)
    assert not hits, f"{nb.name} carries absolute paths: {hits[:3]}"


@pytest.mark.parametrize(
    "nb", sorted(NOTEBOOKS.glob("*.ipynb")), ids=lambda p: p.name
)
def test_no_credentials_in_notebooks(nb):
    """A licence key must reach the notebook through os.environ, never inline."""
    text = nb.read_text(encoding="utf-8")
    for field in ("WLSACCESSID", "WLSSECRET", "LICENSEID"):
        for m in re.finditer(rf"{field}\\?\"\s*:\s*([^,\n]+)", text):
            value = m.group(1)
            assert "environ" in value, (
                f"{nb.name}: {field} is not read from os.environ"
            )

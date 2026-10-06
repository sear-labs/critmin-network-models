"""Smoke tests: the repo's data is loadable, sane, and reachable from the notebook.

Runs on a clean machine with nothing but pandas and openpyxl.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw"
IMPORTS = DATA / "import_data"
NOTEBOOKS = ROOT / "notebooks"

CSVS = sorted(IMPORTS.glob("*.csv"))
EXCELS = sorted(DATA.rglob("*.xlsx"))

# The notebook reads exactly one of these tables. The other four CSVs and all
# three workbooks are committed evidence that nothing executes, so these parse
# checks are the only thing standing between them and silent rot.
ENCODING = "latin1"

# Every extract is UN Comtrade. Two were exported with a trimmed column set,
# but all five carry this core, and the analysis depends on it.
COMTRADE_CORE = {
    "refYear",
    "reporterDesc",
    "partnerDesc",
    "cmdDesc",
    "cifvalue",
    "primaryValue",
}


def test_instance_tables_exist():
    assert CSVS, f"no import tables found under {IMPORTS.relative_to(ROOT)}"
    assert EXCELS, f"no workbooks found under {DATA.relative_to(ROOT)}"


@pytest.mark.parametrize("csv", CSVS, ids=lambda p: p.name)
def test_table_parses_and_is_not_empty(csv):
    df = pd.read_csv(csv, encoding=ENCODING)
    assert not df.empty, f"{csv.name} parsed to zero rows"
    assert not df.columns.str.contains("^Unnamed").all(), (
        f"{csv.name} has no real header row"
    )


@pytest.mark.parametrize("csv", CSVS, ids=lambda p: p.name)
def test_comtrade_core_columns_are_present(csv):
    """The five extracts must stay join-compatible on the columns used."""
    cols = set(pd.read_csv(csv, encoding=ENCODING, nrows=0).columns)
    missing = sorted(COMTRADE_CORE - cols)
    assert not missing, f"{csv.name} is missing Comtrade columns {missing}"


@pytest.mark.parametrize("csv", CSVS, ids=lambda p: p.name)
def test_no_negative_trade_values(csv):
    """Quantities, weights and customs values cannot be negative."""
    df = pd.read_csv(csv, encoding=ENCODING)
    num = df.select_dtypes("number")
    bad = num.lt(0).any()
    offenders = sorted(bad[bad].index.tolist())
    assert not offenders, f"{csv.name} has negative values in {offenders}"


@pytest.mark.parametrize("csv", CSVS, ids=lambda p: p.name)
def test_reference_years_are_plausible(csv):
    """A four-digit year that is not a year is a column-shift, caught here."""
    years = pd.read_csv(csv, encoding=ENCODING)["refYear"].dropna().astype(int)
    assert not years.empty, f"{csv.name} has no reference years"
    assert years.between(1990, 2100).all(), (
        f"{csv.name} has refYear values outside 1990..2100: "
        f"{sorted(set(years[~years.between(1990, 2100)]))[:5]}"
    )


# Documented exception. Comtrade leaves qtyUnitAbbr blank on rows reported
# without a quantity unit -- 6 in graphite, 5 in raw minerals, 2 in processed
# lithium. That is upstream's gap and is expected. A blank in any other
# column is not, and neither is a blank in a value column.
def test_missing_values_are_confined_to_the_quantity_unit_column():
    problems = []
    for csv in CSVS:
        df = pd.read_csv(csv, encoding=ENCODING)
        for col in df.columns:
            n = int(df[col].isna().sum())
            if n and col != "qtyUnitAbbr":
                problems.append(f"{csv.name}:{col}={n}")
    assert not problems, (
        "missing values outside the documented qtyUnitAbbr gap: " + ", ".join(problems)
    )


@pytest.mark.parametrize("xlsx", EXCELS, ids=lambda p: p.name)
def test_workbook_parses_and_has_a_populated_sheet(xlsx):
    sheets = pd.read_excel(xlsx, sheet_name=None)
    assert sheets, f"{xlsx.name} has no sheets"
    assert any(not df.empty for df in sheets.values()), (
        f"{xlsx.name} has sheets but every one of them is empty"
    )


def test_production_workbook_still_covers_all_five_minerals():
    """The production workbook is one sheet per mineral. A dropped sheet is a
    dropped mineral, and nothing else in the repo would say so."""
    path = DATA / "critical_mineral_production" / "Global Critical Mineral Production.xlsx"
    sheets = set(pd.read_excel(path, sheet_name=None))
    expected = {
        "Global Lithium Market Share",
        "Nickel",
        "Cobalt",
        "Copper",
        "Manganese",
    }
    assert expected <= sheets, f"missing mineral sheets: {sorted(expected - sheets)}"


def _code_source(nb_path: Path, drop_comments: bool = True) -> str:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    src = "\n".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"
    )
    if drop_comments:
        src = "\n".join(re.sub(r"#.*$", "", line) for line in src.splitlines())
    return src


@pytest.mark.parametrize(
    "nb", sorted(NOTEBOOKS.glob("*.ipynb")), ids=lambda p: p.name
)
def test_every_notebook_read_resolves_to_a_real_file(nb):
    src = _code_source(nb)
    reads = [
        (m.group(1), IMPORTS / m.group(1))
        for m in re.finditer(
            r"DATA_DIR\s*[/+]\s*['\"]([^'\"]+\.(?:csv|xlsx))['\"]", src
        )
    ]
    if not reads:
        pytest.skip("no DATA_DIR reads in this notebook")
    missing = sorted({lit for lit, path in reads if not path.is_file()})
    assert not missing, f"{nb.name} reads files that do not exist: {missing}"


@pytest.mark.parametrize(
    "nb", sorted(NOTEBOOKS.glob("*.ipynb")), ids=lambda p: p.name
)
def test_data_dir_is_repo_relative_and_overridable(nb):
    src = _code_source(nb)
    if "DATA_DIR" not in src:
        pytest.skip("notebook does not use DATA_DIR")
    assert re.search(r"DATA_DIR\s*=\s*Path\(\s*os\.environ\.get\(", src), (
        f"{nb.name}: DATA_DIR is no longer an os.environ.get() with a "
        "repo-relative default"
    )
    assert "CRITMIN_DATA" in src, f"{nb.name}: the CRITMIN_DATA override is gone"


@pytest.mark.parametrize(
    "nb", sorted(NOTEBOOKS.glob("*.ipynb")), ids=lambda p: p.name
)
def test_no_live_colab_only_calls(nb):
    """This notebook came from Colab, where the data arrived through an
    interactive `files.upload()`. That call cannot run anywhere else, and
    replacing it with a repo-relative path is what made the repo runnable.
    The old line survives as a comment; it must not come back as code."""
    src = _code_source(nb)
    for call in ("files.upload(", "google.colab", "drive.mount("):
        assert call not in src, f"{nb.name} has a live Colab-only call: {call}"


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
    """This repo needs no solver, but the guard is the same one the rest of
    the batch carries and costs nothing to keep in step."""
    text = nb.read_text(encoding="utf-8")
    for field in ("WLSACCESSID", "WLSSECRET", "LICENSEID"):
        for m in re.finditer(rf"{field}\\?\"\s*:\s*([^,\n]+)", text):
            value = m.group(1)
            assert "environ" in value, (
                f"{nb.name}: {field} is not read from os.environ"
            )

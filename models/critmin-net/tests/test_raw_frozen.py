"""The inputs are frozen: every file matches src/critmin_net/data/MANIFEST.sha256 and nothing unlisted appears.

Nothing writes to them (Part 1, rule 4). An input changes only on purpose: see
src/critmin_net/data/SOURCES.md, then `python scripts/freeze_raw.py` and a commit that says why.

Watch it fail
-------------
    echo x >> src/critmin_net/data/calibration/us_tariffs_2024.csv
    pytest -q tests/test_raw_frozen.py       # MUST go red, naming that file
    git checkout src/critmin_net/data                    # restore
"""
import hashlib
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "src" / "critmin_net" / "data"
DOCS = {"MANIFEST.sha256", "SOURCES.md"}


def listed():
    rows = (RAW / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    return dict(reversed(line.split("  ", 1)) for line in rows if line.strip())


def present():
    return {p.relative_to(RAW).as_posix(): p for p in RAW.rglob("*") if p.is_file() and p.name not in DOCS}


def test_manifest_is_not_empty():
    assert len(listed()) >= 55, "MANIFEST.sha256 lists fewer files than the data folder was frozen with (55)"


def test_every_listed_file_is_present_and_unchanged():
    files = present()
    missing = sorted(set(listed()) - set(files))
    changed = sorted(k for k, h in listed().items()
                     if k in files and hashlib.sha256(files[k].read_bytes()).hexdigest() != h)
    assert not missing, f"frozen inputs missing: {missing}"
    assert not changed, f"frozen inputs changed (see src/critmin_net/data/SOURCES.md): {changed}"


def test_no_unlisted_files():
    extra = sorted(set(present()) - set(listed()))
    assert not extra, f"files in the data folder but not in MANIFEST.sha256: {extra}"

"""Write src/critmin_net/data/MANIFEST.sha256: one line per frozen input, sorted, paths relative to the data folder.

Run only when an input is changed on purpose (see src/critmin_net/data/SOURCES.md), then commit both.
"""
import hashlib
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "src" / "critmin_net" / "data"
SKIP = {"MANIFEST.sha256", "SOURCES.md"}


def manifest():
    return {p.relative_to(RAW).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(RAW.rglob("*")) if p.is_file() and p.name not in SKIP}


if __name__ == "__main__":
    m = manifest()
    (RAW / "MANIFEST.sha256").write_text("".join(f"{h}  {k}\n" for k, h in m.items()), encoding="utf-8", newline="\n")
    print(f"{len(m)} files")

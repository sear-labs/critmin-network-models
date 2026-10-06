#!/usr/bin/env python
"""Fail if a tracked file contains something credential-shaped.

    python tools/credscan.py            # scan every tracked file
    python tools/credscan.py --staged   # scan what is about to be committed

**Why this exists.** Copied, unchanged in substance, from
`sear-labs/advopt-lithiumsc/tools/credscan.py`, where it was written 2026-09-03
after a live Gurobi WLS key was found sitting in a notebook code cell - past a
`.gitignore` that excluded `gurobi.lic` and `*.lic`, and past a `git check-ignore`
run on every add. All of that guarded the *file* form of the credential.

This repository then made the same mistake in its own first notebook commit
(2026-09-08), which is the argument for running the check here rather than
assuming the lesson travelled with the model.

A path-based rule cannot catch a secret pasted into a notebook. This scans
content, which is the only thing that can.

The check is deliberately shallow and noisy-on-purpose: it looks for a key name
next to a value that is not obviously a placeholder. False positives are cheap to
silence by using a `<placeholder>`; a false negative ships a key.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# name-of-secret followed by a value, in JSON, Python dict, or KEY=VALUE form
PATTERNS = [
    ("WLS / Gurobi licence",
     re.compile(r'(WLSACCESSID|WLSSECRET|LICENSEID)\s*["\']?\s*[:=]\s*["\']?([^\s,"\'}\]]+)',
                re.IGNORECASE)),
    ("generic secret assignment",
     re.compile(r'\b(api[_-]?key|secret|token|password|passwd|access[_-]?key)\s*'
                r'["\']?\s*[:=]\s*["\']([^"\']{12,})["\']', re.IGNORECASE)),
    ("private key block",
     re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ("AWS access key id", re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
]

# A value that is plainly not a secret. Note the first alternative matches a
# LEADING angle bracket rather than a balanced pair: the value capture above
# stops at whitespace, so "<your WLS access id>" arrives here as "<your".
PLACEHOLDER = re.compile(
    r'^(<.*|\{\{.*|\$\{.*|your[_-].*|xxx+|\.\.\.|none|null|true|false|None)$',
    re.IGNORECASE)

# ...and a value that is obviously code rather than a literal: a call, a
# subscript, an attribute lookup, or the start of an f-string.
CODE_LIKE = re.compile(r'''[(\[]|^f?["']|\.\w+$|^\w+\.\w+''')

TEXT_SUFFIXES = {".py", ".ipynb", ".md", ".yml", ".yaml", ".toml", ".cfg",
                 ".json", ".txt", ".sh", ".ps1", ".csv", ".env"}


def tracked_files(staged: bool) -> list[Path]:
    cmd = (["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
           if staged else ["git", "ls-files"])
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    return [ROOT / line for line in out.splitlines() if line.strip()]


def searchable_text(path: Path) -> str:
    """Notebook sources are JSON-escaped, so decode them before scanning."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".ipynb":
        return raw
    try:
        nb = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    parts = []
    for cell in nb.get("cells", []):
        parts.append("".join(cell.get("source", [])))
        for out in cell.get("outputs", []):
            if "text" in out:
                parts.append("".join(out["text"]))
            for val in (out.get("data") or {}).values():
                parts.append("".join(val) if isinstance(val, list) else str(val))
    return "\n".join(parts)


def is_text(path: Path) -> bool:
    """Decide by suffix - except for dotfiles, which have none.

    `Path('.env').suffix` is '' (the leading dot is the name, not an
    extension), so a suffix test alone skips `.env` and `.env.local`: the one
    file most likely to hold a live key. The first credential scan in this
    lab missed every `.env` for exactly that reason.
    """
    if path.name.lower().startswith(".env"):
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def scan(paths) -> list[tuple[Path, int, str, str]]:
    hits = []
    for path in paths:
        if not is_text(path) or not path.exists():
            continue
        if path.name == "credscan.py":       # this file names the patterns
            continue
        text = searchable_text(path)
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pat in PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                value = m.group(m.lastindex) if m.lastindex else ""
                v = value.strip().strip('"\'')
                if v and (PLACEHOLDER.match(v) or CODE_LIKE.search(v)):
                    continue
                if not value:                # private-key block, no value group
                    hits.append((path, lineno, label, "<key block>"))
                    continue
                masked = value[:2] + "…" + f"({len(value)} chars)"
                hits.append((path, lineno, label, masked))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staged", action="store_true",
                    help="scan staged changes rather than the whole tree")
    args = ap.parse_args()

    paths = tracked_files(args.staged)
    hits = scan(paths)
    scope = "staged files" if args.staged else "tracked files"
    if not hits:
        print(f"credscan: {len(paths)} {scope}, nothing credential-shaped")
        return 0

    print(f"credscan: {len(hits)} possible credential(s) in {scope}\n")
    for path, lineno, label, masked in hits:
        rel = path.relative_to(ROOT)
        print(f"  {rel}:{lineno}  [{label}]  value {masked}")
    print("\nIf these are real, the fix is to ROTATE the credential - deleting it")
    print("in a later commit does not remove it from history. Then read it from")
    print("an environment variable or a Colab secret. If they are examples, write")
    print("the value as <a placeholder in angle brackets> so this check passes.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

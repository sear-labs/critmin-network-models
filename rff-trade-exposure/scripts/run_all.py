"""Single-command entry point — not implemented yet.

Run notebooks/trade-data-analysis.ipynb directly for now.
"""

import sys


def main() -> int:
    sys.stderr.write(
        "scripts/run_all.py is a placeholder.\n"
        "Run notebooks/trade-data-analysis.ipynb for now.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

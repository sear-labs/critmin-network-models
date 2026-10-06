"""Single-command entry point — reproduces every result in the repo.

Not implemented yet. The model currently lives in
``notebooks/full6stage-network.ipynb``; run that directly. This script
becomes real once the build/solve steps move into ``src/mineralnet/``.
"""

import sys


def main() -> int:
    sys.stderr.write(
        "scripts/run_all.py is a placeholder.\n"
        "Run notebooks/full6stage-network.ipynb for now.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

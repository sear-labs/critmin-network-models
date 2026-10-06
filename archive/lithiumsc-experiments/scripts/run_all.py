"""Single-command entry point — not applicable yet.

This repo holds 12 independent exploratory notebooks, not one pipeline.
Run whichever notebook in notebooks/ you need directly.
"""

import sys


def main() -> int:
    sys.stderr.write(
        "scripts/run_all.py is a placeholder -- this repo is an archive of\n"
        "independent notebooks, not one pipeline. Run a notebook directly.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

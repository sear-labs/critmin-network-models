# critmin-net conventions

The portable standard governs this folder. Read it before working here, and again before you finish:
  https://github.com/sear-labs/code-standard

# Part 11: this folder specifically

**Archetype A + C**: a model other projects import. SemVer, `CHANGELOG.md`, real tests.

- **This is the lab's one maintained network model (Jones, 2026-11-20).** Other network models in
  the lab derive from it. Do not start a parallel copy; propose the change here.
- **Two tests must stay green** (`tests/test_solver.py`, `pytest -m solver`, needs a full Gurobi
  licence): agreement with Alavi's notebook to 1e-6, which nothing may move; and the baseline numbers
  to 1e-9, which move only on purpose, with the file regenerated and the reason in the commit and
  CHANGELOG.
- **New features are off by default** and leave the baseline unchanged while off.
- **Sensitivity: private.** `src/critmin_net/data/mineralnet-optsc/` and `src/critmin_net/data/reference/` are Alavi's
  unpublished data. Making this public needs them cleared or removed first, and the decision is Jones's.
- **Writers: one machine at a time** for anything that regenerates `tests/baseline/` (Gurobi and BLAS
  versions can move the last digits).
- **Credit Alavi** for the network wherever it appears, and say the regional map is our calibration,
  not hers or LLNL's.
- `src/critmin_net/data/` is frozen (`test_raw_frozen.py`); refresh an input only on purpose, via
  `scripts/freeze_raw.py`, saying why in the commit and in `src/critmin_net/data/SOURCES.md`.

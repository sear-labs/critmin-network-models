# critmin-net conventions

The portable standard governs this folder. Read it before working here, and again before you finish:
  https://github.com/sear-labs/code-standard

# Part 11: this folder specifically

**Archetype A + C**: a model other projects import. SemVer, `CHANGELOG.md`, real tests.

- **This is the lab's one maintained network model (Jones, 2026-11-20).** Other network models in
  the lab derive from it. Do not start a parallel copy; propose the change here.
- **Every test runs on the current model** (Jones, 2026-11-25): the battery network and its horizon, and the
  engine's mechanics on a toy network (`tests/test_lifecycle.py`). The lithium network was retired in 0.16.0; it
  lives in history (0.15.x), not on main, and no test or data here depends on it.
- **The battery model's objectives** (`tests/baseline/battery_0.16.0.json`, `pytest -m solver`, needs a full
  Gurobi licence) move only on purpose, with the file regenerated and the reason in the commit and CHANGELOG.
- **New features are off by default** and leave the baseline unchanged while off.
- **Sensitivity: public** (Jones, 2026-11-25). The data are ours and cited (CC BY 4.0). Alavi's six-stage inputs
  were taken out of the tree with the lithium network (history keeps them).
- **Writers: one machine at a time** for anything that regenerates `tests/baseline/` (Gurobi and BLAS
  versions can move the last digits).
- **Credit Alavi** for the engine's origin (a port of her six-stage lithium network), and say the regional map is
  our calibration, not hers or LLNL's.
- `src/critmin_net/data/` is frozen (`test_raw_frozen.py`); refresh an input only on purpose, via
  `scripts/freeze_raw.py`, saying why in the commit and in `src/critmin_net/data/SOURCES.md`.

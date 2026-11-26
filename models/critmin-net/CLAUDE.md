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
- **Sensitivity: public** (Jones, 2026-11-25). The data are ours and cited (CC BY 4.0). The prototype's inputs
  left the tree with its lithium network (0.16.0).
- **Releases are archived on Zenodo** (switched on 2026-11-25; all versions: 10.5281/zenodo.24540500). Each GitHub
  release makes a deposit from `.zenodo.json`, so release only on purpose. A release's 202 from Zenodo is not a
  deposit: confirm with an authenticated GET on `/api/deposit/depositions` (state `done`, a DOI), then put the new
  version's DOI in `CITATION.cff` and the READMEs.
- **Writers: one machine at a time** for anything that regenerates `tests/baseline/` (Gurobi and BLAS
  versions can move the last digits).
- **Credit, in one factual line, as the READMEs do** (Jones, 2026-11-26): the model is built on Jones's
  formulation; an early six-stage lithium prototype by Sara Alavi was its starting point; it has since been rebuilt.
  Her own model is in her repository, not here. Say the regional map is our calibration, not LLNL's.
- `src/critmin_net/data/` is frozen (`test_raw_frozen.py`); refresh an input only on purpose, via
  `scripts/freeze_raw.py`, saying why in the commit and in `src/critmin_net/data/SOURCES.md`.

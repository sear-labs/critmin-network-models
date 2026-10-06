# lithiumsc-experiments

> **The rules are not in this file.** They live in one document, deliberately not restated here:
>
>     https://github.com/sear-labs/code-standard    canonical — the same from any machine
>
> **Read it first and last.** This file adds only what is specific to this project.

---

# Part 11 — This project specifically

**Archetype: A**, archival. 12 notebooks, an experimental lineage rather than one model.

**Provenance.** Migrated 2026-09-15 from [`searlab/SEAR_Lab`](https://github.com/searlab/SEAR_Lab)
(`LithiumSupplyChain/`). See `README.md` for the unresolved data-path issue affecting 8 of the 12
notebooks — **do not attempt a blanket path fix without running each notebook to verify**; the
biofuel and mineralnet-optsc-iise-2026 migrations show the pattern to follow one notebook at a time.

**Relationship to `mineralnet-optsc-iise-2026`.** This is the prior/parallel experimental lineage, not a
duplicate to be merged. The user was explicit: keep them separate.

**`data/raw/input_files/` vs `mineralnet-optsc-iise-2026`'s `input_data_3region/`.** Same 42 filenames, same
schema, **not diffed** against each other — do not assume they hold the same values.

**The four startup questions** (standard Part 2c):
- *Sensitivity:* instance data cleared for this private repo.
- *Active development:* archival for now — confirm with Jones which (if any) notebook is still live.
- *Syncing folder:* clone outside OneDrive.
- *Multi-device editing:* single author so far.

**Not done yet:** the `New input files` path fix (8 notebooks, see README), `src/`,
`scripts/run_all.py`, `tests/`, confirming which test notebook (if any) superseded the others.

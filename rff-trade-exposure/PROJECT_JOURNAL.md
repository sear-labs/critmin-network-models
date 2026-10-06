# Project journal

## 2026-09-15 — repository created

- Migrated from Google Drive, `Sara/RFF (Critical Mineral Lab)/` (shared with the author, not a
  prior GitHub repo): 1 notebook, 5 trade-data CSVs, 2 xlsx data tables, 16 docs (briefs,
  presentations, project outline, UN Trade and Development report).
- Notebook's Colab `files.upload()` replaced with a repo-relative `DATA_DIR`; verified
  `LFP-CAM.csv` resolves. Outputs cleared.
- **Excluded** `lfp-0525-granted.csv` (192 MB Lens.org patent-database export) — too large for
  GitHub, redistribution terms unchecked. Noted in README.

### Open

- Confirm with Jones whether this collaboration data needs handling beyond "private repo."
- Decide what to do about the excluded patent-data file (re-derive a smaller query result?).
- Engineering half (`src/`, `scripts/run_all.py`, `tests/`) not started.
- No published paper found on Google Scholar for this specific analysis (as of 2026-09-15) — no
  `CITATION.cff` yet.

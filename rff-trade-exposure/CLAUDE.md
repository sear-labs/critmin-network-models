# critmin-tradeexposure

> **The rules are not in this file.** They live in one document, deliberately not restated here:
>
>     https://github.com/sear-labs/code-standard    canonical — the same from any machine
>
> **Read it first and last.** This file adds only what is specific to this project.

---

# Part 11 — This project specifically

**Archetype: A**, data-analysis (not an optimization model like the other repos). One notebook,
trade tables, presentations/briefs for the RFF Critical Mineral Lab collaboration.

**Provenance.** Migrated 2026-09-15 from a Google Drive folder shared with the author
(`Sara/RFF (Critical Mineral Lab)/`), not from a prior GitHub repo. `file_path` (Colab's
`files.upload()`) replaced with a repo-relative `DATA_DIR`; verified it resolves.

**`lfp-0525-granted.csv` deliberately excluded** (192 MB Lens.org patent export, exceeds GitHub's
file-size limit, license terms unchecked) — see README. If this analysis needs it, re-derive a
smaller query result rather than committing the full export.

**The four startup questions** (standard Part 2c):
- *Sensitivity:* this is external-partner (RFF) collaboration data in a **private** repo. Confirm
  with Jones whether any of it needs handling beyond "private" before wider sharing.
- *Active development:* confirm with Jones/Alavi — migrated from an actively-updated Drive folder
  (files dated through March 2026).
- *Syncing folder:* clone outside OneDrive.
- *Multi-device editing:* single author so far.

**Not done yet:** `src/critmin/` package, `scripts/run_all.py`, `tests/`, deciding what to do about
the excluded patent-data file, `CITATION.cff` (no associated paper found on Scholar for this
specific analysis as of 2026-09-15).

**Lineage.** Assembled 2026-09-15 from the Google Drive folder
`Sara/RFF (Critical Mineral Lab)/`. That folder is superseded by this repository and should not be
edited further; the commit history here records what came from where. One file was deliberately
left behind — see the note on `lfp-0525-granted.csv` in the README.

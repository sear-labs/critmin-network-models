# critmin-tradeexposure — critical mineral trade & import-exposure analysis

Trade and import-exposure analysis for critical minerals (lithium, graphite, cell components,
cathode active material), for the **RFF (Critical Mineral Lab)** project: FEOC (Foreign Entity of
Concern) import exposure, friendshoring, and country-share-of-world-trade by commodity.

This repository is the definitive version of this analysis. It follows [`sear-labs/code-standard`](https://github.com/sear-labs/code-standard)
(Archetype A).

**Status: exploratory — early phase, not yet reproducible.** The notebook runs; there is no
packaged implementation, and `scripts/run_all.py` is a placeholder.

## What is here

| Path | Contents |
|---|---|
| `notebooks/trade-data-analysis.ipynb` | Loads UN Comtrade-style trade data by commodity, computes top-10-country shares and non-PFE-MACR figures, plots by commodity. Outputs cleared; data path fixed (see below). |
| `data/raw/import_data/` | 5 trade tables: `LFP-CAM.csv`, `cell component-separator.csv`, `graphite.csv`, `processed Lithium.csv`, `raw minerals.csv`. |
| `data/raw/critical_mineral_production/` | `Global Critical Mineral Production.xlsx`. |
| `data/raw/friendshoring/` | `Friendshoring Data Collection.xlsx`, `US Investment in FTA Countries.xlsx`. |
| `docs/` | Project outline, FEOC exposure analysis, friendshoring briefs/two-pager, tech-dependence brief, presentations (3/18, mine-permit reform, RFF), UN Trade and Development report, summary-stats PDF. |

## ⚠ Not included: `lfp-0525-granted.csv`

A 192 MB Lens.org patent-database export (LFP-related patents by jurisdiction) sat alongside the
data above. **Not committed** — it exceeds GitHub's per-file size limit, and its redistribution
terms under Lens.org's license weren't checked. It's still in the source Google Drive folder if
needed; consider whether it should be re-derived from a query instead of stored wholesale.

## Run it

```bash
pip install -e .
jupyter lab notebooks/trade-data-analysis.ipynb
```

The notebook reads `../data/raw/import_data/` relative to itself (was Colab's interactive
`files.upload()`). Override with the `CRITMIN_DATA` environment variable.

## Standard

This repo follows [`sear-labs/code-standard`](https://github.com/sear-labs/code-standard). Project
specifics are in [`CLAUDE.md`](CLAUDE.md), Part 11.

## Licence

MIT — see [`LICENSE`](LICENSE).

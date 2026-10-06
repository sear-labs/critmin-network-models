# Project journal

## 2026-09-15 — repository created

- Migrated from `searlab/SEAR_Lab/LithiumSupplyChain/`: 12 notebooks (11 from `Codes/`, 1 from
  `ExcelFiles/ResultAnalysis/`), 42 instance tables (`ExcelFiles/Input_files/`), 7 result
  spreadsheets/CSV (`ExcelFiles/ResultAnalysis/`), 3 papers (`Papers/`).
- Notebook outputs cleared on all 12.
- **Data paths NOT fixed** for 8 of the 12 notebooks — they hardcode
  `C:\Users\sxa2334\Downloads\Lithium Modeling\Code\jupyter_folder\input_csvs\New input files\...`,
  a folder not present in this repo (superset of `data/raw/input_files/`, includes
  import/export/stockpile cost tables). See README for the full list and why this was left rather
  than guessed at.
- Renamed notebooks from their original filenames:

  | New name | Original |
  |---|---|
  | `li-impexp-stock.ipynb` | `Li_ImpExpStock_test-6-9-25-checkpoint (1).ipynb` |
  | `ufl-main-dr-jones-noinitial.ipynb` | `Lithium_UFL_main_Dr.Jones-checkpoint-NoInitial (1).ipynb` |
  | `adding-new-constraints-adjustment.ipynb` | `addingNewCons1By1-SCA-initialCons-Adjustment (1).ipynb` |
  | `lithium-network-v4.ipynb` | `lithium_Network_v4.ipynb` |
  | `marketshare-data-analysis.ipynb` | `main_marketshare_Li_SC_DataAnalysis (1).ipynb` |
  | `test10-only-region-no-trade-initialcons.ipynb` | `test10-OnlyRegion-NoTrade-InitialCons-Copy1 (1).ipynb` |
  | `test11-no-trade-no-initialcons.ipynb` | `test11-NoTrade-NoInitialCons (1).ipynb` |
  | `test2-adding-new-constraints.ipynb` | `test2-addingNewCons1By1-SCA-initialCons-Copy1-checkpoint (1).ipynb` |
  | `test3-marketshare-objective.ipynb` | `test3-MarketShare-ObjectiveFunction (1).ipynb` |
  | `test8-2-impexp-binary-decision.ipynb` | `test8.2-imporexp-CorrectBinaryDecision (1).ipynb` |
  | `test9-only-region-no-trade.ipynb` | `test9-OnlyRegion-NoTrade (1).ipynb` |
  | `semifinal-data-analysis.ipynb` | `semifinal_Li_SC_DataAnalysis_SingleFile.ipynb` |

### Open

- Fix the 8 notebooks' data paths, one at a time, verifying each (see README).
- Confirm with Jones which test variant (if any) is current vs. fully superseded.
- `data/raw/input_files/` not diffed against `mineralnet-optsc`'s `input_data_3region/` despite
  matching filenames — don't assume they're the same values.
- Engineering half (`src/`, `scripts/run_all.py`, `tests/`) not started.

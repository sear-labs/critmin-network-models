# critmin_net/data: where every frozen input came from

Everything here is an input from outside this folder, copied once and never written by any stage.
`MANIFEST.sha256` lists every file's checksum and `tests/test_raw_frozen.py` fails if a file changes,
disappears or appears unlisted. To refresh an input on purpose: copy the new version in, regenerate the
manifest (`python scripts/freeze_raw.py`), and say why in the commit.

The first three folders were copied on 2026-11-20 from critmin-energy-surrogatecoupling's `data/raw/` at
`5c3616a` (here they sat in `data/raw/` until 0.2.0, which moved them into the package so they install with it), byte for byte (the same checksums), where they were frozen on the dates below.

| Folder | Source, commit | Files | Whose |
|---|---|---|---|
| `mineralnet-optsc/` | `sear-labs/mineralnet-optsc` @ `18e67de6b9635b0c2926b4dd94695ebb00235da3` (2026-10-06) | `data/raw/input_data_3region/*.csv`: the six-stage network's inputs | Alavi |
| `reference/` | `scripts/reference_sara_network.py` run on her notebook (`notebooks/full6stage-network.ipynb` at the commit above), 2026-10-26 | her notebook's objective and solution tables, which `network.check_agreement()` compares against | Alavi |
| `calibration/` | compiled 2026-10-28 and 10-29 from published sources, one row per number with its source: USGS Mineral Commodity Summaries 2025; IEA Global EV Outlook 2025, Global Critical Minerals Outlook 2025 and Batteries and Secure Energy Transitions 2024; Kleiner, Karaduman & Xu, Stanford GSB technical report and Excel model (2026-02-02); White House Section 301 fact sheet (2024-05-14); EIA-860M (December 2024) | `country_shares_2024.csv`, `capacity_pipeline.csv`, `grid_storage.csv`, `stage_costs_us_china.csv`, `us_tariffs_2024.csv`: what `network.calibrated()` reads; `regional_shares_2024.csv`: an earlier three-region calibration, kept for the record | public sources |
| `battery_2023_2024/` | compiled 2026-11-21 from published sources, one row per number with its URL and table, figure or page: USGS Mineral Commodity Summaries 2025 (lithium, nickel, cobalt, manganese, graphite chapters); IEA Global Critical Minerals Outlook 2024 and 2025 (annex tables and text); IEA Global EV Outlook 2024 and 2025; ICCT (2024) *Electrifying road transport with less mining*, Table A4 (Argonne GREET 2022 intensities); IRENA (2024), Table A2.6; for losses, Kelly et al. (2021) *Resour. Conserv. Recycl.*, Argonne (BatPaC v5, GREET 2018 cathode update, the 2022 graphite report), Wei et al. (2020) *Energies*, IEA GEVO 2024, ICCT (2024), Fraunhofer FFB, the EU fertiliser BREF (2007) and company feasibility reports (single projects, labelled). `regions.csv` (country to region) is ours. | `mine_production.csv`, `refining_shares.csv`, `battery_demand.csv`, `cell_production.csv`, `material_intensity.csv`, `battery_share_of_demand.csv`, `regions.csv`, `stage_losses.csv` (published losses by stage, 62 rows, gaps marked; `battery.LOSSES` picks from it); added 2026-11-22: `battery_demand_by_use.csv` (IEA, by end use and region, 2015-2024), `mineral_demand_by_use.csv` (IEA GCMO annex, by use; USGS lithium end uses), `refined_production.csv` (IEA, by country), `reserves.csv` (USGS MCS 2025 reserves, resources and mine output; MCS 2015 world reserves), `lifecycle.csv` (120 published values: lifetimes, second life, recovery, recycling utilisation; Xu et al. 2020, Zeng et al. 2022, ICCT, T&E, RMI, IEA, EU Batteries Regulation): what `battery.load()` reads for the multi-mineral test network | public sources; the mapping is ours |

**Not for redistribution.** Alavi's network data and reference solution are unpublished lab data.
The licence covers this folder's code, not these files.

**Alavi's later data.** Her repo moved on after `18e67de` (on 2026-11-18: a 2050 horizon, demand for
her third region, world demand totals). Bringing any of it in is a refresh as above, and must keep
`check_agreement()` meaningful: re-run her notebook at the new commit for a new reference.

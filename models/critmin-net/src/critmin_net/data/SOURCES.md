# critmin_net/data: where every frozen input came from

Everything here is an input from outside this folder, copied once and never written by any stage.
`MANIFEST.sha256` lists every file's checksum and `tests/test_raw_frozen.py` fails if a file changes,
disappears or appears unlisted. To refresh an input on purpose: copy the new version in, regenerate the
manifest (`python scripts/freeze_raw.py`), and say why in the commit.

All three folders were copied on 2026-11-20 from critmin-energy-surrogatecoupling's `data/raw/` at
`5c3616a` (here they sat in `data/raw/` until 0.2.0, which moved them into the package so they install with it), byte for byte (the same checksums), where they were frozen on the dates below.

| Folder | Source, commit | Files | Whose |
|---|---|---|---|
| `mineralnet-optsc/` | `sear-labs/mineralnet-optsc` @ `18e67de6b9635b0c2926b4dd94695ebb00235da3` (2026-10-06) | `data/raw/input_data_3region/*.csv`: the six-stage network's inputs | Alavi |
| `reference/` | `scripts/reference_sara_network.py` run on her notebook (`notebooks/full6stage-network.ipynb` at the commit above), 2026-10-26 | her notebook's objective and solution tables, which `network.check_agreement()` compares against | Alavi |
| `calibration/` | compiled 2026-10-28 and 10-29 from published sources, one row per number with its source: USGS Mineral Commodity Summaries 2025; IEA Global EV Outlook 2025, Global Critical Minerals Outlook 2025 and Batteries and Secure Energy Transitions 2024; Kleiner, Karaduman & Xu, Stanford GSB technical report and Excel model (2026-02-02); White House Section 301 fact sheet (2024-05-14); EIA-860M (December 2024) | `country_shares_2024.csv`, `capacity_pipeline.csv`, `grid_storage.csv`, `stage_costs_us_china.csv`, `us_tariffs_2024.csv`: what `network.calibrated()` reads; `regional_shares_2024.csv`: an earlier three-region calibration, kept for the record | public sources |

**Not for redistribution.** Alavi's network data and reference solution are unpublished lab data.
The licence covers this folder's code, not these files.

**Alavi's later data.** Her repo moved on after `18e67de` (on 2026-11-18: a 2050 horizon, demand for
her third region, world demand totals). Bringing any of it in is a refresh as above, and must keep
`check_agreement()` meaningful: re-run her notebook at the new commit for a new reference.

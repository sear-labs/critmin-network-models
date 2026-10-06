# critmin-network-models — critical-mineral network models and the RFF trade-exposure analysis

All network-optimization models for battery-mineral and lithium supply chains, plus the RFF
(Critical Mineral Lab) trade-exposure analysis. Replaces the earlier repos `mineralnet-optsc`,
`lithiumsc-experiments` and `critmin-tradeexposure`, whose files now live here.

## Layout

| Folder | What it is | Source |
|---|---|---|
| `models/six-stage-mineralnet/` | Six-stage (mine → recycling) multi-region model, exploratory | `mineralnet-optsc` (main branch) |
| `rff-trade-exposure/` | RFF Critical Mineral Lab: import exposure, FEOC, friendshoring | `critmin-tradeexposure` |
| `archive/lithiumsc-experiments/` | Archived lithium formulation lineage (12 notebooks, 3 papers, data). Kept for reference, not maintained. | `lithiumsc-experiments` (archived) |
| `game-theory/` | Not here. Bilevel and Benders formulations live in `sear-labs/lithium-gametheory`. | `lithium-bilevel` (renamed) |
| `tools/credscan.py` | Credential scanner. Run before every commit. | `mineralnet-optsc` |

## Credentials

The Gurobi licence is read from environment variables (`GUROBI_WLSACCESSID`,
`GUROBI_WLSSECRET`, `GUROBI_LICENSEID`), never from a literal in a notebook. The archived
notebooks were scrubbed of their original literals when migrated here. Those literals remain in
the git history of the archived repos, so they MUST be rotated at the Gurobi portal (not yet confirmed).

## Status

Exploratory. Each model is a notebook plus its data. Nothing is reproducible from a clean clone yet.

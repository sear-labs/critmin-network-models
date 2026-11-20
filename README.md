# critmin-network-models — critical-mineral network models and the RFF trade-exposure analysis

All network-optimization models for battery-mineral and lithium supply chains, plus the RFF
(Critical Mineral Lab) trade-exposure analysis. Replaces the earlier repos `mineralnet-optsc`,
`lithiumsc-experiments` and `critmin-tradeexposure`, whose files now live here.

**The lab's network model is [`models/critmin-net/`](models/critmin-net/).** It is the one
maintained version; any network model elsewhere in the lab should derive from it (its README says
how). The other folders are kept as they came.

## Layout

| Folder | What it is | Source |
|---|---|---|
| `models/critmin-net/` | **The lab model.** Alavi's six-stage network as a tested Python package, with scenario hooks and a published-source calibration on LLNL's four regions. Reproduces her notebook to 1e-6. | `critmin-energy-surrogatecoupling` @ `5c3616a` |
| `models/six-stage-mineralnet/` | Alavi's six-stage (mine → recycling) multi-region model as of 2026-10-06, exploratory: the original the lab model derives from. Her live repo is `mineralnet-optsc`. | `mineralnet-optsc` (main branch) |
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

`models/critmin-net/` runs and tests from a clean clone (Gurobi licence needed to solve). The rest
is exploratory: each is a notebook plus its data, not yet reproducible from a clean clone.

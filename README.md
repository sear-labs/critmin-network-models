# critmin-network-models — critical-mineral network models and the RFF trade-exposure analysis

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24540500.svg)](https://doi.org/10.5281/zenodo.24540500)

All network-optimization models for battery-mineral and lithium supply chains, plus the RFF
(Critical Mineral Lab) trade-exposure analysis. Replaces the earlier repos `mineralnet-optsc`,
`lithiumsc-experiments` and `critmin-tradeexposure`, whose files now live here.

**The lab's network model is [`models/critmin-net/`](models/critmin-net/).** It is the one
maintained version; any network model elsewhere in the lab should derive from it (its README says
how). The other folders are kept as they came, as the record of how it got here.

## How to cite

Archived on Zenodo. Cite the release you used: every GitHub release has its own DOI, and
[10.5281/zenodo.24540500](https://doi.org/10.5281/zenodo.24540500) stands for all versions (it resolves to the latest; 0.16.1 is
[10.5281/zenodo.24540501](https://doi.org/10.5281/zenodo.24540501)). `CITATION.cff` and GitHub's "Cite this repository" give the formats:

```bibtex
@software{jones_critmin_network_models,
  author  = {Jones, Erick C., Jr.},
  title   = {critmin-network-models: the SEAR Lab's critical-mineral network models (critmin-net)},
  version = {0.16.1},
  year    = {2026},
  doi     = {10.5281/zenodo.24540501},
  url     = {https://github.com/sear-labs/critmin-network-models}
}
```

## Licence

Code: MIT (`LICENSE`). Data (each model's `data/` folder): CC BY 4.0. Every number in critmin-net's data names
its source (`models/critmin-net/src/critmin_net/data/SOURCES.md`).

## Layout

| Folder | What it is | Source |
|---|---|---|
| `models/critmin-net/` | **The lab model.** One engine for supply-chain networks passed as data (it began as a port of Alavi's six-stage lithium network, retired in 0.16.0), and a multi-mineral lithium-ion battery network projected to 2040 on supply, demand and cost curves, with recycling, mine expansions and royalties, US tariffs, 45X and China's export controls ([docs/battery-horizon.md](models/critmin-net/docs/battery-horizon.md)). | `critmin-energy-surrogatecoupling` @ `5c3616a`, then developed here |
| `models/six-stage-mineralnet/` | Alavi's six-stage (mine → recycling) multi-region model as of 2026-10-06, exploratory: the original the lab model derives from. Her live repo is `mineralnet-optsc`. | `mineralnet-optsc` (main branch) |
| `rff-trade-exposure/` | RFF Critical Mineral Lab: import exposure, FEOC, friendshoring | `critmin-tradeexposure` |
| `archive/lithiumsc-experiments/` | Archived lithium formulation lineage (12 notebooks, 3 papers, data). Kept for reference, not maintained. | `lithiumsc-experiments` (archived) |
| `game-theory/` | Not here. Bilevel and Benders formulations live in `sear-labs/lithium-gametheory`. | `lithium-bilevel` (renamed) |
| `tools/credscan.py` | Credential scanner. Run before every commit. | `mineralnet-optsc` |

## Gurobi

Solving needs a Gurobi licence. `models/critmin-net/` uses whatever licence gurobipy finds (a licence file); the
exploratory notebooks read one from environment variables (`GUROBI_WLSACCESSID`, `GUROBI_WLSSECRET`,
`GUROBI_LICENSEID`). No credential is in this repository (`tools/credscan.py` checks every commit).

## Status

`models/critmin-net/` runs and tests from a clean clone (a full Gurobi licence is needed to solve; version and
changes in its `CHANGELOG.md`). The rest
is exploratory: each is a notebook plus its data, not yet reproducible from a clean clone.

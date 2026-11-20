# critmin-net: the lab's critical-minerals network model

**This is the SEAR lab's one maintained network model.** Any network model elsewhere in the lab (a
student's repo, a paper's working repo, a course) should derive from this one: start from a release
here, and keep a test that checks your version against it. If your version needs something this model
lacks, propose it here by pull request, so the lab keeps one model rather than several drifting copies.

## What it is

A six-stage battery-mineral supply-chain network (mine, refining, cathode, cell, pack, recycling)
solved as a mixed-integer program in gurobipy: regions, trade arcs, integer capacity builds, yields,
and policy and shock scenarios. One module: [`src/critmin_net/network.py`](src/critmin_net/network.py).

- **The formulation is Alavi's** (sear-labs/mineralnet-optsc, `notebooks/full6stage-network.ipynb`),
  ported to a module and checked against her notebook to 1e-6 (`check_agreement()`).
- **Added since:** the scenario hooks (storage demand bought by an energy model, tariffs, quotas,
  embargoes, friendshoring, yields, output limits, a stylised cobalt add-on), and `calibrated()`, a
  calibration on LLNL's four regions (US, US allies, China, rest of world) from published sources.
- **The regional map is our calibration, not Alavi's or LLNL's.** LLNL's report supplies only the
  region taxonomy (LLNL-TR-859392). The shares, costs and tariffs come from USGS, IEA, Stanford GSB's
  cost model and the US Section 301 fact sheet (`src/critmin_net/data/calibration/`, one row per number with its
  source); three assumptions (rest of world's costs, trade cost as a share of value, the price of unmet
  demand) are ours. Say so wherever the map appears.
- **Preliminary.** Results from it are labelled so until the full models replace the testbed.

Every hook is off by default. With none on and her notebook's parameters, it is her model.

## Where it came from

Moved here in 0.1.0 from `critmin-energy-surrogatecoupling` (`src/surrogatecoupling/sara_net.py` at
`5c3616a`, branch `paper2-testbed`), where it was built as the mineral half of the energy coupling.
The move changed nothing: `tests/test_solver.py` gets that repo's numbers back exactly
(`tests/baseline/working_repo_5c3616a.json`). Alavi's original is beside this folder as
[`../six-stage-mineralnet/`](../six-stage-mineralnet/) (copied 2026-10-06); her live repo is
sear-labs/mineralnet-optsc.

## Running it

    cd models/critmin-net
    pip install -e ".[dev]"            # or PYTHONPATH=src with numpy, pandas and gurobipy installed
    python -m critmin_net.network      # agreement with her notebook, then her published multipliers

    from critmin_net import network as N
    r = N.solve(N.calibrated())                      # the calibrated model, alone
    price, base = N.us_cell_price(params=N.calibrated(), extra_cell_demand={...})

Gurobi is required: the pip wheel's size-limited licence imports the module but cannot solve the model.

## Tests

    pytest -q                  # everything; the solver checks skip without a full licence
    pytest -q -m solver        # only the checks that solve (under a minute)

- `test_raw_frozen.py`: every input matches `src/critmin_net/data/MANIFEST.sha256`.
- `test_smoke.py`: imports, and the inputs load and are sane. No solver.
- `test_solver.py`: her notebook to 1e-6, and the baseline numbers to 1e-9.

## Data

The inputs ship inside the package, in `src/critmin_net/data/`, so `pip install` brings them and a
project using the model needs no copy of its own. They are frozen; [`SOURCES.md`](src/critmin_net/data/SOURCES.md)
says where each file came from. To run on other inputs (a student's variant, a refresh being tested), set
`CRITMIN_NET_DATA` to a folder laid out the same way, with its own `MANIFEST.sha256`; the model then
reads that folder or refuses to start, never the shipped copy in its place.

Alavi's inputs are unpublished lab data, so this repository stays private. The calibration is from
public sources.

**Using it from another project** (pin a commit; the repository is private, so the machine or CI job
needs read access to it):

    pip install "critmin-net @ git+https://github.com/sear-labs/critmin-network-models.git@<commit>#subdirectory=models/critmin-net"

## Planned

- A stockpile: stock carried between years at each stage and region, with a holding cost, built up
  and drawn down as the model chooses. Off by default, with the results unchanged while off.
- Minerals beyond lithium's battery chain, rare earths first: mineral as a dimension of the network,
  as LLNL's taxonomy covers many minerals.

## Credit

Alavi built the network (formulation and data). Cite LLNL-TR-859392 for the regions, and the sources
in `src/critmin_net/data/calibration/` for the calibration.

# Changelog

Versions follow SemVer. A change that moves `tests/baseline/` numbers on purpose is at least a minor
version and says why here.

## 0.4.0 (2026-11-21)

- The network is described as sets: `MINERALS` (lithium only for now), `GOODS` (with `MINERAL_OF`),
  `PROCESSES` and `RECIPE` (inputs per process, output per unit input), and `build()` makes every balance,
  trade arc and input variable from them. A process may now take several inputs. `IN_T` and `OUT_T` move to
  module level; the input variables are keyed (node, input good, year).
- `build(..., net=...)`: the network is an argument, its sets and optionally its own years, costs and demand
  (`network.LITHIUM`, the default, documents the format; `check_net()` checks a network's sets). Embedded
  values follow the recipes; levers, the stockpile and results read the network's stages and goods.
- `critmin_net.battery`: a multi-mineral test network (Li, Ni, Co, Mn, graphite; mining, refining, pCAM,
  anode, cathode, cells; LLNL's regions plus Special) for 2023-2024 on sourced quantities
  (`data/battery_2023_2024/`, new frozen inputs) and placeholder costs. Both years are supplied with nothing
  unmet and each mineral is taken in exactly demand x intensity. A test of the mechanism, PRELIMINARY.
- `build(..., losses=...)`: a loss per stage, process or node, optionally by year (output = (1 - loss) x
  recipe x input), over a network's own defaults (`net["losses"]`); `check_losses()` validates them. Off for
  lithium. The battery network's defaults, `battery.LOSSES`, are chosen from `data/battery_2023_2024/stage_losses.csv`
  (new frozen input: published losses by stage with sources); with them both years are still supplied. The
  synthetic graphite placeholder cost rises from 3.0 to 4.0 so natural flake, after its spheronisation loss,
  is still used first.
- The battery network's LFP cathode takes battery-grade iron phosphate, a pCAM good with capacity and cost and no
  mined input.
- No change to the lithium model: across Alavi's parameters, the calibration and every hook (12 cases), `build()`
  makes the same Gurobi model as 0.3.0 (same fingerprint, variables, constraints and nonzeros). The baseline
  numbers are unchanged.

## 0.3.0 (2026-11-21)

- The stockpile hook (`build(stockpile=...)`, options and defaults in `STOCKPILE`): stock carried between
  years by stage, good and region, at a holding cost, with no drawdown in the last year and an end at least
  at the start. Off by default, and off it adds no variables or constraints: the baseline numbers are
  unchanged. The holding cost (10% of value a year) is a placeholder with no source yet.
- Results gain `stock` and `hold_cost`. The pack balance's local `sp` is renamed `spk`; no behaviour change.

## 0.2.0 (2026-11-20)

- The frozen inputs move from `data/raw/` into the package (`src/critmin_net/data/`), so `pip install
  git+...` ships them; a project using the model no longer keeps a copy. Byte-identical; same checksums.
- `network.data_dir()`: `$CRITMIN_NET_DATA` names another inputs folder (used or refused, never replaced
  by the shipped copy); otherwise the shipped copy. The baseline numbers are unchanged.

## 0.1.0 (2026-11-20)

- Moved here from critmin-energy-surrogatecoupling (`src/surrogatecoupling/sara_net.py` at `5c3616a`)
  as the lab's network model. Only the module's opening lines and its data path changed; the
  calibrated model's objective and US cell prices are identical to that repo's.
- Inputs frozen from there: Alavi's network data (mineralnet-optsc @ `18e67de`), her notebook's
  reference solution, and the published-source calibration.

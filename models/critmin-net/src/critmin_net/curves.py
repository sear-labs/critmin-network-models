"""Stepped price-quantity curves for the network: supply (cost) curves and demand curves, as the lab's Texas
energy-system model builds every market (texas-energy-system-model, markets.ladder(): "every market a calibrated
curve, never a fixed flow or a flat price", Jones, 2026-11-17 to 19).

A curve is anchored at an observed or projected point (Q0, P): Q(p) = Q0 * (p / P) ** e, cut into blocks at the price
ratios RATIOS. Supply: blocks offered at ascending ratios, so output beyond Q0 costs more and output short of it
less (e > 0). Demand: blocks taken at descending ratios, so a lower price is met with more demand (e < 0). The
blocks go to build() as cost_curve (an adder per unit on top of the nodes' own costs) and demand_curve (a value per
unit). Rising supply blocks and falling demand blocks keep the model a linear program.

Knobs a scenario turns (horizon.KNOBS): the elasticity e, the anchor quantity Q0 (and how it grows), and the price
P (a multiplier on it, and its path over time).
"""
import numpy as np

# price ratios to the anchor price, as the Texas model's markets.RATIOS (1% steps near the anchor so a small shift
# moves a little, not all or nothing)
RATIOS = np.array([4, 3, 2, 1.6, 1.4, 1.25, 1.15, 1.1, 1.08, 1.06, 1.04, 1.03, 1.02, 1.01, 1.0, 0.99, 0.98, 0.97,
                   0.96, 0.94, 0.92, 0.9, 0.85, 0.75, 0.67, 0.5, 0.33, 0.25])
TOP = 4.0                    # the open last supply block's ratio: output past the curve's end, at four times P
# supply curves step finer near the anchor (0.2%), so a calibrated region lands within a fraction of a percent of its
# observed output; HALF_STEP is the shift that puts the anchor between two of those blocks
SUPPLY_RATIOS = np.array(sorted(set(np.round(np.r_[RATIOS, np.arange(0.98, 1.0201, 0.002)], 6)), reverse=True))
HALF_STEP = 0.001


def ladder(Q0, e, side):
    """Block sizes and price ratios of the stepped curve Q0 * r ** e. side "supply": ascending ratios (cumulative
    Q0 * r ** e, so the block ending at r = 1 ends at Q0); "demand": descending ratios."""
    if side not in ("supply", "demand"):
        raise ValueError(f"side: 'supply' or 'demand', got {side!r}")
    if (side == "supply" and e <= 0) or (side == "demand" and e >= 0):
        raise ValueError(f"a {side} curve needs elasticity {'> 0' if side == 'supply' else '< 0'}, got {e!r}")
    r = SUPPLY_RATIOS[::-1] if side == "supply" else RATIOS
    size = np.diff(np.r_[0.0, Q0 * r ** float(e)])
    return size, r.astype(float)


def supply_blocks(Q0, P, e, offset=0.0, steps=None, steps_total=None, growth_cost=None):
    """[(size, adder)] for build()'s cost_curve: the nodes' output in blocks, each costing `adder` on top of the nodes'
    own unit cost P: offset + (r - 1) * P, so the block ending at Q0 costs offset more than P, and an open last block
    at TOP.

    steps: [(size, cost)] of known operations. Observed years (steps_total None): the operations, scaled to Q0, fill
    the curve below Q0, each at offset + (cost - P), and the blocks above Q0 rise from the dearest operation's cost,
    so the anchor sits at a block boundary (calibrate() needs that). Later years (steps_total, the operations' own
    size, retiring): a merit order of every tranche sorted by cost: the operations at their own costs and size, the
    room up to Q0 at P (new capacity at the region's sourced cost; growth_cost, a greenfield cost, where given), and
    the curve's blocks above Q0 at that cost x r."""
    if steps and steps_total is not None:          # a later year: merit order
        tot = sum(s for s, _ in steps)
        size_to = min(steps_total, Q0) if Q0 > 0 else 0.0
        tr = [(s * size_to / tot if tot else 0.0, c) for s, c in steps]
        gc = P if growth_cost is None else growth_cost
        if Q0 > size_to:
            tr.append((Q0 - size_to, gc))
        if Q0 > 0:
            size, r = ladder(Q0, e, "supply")
            tr += [(float(sz), rr * gc) for sz, rr in zip(size, r) if rr > 1.0]
        tr.sort(key=lambda x: x[1])
        out = [(sz, offset + (c - P)) for sz, c in tr]
        top = max(TOP * gc, max(c for _, c in tr) if tr else 0.0)
        out.append((None, offset + (top - P)))
        return out
    out = []
    base, lift = P, 0.0                            # the curve above Q0: ratios of `base`, from `lift` over P
    if steps:
        tot = sum(s for s, _ in steps)
        for s, c in sorted(steps, key=lambda x: x[1]):
            out.append((s * Q0 / tot if tot else 0.0, offset + (c - P)))
        base = max(c for _, c in steps)
        lift = base - P
    if Q0 > 0:
        size, r = ladder(Q0, e, "supply")
        for s, rr in zip(size, r):
            if steps and rr <= 1.0:
                continue
            out.append((float(s), offset + lift + (rr - 1.0) * base))
    out.append((None, offset + lift + (TOP - 1.0) * base))
    for (_, a), (_, b) in zip(out, out[1:]):
        if b < a - 1e-9:
            raise ValueError("supply_blocks: adders must not fall block by block (a convex curve)")
    return out


def demand_blocks(Q0, V, e):
    """[(size, value)] for build()'s demand_curve: Q0 * r ** e in blocks worth V * r each (r descending), so at the
    anchor value V the demand taken is Q0."""
    size, r = ladder(Q0, e, "demand")
    return [(float(s), float(V * rr)) for s, rr in zip(size, r)]

"""Per-bin amount distribution helpers for liquidity adds.

v0 simplification — see `2026-04-30-precision-curve-mechanics.md` and
`2026-05-01-autoresearch-design.md`. We approximate Meteora's distribution
shapes (Spot / Curve / BidAsk) with simple integer-weight distributions:

  spot:    uniform per bin on each side
  curve:   linear taper, peak at active bin, decreasing to edges
  bid_ask: inverse linear taper, trough at active, peaks at edges

The active bin (when in range) holds both X and Y at half-weight per side.
Bins above active hold only X; bins below hold only Y. Integer-division
residuals get swept into the outermost bin on each side so totals reconcile
exactly.

This is qualitatively shaped after HawkFi's open-source `(x0, y0, deltaX, deltaY)`
parameterization but does not reimplement its Q64.64 fixed-point math.
v1 calibration (Phase 4 follow-up) is to mirror the SDK math exactly if
empirical results call for it; deferred for v0 infrastructure validation.
"""

from __future__ import annotations

from typing import Literal

DistributionShape = Literal["spot", "curve", "bid_ask"]


def _spot_weights(
    lower_bin: int, upper_bin: int, active_bin: int
) -> tuple[dict[int, int], dict[int, int]]:
    """Uniform weights: every bin = 2 on its side, active bin = 1 on each side."""
    x_weights: dict[int, int] = {}
    y_weights: dict[int, int] = {}
    for b in range(lower_bin, upper_bin + 1):
        if b > active_bin:
            x_weights[b] = 2
        elif b < active_bin:
            y_weights[b] = 2
        else:  # active_bin in range
            x_weights[b] = 1
            y_weights[b] = 1
    return x_weights, y_weights


def _curve_weights(
    lower_bin: int, upper_bin: int, active_bin: int
) -> tuple[dict[int, int], dict[int, int]]:
    """Linear taper. Peak adjacent to active bin, decreasing toward edges."""
    x_weights: dict[int, int] = {}
    y_weights: dict[int, int] = {}
    range_above = max(0, upper_bin - active_bin)
    range_below = max(0, active_bin - lower_bin)
    for b in range(lower_bin, upper_bin + 1):
        if b > active_bin:
            # weight decreases as b approaches upper_bin
            x_weights[b] = (range_above - (b - active_bin) + 1) * 2
        elif b < active_bin:
            y_weights[b] = (range_below - (active_bin - b) + 1) * 2
        else:  # active_bin
            x_weights[b] = max(range_above, 1)
            y_weights[b] = max(range_below, 1)
    return x_weights, y_weights


def _bid_ask_weights(
    lower_bin: int, upper_bin: int, active_bin: int
) -> tuple[dict[int, int], dict[int, int]]:
    """Inverse linear taper. Minimum at active, peaks at edges."""
    x_weights: dict[int, int] = {}
    y_weights: dict[int, int] = {}
    for b in range(lower_bin, upper_bin + 1):
        if b > active_bin:
            x_weights[b] = (b - active_bin) * 2
        elif b < active_bin:
            y_weights[b] = (active_bin - b) * 2
        else:  # active_bin
            x_weights[b] = 1
            y_weights[b] = 1
    return x_weights, y_weights


def distribute(
    *,
    amount_x: int,
    amount_y: int,
    lower_bin: int,
    upper_bin: int,
    active_bin: int,
    distribution: DistributionShape,
) -> dict[int, tuple[int, int]]:
    """Distribute (amount_x, amount_y) across [lower_bin, upper_bin] per shape.

    Returns dict[bin_id -> (x_amount, y_amount)] containing only bins with
    nonzero allocation. Sweeps integer-division residuals into the outermost
    bin on each side so sum(x) == amount_x exactly (same for y).
    """
    if lower_bin > upper_bin:
        raise ValueError(f"invalid range [{lower_bin}, {upper_bin}]")

    if distribution == "spot":
        x_weights, y_weights = _spot_weights(lower_bin, upper_bin, active_bin)
    elif distribution == "curve":
        x_weights, y_weights = _curve_weights(lower_bin, upper_bin, active_bin)
    elif distribution == "bid_ask":
        x_weights, y_weights = _bid_ask_weights(lower_bin, upper_bin, active_bin)
    else:  # pragma: no cover — guarded at the type level
        raise ValueError(f"unknown distribution {distribution!r}")

    total_x_w = sum(x_weights.values())
    total_y_w = sum(y_weights.values())

    per_bin: dict[int, list[int]] = {b: [0, 0] for b in range(lower_bin, upper_bin + 1)}
    for b, w in x_weights.items():
        per_bin[b][0] = (amount_x * w) // total_x_w if total_x_w > 0 else 0
    for b, w in y_weights.items():
        per_bin[b][1] = (amount_y * w) // total_y_w if total_y_w > 0 else 0

    # Sweep residuals — outermost bin on each side absorbs the integer remainder
    # so totals reconcile exactly. Mirrors HawkFi SDK's hybrid-distribution sweep.
    if amount_x > 0 and x_weights:
        sum_x = sum(p[0] for p in per_bin.values())
        residual_x = amount_x - sum_x
        if residual_x != 0:
            outer_x = max(x_weights.keys())  # furthest above active
            per_bin[outer_x][0] += residual_x
    if amount_y > 0 and y_weights:
        sum_y = sum(p[1] for p in per_bin.values())
        residual_y = amount_y - sum_y
        if residual_y != 0:
            outer_y = min(y_weights.keys())  # furthest below active
            per_bin[outer_y][1] += residual_y

    return {b: (x, y) for b, (x, y) in per_bin.items() if x > 0 or y > 0}

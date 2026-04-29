"""Weighted-composite metric over precomputed primitives.

Composites are pure functions over `BacktestResult.primitives` — they don't
re-derive anything from the trajectory. Unknown primitive names in `weights`
are silently ignored (forward-compat for primitives added in v1.5+ that v1
results don't have).
"""

from __future__ import annotations

from asteroid_belt.engine.result import BacktestResult


def composite(r: BacktestResult, *, weights: dict[str, float]) -> float:
    """Weighted sum of named primitives.

    Example:
        composite(r, weights={"net_pnl": 1.0, "rebalance_count": -0.1})
        -> r.primitives["net_pnl"] - 0.1 * r.primitives["rebalance_count"]
    """
    total = 0.0
    for name, weight in weights.items():
        if name in r.primitives:
            total += weight * r.primitives[name]
    return total

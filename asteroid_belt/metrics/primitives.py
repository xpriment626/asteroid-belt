"""Pure-function metrics over BacktestResult.

Every shipped primitive is computed on every result regardless of which one
the run config names as `selection_metric`. Adding a new primitive is
additive — it never invalidates old runs because re-evaluation is cheap.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import cast

import polars as pl

from asteroid_belt.engine.result import BacktestResult

_EPS = 1e-9

MetricFn = Callable[[BacktestResult], float]


def _scalar_float(value: object) -> float:
    """Cast a polars scalar (which mypy widens to a big union) to float."""
    if value is None:
        return 0.0
    return float(cast(float, value))


def net_pnl(r: BacktestResult) -> float:
    """Final position value - initial position value, in USD."""
    df = r.trajectory
    if df.is_empty():
        return 0.0
    first = float(df["position_value_usd"][0])
    last = float(df["position_value_usd"][-1])
    return last - first


def time_in_range_pct(r: BacktestResult) -> float:
    """Percentage of trajectory steps where the position was in range."""
    df = r.trajectory
    if df.is_empty():
        return 0.0
    in_range_count = int(df["in_range"].sum())
    return 100.0 * in_range_count / df.height


def _daily_pnl_series(r: BacktestResult) -> pl.Series:
    """Convert per-step position value into per-day deltas."""
    df = r.trajectory
    if df.is_empty():
        return pl.Series([], dtype=pl.Float64)
    day_ms = 24 * 60 * 60 * 1000
    daily = (
        df.with_columns(
            [
                (pl.col("ts") // day_ms).alias("day"),
            ]
        )
        .group_by("day", maintain_order=True)
        .agg(pl.col("position_value_usd").last().alias("eod_value"))
        .sort("day")
    )
    if daily.height < 2:
        return pl.Series([], dtype=pl.Float64)
    eod = daily["eod_value"].to_list()
    deltas = [eod[i] - eod[i - 1] for i in range(1, len(eod))]
    return pl.Series(deltas, dtype=pl.Float64)


def sharpe(r: BacktestResult) -> float:
    """Sharpe ratio computed on daily PnL. Returns 0.0 when undefined."""
    deltas = _daily_pnl_series(r)
    if deltas.is_empty():
        return 0.0
    mean = _scalar_float(deltas.mean())
    std = _scalar_float(deltas.std())
    if std < _EPS:
        return 0.0
    # Annualize from daily: sqrt(365). Reasonable for a 24/7 LP context.
    return mean / std * math.sqrt(365)


def sortino(r: BacktestResult) -> float:
    """Sortino ratio: like Sharpe but only penalizes downside variance."""
    deltas = _daily_pnl_series(r)
    if deltas.is_empty():
        return 0.0
    mean = _scalar_float(deltas.mean())
    downside = deltas.filter(deltas < 0)
    if downside.is_empty():
        # No downside days: ratio is unbounded; clamp to a large positive sentinel
        # so the metric is comparable across runs.
        return mean / _EPS if mean > 0 else 0.0
    downside_std = _scalar_float(downside.std())
    if downside_std < _EPS:
        return 0.0
    return mean / downside_std * math.sqrt(365)


def capital_efficiency(r: BacktestResult) -> float:
    """net_pnl / max(|cumulative IL|, eps). Higher = more PnL per unit of IL."""
    pnl = net_pnl(r)
    df = r.trajectory
    if df.is_empty():
        return 0.0
    # il_cumulative is Float64 by trajectory schema; .min() returns a numeric scalar.
    il_abs = abs(_scalar_float(df["il_cumulative"].cast(pl.Float64).min()))
    return pnl / max(il_abs, _EPS)


def rebalance_count(r: BacktestResult) -> float:
    """Number of rebalances during the run."""
    return float(len(r.rebalances))


# Registry of all shipped primitives, used at result-build time.
PRIMITIVE_REGISTRY: dict[str, MetricFn] = {
    "net_pnl": net_pnl,
    "sharpe": sharpe,
    "sortino": sortino,
    "capital_efficiency": capital_efficiency,
    "time_in_range_pct": time_in_range_pct,
    "rebalance_count": rebalance_count,
}

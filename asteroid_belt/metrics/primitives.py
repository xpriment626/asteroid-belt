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


def _run_duration_days(r: BacktestResult) -> float:
    df = r.trajectory
    if df.is_empty() or df.height < 2:
        return 0.0
    span_ms = float(df["ts"][-1]) - float(df["ts"][0])
    return span_ms / (24 * 60 * 60 * 1000)


def info_ratio_vs_hodl(r: BacktestResult) -> float:
    """Annualized information ratio of LP returns vs HODL benchmark.

    Tracks daily excess PnL = delta(position_value) - delta(hodl_value).
    Returns 0 when undefined (single-day run, zero variance).
    """
    df = r.trajectory
    if df.is_empty() or df.height < 2:
        return 0.0
    day_ms = 24 * 60 * 60 * 1000
    daily = (
        df.with_columns([(pl.col("ts") // day_ms).alias("day")])
        .group_by("day", maintain_order=True)
        .agg(
            [
                pl.col("position_value_usd").last().alias("eod_pos"),
                pl.col("hodl_value_usd").last().alias("eod_hodl"),
            ]
        )
        .sort("day")
    )
    if daily.height < 2:
        return 0.0
    pos = daily["eod_pos"].to_list()
    hodl = daily["eod_hodl"].to_list()
    excess = [(pos[i] - pos[i - 1]) - (hodl[i] - hodl[i - 1]) for i in range(1, len(pos))]
    s = pl.Series(excess, dtype=pl.Float64)
    mean = _scalar_float(s.mean())
    std = _scalar_float(s.std())
    if std < _EPS:
        return 0.0
    return mean / std * math.sqrt(365)


def net_fee_yield(r: BacktestResult) -> float:
    """Annualized fee yield = total fees collected / initial value.

    Uses fees_value_usd at end of run, divided by hodl_value at start (≈ initial
    capital), annualized to APR. Returns 0 when undefined.
    """
    df = r.trajectory
    if df.is_empty():
        return 0.0
    final_fees = float(df["fees_value_usd"][-1])
    initial_value = float(df["hodl_value_usd"][0])
    if initial_value < _EPS:
        return 0.0
    days = _run_duration_days(r)
    if days < _EPS:
        return 0.0
    return (final_fees / initial_value) * (365.0 / days)


def calmar(r: BacktestResult) -> float:
    """Annualized return divided by max drawdown.

    Total LP value = position_value + fees_value. Drawdown is computed over
    that combined series. Returns 0 when undefined (zero drawdown or
    single-day run).
    """
    df = r.trajectory
    if df.is_empty() or df.height < 2:
        return 0.0
    total = [float(v) for v in (df["position_value_usd"] + df["fees_value_usd"]).to_list()]
    initial = total[0]
    if initial < _EPS:
        return 0.0
    days = _run_duration_days(r)
    if days < _EPS:
        return 0.0
    annualized_return = (total[-1] / initial) ** (365.0 / days) - 1.0
    peak = total[0]
    max_dd = 0.0
    for v in total:
        if v > peak:
            peak = v
        if peak > _EPS:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    if max_dd < _EPS:
        return 0.0
    return float(annualized_return / max_dd)


def vol_capture(r: BacktestResult) -> float:
    """Fee yield per unit of realized price volatility.

    Captures how efficiently the LP turns realized vol into fees:
    (annualized_fee_yield) / (annualized_realized_vol_of_price).
    Higher = the strategy harvests more fees per unit of price churn.
    Returns 0 when realized vol is undefined.
    """
    df = r.trajectory
    if df.is_empty() or df.height < 2:
        return 0.0
    fee_yield = net_fee_yield(r)
    # Daily log returns of price.
    day_ms = 24 * 60 * 60 * 1000
    daily = (
        df.with_columns([(pl.col("ts") // day_ms).alias("day")])
        .group_by("day", maintain_order=True)
        .agg(pl.col("price").last().alias("eod_price"))
        .sort("day")
    )
    if daily.height < 2:
        return 0.0
    prices = daily["eod_price"].to_list()
    log_rets = [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, len(prices))
        if prices[i - 1] > _EPS and prices[i] > _EPS
    ]
    if len(log_rets) < 2:
        return 0.0
    s = pl.Series(log_rets, dtype=pl.Float64)
    daily_vol = _scalar_float(s.std())
    if daily_vol < _EPS:
        return 0.0
    annualized_vol = daily_vol * math.sqrt(365)
    return fee_yield / annualized_vol


# Default scalar objective for autoresearch / demo runs. The five "honest"
# LP-specific objectives (info_ratio_vs_hodl, net_fee_yield, sharpe, calmar,
# vol_capture) are all populated on every result; the agent climbs whichever
# one is named here. vol_capture is the demo default per checkpoint
# 2026-05-01 — most visually distinct on charts.
DEFAULT_SELECTION_METRIC = "vol_capture"


# Registry of all shipped primitives, used at result-build time.
PRIMITIVE_REGISTRY: dict[str, MetricFn] = {
    "net_pnl": net_pnl,
    "sharpe": sharpe,
    "sortino": sortino,
    "capital_efficiency": capital_efficiency,
    "time_in_range_pct": time_in_range_pct,
    "rebalance_count": rebalance_count,
    "info_ratio_vs_hodl": info_ratio_vs_hodl,
    "net_fee_yield": net_fee_yield,
    "calmar": calmar,
    "vol_capture": vol_capture,
}

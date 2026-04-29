import polars as pl

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord
from asteroid_belt.metrics.primitives import (
    capital_efficiency,
    net_pnl,
    rebalance_count,
    sharpe,
    sortino,
    time_in_range_pct,
)


def _make_result(
    *,
    position_values: list[float],
    hodl_values: list[float],
    in_range_flags: list[bool],
    rebalances: int = 0,
) -> BacktestResult:
    n = len(position_values)
    # One row per UTC day so sharpe/sortino's daily aggregation has multiple data points.
    day_ms = 24 * 60 * 60 * 1000
    df = pl.DataFrame(
        {
            "ts": [i * day_ms for i in range(n)],
            "price": [1.0] * n,
            "active_bin": [0] * n,
            "position_value_usd": position_values,
            "hodl_value_usd": hodl_values,
            "fees_x_cumulative": [0] * n,
            "fees_y_cumulative": [0] * n,
            "il_cumulative": [p - h for p, h in zip(position_values, hodl_values, strict=False)],
            "in_range": in_range_flags,
            "capital_idle_usd": [0.0] * n,
        }
    )
    return BacktestResult(
        run_id="t",
        config_hash="t",
        schema_version="1.0",
        started_at=0,
        ended_at=0,
        status="ok",
        trajectory=df,
        rebalances=[
            RebalanceRecord(
                ts=0,
                trigger="x",
                old_lower_bin=0,
                old_upper_bin=0,
                new_lower_bin=0,
                new_upper_bin=0,
                gas_lamports=0,
                composition_fee_x=0,
                composition_fee_y=0,
                fees_claimed_x=0,
                fees_claimed_y=0,
            )
        ]
        * rebalances,
        primitives={},
        score=0.0,
        score_metric="net_pnl",
    )


def test_net_pnl_zero_when_position_matches_hodl() -> None:
    r = _make_result(
        position_values=[100, 100, 100],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    assert net_pnl(r) == 0.0


def test_net_pnl_positive_when_outperforming() -> None:
    r = _make_result(
        position_values=[100, 105, 110],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    assert net_pnl(r) == 10.0


def test_time_in_range_basic() -> None:
    r = _make_result(
        position_values=[100, 100, 100, 100],
        hodl_values=[100, 100, 100, 100],
        in_range_flags=[True, True, False, True],
    )
    assert time_in_range_pct(r) == 75.0


def test_capital_efficiency_division_safety() -> None:
    # No IL -> epsilon prevents division-by-zero blowup.
    r = _make_result(
        position_values=[100, 100, 100],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    # net_pnl = 0, so capital_efficiency = 0 regardless
    assert capital_efficiency(r) == 0.0


def test_sharpe_zero_when_constant_pnl() -> None:
    # Constant PnL -> zero variance -> sharpe undefined; we return 0.0
    r = _make_result(
        position_values=[100, 100, 100],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    assert sharpe(r) == 0.0


def test_sharpe_positive_when_increasing() -> None:
    # Increments must vary or sharpe = mean/std = mean/0 → undefined → 0.
    r = _make_result(
        position_values=[100, 101, 103, 104, 107],
        hodl_values=[100, 100, 100, 100, 100],
        in_range_flags=[True] * 5,
    )
    assert sharpe(r) > 0


def test_sortino_only_penalizes_downside() -> None:
    # All-up PnL: sortino is high (only downside variance counts).
    # Uneven steps so daily deltas have non-zero variance.
    up = _make_result(
        position_values=[100, 101, 103, 104],
        hodl_values=[100, 100, 100, 100],
        in_range_flags=[True] * 4,
    )
    s_up = sortino(up)
    assert s_up > 0


def test_rebalance_count() -> None:
    r = _make_result(
        position_values=[100, 100],
        hodl_values=[100, 100],
        in_range_flags=[True, True],
        rebalances=5,
    )
    assert rebalance_count(r) == 5

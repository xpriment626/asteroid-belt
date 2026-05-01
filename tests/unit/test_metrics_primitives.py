import polars as pl

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord
from asteroid_belt.metrics.primitives import (
    calmar,
    capital_efficiency,
    info_ratio_vs_hodl,
    net_fee_yield,
    net_pnl,
    rebalance_count,
    sharpe,
    sortino,
    time_in_range_pct,
    vol_capture,
)


def _make_result(
    *,
    position_values: list[float],
    hodl_values: list[float],
    in_range_flags: list[bool],
    rebalances: int = 0,
    fees_values: list[float] | None = None,
    prices: list[float] | None = None,
) -> BacktestResult:
    n = len(position_values)
    # One row per UTC day so sharpe/sortino's daily aggregation has multiple data points.
    day_ms = 24 * 60 * 60 * 1000
    df = pl.DataFrame(
        {
            "ts": [i * day_ms for i in range(n)],
            "price": prices if prices is not None else [1.0] * n,
            "active_bin": [0] * n,
            "position_value_usd": position_values,
            "hodl_value_usd": hodl_values,
            "fees_x_cumulative": [0] * n,
            "fees_y_cumulative": [0] * n,
            "fees_value_usd": fees_values if fees_values is not None else [0.0] * n,
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


def test_info_ratio_vs_hodl_zero_when_position_tracks_hodl() -> None:
    r = _make_result(
        position_values=[100, 101, 102, 103],
        hodl_values=[100, 101, 102, 103],
        in_range_flags=[True] * 4,
    )
    assert info_ratio_vs_hodl(r) == 0.0


def test_info_ratio_vs_hodl_positive_when_outperforming() -> None:
    # Position consistently beats HODL day-over-day with non-zero variance.
    r = _make_result(
        position_values=[100, 102, 105, 109],
        hodl_values=[100, 100, 100, 100],
        in_range_flags=[True] * 4,
    )
    assert info_ratio_vs_hodl(r) > 0.0


def test_net_fee_yield_zero_with_no_fees() -> None:
    r = _make_result(
        position_values=[100, 100],
        hodl_values=[100, 100],
        in_range_flags=[True, True],
    )
    assert net_fee_yield(r) == 0.0


def test_net_fee_yield_annualized_apr() -> None:
    # 1.0 fee on 100 initial over 1 day -> 1% daily -> 365% APR.
    r = _make_result(
        position_values=[100, 100],
        hodl_values=[100, 100],
        in_range_flags=[True, True],
        fees_values=[0.0, 1.0],
    )
    assert abs(net_fee_yield(r) - 3.65) < 1e-6


def test_calmar_zero_when_flat() -> None:
    r = _make_result(
        position_values=[100, 100, 100],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    assert calmar(r) == 0.0


def test_calmar_positive_when_growth_with_drawdown() -> None:
    # Growth from 100 -> 110 with a dip to 95 -> finite calmar.
    r = _make_result(
        position_values=[100, 95, 105, 110],
        hodl_values=[100, 100, 100, 100],
        in_range_flags=[True] * 4,
    )
    assert calmar(r) > 0.0


def test_vol_capture_zero_with_constant_price() -> None:
    r = _make_result(
        position_values=[100, 100, 100, 100],
        hodl_values=[100, 100, 100, 100],
        in_range_flags=[True] * 4,
        fees_values=[0.0, 0.5, 1.0, 1.5],
    )
    # Constant price -> realized vol = 0 -> vol_capture = 0.
    assert vol_capture(r) == 0.0


def test_vol_capture_positive_when_fees_accrue_with_vol() -> None:
    r = _make_result(
        position_values=[100, 100, 100, 100],
        hodl_values=[100, 100, 100, 100],
        in_range_flags=[True] * 4,
        fees_values=[0.0, 0.5, 1.0, 1.5],
        prices=[1.0, 1.05, 0.98, 1.02],
    )
    assert vol_capture(r) > 0.0

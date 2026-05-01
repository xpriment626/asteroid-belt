"""Trajectory population tests — verify per-row real values, not stub zeros."""

from collections.abc import Iterator
from decimal import Decimal

from asteroid_belt.data.adapters.base import (
    PoolKey,
    SwapEvent,
    TimeWindow,
)
from asteroid_belt.engine.runner import RunConfigParams, run_backtest
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import (
    PoolState,
    StaticFeeParams,
    VolatilityState,
)
from asteroid_belt.strategies.base import (
    Action,
    Capital,
    NoOp,
    OpenPosition,
    Strategy,
)


class _SingleSwapAdapter:
    """One synthetic swap event so the trajectory loop runs at least once."""

    def __init__(self) -> None:
        self.pool = PoolKey(address="test_pool")

    def stream(self, window: TimeWindow) -> Iterator[SwapEvent]:
        del window
        yield SwapEvent(
            ts=500,
            signature="sig",
            event_index=0,
            swap_for_y=True,
            amount_in=1_000_000,
            amount_out=999_000,
            fee_amount=3_000,
            protocol_fee_amount=300,
            host_fee_amount=0,
            price_after=Decimal("1.01"),
            bin_id_after=1,
        )


class _BuyAndHoldStrategy(Strategy):
    def initialize(self, pool: PoolState, capital: Capital) -> Action:
        del pool, capital
        return OpenPosition(lower_bin=-30, upper_bin=30, distribution="curve")

    def on_swap(self, event: SwapEvent, pool: PoolState, position: PositionState) -> Action:
        del event, pool, position
        return NoOp()


def _initial_pool_state() -> PoolState:
    return PoolState(
        active_bin=0,
        bin_step=10,
        mid_price=Decimal("1"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={},
        last_swap_ts=0,
        reward_infos=[],
    )


def _config(selection_metric: str = "net_pnl") -> RunConfigParams:
    return RunConfigParams(
        run_id="t",
        config_hash="h",
        window=TimeWindow(start_ms=0, end_ms=1_000),
        tick_secs=10_000,  # > window so no time ticks fire
        initial_x=1_000_000_000,  # 1.0 SOL (decimals_x=9)
        initial_y=8_000_000_000,  # 8000 USDC (decimals_y=6)
        decimals_x=9,
        decimals_y=6,
        priority_fee_lamports=10_000,
        selection_metric=selection_metric,
    )


def test_trajectory_has_real_hodl_value() -> None:
    result = run_backtest(
        strategy=_BuyAndHoldStrategy(),
        adapter=_SingleSwapAdapter(),
        initial_pool_state=_initial_pool_state(),
        config=_config(),
    )
    assert result.trajectory.height == 1
    row = result.trajectory.row(0, named=True)
    # hodl = 1.0 SOL * 1.01 + 8000 USDC = 8001.01
    assert abs(row["hodl_value_usd"] - 8001.01) < 1e-6


def test_trajectory_has_real_position_value_after_open() -> None:
    result = run_backtest(
        strategy=_BuyAndHoldStrategy(),
        adapter=_SingleSwapAdapter(),
        initial_pool_state=_initial_pool_state(),
        config=_config(),
    )
    row = result.trajectory.row(0, named=True)
    # OpenPosition deposits all capital -> position_value_usd should be non-zero
    # and roughly within ~5% of hodl (curve distribution at active_bin=0 with
    # post-swap price=1.01 should be close to hodl).
    assert row["position_value_usd"] > 0.0
    assert row["position_value_usd"] > row["hodl_value_usd"] * 0.5


def test_trajectory_capital_idle_zero_after_full_deposit() -> None:
    result = run_backtest(
        strategy=_BuyAndHoldStrategy(),
        adapter=_SingleSwapAdapter(),
        initial_pool_state=_initial_pool_state(),
        config=_config(),
    )
    row = result.trajectory.row(0, named=True)
    # OpenPosition deposits everything; idle capital should be ~0 (small dust ok).
    assert row["capital_idle_usd"] < 1.0


def test_trajectory_in_range_true_when_active_within_range() -> None:
    result = run_backtest(
        strategy=_BuyAndHoldStrategy(),
        adapter=_SingleSwapAdapter(),
        initial_pool_state=_initial_pool_state(),
        config=_config(),
    )
    row = result.trajectory.row(0, named=True)
    # active_bin moves to 1 post-swap; range is [-30, 30].
    assert row["active_bin"] == 1
    assert row["in_range"] is True


def test_trajectory_il_is_finite() -> None:
    result = run_backtest(
        strategy=_BuyAndHoldStrategy(),
        adapter=_SingleSwapAdapter(),
        initial_pool_state=_initial_pool_state(),
        config=_config(),
    )
    row = result.trajectory.row(0, named=True)
    # IL = position - hodl. After single-bin drift, it's small but defined.
    il = row["il_cumulative"]
    assert isinstance(il, float)
    # Sanity: |IL| should be small relative to hodl on a tiny price move.
    assert abs(il) < row["hodl_value_usd"]

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


class _EmptyAdapter:
    """No events at all — verifies the loop terminates cleanly."""

    def __init__(self) -> None:
        self.pool = PoolKey(address="test_pool")

    def stream(self, window: TimeWindow) -> Iterator[SwapEvent]:
        del window
        return iter([])


class _BuyAndHoldStrategy(Strategy):
    """Opens a single position at start; never rebalances."""

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


def test_empty_backtest_terminates() -> None:
    cfg = RunConfigParams(
        run_id="test_run",
        config_hash="test_hash",
        window=TimeWindow(start_ms=0, end_ms=1_000),
        tick_secs=300,
        initial_x=1_000_000_000,
        initial_y=8_000_000_000,
        decimals_x=9,
        decimals_y=6,
        priority_fee_lamports=10_000,
        selection_metric="net_pnl",
    )
    result = run_backtest(
        strategy=_BuyAndHoldStrategy(),
        adapter=_EmptyAdapter(),
        initial_pool_state=_initial_pool_state(),
        config=cfg,
    )
    assert result.status == "ok"
    assert result.run_id == "test_run"

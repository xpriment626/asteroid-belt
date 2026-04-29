from decimal import Decimal

from asteroid_belt.engine.guards import MAX_BINS_PER_POSITION, validate_action
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import (
    PoolState,
    StaticFeeParams,
    VolatilityState,
)
from asteroid_belt.strategies.base import (
    BinRangeAdd,
    NoOp,
    OpenPosition,
    Rebalance,
)


def _pool() -> PoolState:
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


def _empty_position() -> PositionState | None:
    return None  # no position open yet


def test_valid_open_passes() -> None:
    a = OpenPosition(lower_bin=-30, upper_bin=30, distribution="curve")
    out, msg = validate_action(
        action=a,
        pool=_pool(),
        position=_empty_position(),
        capital_x=1_000_000_000,
        capital_y=8_000_000_000,
        priority_fee_lamports=10_000,
    )
    assert isinstance(out, OpenPosition)
    assert msg is None


def test_open_with_too_wide_range_becomes_noop() -> None:
    a = OpenPosition(lower_bin=-100, upper_bin=100, distribution="curve")
    out, msg = validate_action(
        action=a,
        pool=_pool(),
        position=_empty_position(),
        capital_x=1_000_000_000,
        capital_y=8_000_000_000,
        priority_fee_lamports=10_000,
    )
    assert isinstance(out, NoOp)
    assert msg is not None
    assert "MAX_BINS_PER_POSITION" in msg or str(MAX_BINS_PER_POSITION) in msg


def test_open_with_insufficient_capital_becomes_noop() -> None:
    a = OpenPosition(lower_bin=-30, upper_bin=30, distribution="curve")
    out, msg = validate_action(
        action=a,
        pool=_pool(),
        position=_empty_position(),
        capital_x=0,
        capital_y=0,
        priority_fee_lamports=10_000,
    )
    assert isinstance(out, NoOp)
    assert msg is not None


def test_rebalance_when_no_position_becomes_noop() -> None:
    a = Rebalance(
        removes=[],
        adds=[
            BinRangeAdd(
                lower_bin=-10,
                upper_bin=10,
                distribution="spot",
                amount_x=100,
                amount_y=100,
            )
        ],
    )
    out, msg = validate_action(
        action=a,
        pool=_pool(),
        position=_empty_position(),
        capital_x=1_000_000_000,
        capital_y=1_000_000_000,
        priority_fee_lamports=10_000,
    )
    assert isinstance(out, NoOp)
    assert msg is not None and "no position open" in msg

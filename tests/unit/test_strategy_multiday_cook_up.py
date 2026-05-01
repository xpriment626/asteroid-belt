"""MultidayCookUpStrategy — thin baseline behavior tests.

Strategy is intentionally thin (see strategy module docstring). Tests verify
the conceptual contract:
- open returns a spot range centered on active
- on_swap is NoOp when active is in range (regardless of drift)
- on_swap is NoOp when active drifts BELOW range (the "cook" — let dip recover)
- on_swap returns Rebalance when active drifts ABOVE range (up-only)
- rebalance shifts the range to recenter on the new active bin
"""

from __future__ import annotations

from decimal import Decimal

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import PoolState, StaticFeeParams, VolatilityState
from asteroid_belt.strategies.base import (
    BinRangeAdd,
    Capital,
    NoOp,
    OpenPosition,
    Rebalance,
)
from asteroid_belt.strategies.multiday_cook_up import MultidayCookUpStrategy


def _pool(active_bin: int) -> PoolState:
    return PoolState(
        active_bin=active_bin,
        bin_step=10,
        mid_price=Decimal("1"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(10_000, 30, 600, 5_000, 40_000, 500, 350_000),
        bin_liquidity={},
        last_swap_ts=0,
        reward_infos=[],
    )


def _position_with_composition(
    lower: int, upper: int, x_per_bin: int = 50, y_per_bin: int = 50
) -> PositionState:
    composition = {
        b: BinComposition(amount_x=x_per_bin, amount_y=y_per_bin, liquidity_share=1.0)
        for b in range(lower, upper + 1)
    }
    return PositionState(
        lower_bin=lower,
        upper_bin=upper,
        composition=composition,
        fee_pending_x=0,
        fee_pending_y=0,
        fee_pending_per_bin={},
        total_claimed_x=0,
        total_claimed_y=0,
        fee_owner=None,
    )


def _swap_event() -> SwapEvent:
    return SwapEvent(
        ts=0,
        signature="sig",
        event_index=0,
        swap_for_y=True,
        amount_in=0,
        amount_out=0,
        fee_amount=0,
        protocol_fee_amount=0,
        host_fee_amount=0,
        price_after=Decimal("1"),
        bin_id_after=0,
    )


def test_mcu_initialize_returns_spot_open_centered_on_active() -> None:
    strat = MultidayCookUpStrategy(bin_range_width=30)
    action = strat.initialize(_pool(active_bin=200), Capital(x=1_000, y=1_000))
    assert isinstance(action, OpenPosition)
    assert action.distribution == "spot"
    assert action.upper_bin - action.lower_bin + 1 == 30
    assert action.lower_bin <= 200 <= action.upper_bin


def test_mcu_on_swap_noop_when_active_within_range() -> None:
    strat = MultidayCookUpStrategy(bin_range_width=11)
    strat.initialize(_pool(active_bin=100), Capital(x=0, y=0))
    pos = _position_with_composition(95, 105)
    action = strat.on_swap(_swap_event(), _pool(active_bin=102), pos)
    assert isinstance(action, NoOp)


def test_mcu_on_swap_noop_when_active_drifts_below_range() -> None:
    """Cook the dip — when active drifts below range, do nothing."""
    strat = MultidayCookUpStrategy(bin_range_width=11)
    strat.initialize(_pool(active_bin=100), Capital(x=0, y=0))
    pos = _position_with_composition(95, 105)
    # active well below the range
    action = strat.on_swap(_swap_event(), _pool(active_bin=80), pos)
    assert isinstance(action, NoOp)


def test_mcu_on_swap_rebalances_when_active_drifts_above_range() -> None:
    strat = MultidayCookUpStrategy(bin_range_width=11)
    strat.initialize(_pool(active_bin=100), Capital(x=0, y=0))
    pos = _position_with_composition(95, 105)
    # active above the range
    action = strat.on_swap(_swap_event(), _pool(active_bin=120), pos)
    assert isinstance(action, Rebalance)


def test_mcu_rebalance_shifts_range_to_recenter_on_new_active() -> None:
    """The new range should be centered on the new active bin."""
    strat = MultidayCookUpStrategy(bin_range_width=11)
    strat.initialize(_pool(active_bin=100), Capital(x=0, y=0))
    pos = _position_with_composition(95, 105)
    action = strat.on_swap(_swap_event(), _pool(active_bin=120), pos)
    assert isinstance(action, Rebalance)
    add = action.adds[0]
    assert isinstance(add, BinRangeAdd)
    # New range is 11 bins wide and centered on the new active (120) → [115, 125]
    assert add.upper_bin - add.lower_bin + 1 == 11
    assert add.lower_bin <= 120 <= add.upper_bin


def test_mcu_subsequent_swap_below_new_range_does_nothing() -> None:
    """After shifting up, a drift below the *new* range still cooks (no rebalance down)."""
    strat = MultidayCookUpStrategy(bin_range_width=11)
    strat.initialize(_pool(active_bin=100), Capital(x=0, y=0))
    pos = _position_with_composition(95, 105)
    # First: rebalance up to ~120
    action_1 = strat.on_swap(_swap_event(), _pool(active_bin=120), pos)
    assert isinstance(action_1, Rebalance)
    # Now active drifts below the new range — should still NoOp
    action_2 = strat.on_swap(_swap_event(), _pool(active_bin=110), pos)
    assert isinstance(action_2, NoOp)


def test_mcu_rebalance_redeploys_full_composition() -> None:
    strat = MultidayCookUpStrategy(bin_range_width=5)
    strat.initialize(_pool(active_bin=10), Capital(x=0, y=0))
    pos = _position_with_composition(8, 12, x_per_bin=100, y_per_bin=200)
    # 5 bins * 100 X = 500, 5 bins * 200 Y = 1000
    action = strat.on_swap(_swap_event(), _pool(active_bin=20), pos)
    assert isinstance(action, Rebalance)
    add = action.adds[0]
    assert add.amount_x == 500
    assert add.amount_y == 1_000

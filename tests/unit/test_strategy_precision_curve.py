"""PrecisionCurveStrategy — thin baseline behavior tests.

Strategy is intentionally thin (see strategy module docstring). Tests verify
the conceptual contract:
- open returns a wide-range curve with the configured width
- on_swap returns NoOp when active-bin drift is below the trigger
- on_swap returns a swapless Rebalance when drift hits the trigger
- the rebalance preserves the original bin range (in-place reshape)
"""

from __future__ import annotations

from decimal import Decimal

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import PoolState, StaticFeeParams, VolatilityState
from asteroid_belt.strategies.base import (
    BinRangeAdd,
    BinRangeRemoval,
    Capital,
    NoOp,
    OpenPosition,
    Rebalance,
)
from asteroid_belt.strategies.precision_curve import PrecisionCurveStrategy


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
    lower: int, upper: int, x_per_bin: int, y_per_bin: int
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


def _swap_event(ts: int = 0) -> SwapEvent:
    return SwapEvent(
        ts=ts,
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


def test_pc_initialize_returns_open_with_curve_distribution() -> None:
    strat = PrecisionCurveStrategy(bin_range_width=69)
    action = strat.initialize(_pool(active_bin=100), Capital(x=1_000, y=1_000))
    assert isinstance(action, OpenPosition)
    assert action.distribution == "curve"
    # 69-bin range centered on active=100 → [66, 134]
    assert action.upper_bin - action.lower_bin + 1 == 69
    assert action.lower_bin <= 100 <= action.upper_bin


def test_pc_initialize_centers_on_active_bin() -> None:
    strat = PrecisionCurveStrategy(bin_range_width=11)  # ±5 bins
    action = strat.initialize(_pool(active_bin=50), Capital(x=0, y=0))
    assert isinstance(action, OpenPosition)
    assert action.lower_bin == 45
    assert action.upper_bin == 55


def test_pc_on_swap_noop_when_drift_below_trigger() -> None:
    strat = PrecisionCurveStrategy(bin_range_width=69, reshape_trigger_bins=5)
    strat.initialize(_pool(active_bin=100), Capital(x=1_000, y=1_000))
    # active drifted by 4 bins (< 5 trigger)
    pool = _pool(active_bin=104)
    pos = _position_with_composition(66, 134, x_per_bin=10, y_per_bin=10)
    action = strat.on_swap(_swap_event(), pool, pos)
    assert isinstance(action, NoOp)


def test_pc_on_swap_rebalances_when_drift_meets_trigger() -> None:
    strat = PrecisionCurveStrategy(bin_range_width=69, reshape_trigger_bins=5)
    strat.initialize(_pool(active_bin=100), Capital(x=1_000, y=1_000))
    pool = _pool(active_bin=105)  # drift = 5, exactly at trigger
    pos = _position_with_composition(66, 134, x_per_bin=10, y_per_bin=10)
    action = strat.on_swap(_swap_event(), pool, pos)
    assert isinstance(action, Rebalance)


def test_pc_rebalance_preserves_original_range() -> None:
    """The whole point of Precision Curve: range stays fixed; only shape moves."""
    strat = PrecisionCurveStrategy(bin_range_width=11, reshape_trigger_bins=2)
    strat.initialize(_pool(active_bin=50), Capital(x=1_000, y=1_000))
    pool = _pool(active_bin=53)  # drift = 3 > 2
    pos = _position_with_composition(45, 55, x_per_bin=100, y_per_bin=100)
    action = strat.on_swap(_swap_event(), pool, pos)
    assert isinstance(action, Rebalance)
    # Single full remove over the original range
    assert action.removes == [BinRangeRemoval(lower_bin=45, upper_bin=55, bps=10_000)]
    # Single add over the SAME original range, curve-shaped
    assert len(action.adds) == 1
    add = action.adds[0]
    assert isinstance(add, BinRangeAdd)
    assert add.lower_bin == 45
    assert add.upper_bin == 55
    assert add.distribution == "curve"


def test_pc_rebalance_redeploys_full_composition() -> None:
    """Reshape: the rebalance redeploys exactly what's currently in composition.
    Swapless under our engine because totals match."""
    strat = PrecisionCurveStrategy(bin_range_width=5, reshape_trigger_bins=2)
    strat.initialize(_pool(active_bin=10), Capital(x=0, y=0))
    pool = _pool(active_bin=13)
    pos = _position_with_composition(8, 12, x_per_bin=200, y_per_bin=300)
    # 5 bins * 200 X = 1000; 5 bins * 300 Y = 1500
    action = strat.on_swap(_swap_event(), pool, pos)
    assert isinstance(action, Rebalance)
    add = action.adds[0]
    assert add.amount_x == 1_000
    assert add.amount_y == 1_500


def test_pc_drift_resets_after_rebalance() -> None:
    """After a rebalance, drift is measured from the new active bin, not the old one."""
    strat = PrecisionCurveStrategy(bin_range_width=11, reshape_trigger_bins=5)
    strat.initialize(_pool(active_bin=100), Capital(x=0, y=0))
    pos = _position_with_composition(95, 105, x_per_bin=10, y_per_bin=10)
    # First swap: drift 5 → rebalance fires, reshape center moves to 105
    action_1 = strat.on_swap(_swap_event(), _pool(active_bin=105), pos)
    assert isinstance(action_1, Rebalance)
    # Next swap at active=108: new drift = |108 - 105| = 3, below trigger
    action_2 = strat.on_swap(_swap_event(), _pool(active_bin=108), pos)
    assert isinstance(action_2, NoOp)

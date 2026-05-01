"""MultidayCookUpStrategy — thin reference baseline.

ILLUSTRATIVE, NOT FAITHFUL. See `docs/superpowers/research/2026-05-01-
autoresearch-design.md` for the autoresearch framing — the agent will
mutate this freely; this code is a worked example of one composition
pattern, not a calibrated HawkFi reimplementation.

Behavior (loosely inspired by HawkFi's "Multiday Cook Up" preset):
- Open a Spot-distribution position centered on the current active bin.
- "Up-only auto-rebalance": if active drifts ABOVE the position range,
  shift the range up to recenter. If active drifts BELOW the range, do
  nothing — let the dip "cook" with fee accrual until price comes back.
- The directional bias (up-only) is the differentiator vs Precision Curve.
  PC reshapes within a fixed range on any drift; MCU moves the range up
  but never down.
"""

from __future__ import annotations

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import PoolState
from asteroid_belt.strategies.base import (
    Action,
    BinRangeAdd,
    BinRangeRemoval,
    Capital,
    NoOp,
    OpenPosition,
    Rebalance,
    Strategy,
)


class MultidayCookUpStrategy(Strategy):
    """Spot LP with directional up-only auto-rebalance."""

    def __init__(self, bin_range_width: int = 30) -> None:
        if bin_range_width <= 0:
            raise ValueError(f"bin_range_width must be positive, got {bin_range_width}")
        self.bin_range_width = bin_range_width
        self._range_lower: int | None = None
        self._range_upper: int | None = None

    def initialize(self, pool: PoolState, capital: Capital) -> Action:
        del capital
        center = pool.active_bin
        half = self.bin_range_width // 2
        self._range_lower = center - half
        self._range_upper = center + (self.bin_range_width - half - 1)
        return OpenPosition(
            lower_bin=self._range_lower,
            upper_bin=self._range_upper,
            distribution="spot",
        )

    def on_swap(self, event: SwapEvent, pool: PoolState, position: PositionState) -> Action:
        del event
        if self._range_lower is None or self._range_upper is None:
            return NoOp()
        # Directional: only react when active is above current range.
        # Below-range drift is the "cook" — let dip recovery fees accrue.
        if pool.active_bin <= self._range_upper:
            return NoOp()
        # Shift range up to recenter on the new active bin.
        old_lower = self._range_lower
        old_upper = self._range_upper
        new_lower = pool.active_bin - self.bin_range_width // 2
        new_upper = pool.active_bin + (self.bin_range_width - self.bin_range_width // 2 - 1)
        amount_x = sum(c.amount_x for c in position.composition.values())
        amount_y = sum(c.amount_y for c in position.composition.values())
        self._range_lower = new_lower
        self._range_upper = new_upper
        return Rebalance(
            removes=[BinRangeRemoval(lower_bin=old_lower, upper_bin=old_upper, bps=10_000)],
            adds=[
                BinRangeAdd(
                    lower_bin=new_lower,
                    upper_bin=new_upper,
                    distribution="spot",
                    amount_x=amount_x,
                    amount_y=amount_y,
                )
            ],
        )

"""PrecisionCurveStrategy — thin reference baseline.

ILLUSTRATIVE, NOT FAITHFUL. See `docs/superpowers/research/2026-04-30-
precision-curve-mechanics.md` for the conceptual inspiration (HawkFi's
Precision Curve preset) and `docs/superpowers/research/2026-05-01-
autoresearch-design.md` for why this is intentionally not a precise
reimplementation. The autoresearch agent will mutate this strategy freely;
tightly fitting it to HawkFi's defaults would create a basin the agent
gets stuck in.

Behavior:
- Open a wide-range Curve-distribution position centered on the current
  active bin. All available capital is deposited at open.
- On every swap, check active-bin drift from the last reshape center.
  If drift >= reshape_trigger_bins, fire a swapless Rebalance: full remove
  + full re-add Curve-shaped around the new active. Range stays fixed.
- No claim mid-strategy; pending fees compound implicitly via Close at end.
- No TP / SL / AR — those are agent-mutated extensions.
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


class PrecisionCurveStrategy(Strategy):
    """Wide-range Curve LP with periodic in-place reshape on bin drift."""

    def __init__(
        self,
        bin_range_width: int = 69,
        reshape_trigger_bins: int = 5,
    ) -> None:
        if bin_range_width <= 0:
            raise ValueError(f"bin_range_width must be positive, got {bin_range_width}")
        if reshape_trigger_bins <= 0:
            raise ValueError(f"reshape_trigger_bins must be positive, got {reshape_trigger_bins}")
        self.bin_range_width = bin_range_width
        self.reshape_trigger_bins = reshape_trigger_bins
        self._range_lower: int | None = None
        self._range_upper: int | None = None
        self._last_reshape_active_bin: int | None = None

    def initialize(self, pool: PoolState, capital: Capital) -> Action:
        del capital  # OpenPosition deposits whatever is in capital_x / capital_y
        center = pool.active_bin
        half = self.bin_range_width // 2
        self._range_lower = center - half
        self._range_upper = center + (self.bin_range_width - half - 1)
        self._last_reshape_active_bin = center
        return OpenPosition(
            lower_bin=self._range_lower,
            upper_bin=self._range_upper,
            distribution="curve",
        )

    def on_swap(self, event: SwapEvent, pool: PoolState, position: PositionState) -> Action:
        del event
        if (
            self._range_lower is None
            or self._range_upper is None
            or self._last_reshape_active_bin is None
        ):
            return NoOp()
        drift = abs(pool.active_bin - self._last_reshape_active_bin)
        if drift < self.reshape_trigger_bins:
            return NoOp()
        # Swapless reshape: full remove, full re-add curve-shaped on new active.
        amount_x = sum(c.amount_x for c in position.composition.values())
        amount_y = sum(c.amount_y for c in position.composition.values())
        self._last_reshape_active_bin = pool.active_bin
        return Rebalance(
            removes=[
                BinRangeRemoval(
                    lower_bin=self._range_lower,
                    upper_bin=self._range_upper,
                    bps=10_000,
                )
            ],
            adds=[
                BinRangeAdd(
                    lower_bin=self._range_lower,
                    upper_bin=self._range_upper,
                    distribution="curve",
                    amount_x=amount_x,
                    amount_y=amount_y,
                )
            ],
        )

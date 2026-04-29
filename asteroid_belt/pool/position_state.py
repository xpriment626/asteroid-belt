"""PositionState and BinComposition.

Pending fees are accumulated outside position liquidity. Meteora doesn't
auto-compound; fees fold into capital only on explicit ClaimFees or
ClosePosition.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BinComposition:
    """Holdings in a single bin owned by our position."""

    amount_x: int
    amount_y: int
    liquidity_share: float  # our share of bin's total liquidity_supply, 0..1


@dataclass(frozen=True)
class PositionState:
    """Read-only snapshot of our position. `in_range` is computed, not stored."""

    lower_bin: int
    upper_bin: int
    composition: dict[int, BinComposition]
    fee_pending_x: int  # aggregated, raw token units
    fee_pending_y: int
    fee_pending_per_bin: dict[int, tuple[int, int]]  # bin_id -> (x, y)
    total_claimed_x: int  # lifetime claimed, raw token units
    total_claimed_y: int
    fee_owner: str | None = None  # public key as base58; None = position owner

    def in_range(self, active_bin: int) -> bool:
        return self.lower_bin <= active_bin <= self.upper_bin

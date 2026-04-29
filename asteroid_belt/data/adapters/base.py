"""Adapter event types and Protocol.

Events are the unified data primitive that flows from data adapters to the
backtest engine. Both the bar-synthesized adapter (v1) and the on-chain swap
adapter (v1.5+) emit SwapEvents. TimeTicks are interleaved by the engine at a
configurable cadence so time-based strategies have a hook.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class SwapEvent:
    """One bin-crossing of a swap. A user swap that crosses N bins emits N
    SwapEvents with the same `signature` but distinct `event_index` and
    `bin_id_after` values. The fee is denominated in the input token."""

    ts: int  # ms since epoch
    signature: str
    event_index: int
    swap_for_y: bool  # True = X -> Y (e.g. SOL -> USDC for SOL/USDC pool)
    amount_in: int  # raw token units (input side)
    amount_out: int  # raw token units (output side)
    fee_amount: int  # total fee in input-token raw units
    protocol_fee_amount: int  # carved out before LP share
    host_fee_amount: int  # smaller carve-out
    price_after: Decimal  # post-swap mid price
    bin_id_after: int  # bin this event landed in

    @property
    def lp_fee_amount(self) -> int:
        """LP-side fee after protocol and host carve-outs."""
        return self.fee_amount - self.protocol_fee_amount - self.host_fee_amount


@dataclass(frozen=True)
class TimeTick:
    """Synthetic time-based event interleaved by the engine at run-config
    cadence. Strategies can react via `on_tick`."""

    ts: int


Event = SwapEvent | TimeTick


@dataclass(frozen=True)
class PoolKey:
    """Identifies a Meteora DLMM pool."""

    address: str  # base58 mint of the LbPair account


@dataclass(frozen=True)
class TimeWindow:
    """Half-open time window [start_ms, end_ms). Adapter MUST NOT yield events
    at or after end_ms."""

    start_ms: int
    end_ms: int


class AdapterProtocol(Protocol):
    """The lookahead-bias seam. Adapters are constructed pointing at a single
    parquet path; engine never sees the path. Holdout data lives at a
    physically separate path that agent-run adapters cannot reach."""

    pool: PoolKey

    def stream(self, window: TimeWindow) -> Iterator[SwapEvent]:
        """Yield events in chronological order strictly within `window`.
        Implementation MUST NOT read past window.end_ms or expose state from
        outside the window."""
        ...

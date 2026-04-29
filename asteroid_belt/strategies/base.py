"""Strategy ABC and Action union types.

Strategies are the single mutable surface of the research env. They consume
events and return Actions; the engine validates and applies them. The Action
union is shaped after Meteora SDK primitives — Spot/Curve/BidAsk distributions
match the on-chain `StrategyType` enum (no scalar `skew` parameter; shapes are
baked into SDK helpers).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import PoolState

DistributionShape = Literal["spot", "curve", "bid_ask"]
_VALID_DISTRIBUTIONS: tuple[str, ...] = ("spot", "curve", "bid_ask")


@dataclass(frozen=True)
class BinRangeRemoval:
    """Per-bin partial remove during a rebalance."""

    lower_bin: int
    upper_bin: int
    bps: int  # 0..10000

    def __post_init__(self) -> None:
        if not 0 <= self.bps <= 10_000:
            raise ValueError(f"bps must be 0..10000, got {self.bps}")
        if self.lower_bin > self.upper_bin:
            raise ValueError(f"lower_bin ({self.lower_bin}) > upper_bin ({self.upper_bin})")


@dataclass(frozen=True)
class BinRangeAdd:
    """Per-bin add with shape and amount during a rebalance or top-up."""

    lower_bin: int
    upper_bin: int
    distribution: DistributionShape
    amount_x: int
    amount_y: int

    def __post_init__(self) -> None:
        if self.distribution not in _VALID_DISTRIBUTIONS:
            raise ValueError(f"distribution must be one of {_VALID_DISTRIBUTIONS}")
        if self.lower_bin > self.upper_bin:
            raise ValueError(f"lower_bin ({self.lower_bin}) > upper_bin ({self.upper_bin})")


@dataclass(frozen=True)
class OpenPosition:
    """Initial position open. capital_x_pct=None means SDK-balanced via autoFill."""

    lower_bin: int
    upper_bin: int
    distribution: DistributionShape
    capital_x_pct: float | None = None
    slippage_bps: int = 50

    def __post_init__(self) -> None:
        if self.distribution not in _VALID_DISTRIBUTIONS:
            raise ValueError(f"distribution must be one of {_VALID_DISTRIBUTIONS}")
        if self.lower_bin > self.upper_bin:
            raise ValueError(f"lower_bin ({self.lower_bin}) > upper_bin ({self.upper_bin})")
        if self.capital_x_pct is not None and not 0.0 <= self.capital_x_pct <= 1.0:
            raise ValueError(f"capital_x_pct must be 0.0..1.0, got {self.capital_x_pct}")


@dataclass(frozen=True)
class Rebalance:
    """In-place rebalance shaped after SDK rebalanceLiquidity. Swapless is
    emergent: if removes and adds sum to identical X/Y totals, no swap fires."""

    removes: list[BinRangeRemoval] = field(default_factory=list)
    adds: list[BinRangeAdd] = field(default_factory=list)
    max_active_bin_slippage: int = 0


@dataclass(frozen=True)
class AddLiquidity:
    """Top up an existing position range without rebalancing."""

    bin_range: tuple[int, int]
    distribution: DistributionShape
    amount_x: int
    amount_y: int

    def __post_init__(self) -> None:
        if self.distribution not in _VALID_DISTRIBUTIONS:
            raise ValueError(f"distribution must be one of {_VALID_DISTRIBUTIONS}")
        if self.bin_range[0] > self.bin_range[1]:
            raise ValueError(f"invalid bin_range {self.bin_range}")


@dataclass(frozen=True)
class RemoveLiquidity:
    """Partial remove from an existing range, in basis points."""

    bin_range: tuple[int, int]
    bps: int  # 0..10000

    def __post_init__(self) -> None:
        if not 0 <= self.bps <= 10_000:
            raise ValueError(f"bps must be 0..10000, got {self.bps}")
        if self.bin_range[0] > self.bin_range[1]:
            raise ValueError(f"invalid bin_range {self.bin_range}")


@dataclass(frozen=True)
class ClosePosition:
    """Close the position; implies fee claim and rent refund."""


@dataclass(frozen=True)
class ClaimFees:
    """Mid-position fee claim without closing."""


@dataclass(frozen=True)
class NoOp:
    """Do nothing this step."""


Action = (
    OpenPosition | Rebalance | AddLiquidity | RemoveLiquidity | ClosePosition | ClaimFees | NoOp
)


# --- Strategy ABC ---


@dataclass(frozen=True)
class Capital:
    """Capital available to the strategy at initialize time."""

    x: int  # raw token units
    y: int


class Strategy(ABC):
    """The single mutable surface of the research env.

    Strategies receive read-only snapshots and emit Actions. They have no path
    to: future events, the adapter, the cost model, the clock outside what's
    handed in, or the holdout data.
    """

    @abstractmethod
    def initialize(self, pool: PoolState, capital: Capital) -> Action:
        """Called once at backtest start. Returns OpenPosition or NoOp."""

    @abstractmethod
    def on_swap(self, event: SwapEvent, pool: PoolState, position: PositionState) -> Action:
        """Per-swap decision point. Most strategies return NoOp here."""

    def on_tick(self, ts: int, pool: PoolState, position: PositionState) -> Action:
        """Optional time-based hook. Default: NoOp."""
        del ts, pool, position
        return NoOp()

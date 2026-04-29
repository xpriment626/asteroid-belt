"""PoolState and its sub-types — the read-only view strategies receive."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class VolatilityState:
    """LbPair.v_parameters. Drives the variable fee at any tick."""

    volatility_accumulator: int
    volatility_reference: int
    index_reference: int
    last_update_timestamp: int


@dataclass(frozen=True)
class StaticFeeParams:
    """LbPair.s_parameters. Time-decay gates and fee constants."""

    base_factor: int
    filter_period: int  # seconds
    decay_period: int  # seconds
    reduction_factor: int  # bps; how much v_r reduces between filter and decay periods
    variable_fee_control: int
    protocol_share: int  # bps of total fee going to protocol
    max_volatility_accumulator: int


@dataclass(frozen=True)
class BinReserves:
    """Per-bin reserves at a moment in time."""

    amount_x: int
    amount_y: int
    liquidity_supply: int
    price: Decimal

    def __post_init__(self) -> None:
        if self.amount_x < 0 or self.amount_y < 0 or self.liquidity_supply < 0:
            raise ValueError("bin reserve amounts must be non-negative")


@dataclass(frozen=True)
class RewardInfo:
    """Reward emission info per LbPair. Empty for SOL/USDC 10bps."""

    mint: str
    reward_rate: int
    reward_duration_end: int
    last_update_time: int


@dataclass(frozen=True)
class PoolState:
    """Read-only snapshot of pool state at the moment of an event.

    bin_liquidity is materialized for [active_bin - N, active_bin + N], where
    N comes from the run config (default 100). Strategies that need depth
    information beyond this window are out of scope for v1.
    """

    active_bin: int
    bin_step: int  # bps
    mid_price: Decimal
    volatility: VolatilityState
    static_fee: StaticFeeParams
    bin_liquidity: dict[int, BinReserves]
    last_swap_ts: int
    reward_infos: list[RewardInfo] = field(default_factory=list)

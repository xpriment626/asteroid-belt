from decimal import Decimal

import pytest

from asteroid_belt.pool.state import (
    BinReserves,
    PoolState,
    RewardInfo,
    StaticFeeParams,
    VolatilityState,
)


def _vparams() -> VolatilityState:
    return VolatilityState(
        volatility_accumulator=0,
        volatility_reference=0,
        index_reference=0,
        last_update_timestamp=0,
    )


def _sparams() -> StaticFeeParams:
    return StaticFeeParams(
        base_factor=10000,
        filter_period=30,
        decay_period=600,
        reduction_factor=5000,
        variable_fee_control=40000,
        protocol_share=500,
        max_volatility_accumulator=350000,
    )


def test_pool_state_minimal() -> None:
    s = PoolState(
        active_bin=1234,
        bin_step=10,
        mid_price=Decimal("87.55"),
        volatility=_vparams(),
        static_fee=_sparams(),
        bin_liquidity={},
        last_swap_ts=1_700_000_000_000,
        reward_infos=[],
    )
    assert s.active_bin == 1234
    assert s.bin_step == 10


def test_bin_reserves_invariants() -> None:
    r = BinReserves(amount_x=100, amount_y=200, liquidity_supply=300, price=Decimal("2"))
    assert r.amount_x == 100
    with pytest.raises(ValueError):
        BinReserves(amount_x=-1, amount_y=0, liquidity_supply=0, price=Decimal("1"))


def test_reward_info_defaults() -> None:
    r = RewardInfo(
        mint="So11111111111111111111111111111111111111112",
        reward_rate=0,
        reward_duration_end=0,
        last_update_time=0,
    )
    assert r.reward_rate == 0

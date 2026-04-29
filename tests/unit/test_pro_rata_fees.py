from decimal import Decimal

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.engine.runner import credit_lp_fees_pro_rata
from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import (
    BinReserves,
    PoolState,
    StaticFeeParams,
    VolatilityState,
)


def _make_pool(bin_id: int, our_amount_x: int, others_amount_x: int) -> PoolState:
    return PoolState(
        active_bin=bin_id,
        bin_step=10,
        mid_price=Decimal("87.55"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={
            bin_id: BinReserves(
                amount_x=our_amount_x + others_amount_x,
                amount_y=0,
                liquidity_supply=our_amount_x + others_amount_x,
                price=Decimal("87.55"),
            ),
        },
        last_swap_ts=0,
        reward_infos=[],
    )


def _swap(bin_id: int, fee: int, protocol: int = 50, host: int = 0) -> SwapEvent:
    return SwapEvent(
        ts=1_000_000,
        signature="x",
        event_index=0,
        swap_for_y=False,
        amount_in=10_000_000,
        amount_out=11_000,
        fee_amount=fee,
        protocol_fee_amount=protocol,
        host_fee_amount=host,
        price_after=Decimal("87.55"),
        bin_id_after=bin_id,
    )


def _position(bin_id: int, our_share: float) -> PositionState:
    return PositionState(
        lower_bin=bin_id,
        upper_bin=bin_id,
        composition={
            bin_id: BinComposition(amount_x=10, amount_y=0, liquidity_share=our_share),
        },
        fee_pending_x=0,
        fee_pending_y=0,
        fee_pending_per_bin={},
        total_claimed_x=0,
        total_claimed_y=0,
        fee_owner=None,
    )


def test_no_credit_when_position_outside_swap_bin() -> None:
    pool = _make_pool(bin_id=100, our_amount_x=50, others_amount_x=50)
    pos = _position(bin_id=99, our_share=0.5)  # different bin
    event = _swap(bin_id=100, fee=1000)
    new_pos = credit_lp_fees_pro_rata(position=pos, pool=pool, event=event)
    assert new_pos.fee_pending_x == 0
    assert new_pos.fee_pending_y == 0


def test_credit_proportional_to_share() -> None:
    pool = _make_pool(bin_id=100, our_amount_x=50, others_amount_x=50)
    pos = _position(bin_id=100, our_share=0.5)
    # swap_for_y=False (Y->X) -> fee in Y; lp_fee = 1000 - 50 - 0 = 950; share 0.5 -> 475
    event = _swap(bin_id=100, fee=1000, protocol=50, host=0)
    new_pos = credit_lp_fees_pro_rata(position=pos, pool=pool, event=event)
    assert new_pos.fee_pending_y == 475
    assert new_pos.fee_pending_x == 0


def test_credit_x_when_swap_for_y() -> None:
    pool = _make_pool(bin_id=100, our_amount_x=50, others_amount_x=50)
    pos = _position(bin_id=100, our_share=0.4)
    # swap_for_y=True -> fee in X
    event = SwapEvent(
        ts=1_000_000,
        signature="x",
        event_index=0,
        swap_for_y=True,
        amount_in=10_000_000,
        amount_out=11_000,
        fee_amount=1000,
        protocol_fee_amount=50,
        host_fee_amount=0,
        price_after=Decimal("87.55"),
        bin_id_after=100,
    )
    new_pos = credit_lp_fees_pro_rata(position=pos, pool=pool, event=event)
    # lp_fee = 950; our share 0.4 -> 380
    assert new_pos.fee_pending_x == 380
    assert new_pos.fee_pending_y == 0


def test_jit_dilution_when_others_added_liquidity() -> None:
    # Our share is computed against the bin liquidity AT swap time, including
    # any JIT-bot adds that show up in the historical record.
    # If our_share is set to 0.1 (because a JIT bot 10x'd the bin liquidity),
    # we get 10% of fees, not 100%.
    pool = _make_pool(bin_id=100, our_amount_x=10, others_amount_x=90)
    pos = _position(bin_id=100, our_share=0.1)
    event = _swap(bin_id=100, fee=1000)
    new_pos = credit_lp_fees_pro_rata(position=pos, pool=pool, event=event)
    # lp_fee 950 * 0.1 = 95
    assert new_pos.fee_pending_y == 95

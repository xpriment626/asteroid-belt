import dataclasses
from decimal import Decimal

import pytest

from asteroid_belt.data.adapters.base import SwapEvent, TimeTick


def test_swap_event_is_frozen() -> None:
    e = SwapEvent(
        ts=1_700_000_000_000,
        signature="abc",
        event_index=0,
        swap_for_y=True,
        amount_in=1_000_000_000,
        amount_out=87_550_000,
        fee_amount=1_000_000,
        protocol_fee_amount=50_000,
        host_fee_amount=0,
        price_after=Decimal("87.55"),
        bin_id_after=1234,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.ts = 0  # type: ignore[misc]


def test_swap_event_lp_fee_helper() -> None:
    e = SwapEvent(
        ts=0,
        signature="x",
        event_index=0,
        swap_for_y=True,
        amount_in=100,
        amount_out=99,
        fee_amount=1000,
        protocol_fee_amount=50,
        host_fee_amount=10,
        price_after=Decimal("1"),
        bin_id_after=0,
    )
    # LP fee = total fee minus carve-outs
    assert e.lp_fee_amount == 940


def test_time_tick_basic() -> None:
    t = TimeTick(ts=1_700_000_000_000)
    assert t.ts == 1_700_000_000_000

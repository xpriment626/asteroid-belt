import dataclasses

import pytest

from asteroid_belt.pool.position_state import (
    BinComposition,
    PositionState,
)


def test_in_range_derived() -> None:
    p = PositionState(
        lower_bin=-10,
        upper_bin=10,
        composition={},
        fee_pending_x=0,
        fee_pending_y=0,
        fee_pending_per_bin={},
        total_claimed_x=0,
        total_claimed_y=0,
        fee_owner=None,
    )
    assert p.in_range(active_bin=0) is True
    assert p.in_range(active_bin=-10) is True  # boundaries inclusive
    assert p.in_range(active_bin=10) is True
    assert p.in_range(active_bin=11) is False
    assert p.in_range(active_bin=-11) is False


def test_position_state_immutable() -> None:
    p = PositionState(
        lower_bin=0,
        upper_bin=10,
        composition={},
        fee_pending_x=0,
        fee_pending_y=0,
        fee_pending_per_bin={},
        total_claimed_x=0,
        total_claimed_y=0,
        fee_owner=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.lower_bin = -1  # type: ignore[misc]


def test_bin_composition() -> None:
    c = BinComposition(amount_x=100, amount_y=200, liquidity_share=0.05)
    assert c.amount_x == 100
    assert c.liquidity_share == 0.05

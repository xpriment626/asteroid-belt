from decimal import Decimal

import pytest

from asteroid_belt.pool.bins import bin_id_to_price, price_to_bin_id, walk_bins_for_swap


def test_bin_zero_is_unit_price() -> None:
    assert bin_id_to_price(0, bin_step=10) == Decimal("1")


def test_bin_step_10_progression() -> None:
    # 10 bps = 0.1% per bin
    p1 = bin_id_to_price(1, bin_step=10)
    p0 = bin_id_to_price(0, bin_step=10)
    ratio = p1 / p0
    assert abs(ratio - Decimal("1.001")) < Decimal("1e-12")


def test_round_trip_positive_bins() -> None:
    for bin_id in [1, 100, 1000, 10000]:
        price = bin_id_to_price(bin_id, bin_step=10)
        recovered = price_to_bin_id(price, bin_step=10)
        assert recovered == bin_id, f"failed at {bin_id}: got {recovered}"


def test_round_trip_negative_bins() -> None:
    for bin_id in [-1, -100, -1000, -10000]:
        price = bin_id_to_price(bin_id, bin_step=10)
        recovered = price_to_bin_id(price, bin_step=10)
        assert recovered == bin_id, f"failed at {bin_id}: got {recovered}"


def test_invalid_bin_step() -> None:
    with pytest.raises(ValueError):
        bin_id_to_price(0, bin_step=0)
    with pytest.raises(ValueError):
        bin_id_to_price(0, bin_step=-1)


def test_walk_bins_no_movement() -> None:
    # If end_bin == start_bin, walk yields just the active bin.
    path = list(walk_bins_for_swap(start_bin=100, end_bin=100, swap_for_y=True))
    assert path == [100]


def test_walk_bins_swap_for_y_descends() -> None:
    # swap_for_y=True (X->Y): price drops, active_bin decreases.
    path = list(walk_bins_for_swap(start_bin=10, end_bin=7, swap_for_y=True))
    assert path == [10, 9, 8, 7]


def test_walk_bins_swap_for_x_ascends() -> None:
    # swap_for_y=False (Y->X): price rises, active_bin increases.
    path = list(walk_bins_for_swap(start_bin=7, end_bin=10, swap_for_y=False))
    assert path == [7, 8, 9, 10]

from asteroid_belt.engine.cost import (
    BIN_ARRAY_RENT_LAMPORTS,
    COST_MODEL_VERSION,
    POSITION_RENT_LAMPORTS,
    composition_fee,
    open_position_lamports,
    rebalance_lamports,
)


def test_cost_model_version_present() -> None:
    assert COST_MODEL_VERSION  # non-empty string


def test_open_position_with_one_bin_array() -> None:
    cost = open_position_lamports(num_new_bin_arrays=1, priority_fee_lamports=10_000)
    expected = POSITION_RENT_LAMPORTS + 1 * BIN_ARRAY_RENT_LAMPORTS + 10_000
    assert cost == expected


def test_open_position_with_no_new_bin_arrays() -> None:
    cost = open_position_lamports(num_new_bin_arrays=0, priority_fee_lamports=10_000)
    expected = POSITION_RENT_LAMPORTS + 10_000
    assert cost == expected


def test_rebalance_no_new_bin_arrays() -> None:
    cost = rebalance_lamports(num_new_bin_arrays=0, priority_fee_lamports=20_000)
    assert cost == 20_000


def test_rebalance_with_one_new_bin_array() -> None:
    cost = rebalance_lamports(num_new_bin_arrays=1, priority_fee_lamports=20_000)
    assert cost == BIN_ARRAY_RENT_LAMPORTS + 20_000


def test_composition_fee_zero_when_balanced() -> None:
    # If x and y added match the bin's existing X/Y ratio, no composition fee.
    fee_x, fee_y = composition_fee(
        added_x=100,
        added_y=100,
        bin_total_x=1000,
        bin_total_y=1000,
        base_fee_rate_bps=100,
    )
    assert fee_x == 0
    assert fee_y == 0


def test_composition_fee_when_imbalanced() -> None:
    # Bin is all-Y, we add half X, half Y (relative to ratio).
    # The X side is the "wrong" side and gets charged composition fee.
    fee_x, fee_y = composition_fee(
        added_x=100,
        added_y=100,
        bin_total_x=0,
        bin_total_y=1000,
        base_fee_rate_bps=100,  # 1%
    )
    # Adding X to an all-Y bin charges composition fee on the X side.
    assert fee_x > 0
    assert fee_y == 0

import pytest

from asteroid_belt.strategies.base import (
    Action,
    AddLiquidity,
    BinRangeAdd,
    BinRangeRemoval,
    ClaimFees,
    ClosePosition,
    NoOp,
    OpenPosition,
    Rebalance,
    RemoveLiquidity,
)


def test_open_position_defaults() -> None:
    a = OpenPosition(lower_bin=-30, upper_bin=30, distribution="curve")
    assert a.capital_x_pct is None
    assert a.slippage_bps == 50


def test_open_position_with_explicit_balance() -> None:
    a = OpenPosition(
        lower_bin=-30, upper_bin=30, distribution="spot", capital_x_pct=0.7, slippage_bps=100
    )
    assert a.capital_x_pct == 0.7


def test_open_position_invalid_distribution_rejected() -> None:
    # Using Literal types via type checker; runtime check via __post_init__
    with pytest.raises(ValueError):
        OpenPosition(lower_bin=0, upper_bin=10, distribution="banana")  # type: ignore[arg-type]


def test_rebalance_swapless_emergent() -> None:
    r = Rebalance(
        removes=[BinRangeRemoval(lower_bin=-5, upper_bin=5, bps=10000)],
        adds=[
            BinRangeAdd(lower_bin=-3, upper_bin=3, distribution="spot", amount_x=100, amount_y=100)
        ],
    )
    assert r.max_active_bin_slippage == 0


def test_remove_liquidity_bps_range() -> None:
    with pytest.raises(ValueError):
        RemoveLiquidity(bin_range=(0, 10), bps=20000)  # > 10000


def test_actions_in_union() -> None:
    actions: list[Action] = [
        OpenPosition(lower_bin=0, upper_bin=10, distribution="spot"),
        Rebalance(removes=[], adds=[]),
        AddLiquidity(bin_range=(0, 5), distribution="spot", amount_x=1, amount_y=1),
        RemoveLiquidity(bin_range=(0, 5), bps=5000),
        ClosePosition(),
        ClaimFees(),
        NoOp(),
    ]
    assert len(actions) == 7

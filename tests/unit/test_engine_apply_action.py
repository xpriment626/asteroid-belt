"""Engine apply_action — full-fidelity composition tracking.

Composition tracking is where engine bugs manifest as silent miscounting.
Tests cover the four transitions Phase 2 left as no-ops:
  AddLiquidity, RemoveLiquidity, Rebalance, ClaimFees.

v0 simplifications, marked in implementation:
- liquidity_share = 1.0 (we treat ourselves as the only LP).
- Distribution shapes are linear approximations of HawkFi's (x0,y0,dX,dY)
  parameterization; sufficient for v0 infrastructure validation.
"""

from __future__ import annotations

from decimal import Decimal

from asteroid_belt.engine.result import RebalanceRecord
from asteroid_belt.engine.runner import apply_action
from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import PoolState, StaticFeeParams, VolatilityState
from asteroid_belt.strategies.base import (
    AddLiquidity,
    BinRangeAdd,
    BinRangeRemoval,
    ClaimFees,
    OpenPosition,
    Rebalance,
    RemoveLiquidity,
)


def _pool(active_bin: int = 0, base_fee_bps: int = 30) -> PoolState:
    bin_step = 10
    # Invert Meteora's base_fee_rate = base_factor * bin_step * 10 (fee_precision=1e9 units),
    # converted to bps as base_factor * bin_step // 10_000. Solve for base_factor.
    base_factor = base_fee_bps * 10_000 // bin_step
    return PoolState(
        active_bin=active_bin,
        bin_step=bin_step,
        mid_price=Decimal("1"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(base_factor, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={},
        last_swap_ts=0,
        reward_infos=[],
    )


def _position(
    *,
    lower_bin: int = -5,
    upper_bin: int = 5,
    composition: dict[int, BinComposition] | None = None,
    fee_pending_x: int = 0,
    fee_pending_y: int = 0,
    fee_pending_per_bin: dict[int, tuple[int, int]] | None = None,
    total_claimed_x: int = 0,
    total_claimed_y: int = 0,
) -> PositionState:
    return PositionState(
        lower_bin=lower_bin,
        upper_bin=upper_bin,
        composition=composition or {},
        fee_pending_x=fee_pending_x,
        fee_pending_y=fee_pending_y,
        fee_pending_per_bin=fee_pending_per_bin or {},
        total_claimed_x=total_claimed_x,
        total_claimed_y=total_claimed_y,
        fee_owner=None,
    )


# --- OpenPosition (deposit) ---


def test_open_position_deposits_all_capital_into_composition() -> None:
    """OpenPosition opens the range AND deposits all available capital."""
    new_pos, new_x, new_y = apply_action(
        action=OpenPosition(lower_bin=-2, upper_bin=2, distribution="spot"),
        pool=_pool(active_bin=0),
        position=None,
        capital_x=1_000,
        capital_y=1_000,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    assert new_pos.lower_bin == -2
    assert new_pos.upper_bin == 2
    # All capital deployed (composition fee on active bin against an empty bin = 0)
    total_x = sum(c.amount_x for c in new_pos.composition.values())
    total_y = sum(c.amount_y for c in new_pos.composition.values())
    assert total_x == 1_000
    assert total_y == 1_000
    assert new_x == 0
    assert new_y == 0


def test_open_position_with_zero_capital_yields_empty_composition() -> None:
    """OpenPosition with no capital allocates the range but composition stays empty."""
    new_pos, new_x, new_y = apply_action(
        action=OpenPosition(lower_bin=0, upper_bin=10, distribution="curve"),
        pool=_pool(active_bin=0),
        position=None,
        capital_x=0,
        capital_y=0,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    assert new_pos.lower_bin == 0
    assert new_pos.upper_bin == 10
    assert new_pos.composition == {}
    assert new_x == 0
    assert new_y == 0


# --- ClaimFees ---


def test_claim_fees_zeros_pending_grows_claimed() -> None:
    position = _position(
        fee_pending_x=1_000,
        fee_pending_y=2_500,
        fee_pending_per_bin={0: (1_000, 2_500)},
        total_claimed_x=500,
        total_claimed_y=1_000,
    )
    log: list[RebalanceRecord] = []
    new_pos, _new_x, _new_y = apply_action(
        action=ClaimFees(),
        pool=_pool(),
        position=position,
        capital_x=10_000,
        capital_y=20_000,
        rebalance_log=log,
        event_ts=0,
    )
    assert new_pos is not None
    assert new_pos.fee_pending_x == 0
    assert new_pos.fee_pending_y == 0
    assert new_pos.fee_pending_per_bin == {}
    assert new_pos.total_claimed_x == 1_500
    assert new_pos.total_claimed_y == 3_500


def test_claim_fees_grows_capital_by_pending_amounts() -> None:
    position = _position(fee_pending_x=750, fee_pending_y=1_250)
    new_pos, new_x, new_y = apply_action(
        action=ClaimFees(),
        pool=_pool(),
        position=position,
        capital_x=10_000,
        capital_y=20_000,
        rebalance_log=[],
        event_ts=0,
    )
    del new_pos
    assert new_x == 10_750
    assert new_y == 21_250


def test_claim_fees_with_no_pending_is_noop() -> None:
    position = _position()
    new_pos, new_x, new_y = apply_action(
        action=ClaimFees(),
        pool=_pool(),
        position=position,
        capital_x=10_000,
        capital_y=20_000,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos == position
    assert new_x == 10_000
    assert new_y == 20_000


# --- RemoveLiquidity ---


def test_remove_liquidity_shrinks_composition_proportionally() -> None:
    composition = {
        -1: BinComposition(amount_x=0, amount_y=2_000, liquidity_share=1.0),
        0: BinComposition(amount_x=1_000, amount_y=1_000, liquidity_share=1.0),
        1: BinComposition(amount_x=2_000, amount_y=0, liquidity_share=1.0),
    }
    position = _position(composition=composition)
    new_pos, _new_x, _new_y = apply_action(
        action=RemoveLiquidity(bin_range=(-1, 1), bps=2_500),  # remove 25%
        pool=_pool(),
        position=position,
        capital_x=0,
        capital_y=0,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    # 25% removed → 75% remains
    assert new_pos.composition[-1].amount_y == 1_500
    assert new_pos.composition[0].amount_x == 750
    assert new_pos.composition[0].amount_y == 750
    assert new_pos.composition[1].amount_x == 1_500
    # liquidity_share scales proportionally too
    assert new_pos.composition[0].liquidity_share == 0.75


def test_remove_liquidity_grows_capital_by_amount_removed() -> None:
    composition = {0: BinComposition(amount_x=4_000, amount_y=4_000, liquidity_share=1.0)}
    position = _position(composition=composition)
    _new_pos, new_x, new_y = apply_action(
        action=RemoveLiquidity(bin_range=(0, 0), bps=5_000),  # remove 50%
        pool=_pool(),
        position=position,
        capital_x=100,
        capital_y=200,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_x == 100 + 2_000
    assert new_y == 200 + 2_000


def test_remove_liquidity_full_empties_bins_in_range() -> None:
    composition = {
        0: BinComposition(amount_x=1_000, amount_y=1_000, liquidity_share=1.0),
        1: BinComposition(amount_x=2_000, amount_y=0, liquidity_share=1.0),
        2: BinComposition(amount_x=500, amount_y=500, liquidity_share=1.0),
    }
    position = _position(composition=composition)
    new_pos, _new_x, _new_y = apply_action(
        action=RemoveLiquidity(bin_range=(0, 1), bps=10_000),  # remove 100%
        pool=_pool(),
        position=position,
        capital_x=0,
        capital_y=0,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    # bins 0 and 1 emptied; bin 2 untouched
    assert new_pos.composition[0].amount_x == 0
    assert new_pos.composition[0].amount_y == 0
    assert new_pos.composition[0].liquidity_share == 0.0
    assert new_pos.composition[1].amount_x == 0
    assert new_pos.composition[2].amount_x == 500


def test_remove_liquidity_does_not_touch_pending_fees() -> None:
    composition = {0: BinComposition(amount_x=1_000, amount_y=1_000, liquidity_share=1.0)}
    position = _position(
        composition=composition,
        fee_pending_x=300,
        fee_pending_y=400,
        fee_pending_per_bin={0: (300, 400)},
    )
    new_pos, _new_x, _new_y = apply_action(
        action=RemoveLiquidity(bin_range=(0, 0), bps=10_000),
        pool=_pool(),
        position=position,
        capital_x=0,
        capital_y=0,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    # Meteora's raw removeLiquidity does NOT claim — fees persist for separate ClaimFees.
    assert new_pos.fee_pending_x == 300
    assert new_pos.fee_pending_y == 400
    assert new_pos.fee_pending_per_bin == {0: (300, 400)}


# --- AddLiquidity ---


def test_add_liquidity_spot_grows_composition_uniformly() -> None:
    """SPOT distribution: equal split of X across ask-side bins, Y across bid-side."""
    position = _position(lower_bin=-2, upper_bin=2)
    new_pos, _new_x, _new_y = apply_action(
        action=AddLiquidity(
            bin_range=(-2, 2),
            distribution="spot",
            amount_x=3_000,  # ask side: bins 1, 2 (active=0 also gets X half)
            amount_y=3_000,  # bid side: bins -2, -1 (active=0 also gets Y half)
        ),
        pool=_pool(active_bin=0),
        position=position,
        capital_x=10_000,
        capital_y=10_000,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    # Active bin (0) gets balanced split; bins above only X, bins below only Y.
    # With 5 bins (-2..2), 1 active + 2 ask + 2 bid:
    # X: split across {0, 1, 2} but active gets half-share → 3000 / (0.5 + 1 + 1) = 1200
    #   active_x = 600, bin1_x = 1200, bin2_x = 1200
    # Y: split across {-2, -1, 0} mirror.
    assert new_pos.composition[2].amount_x == 1_200
    assert new_pos.composition[1].amount_x == 1_200
    assert new_pos.composition[0].amount_x == 600
    assert new_pos.composition[-1].amount_y == 1_200
    assert new_pos.composition[-2].amount_y == 1_200
    assert new_pos.composition[0].amount_y == 600


def test_add_liquidity_reduces_capital_by_amount_added() -> None:
    position = _position(lower_bin=-2, upper_bin=2)
    _new_pos, new_x, new_y = apply_action(
        action=AddLiquidity(
            bin_range=(-2, 2),
            distribution="spot",
            amount_x=1_500,
            amount_y=2_000,
        ),
        pool=_pool(active_bin=0),
        position=position,
        capital_x=10_000,
        capital_y=10_000,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_x == 10_000 - 1_500
    assert new_y == 10_000 - 2_000


def test_add_liquidity_to_existing_bin_accumulates() -> None:
    """Second add to a bin grows the existing composition rather than overwriting."""
    composition = {0: BinComposition(amount_x=500, amount_y=500, liquidity_share=1.0)}
    position = _position(lower_bin=0, upper_bin=0, composition=composition)
    new_pos, _new_x, _new_y = apply_action(
        action=AddLiquidity(
            bin_range=(0, 0),
            distribution="spot",
            amount_x=200,
            amount_y=200,  # balanced add — no composition fee
        ),
        pool=_pool(active_bin=0),
        position=position,
        capital_x=10_000,
        capital_y=10_000,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    # Balanced add (matches existing 1:1 ratio) → no composition fee
    assert new_pos.composition[0].amount_x == 700
    assert new_pos.composition[0].amount_y == 700


def test_add_liquidity_charges_composition_fee_on_imbalanced_active_bin_add() -> None:
    """An imbalanced add to a bin that already has a different ratio pays a fee."""
    # Existing bin holds 1000 X / 0 Y (single-side ask).
    composition = {0: BinComposition(amount_x=1_000, amount_y=0, liquidity_share=1.0)}
    position = _position(lower_bin=0, upper_bin=0, composition=composition)
    new_pos, _new_x, _new_y = apply_action(
        action=AddLiquidity(
            bin_range=(0, 0),
            distribution="spot",
            amount_x=0,
            amount_y=1_000,  # all Y into a bin that's all X — maximally imbalanced
        ),
        pool=_pool(active_bin=0, base_fee_bps=30),
        position=position,
        capital_x=10_000,
        capital_y=10_000,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    # composition_fee per cost.py: fee on the "wrong-side" (excess) portion.
    # bin_total = 1000, added (x+y) = 1000 → ideal_x = 1000 * 1000/1000 = 1000, ideal_y = 0
    # excess_y = 1000 - 0 = 1000 → fee_y = 1000 * 30 // 10_000 = 3
    # excess_x = max(0, 0 - 1000) = 0 → fee_x = 0
    assert new_pos.composition[0].amount_x == 1_000  # X side unchanged (no excess)
    # Y: added 1000, fee 3 deducted → 997
    assert new_pos.composition[0].amount_y == 997


# --- Rebalance ---


def test_rebalance_remove_then_add_appends_record() -> None:
    composition = {
        0: BinComposition(amount_x=1_000, amount_y=1_000, liquidity_share=1.0),
    }
    position = _position(lower_bin=-1, upper_bin=1, composition=composition)
    log: list[RebalanceRecord] = []
    new_pos, _new_x, _new_y = apply_action(
        action=Rebalance(
            removes=[BinRangeRemoval(lower_bin=0, upper_bin=0, bps=10_000)],
            adds=[
                BinRangeAdd(
                    lower_bin=2,
                    upper_bin=4,
                    distribution="spot",
                    amount_x=1_000,
                    amount_y=0,
                )
            ],
        ),
        pool=_pool(active_bin=0),
        position=position,
        capital_x=10_000,
        capital_y=10_000,
        rebalance_log=log,
        event_ts=12_345,
    )
    assert new_pos is not None
    # Old bin 0 emptied
    assert new_pos.composition[0].amount_x == 0
    # New bins 2..4 hold X (single-side ask: active=0, all bins above)
    assert new_pos.composition[2].amount_x > 0
    assert new_pos.composition[3].amount_x > 0
    assert new_pos.composition[4].amount_x > 0
    # Sum of new ask-side X equals what we put in (no composition fee for non-active-bin adds)
    new_total_x = sum(c.amount_x for k, c in new_pos.composition.items() if k > 0)
    assert new_total_x == 1_000
    # Rebalance record appended
    assert len(log) == 1
    rec = log[0]
    assert rec.ts == 12_345
    assert rec.old_lower_bin == -1
    assert rec.old_upper_bin == 1
    # New range expands to encompass adds
    assert rec.new_lower_bin == -1
    assert rec.new_upper_bin == 4


def test_rebalance_swapless_when_balanced_charges_no_composition_fee() -> None:
    """Reshape: remove all and re-add same totals over same range. No composition fee."""
    composition = {
        -1: BinComposition(amount_x=0, amount_y=1_000, liquidity_share=1.0),
        0: BinComposition(amount_x=500, amount_y=500, liquidity_share=1.0),
        1: BinComposition(amount_x=1_000, amount_y=0, liquidity_share=1.0),
    }
    position = _position(lower_bin=-1, upper_bin=1, composition=composition)
    new_pos, _new_x, _new_y = apply_action(
        action=Rebalance(
            removes=[BinRangeRemoval(lower_bin=-1, upper_bin=1, bps=10_000)],
            adds=[
                BinRangeAdd(
                    lower_bin=-1,
                    upper_bin=1,
                    distribution="spot",
                    amount_x=1_500,  # what we removed in X
                    amount_y=1_500,  # what we removed in Y
                )
            ],
        ),
        pool=_pool(active_bin=0, base_fee_bps=30),
        position=position,
        capital_x=10_000,
        capital_y=10_000,
        rebalance_log=[],
        event_ts=0,
    )
    assert new_pos is not None
    # Active bin (0) balanced add: ideal == added → no excess → no fee.
    # Total X conserved (no fee burned), total Y conserved.
    total_x = sum(c.amount_x for c in new_pos.composition.values())
    total_y = sum(c.amount_y for c in new_pos.composition.values())
    assert total_x == 1_500
    assert total_y == 1_500


def test_rebalance_with_no_position_logs_nothing() -> None:
    """Defensive: apply_action shouldn't crash if validate_action let through a Rebalance
    with no position (it shouldn't, but defense in depth)."""
    log: list[RebalanceRecord] = []
    new_pos, new_x, new_y = apply_action(
        action=Rebalance(removes=[], adds=[]),
        pool=_pool(),
        position=None,
        capital_x=10_000,
        capital_y=20_000,
        rebalance_log=log,
        event_ts=0,
    )
    assert new_pos is None
    assert new_x == 10_000
    assert new_y == 20_000
    assert log == []

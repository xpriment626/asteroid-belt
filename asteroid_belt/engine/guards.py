"""Action validation. Frozen rule.

Bad actions become logged NoOps with a reason string, never raise. Strategies
cannot crash the engine. Validation is conservative — anything ambiguous is
rejected and the strategy can try again with a corrected action next event.
"""

from __future__ import annotations

from asteroid_belt.engine.cost import (
    open_position_lamports,
    rebalance_lamports,
)
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import PoolState
from asteroid_belt.strategies.base import (
    Action,
    AddLiquidity,
    ClaimFees,
    ClosePosition,
    NoOp,
    OpenPosition,
    Rebalance,
    RemoveLiquidity,
)

# Meteora FAQ: max 69 bins per position. Verify against deployed program before
# trusting absolutely.
MAX_BINS_PER_POSITION = 69


def validate_action(
    *,
    action: Action,
    pool: PoolState,
    position: PositionState | None,
    capital_x: int,
    capital_y: int,
    priority_fee_lamports: int,
) -> tuple[Action, str | None]:
    """Validate an action; return (action_or_NoOp, reason_if_rejected).

    On rejection: returns (NoOp(), "human-readable reason").
    On accept: returns (original_action, None).
    """
    del pool, capital_y  # currently unused; kept in signature for forward compat
    match action:
        case OpenPosition(lower_bin=lo, upper_bin=hi):
            if position is not None:
                return NoOp(), "OpenPosition rejected: position already open"
            width = hi - lo + 1
            if width > MAX_BINS_PER_POSITION:
                return NoOp(), (
                    f"OpenPosition rejected: width {width} exceeds "
                    f"MAX_BINS_PER_POSITION ({MAX_BINS_PER_POSITION})"
                )
            # Coarse capital sufficiency check: must cover gas/rent on a fresh open.
            min_lamports = open_position_lamports(
                num_new_bin_arrays=2,  # conservative upper bound for any 69-bin range
                priority_fee_lamports=priority_fee_lamports,
            )
            # SOL is X for SOL/USDC pools. For pool-agnostic correctness, the
            # caller must ensure capital_x is the SOL/native side.
            if capital_x < min_lamports:
                return NoOp(), (
                    f"OpenPosition rejected: insufficient SOL "
                    f"(need {min_lamports}, have {capital_x})"
                )
            return action, None

        case Rebalance() if position is None:
            return NoOp(), "Rebalance rejected: no position open"

        case Rebalance(removes=_, adds=adds):
            for add in adds:
                width = add.upper_bin - add.lower_bin + 1
                if width > MAX_BINS_PER_POSITION:
                    return NoOp(), (
                        f"Rebalance rejected: add range width {width} exceeds "
                        f"MAX_BINS_PER_POSITION"
                    )
            min_lamports = rebalance_lamports(
                num_new_bin_arrays=2,
                priority_fee_lamports=priority_fee_lamports,
            )
            if capital_x < min_lamports:
                return NoOp(), (
                    f"Rebalance rejected: insufficient SOL for fees "
                    f"(need {min_lamports}, have {capital_x})"
                )
            return action, None

        case AddLiquidity() | RemoveLiquidity() | ClaimFees() if position is None:
            return NoOp(), f"{type(action).__name__} rejected: no position open"

        case ClosePosition() if position is None:
            return NoOp(), "ClosePosition rejected: no position open"

        case _:
            return action, None

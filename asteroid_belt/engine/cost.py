"""Cost model for backtest action accounting.

Frozen surface — strategy code reads via run results but cannot modify.

The v1 constants below are best-effort placeholders. Verify against the
deployed Meteora DLMM program before relying on absolute lamport amounts:
  - POSITION_RENT_LAMPORTS: read account size, then
    getMinimumBalanceForRentExemption
  - BIN_ARRAY_RENT_LAMPORTS: same procedure for BinArray
  - DEFAULT_PRIORITY_FEE_LAMPORTS: empirical recent fee distribution

When constants change, bump COST_MODEL_VERSION. Each run records its
cost_model_version so the dashboard can warn when comparing across drift.
"""

from __future__ import annotations

# v1 placeholders — see file docstring for verification procedure.
COST_MODEL_VERSION = "v0.1.0-unverified"

POSITION_RENT_LAMPORTS = 57_000_000  # ~0.057 SOL, refundable on close
BIN_ARRAY_RENT_LAMPORTS = 75_000_000  # ~0.075 SOL per uninitialized BinArray
DEFAULT_PRIORITY_FEE_LAMPORTS = 10_000  # ~0.00001 SOL


def open_position_lamports(*, num_new_bin_arrays: int, priority_fee_lamports: int) -> int:
    """Lamports cost for opening a fresh position."""
    return (
        POSITION_RENT_LAMPORTS
        + num_new_bin_arrays * BIN_ARRAY_RENT_LAMPORTS
        + priority_fee_lamports
    )


def rebalance_lamports(*, num_new_bin_arrays: int, priority_fee_lamports: int) -> int:
    """Lamports cost for an in-place rebalance.

    No POSITION_RENT charge (existing position reused). New BinArrays charged
    if the rebalance enters bin ranges that don't yet have backing arrays.
    """
    return num_new_bin_arrays * BIN_ARRAY_RENT_LAMPORTS + priority_fee_lamports


def composition_fee(
    *,
    added_x: int,
    added_y: int,
    bin_total_x: int,
    bin_total_y: int,
    base_fee_rate_bps: int,
) -> tuple[int, int]:
    """Composition fee charged when adding asymmetric liquidity to a bin.

    Returns (fee_x, fee_y) in raw token units. If the added (x, y) matches the
    bin's existing ratio, both fees are 0. Otherwise the "wrong-side" portion
    is charged base_fee_rate_bps.

    Implementation is a simplified version of Meteora's per-bin composition
    fee math; pre-implementation TODO: cross-check against the on-chain
    LbPair::add_liquidity path to verify the rounding/precision exactly.
    """
    bin_total = bin_total_x + bin_total_y
    if bin_total == 0:
        # Empty bin: no composition fee (any deposit is "balanced" by definition).
        return 0, 0

    # Ideal added amounts to maintain the bin's current ratio.
    ideal_x = (bin_total_x * (added_x + added_y)) // bin_total
    ideal_y = (added_x + added_y) - ideal_x

    # The amount that exceeds the ideal on each side is the "wrong-side" amount.
    excess_x = max(0, added_x - ideal_x)
    excess_y = max(0, added_y - ideal_y)

    fee_x = excess_x * base_fee_rate_bps // 10_000
    fee_y = excess_y * base_fee_rate_bps // 10_000

    return fee_x, fee_y

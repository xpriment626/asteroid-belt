"""DLMM fee math and vParameters evolution.

Frozen rule. The agent's strategy code can READ pool fee state via PoolState
but cannot modify these functions. Implements the LB whitepaper update rule
governed by filter_period / decay_period gates.

Reference: Meteora /dlmm-fee-calculation, Trader Joe LB whitepaper.
"""

from __future__ import annotations

from asteroid_belt.pool.state import StaticFeeParams, VolatilityState

# Fee rates use a 1e10 precision (Meteora "FEE_PRECISION").
MAX_FEE_RATE = 10_000_000_000  # 100% in fee-precision units


def base_fee_rate(*, base_factor: int, bin_step: int) -> int:
    """base_fee_rate = base_factor * bin_step * 10."""
    return base_factor * bin_step * 10


def variable_fee_rate(
    *, volatility_accumulator: int, bin_step: int, variable_fee_control: int
) -> int:
    """variable_fee_rate =
    ((va * bin_step) ** 2 * variable_fee_control + 99_999_999_999) // 1e11.
    """
    numerator = (volatility_accumulator * bin_step) ** 2 * variable_fee_control + 99_999_999_999
    return numerator // 100_000_000_000


def total_fee_rate(*, base: int, variable: int) -> int:
    """Sum capped at MAX_FEE_RATE."""
    return min(MAX_FEE_RATE, base + variable)


def lp_fee_after_protocol_share(*, total_fee: int, protocol_share: int) -> int:
    """LP-side fee after protocol carve-out. protocol_share is in bps."""
    return total_fee * (10_000 - protocol_share) // 10_000


def evolve_v_params(
    *,
    state: VolatilityState,
    sparams: StaticFeeParams,
    event_ts: int,  # in seconds; if your timestamps are ms, divide before calling
    active_bin_before: int,
    target_bin: int,
) -> VolatilityState:
    """Evolve volatility accumulator state for an incoming swap.

    Time gates (dt = event_ts - last_update_timestamp, in seconds):
    - dt < filter_period: keep volatility_reference
    - filter_period <= dt < decay_period: ref = va * reduction_factor / 10_000
    - dt >= decay_period: ref = 0

    After updating reference and index_reference, va is set to:
      min(max_volatility_accumulator,
          volatility_reference + |target - index_reference| * 10_000)
    """
    dt = event_ts - state.last_update_timestamp

    if dt < sparams.filter_period:
        new_ref = state.volatility_reference
        new_index_ref = state.index_reference
    elif dt < sparams.decay_period:
        new_ref = state.volatility_accumulator * sparams.reduction_factor // 10_000
        new_index_ref = active_bin_before
    else:
        new_ref = 0
        new_index_ref = active_bin_before

    bin_distance = abs(target_bin - new_index_ref)
    new_va = min(
        sparams.max_volatility_accumulator,
        new_ref + bin_distance * 10_000,
    )

    return VolatilityState(
        volatility_accumulator=new_va,
        volatility_reference=new_ref,
        index_reference=new_index_ref,
        last_update_timestamp=event_ts,
    )

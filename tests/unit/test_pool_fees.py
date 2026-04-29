from asteroid_belt.pool.fees import (
    base_fee_rate,
    evolve_v_params,
    lp_fee_after_protocol_share,
    total_fee_rate,
    variable_fee_rate,
)
from asteroid_belt.pool.state import StaticFeeParams, VolatilityState


def _sparams(**kw: int) -> StaticFeeParams:
    defaults: dict[str, int] = dict(
        base_factor=10000,
        filter_period=30,
        decay_period=600,
        reduction_factor=5000,
        variable_fee_control=40000,
        protocol_share=500,
        max_volatility_accumulator=350000,
    )
    defaults.update(kw)
    return StaticFeeParams(**defaults)


def test_base_fee_rate_basic() -> None:
    # base_factor=10000, bin_step=10 -> 10000*10*10 = 1_000_000 (~ 0.01% in 1e10 precision)
    assert base_fee_rate(base_factor=10000, bin_step=10) == 1_000_000


def test_variable_fee_rate_zero_when_va_zero() -> None:
    assert variable_fee_rate(volatility_accumulator=0, bin_step=10, variable_fee_control=40000) == 0


def test_variable_fee_rate_positive_when_va_positive() -> None:
    rate = variable_fee_rate(volatility_accumulator=10000, bin_step=10, variable_fee_control=40000)
    assert rate > 0
    expected = ((10000 * 10) ** 2 * 40000 + 99_999_999_999) // 100_000_000_000
    assert rate == expected


def test_total_fee_rate_capped() -> None:
    # Cap at 1e10
    capped = total_fee_rate(base=9_000_000_000, variable=5_000_000_000)
    assert capped == 10_000_000_000


def test_lp_fee_after_protocol_share() -> None:
    assert lp_fee_after_protocol_share(total_fee=1000, protocol_share=500) == 950
    assert lp_fee_after_protocol_share(total_fee=1000, protocol_share=0) == 1000
    assert lp_fee_after_protocol_share(total_fee=1000, protocol_share=10000) == 0


def test_evolve_within_filter_period() -> None:
    # dt < filter_period (30s): volatility_reference stays
    state = VolatilityState(
        volatility_accumulator=20000,
        volatility_reference=15000,
        index_reference=100,
        last_update_timestamp=1_000_000,
    )
    s = _sparams()
    new = evolve_v_params(
        state=state,
        sparams=s,
        event_ts=1_000_010,  # 10s later
        active_bin_before=100,
        target_bin=102,
    )
    # filter_period gate: ref unchanged
    assert new.volatility_reference == 15000
    # va = min(max, ref + |target - index_ref|*10000) = 15000 + 2*10000 = 35000
    assert new.volatility_accumulator == 35000
    assert new.last_update_timestamp == 1_000_010


def test_evolve_within_decay_period() -> None:
    state = VolatilityState(
        volatility_accumulator=40000,
        volatility_reference=20000,
        index_reference=100,
        last_update_timestamp=1_000_000,
    )
    s = _sparams()
    new = evolve_v_params(
        state=state,
        sparams=s,
        event_ts=1_000_300,  # 300s, between filter (30) and decay (600)
        active_bin_before=100,
        target_bin=100,
    )
    # ref decays: va * reduction_factor / 10000 = 40000 * 5000 / 10000 = 20000
    assert new.volatility_reference == 20000
    # va = ref + 0 (no bin movement) = 20000
    assert new.volatility_accumulator == 20000


def test_evolve_past_decay_period_resets() -> None:
    state = VolatilityState(
        volatility_accumulator=50000,
        volatility_reference=30000,
        index_reference=100,
        last_update_timestamp=1_000_000,
    )
    s = _sparams()
    new = evolve_v_params(
        state=state,
        sparams=s,
        event_ts=1_001_000,  # 1000s, past decay (600)
        active_bin_before=100,
        target_bin=105,
    )
    assert new.volatility_reference == 0
    assert new.volatility_accumulator == 50000  # 0 + 5*10000


def test_evolve_caps_at_max() -> None:
    state = VolatilityState(
        volatility_accumulator=0,
        volatility_reference=0,
        index_reference=100,
        last_update_timestamp=1_000_000,
    )
    s = _sparams(max_volatility_accumulator=100000)
    new = evolve_v_params(
        state=state,
        sparams=s,
        event_ts=1_000_001,
        active_bin_before=100,
        target_bin=200,  # 100 bins moved -> would be 1_000_000
    )
    assert new.volatility_accumulator == 100000  # capped

"""Backtest engine main loop.

Single-pass, deterministic. Same config + same input = bit-identical result.
Determinism is non-negotiable: the future agent loop's keep/discard decisions
rely on it.

This task lands the scaffold. Pro-rata fee distribution is stubbed (returns
position unchanged); Task 2.5 fills it in. Action application is also stubbed
(only OpenPosition/ClosePosition/NoOp transition state); real action
application lands incrementally in later phases as adapters and strategies
are integrated.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from heapq import merge

import polars as pl

from asteroid_belt.data.adapters.base import (
    AdapterProtocol,
    SwapEvent,
    TimeTick,
    TimeWindow,
)
from asteroid_belt.engine.composition import distribute
from asteroid_belt.engine.cost import composition_fee
from asteroid_belt.engine.guards import validate_action
from asteroid_belt.engine.result import (
    BacktestResult,
    RebalanceRecord,
)
from asteroid_belt.metrics.primitives import PRIMITIVE_REGISTRY
from asteroid_belt.pool.fees import evolve_v_params
from asteroid_belt.pool.position import (
    hodl_value_in_y,
    il_vs_hodl,
    position_value_in_y,
)
from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import PoolState
from asteroid_belt.strategies.base import (
    Action,
    AddLiquidity,
    BinRangeAdd,
    BinRangeRemoval,
    Capital,
    ClaimFees,
    ClosePosition,
    NoOp,
    OpenPosition,
    Rebalance,
    RemoveLiquidity,
    Strategy,
)


@dataclass(frozen=True)
class RunConfigParams:
    """Engine-level run config (subset of the full RunConfig in config.py).

    The CLI/RunConfig produces this for the engine; engine doesn't care about
    YAML or storage details.
    """

    run_id: str
    config_hash: str
    window: TimeWindow
    tick_secs: int  # TimeTick cadence
    initial_x: int  # raw token units
    initial_y: int
    decimals_x: int
    decimals_y: int
    priority_fee_lamports: int
    selection_metric: str  # name; lookup happens at result-build time


def _generate_time_ticks(window: TimeWindow, tick_secs: int) -> Iterator[TimeTick]:
    """Generate TimeTicks at tick_secs cadence within window (half-open)."""
    cadence_ms = tick_secs * 1000
    ts = window.start_ms + cadence_ms
    while ts < window.end_ms:
        yield TimeTick(ts=ts)
        ts += cadence_ms


def _interleave_chronologically(
    swaps: Iterator[SwapEvent], ticks: Iterator[TimeTick]
) -> Iterator[SwapEvent | TimeTick]:
    """Merge two ordered streams by ts.

    Stable tie-break: at equal ts, SwapEvent (priority 0) is processed before
    TimeTick (priority 1).
    """

    def keyed_swaps() -> Iterator[tuple[int, int, SwapEvent | TimeTick]]:
        for e in swaps:
            yield (e.ts, 0, e)

    def keyed_ticks() -> Iterator[tuple[int, int, SwapEvent | TimeTick]]:
        for e in ticks:
            yield (e.ts, 1, e)

    for _, _, event in merge(keyed_swaps(), keyed_ticks()):
        yield event


def credit_lp_fees_pro_rata(
    *,
    position: PositionState,
    pool: PoolState,
    event: SwapEvent,
) -> PositionState:
    """Credit our position's share of LP fees from this swap.

    Frozen rule. LP fee = (fee_amount - protocol_fee_amount - host_fee_amount).
    Our share = our position's `liquidity_share` in the swap's bin AT swap time.
    Fee is credited in input-token units (X if swap_for_y, else Y).

    Multi-bin swaps are handled at the loop level: each bin-crossing event
    fires this function once with its own `bin_id_after`.
    """
    del pool  # bin liquidity is captured in position.composition[bin_id].liquidity_share
    bin_id = event.bin_id_after
    if bin_id not in position.composition:
        return position

    our_share = position.composition[bin_id].liquidity_share
    if our_share == 0:
        return position

    lp_fee_total = event.lp_fee_amount  # int
    our_credit = int(lp_fee_total * our_share)
    if our_credit == 0:
        return position

    if event.swap_for_y:
        # Fee in X
        new_pending_x = position.fee_pending_x + our_credit
        new_pending_y = position.fee_pending_y
        existing_bin = position.fee_pending_per_bin.get(bin_id, (0, 0))
        new_per_bin = {
            **position.fee_pending_per_bin,
            bin_id: (existing_bin[0] + our_credit, existing_bin[1]),
        }
    else:
        # Fee in Y
        new_pending_x = position.fee_pending_x
        new_pending_y = position.fee_pending_y + our_credit
        existing_bin = position.fee_pending_per_bin.get(bin_id, (0, 0))
        new_per_bin = {
            **position.fee_pending_per_bin,
            bin_id: (existing_bin[0], existing_bin[1] + our_credit),
        }

    return PositionState(
        lower_bin=position.lower_bin,
        upper_bin=position.upper_bin,
        composition=position.composition,
        fee_pending_x=new_pending_x,
        fee_pending_y=new_pending_y,
        fee_pending_per_bin=new_per_bin,
        total_claimed_x=position.total_claimed_x,
        total_claimed_y=position.total_claimed_y,
        fee_owner=position.fee_owner,
    )


def apply_swap_to_pool(*, pool: PoolState, event: SwapEvent) -> PoolState:
    """Update pool state after a swap event lands.

    Stubbed: returns pool with active_bin/mid_price updated to event values.
    Bin liquidity drift is left for a later phase that integrates adapter swap
    deltas (out of scope for v1 bar-level adapter, which doesn't track per-bin
    deltas faithfully anyway).
    """
    return PoolState(
        active_bin=event.bin_id_after,
        bin_step=pool.bin_step,
        mid_price=event.price_after,
        volatility=pool.volatility,
        static_fee=pool.static_fee,
        bin_liquidity=pool.bin_liquidity,
        last_swap_ts=event.ts // 1000,  # ms -> s for v_params evolution
        reward_infos=pool.reward_infos,
    )


def _replace_position(
    position: PositionState,
    *,
    lower_bin: int | None = None,
    upper_bin: int | None = None,
    composition: dict[int, BinComposition] | None = None,
    fee_pending_x: int | None = None,
    fee_pending_y: int | None = None,
    fee_pending_per_bin: dict[int, tuple[int, int]] | None = None,
    total_claimed_x: int | None = None,
    total_claimed_y: int | None = None,
) -> PositionState:
    """Functional update of a frozen PositionState. Local helper to keep
    apply_action branches readable."""
    return PositionState(
        lower_bin=lower_bin if lower_bin is not None else position.lower_bin,
        upper_bin=upper_bin if upper_bin is not None else position.upper_bin,
        composition=composition if composition is not None else position.composition,
        fee_pending_x=fee_pending_x if fee_pending_x is not None else position.fee_pending_x,
        fee_pending_y=fee_pending_y if fee_pending_y is not None else position.fee_pending_y,
        fee_pending_per_bin=(
            fee_pending_per_bin if fee_pending_per_bin is not None else position.fee_pending_per_bin
        ),
        total_claimed_x=(
            total_claimed_x if total_claimed_x is not None else position.total_claimed_x
        ),
        total_claimed_y=(
            total_claimed_y if total_claimed_y is not None else position.total_claimed_y
        ),
        fee_owner=position.fee_owner,
    )


def _apply_remove(
    position: PositionState,
    removal: BinRangeRemoval,
) -> tuple[PositionState, int, int]:
    """Shrink composition in [lower, upper] by bps; return (new_position, removed_x, removed_y).

    v0: liquidity_share scales by the same bps fraction. Real share-tracking would
    require knowing pool's per-bin total liquidity which the bar adapter doesn't
    reconstruct precisely; deferred to v1. Pending fees are NOT touched —
    Meteora's raw removeLiquidity doesn't claim.
    """
    new_comp = dict(position.composition)
    removed_x_total = 0
    removed_y_total = 0
    keep = (10_000 - removal.bps) / 10_000  # for liquidity_share scaling (float)
    for bin_id in range(removal.lower_bin, removal.upper_bin + 1):
        bc = new_comp.get(bin_id)
        if bc is None:
            continue
        rem_x = bc.amount_x * removal.bps // 10_000
        rem_y = bc.amount_y * removal.bps // 10_000
        removed_x_total += rem_x
        removed_y_total += rem_y
        new_comp[bin_id] = BinComposition(
            amount_x=bc.amount_x - rem_x,
            amount_y=bc.amount_y - rem_y,
            liquidity_share=bc.liquidity_share * keep,
        )
    return _replace_position(position, composition=new_comp), removed_x_total, removed_y_total


def _apply_add(
    position: PositionState,
    add: BinRangeAdd,
    *,
    pool: PoolState,
    base_fee_rate_bps: int,
) -> tuple[PositionState, int, int]:
    """Grow composition with the per-bin distribution; return (new_position, fee_x, fee_y).

    Composition fee is charged only on the active bin's "wrong-side" portion
    (per cost.composition_fee). Other bins hold pure-X (above active) or pure-Y
    (below active), so any add lands at the bin's existing token-zero ratio
    and incurs no fee.

    Returned fee_x, fee_y are total composition fees burned (already deducted
    from the composition amounts).
    """
    per_bin = distribute(
        amount_x=add.amount_x,
        amount_y=add.amount_y,
        lower_bin=add.lower_bin,
        upper_bin=add.upper_bin,
        active_bin=pool.active_bin,
        distribution=add.distribution,
    )

    new_comp = dict(position.composition)
    total_fee_x = 0
    total_fee_y = 0

    for bin_id, (add_x, add_y) in per_bin.items():
        existing = new_comp.get(bin_id)
        bin_total_x = existing.amount_x if existing else 0
        bin_total_y = existing.amount_y if existing else 0

        # Composition fee only on the active bin (only place a non-zero
        # ratio mismatch can arise — non-active bins are single-token).
        fee_x = 0
        fee_y = 0
        if bin_id == pool.active_bin:
            fee_x, fee_y = composition_fee(
                added_x=add_x,
                added_y=add_y,
                bin_total_x=bin_total_x,
                bin_total_y=bin_total_y,
                base_fee_rate_bps=base_fee_rate_bps,
            )
            total_fee_x += fee_x
            total_fee_y += fee_y

        # Net amount that lands in the bin (after fee burn)
        net_x = add_x - fee_x
        net_y = add_y - fee_y

        new_amount_x = bin_total_x + net_x
        new_amount_y = bin_total_y + net_y
        # v0 share: 1.0 (we treat ourselves as the only LP).
        new_comp[bin_id] = BinComposition(
            amount_x=new_amount_x,
            amount_y=new_amount_y,
            liquidity_share=1.0,
        )

    return _replace_position(position, composition=new_comp), total_fee_x, total_fee_y


def apply_action(
    *,
    action: Action,
    pool: PoolState,
    position: PositionState | None,
    capital_x: int,
    capital_y: int,
    rebalance_log: list[RebalanceRecord],
    event_ts: int,
) -> tuple[PositionState | None, int, int]:
    """Apply an action to position state, returning new (position, cap_x, cap_y).

    Composition tracking is the bug-prone surface — see test_engine_apply_action
    for the contract each branch must satisfy.
    """
    # Meteora: base_fee_rate (in fee_precision=1e9 units) = base_factor * bin_step * 10.
    # Convert to bps: base_fee_rate / 1e9 * 1e4 = base_fee_rate / 1e5.
    # → base_fee_bps = base_factor * bin_step // 10_000.
    base_fee_bps = pool.static_fee.base_factor * pool.bin_step // 10_000
    match action:
        case NoOp():
            return position, capital_x, capital_y

        case OpenPosition(lower_bin=lo, upper_bin=hi, distribution=dist):
            # Open allocates the bin range AND deposits all available capital
            # using the chosen distribution. v0 simplification: capital_x_pct
            # (intended for SDK-side autoFill swap) is ignored — the position
            # opens with whatever ratio the strategy passes in via Capital.
            empty_position = PositionState(
                lower_bin=lo,
                upper_bin=hi,
                composition={},
                fee_pending_x=0,
                fee_pending_y=0,
                fee_pending_per_bin={},
                total_claimed_x=0,
                total_claimed_y=0,
                fee_owner=None,
            )
            if capital_x == 0 and capital_y == 0:
                return empty_position, 0, 0
            initial_add = BinRangeAdd(
                lower_bin=lo,
                upper_bin=hi,
                distribution=dist,
                amount_x=capital_x,
                amount_y=capital_y,
            )
            new_position, _fx, _fy = _apply_add(
                empty_position, initial_add, pool=pool, base_fee_rate_bps=base_fee_bps
            )
            return new_position, 0, 0

        case ClosePosition():
            if position is None:
                return None, capital_x, capital_y
            # Refund composition + pending fees to capital.
            refund_x = sum(c.amount_x for c in position.composition.values())
            refund_x += position.fee_pending_x
            refund_y = sum(c.amount_y for c in position.composition.values())
            refund_y += position.fee_pending_y
            return None, capital_x + refund_x, capital_y + refund_y

        case ClaimFees():
            if position is None:
                return None, capital_x, capital_y
            new_capital_x = capital_x + position.fee_pending_x
            new_capital_y = capital_y + position.fee_pending_y
            new_pos = _replace_position(
                position,
                fee_pending_x=0,
                fee_pending_y=0,
                fee_pending_per_bin={},
                total_claimed_x=position.total_claimed_x + position.fee_pending_x,
                total_claimed_y=position.total_claimed_y + position.fee_pending_y,
            )
            return new_pos, new_capital_x, new_capital_y

        case AddLiquidity(
            bin_range=(lo, hi),
            distribution=dist,
            amount_x=ax,
            amount_y=ay,
        ):
            if position is None:
                return None, capital_x, capital_y
            add = BinRangeAdd(
                lower_bin=lo,
                upper_bin=hi,
                distribution=dist,
                amount_x=ax,
                amount_y=ay,
            )
            new_pos, _fee_x, _fee_y = _apply_add(
                position, add, pool=pool, base_fee_rate_bps=base_fee_bps
            )
            # Capital deduction is by the full added amount; the composition fee
            # comes out of the deposited tokens themselves (Meteora semantics).
            return new_pos, capital_x - ax, capital_y - ay

        case RemoveLiquidity(bin_range=(lo, hi), bps=bps):
            if position is None:
                return None, capital_x, capital_y
            removal = BinRangeRemoval(lower_bin=lo, upper_bin=hi, bps=bps)
            new_pos, removed_x, removed_y = _apply_remove(position, removal)
            return new_pos, capital_x + removed_x, capital_y + removed_y

        case Rebalance(removes=removes, adds=adds):
            if position is None:
                return None, capital_x, capital_y
            current = position
            # 1) Apply all removes (returns capital).
            removed_x_total = 0
            removed_y_total = 0
            for r in removes:
                current, rx, ry = _apply_remove(current, r)
                removed_x_total += rx
                removed_y_total += ry
            cap_x = capital_x + removed_x_total
            cap_y = capital_y + removed_y_total

            # 2) Apply all adds (consumes capital, accrues composition fees).
            comp_fee_x = 0
            comp_fee_y = 0
            adds_total_x = 0
            adds_total_y = 0
            for a in adds:
                current, fx, fy = _apply_add(current, a, pool=pool, base_fee_rate_bps=base_fee_bps)
                comp_fee_x += fx
                comp_fee_y += fy
                adds_total_x += a.amount_x
                adds_total_y += a.amount_y
            cap_x -= adds_total_x
            cap_y -= adds_total_y

            # 3) Range envelope expands to encompass all add ranges.
            new_lower = current.lower_bin
            new_upper = current.upper_bin
            for a in adds:
                new_lower = min(new_lower, a.lower_bin)
                new_upper = max(new_upper, a.upper_bin)
            if new_lower != current.lower_bin or new_upper != current.upper_bin:
                current = _replace_position(current, lower_bin=new_lower, upper_bin=new_upper)

            # 4) Log the rebalance.
            rebalance_log.append(
                RebalanceRecord(
                    ts=event_ts,
                    trigger="strategy",
                    old_lower_bin=position.lower_bin,
                    old_upper_bin=position.upper_bin,
                    new_lower_bin=current.lower_bin,
                    new_upper_bin=current.upper_bin,
                    gas_lamports=0,  # gas accounted at run-config layer; v0 stub
                    composition_fee_x=comp_fee_x,
                    composition_fee_y=comp_fee_y,
                    fees_claimed_x=0,
                    fees_claimed_y=0,
                )
            )
            return current, cap_x, cap_y

        case _:
            # Defensive — unknown action types become no-ops.
            return position, capital_x, capital_y


def _empty_trajectory() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": pl.Series([], dtype=pl.Int64),
            "price": pl.Series([], dtype=pl.Float64),
            "active_bin": pl.Series([], dtype=pl.Int32),
            "position_value_usd": pl.Series([], dtype=pl.Float64),
            "hodl_value_usd": pl.Series([], dtype=pl.Float64),
            "fees_x_cumulative": pl.Series([], dtype=pl.Int64),
            "fees_y_cumulative": pl.Series([], dtype=pl.Int64),
            "fees_value_usd": pl.Series([], dtype=pl.Float64),
            "il_cumulative": pl.Series([], dtype=pl.Float64),
            "in_range": pl.Series([], dtype=pl.Boolean),
            "capital_idle_usd": pl.Series([], dtype=pl.Float64),
        }
    )


def run_backtest(
    *,
    strategy: Strategy,
    adapter: AdapterProtocol,
    initial_pool_state: PoolState,
    config: RunConfigParams,
) -> BacktestResult:
    """Run one backtest. Deterministic single-pass."""
    started_at = int(time.time() * 1000)
    pool = initial_pool_state
    capital_x, capital_y = config.initial_x, config.initial_y
    rebalances: list[RebalanceRecord] = []

    # Initial action
    initial_action = strategy.initialize(pool, Capital(x=capital_x, y=capital_y))
    validated, _reason = validate_action(
        action=initial_action,
        pool=pool,
        position=None,
        capital_x=capital_x,
        capital_y=capital_y,
        priority_fee_lamports=config.priority_fee_lamports,
    )
    position, capital_x, capital_y = apply_action(
        action=validated,
        pool=pool,
        position=None,
        capital_x=capital_x,
        capital_y=capital_y,
        rebalance_log=rebalances,
        event_ts=config.window.start_ms,
    )

    trajectory_rows: list[dict[str, object]] = []

    # Main loop: interleave swaps + ticks chronologically
    swaps = adapter.stream(config.window)
    ticks = _generate_time_ticks(config.window, config.tick_secs)
    for event in _interleave_chronologically(swaps, ticks):
        action: Action
        if isinstance(event, SwapEvent):
            pool = PoolState(
                active_bin=pool.active_bin,
                bin_step=pool.bin_step,
                mid_price=pool.mid_price,
                volatility=evolve_v_params(
                    state=pool.volatility,
                    sparams=pool.static_fee,
                    event_ts=event.ts // 1000,
                    active_bin_before=pool.active_bin,
                    target_bin=event.bin_id_after,
                ),
                static_fee=pool.static_fee,
                bin_liquidity=pool.bin_liquidity,
                last_swap_ts=pool.last_swap_ts,
                reward_infos=pool.reward_infos,
            )
            if position is not None:
                position = credit_lp_fees_pro_rata(position=position, pool=pool, event=event)
            pool = apply_swap_to_pool(pool=pool, event=event)
            action = strategy.on_swap(event, pool, position) if position is not None else NoOp()
        else:  # TimeTick
            action = strategy.on_tick(event.ts, pool, position) if position is not None else NoOp()

        validated, _reason = validate_action(
            action=action,
            pool=pool,
            position=position,
            capital_x=capital_x,
            capital_y=capital_y,
            priority_fee_lamports=config.priority_fee_lamports,
        )
        position, capital_x, capital_y = apply_action(
            action=validated,
            pool=pool,
            position=position,
            capital_x=capital_x,
            capital_y=capital_y,
            rebalance_log=rebalances,
            event_ts=event.ts,
        )

        price = pool.mid_price
        if position is not None:
            position_value_usd = float(
                position_value_in_y(
                    composition=position.composition,
                    price=price,
                    decimals_x=config.decimals_x,
                    decimals_y=config.decimals_y,
                )
            )
            il_cumulative = float(
                il_vs_hodl(
                    composition=position.composition,
                    initial_x=config.initial_x,
                    initial_y=config.initial_y,
                    price=price,
                    decimals_x=config.decimals_x,
                    decimals_y=config.decimals_y,
                )
            )
            fees_x_cumulative = position.total_claimed_x + position.fee_pending_x
            fees_y_cumulative = position.total_claimed_y + position.fee_pending_y
            in_range = position.in_range(pool.active_bin)
        else:
            position_value_usd = 0.0
            il_cumulative = 0.0
            fees_x_cumulative = 0
            fees_y_cumulative = 0
            in_range = False

        fees_value_usd = float(
            (Decimal(fees_x_cumulative) / Decimal(10) ** config.decimals_x) * price
            + (Decimal(fees_y_cumulative) / Decimal(10) ** config.decimals_y)
        )

        hodl_value_usd = float(
            hodl_value_in_y(
                initial_x=config.initial_x,
                initial_y=config.initial_y,
                price=price,
                decimals_x=config.decimals_x,
                decimals_y=config.decimals_y,
            )
        )
        capital_idle_usd = float(
            (Decimal(capital_x) / Decimal(10) ** config.decimals_x) * price
            + (Decimal(capital_y) / Decimal(10) ** config.decimals_y)
        )

        trajectory_rows.append(
            {
                "ts": event.ts,
                "price": float(price),
                "active_bin": pool.active_bin,
                "position_value_usd": position_value_usd,
                "hodl_value_usd": hodl_value_usd,
                "fees_x_cumulative": fees_x_cumulative,
                "fees_y_cumulative": fees_y_cumulative,
                "fees_value_usd": fees_value_usd,
                "il_cumulative": il_cumulative,
                "in_range": in_range,
                "capital_idle_usd": capital_idle_usd,
            }
        )

    ended_at = int(time.time() * 1000)
    trajectory = pl.DataFrame(trajectory_rows) if trajectory_rows else _empty_trajectory()

    # Build a partial result so PRIMITIVE_REGISTRY functions can read trajectory
    # + rebalances. Score is filled in after primitives are computed.
    partial = BacktestResult(
        run_id=config.run_id,
        config_hash=config.config_hash,
        schema_version="1.0",
        started_at=started_at,
        ended_at=ended_at,
        status="ok",
        trajectory=trajectory,
        rebalances=rebalances,
        primitives={},
        score=0.0,
        score_metric=config.selection_metric,
    )
    primitives = {name: fn(partial) for name, fn in PRIMITIVE_REGISTRY.items()}
    score = primitives.get(config.selection_metric, 0.0)

    return BacktestResult(
        run_id=config.run_id,
        config_hash=config.config_hash,
        schema_version="1.0",
        started_at=started_at,
        ended_at=ended_at,
        status="ok",
        trajectory=trajectory,
        rebalances=rebalances,
        primitives=primitives,
        score=score,
        score_metric=config.selection_metric,
    )

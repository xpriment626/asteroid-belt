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
from heapq import merge

import polars as pl

from asteroid_belt.data.adapters.base import (
    AdapterProtocol,
    SwapEvent,
    TimeTick,
    TimeWindow,
)
from asteroid_belt.engine.guards import validate_action
from asteroid_belt.engine.result import (
    BacktestResult,
    RebalanceRecord,
)
from asteroid_belt.pool.fees import evolve_v_params
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import PoolState
from asteroid_belt.strategies.base import (
    Action,
    Capital,
    ClosePosition,
    NoOp,
    OpenPosition,
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
    """Credit our position's share of the LP fee from this swap.

    Stubbed in this task. Task 2.5 implements the real pro-rata distribution
    that respects bin liquidity at swap time (handles JIT-bot fee dilution).
    """
    del pool, event
    return position


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

    Stubbed for v1 scaffold: only OpenPosition / ClosePosition / NoOp
    transition state. Full action application lands incrementally in Phase 3
    as strategies and adapters are integrated.
    """
    del pool, rebalance_log, event_ts  # unused in scaffold
    match action:
        case NoOp():
            return position, capital_x, capital_y
        case OpenPosition(lower_bin=lo, upper_bin=hi):
            new_position = PositionState(
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
            return new_position, capital_x, capital_y
        case ClosePosition():
            return None, capital_x, capital_y
        case _:
            # Other actions are no-ops in the scaffold.
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

        # Append trajectory row (stub values — Phase 3+ fills in real numbers).
        trajectory_rows.append(
            {
                "ts": event.ts,
                "price": float(pool.mid_price),
                "active_bin": pool.active_bin,
                "position_value_usd": 0.0,
                "hodl_value_usd": 0.0,
                "fees_x_cumulative": 0,
                "fees_y_cumulative": 0,
                "il_cumulative": 0.0,
                "in_range": position.in_range(pool.active_bin) if position is not None else False,
                "capital_idle_usd": 0.0,
            }
        )

    ended_at = int(time.time() * 1000)
    trajectory = pl.DataFrame(trajectory_rows) if trajectory_rows else _empty_trajectory()

    # Primitives are computed in Phase 2 metrics tasks; for the scaffold, return zeros.
    primitives = {config.selection_metric: 0.0}

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
        score=0.0,
        score_metric=config.selection_metric,
    )

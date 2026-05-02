"""Trial / iteration / run endpoints — backed by the DuckDB run store.

Reads agent iterations from the `runs` + `run_artifacts` tables via
`store.agent_runs`. Response shapes are unchanged from the demo's flat-file
era so the frontend client doesn't move.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, cast

import polars as pl
from fastapi import APIRouter, BackgroundTasks, HTTPException

from asteroid_belt.server.schemas import (
    BuildActionRequest,
    BuildActionResponse,
    IterationDetail,
    IterationSummary,
    RunStartRequest,
    RunStatus,
    TrajectoryRow,
    TrialDetail,
    TrialSummary,
)
from asteroid_belt.store.agent_runs import (
    AgentIterationPayload,
    ensure_agent_session,
    get_iteration_payload,
    get_iteration_trajectory,
    list_agent_trials,
    list_iteration_payloads,
    record_agent_iteration,
)
from asteroid_belt.store.runs import RunStore

# In-process store of currently-active runs. Keyed by run_id; values are
# RunStatus dataclasses we mutate on the worker thread. Demo-grade — v2
# moves this to a redis hash / dedicated DB table once we need
# multi-worker / restart-safety.
_RUNS: dict[str, RunStatus] = {}
_RUNS_LOCK = threading.Lock()


def _short_error(msg: str | None) -> str | None:
    if msg is None:
        return None
    first = msg.splitlines()[0] if msg else ""
    return first[:200]


def _safe_score(raw: Any) -> float | None:
    """Map -inf / nan / None to None so JSON encodes cleanly. Otherwise float()."""
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):  # NaN check is x != x
        return None
    return v


def _summarize_trial(trial: str, payloads: list[AgentIterationPayload]) -> TrialSummary:
    iteration_count = len(payloads)
    success = [p for p in payloads if p.error is None]
    errors = [p for p in payloads if p.error is not None]
    degenerate = [p for p in success if (p.score or 0.0) == 0.0]
    best: AgentIterationPayload | None = None
    if success:
        best = max(success, key=lambda p: p.score if p.score is not None else float("-inf"))
    timestamps = [p.timestamp for p in payloads if p.timestamp]
    return TrialSummary(
        trial=trial,
        iteration_count=iteration_count,
        success_count=len(success),
        error_count=len(errors),
        degenerate_count=len(degenerate),
        best_iteration=best.iteration if best else None,
        best_score=_safe_score(best.score) if best else None,
        score_metric=best.score_metric if best else None,
        started_at=min(timestamps) if timestamps else None,
        last_updated=max(timestamps) if timestamps else None,
    )


def _to_iteration_summary(payload: AgentIterationPayload) -> IterationSummary:
    return IterationSummary(
        iteration=payload.iteration,
        timestamp=payload.timestamp,
        code_hash=payload.code_hash,
        score=_safe_score(payload.score),
        score_metric=payload.score_metric,
        rebalance_count=payload.rebalance_count,
        error=_short_error(payload.error),
        has_trajectory=payload.has_trajectory,
        primitives={
            k: v
            for k, v in ((k, _safe_score(v)) for k, v in payload.primitives.items())
            if v is not None
        },
    )


def build_router(*, store: RunStore, data_dir: Path, runs_dir: Path) -> APIRouter:
    """FastAPI router for trial endpoints. Tests pass a tmp store + dirs."""
    router = APIRouter()

    @router.get("/trials", response_model=list[TrialSummary])
    def list_trials() -> list[TrialSummary]:
        out: list[TrialSummary] = []
        for sess in list_agent_trials(store):
            payloads = list_iteration_payloads(store, trial=sess.session_id)
            out.append(_summarize_trial(sess.session_id, payloads))
        # Most-recently-touched trials first.
        out.sort(key=lambda s: s.last_updated or 0, reverse=True)
        return out

    @router.get("/trials/{trial}", response_model=TrialDetail)
    def get_trial(trial: str) -> TrialDetail:
        try:
            store.get_session(trial)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"trial {trial} not found") from e
        payloads = list_iteration_payloads(store, trial=trial)
        summary = _summarize_trial(trial, payloads)
        iterations = [_to_iteration_summary(p) for p in payloads]
        return TrialDetail(**summary.model_dump(), iterations=iterations)

    @router.get("/trials/{trial}/iterations/{iteration}", response_model=IterationDetail)
    def get_iteration(trial: str, iteration: int) -> IterationDetail:
        try:
            store.get_session(trial)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"trial {trial} not found") from e
        payload = get_iteration_payload(store, trial=trial, iteration=iteration)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail=f"iteration {iteration} not found in trial {trial}",
            )
        return IterationDetail(
            iteration=payload.iteration,
            timestamp=payload.timestamp,
            code_hash=payload.code_hash,
            score=_safe_score(payload.score),
            score_metric=payload.score_metric,
            rebalance_count=payload.rebalance_count,
            error=payload.error,  # full traceback on detail endpoint
            has_trajectory=payload.has_trajectory,
            primitives={
                k: v
                for k, v in ((k, _safe_score(v)) for k, v in payload.primitives.items())
                if v is not None
            },
            strategy_code=payload.strategy_code,
        )

    @router.get(
        "/trials/{trial}/iterations/{iteration}/trajectory",
        response_model=list[TrajectoryRow],
    )
    def get_trajectory(trial: str, iteration: int) -> list[TrajectoryRow]:
        try:
            store.get_session(trial)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"trial {trial} not found") from e
        df = get_iteration_trajectory(store, trial=trial, iteration=iteration)
        if df is None:
            raise HTTPException(
                status_code=404,
                detail=f"trajectory for iteration {iteration} in trial {trial} not found",
            )
        return [
            TrajectoryRow(
                ts=int(row["ts"]),
                price=float(row["price"]),
                active_bin=int(row["active_bin"]),
                position_value_usd=float(row["position_value_usd"]),
                hodl_value_usd=float(row["hodl_value_usd"]),
                fees_value_usd=float(row["fees_value_usd"]),
                il_cumulative=float(row["il_cumulative"]),
                in_range=bool(row["in_range"]),
                capital_idle_usd=float(row["capital_idle_usd"]),
            )
            for row in df.iter_rows(named=True)
        ]

    @router.post(
        "/trials/{trial}/iterations/{iteration}/build-action",
        response_model=BuildActionResponse,
    )
    def build_action(trial: str, iteration: int, req: BuildActionRequest) -> BuildActionResponse:
        """Run a stored iteration's strategy.initialize() against a live pool."""
        try:
            store.get_session(trial)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"trial {trial} not found") from e
        payload = get_iteration_payload(store, trial=trial, iteration=iteration)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail=f"iteration {iteration} not found in trial {trial}",
            )
        if payload.error:
            return BuildActionResponse(
                action_type="error",
                lower_bin=None,
                upper_bin=None,
                distribution=None,
                error="cannot deploy an iteration that errored during scoring",
            )

        # Lazy imports — keep the trial-listing path light.
        from decimal import Decimal

        from asteroid_belt.agent.tools import _exec_strategy_code
        from asteroid_belt.pool.state import (
            PoolState,
            StaticFeeParams,
            VolatilityState,
        )
        from asteroid_belt.strategies.base import Capital, OpenPosition

        try:
            cls = _exec_strategy_code(payload.strategy_code)
            strategy = cls()
            pool = PoolState(
                active_bin=req.active_bin,
                bin_step=req.bin_step,
                mid_price=Decimal("1"),
                volatility=VolatilityState(0, 0, 0, 0),
                static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
                bin_liquidity={},
                last_swap_ts=0,
                reward_infos=[],
            )
            action = strategy.initialize(pool, Capital(x=req.initial_x, y=req.initial_y))
        except Exception as exc:
            return BuildActionResponse(
                action_type="error",
                lower_bin=None,
                upper_bin=None,
                distribution=None,
                error=f"{type(exc).__name__}: {exc}",
            )

        if isinstance(action, OpenPosition):
            return BuildActionResponse(
                action_type="open_position",
                lower_bin=action.lower_bin,
                upper_bin=action.upper_bin,
                distribution=action.distribution,
                error=None,
            )
        return BuildActionResponse(
            action_type="no_op",
            lower_bin=None,
            upper_bin=None,
            distribution=None,
            error=(
                "strategy.initialize() returned a non-OpenPosition action — "
                "cannot build a deploy tx for it"
            ),
        )

    @router.post("/runs/start", response_model=RunStatus)
    def start_run(req: RunStartRequest, background_tasks: BackgroundTasks) -> RunStatus:
        pool_dir = data_dir / "pools" / req.pool
        if not pool_dir.exists():
            raise HTTPException(status_code=404, detail=f"pool {req.pool} not found")

        run_id = uuid.uuid4().hex[:12]
        status = RunStatus(
            run_id=run_id,
            trial=req.trial,
            state="running",
            iterations_completed=0,
            budget=req.budget,
            started_at=int(time.time() * 1000),
            ended_at=None,
            error=None,
        )
        with _RUNS_LOCK:
            _RUNS[run_id] = status

        background_tasks.add_task(
            _execute_run,
            run_id=run_id,
            pool_dir=pool_dir,
            trial=req.trial,
            budget=req.budget,
            objective=req.objective,
            initial_x=req.initial_x,
            initial_y=req.initial_y,
            store=store,
            runs_dir=runs_dir,
        )
        return status

    @router.get("/runs/{run_id}", response_model=RunStatus)
    def get_run(run_id: str) -> RunStatus:
        with _RUNS_LOCK:
            current = _RUNS.get(run_id)
        if current is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        # Iterations land in DB while the worker is busy; reflect that here.
        if current.state == "running":
            try:
                payloads = list_iteration_payloads(store, trial=current.trial)
                with _RUNS_LOCK:
                    _RUNS[run_id].iterations_completed = len(payloads)
                    current = _RUNS[run_id]
            except Exception:
                pass
        return current

    return router


def _execute_run(
    *,
    run_id: str,
    pool_dir: Path,
    trial: str,
    budget: int,
    objective: str,
    initial_x: int,
    initial_y: int,
    store: RunStore,
    runs_dir: Path,
) -> None:
    """Background worker — runs one tournament loop, mutates _RUNS state."""
    try:
        # Lazy imports so the API process doesn't pay the cost unless a run fires.
        from asteroid_belt.agent.llm import LLMClient
        from asteroid_belt.agent.tools import (
            data_summary,
            extract_python,
            history_summary,
            load_pool_dataset,
            read_strategy,
            run_candidate,
        )
        from asteroid_belt.data.adapters.base import TimeWindow

        dataset = load_pool_dataset(pool_dir)
        df = pl.read_parquet(dataset.parquet_path).sort("ts")
        first_ts = cast(int, df["ts"][0])
        window = TimeWindow(
            start_ms=int(first_ts),
            end_ms=int(first_ts) + 7 * 24 * 60 * 60 * 1000,
        )

        ensure_agent_session(
            store,
            trial=trial,
            pool_address=dataset.pool_key.address,
            objective=objective,
            budget=budget,
        )

        prompt_path = Path(__file__).resolve().parents[1] / "agent" / "prompt.txt"
        system_prompt = prompt_path.read_text()
        worked_examples = {
            "precision_curve": read_strategy("precision_curve"),
            "multiday_cook_up": read_strategy("multiday_cook_up"),
        }

        llm = LLMClient()
        history = list_iteration_payloads(store, trial=trial)
        history_dicts = [
            {
                "iteration": p.iteration,
                "score": p.score,
                "score_metric": p.score_metric,
                "primitives": p.primitives,
                "rebalance_count": p.rebalance_count,
                "error": p.error,
            }
            for p in history
        ]
        start_iter = max((p.iteration for p in history), default=-1) + 1

        for i in range(start_iter, start_iter + budget):
            history_text = history_summary(history_dicts)
            user_parts = [
                f"OBJECTIVE: maximize `{objective}`",
                "",
                "DATA SUMMARY:",
                data_summary(dataset, window),
                "",
                "PRIOR EXPERIMENTS:",
                history_text,
                "",
                "WORKED EXAMPLES (illustrative — mutate freely; do not just copy):",
            ]
            for name, code in worked_examples.items():
                user_parts.append(f"\n## {name}.py\n```python\n{code}\n```")
            user_parts.append(
                "\nNow produce ONE new candidate MyStrategy. Output only one "
                "```python ... ``` block. No prose."
            )
            user_prompt = "\n".join(user_parts)

            response = llm.complete(system=system_prompt, user=user_prompt)
            code = extract_python(response)
            result = run_candidate(
                strategy_code=code,
                dataset=dataset,
                window=window,
                initial_x=initial_x,
                initial_y=initial_y,
                selection_metric=objective,
                iteration=i,
            )
            now = int(time.time() * 1000)
            record_agent_iteration(
                store,
                runs_dir=runs_dir,
                trial=trial,
                iteration=i,
                code_hash=result.code_hash,
                strategy_code=result.strategy_code,
                pool_address=dataset.pool_key.address,
                window_start=window.start_ms,
                window_end=window.end_ms,
                initial_x=initial_x,
                initial_y=initial_y,
                selection_metric=objective,
                started_at=now,
                ended_at=now,
                status="error" if result.error else "ok",
                score=None if result.error else result.score,
                primitives=result.primitives if not result.error else None,
                error_msg=result.error,
                trajectory=result.trajectory,
            )
            history_dicts.append(
                {
                    "iteration": i,
                    "score": result.score if not result.error else None,
                    "score_metric": objective,
                    "primitives": result.primitives,
                    "rebalance_count": result.rebalance_count,
                    "error": result.error,
                }
            )

            with _RUNS_LOCK:
                _RUNS[run_id].iterations_completed = len(history_dicts)

        with _RUNS_LOCK:
            _RUNS[run_id].state = "done"
            _RUNS[run_id].ended_at = int(time.time() * 1000)
    except Exception as exc:
        with _RUNS_LOCK:
            _RUNS[run_id].state = "failed"
            _RUNS[run_id].ended_at = int(time.time() * 1000)
            _RUNS[run_id].error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"

"""Trial / iteration / run endpoints.

Reads the agent's flat-file output at `<results_root>/<trial>/<iter>_<hash>.{json,parquet}`.
Trial persistence is intentionally file-based for the demo (see checkpoint
2026-05-01); migration to a real DB is a post-demo concern.
"""

from __future__ import annotations

import json
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

# In-process store of currently-active runs. Keyed by run_id; values are
# RunStatus dataclasses we mutate on the worker thread. Demo-only — would
# be a redis hash / db row in production.
_RUNS: dict[str, RunStatus] = {}
_RUNS_LOCK = threading.Lock()


def _trial_dir(results_root: Path, trial: str) -> Path:
    return results_root / trial


def _iteration_payloads(trial_dir: Path) -> list[dict[str, Any]]:
    if not trial_dir.exists():
        return []
    payloads: list[dict[str, Any]] = []
    for p in sorted(trial_dir.glob("*.json")):
        try:
            payloads.append(json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    payloads.sort(key=lambda d: int(d.get("iteration", 0)))
    return payloads


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


def _summarize_trial(trial: str, payloads: list[dict[str, Any]]) -> TrialSummary:
    iteration_count = len(payloads)
    success = [p for p in payloads if p.get("error") is None]
    errors = [p for p in payloads if p.get("error") is not None]
    degenerate = [p for p in success if float(p.get("score", 0.0)) == 0.0]
    best: dict[str, Any] | None = None
    if success:
        best = max(success, key=lambda p: float(p.get("score", float("-inf"))))
    timestamps = [int(p.get("timestamp", 0)) for p in payloads if p.get("timestamp")]
    return TrialSummary(
        trial=trial,
        iteration_count=iteration_count,
        success_count=len(success),
        error_count=len(errors),
        degenerate_count=len(degenerate),
        best_iteration=int(best["iteration"]) if best else None,
        best_score=_safe_score(best["score"]) if best else None,
        score_metric=str(best["score_metric"]) if best else None,
        started_at=min(timestamps) if timestamps else None,
        last_updated=max(timestamps) if timestamps else None,
    )


def _to_iteration_summary(payload: dict[str, Any]) -> IterationSummary:
    return IterationSummary(
        iteration=int(payload["iteration"]),
        timestamp=int(payload.get("timestamp", 0)),
        code_hash=str(payload.get("code_hash", "")),
        score=_safe_score(payload.get("score")),
        score_metric=str(payload.get("score_metric", "")),
        rebalance_count=int(payload.get("rebalance_count", 0)),
        error=_short_error(payload.get("error")),
        has_trajectory=bool(payload.get("has_trajectory", False)),
        primitives={
            k: v
            for k, v in ((k, _safe_score(v)) for k, v in (payload.get("primitives") or {}).items())
            if v is not None
        },
    )


def build_router(*, results_root: Path, data_dir: Path) -> APIRouter:
    """FastAPI router for trial endpoints. Tests can pass a tmp results_root."""
    router = APIRouter()

    @router.get("/trials", response_model=list[TrialSummary])
    def list_trials() -> list[TrialSummary]:
        if not results_root.exists():
            return []
        out: list[TrialSummary] = []
        for d in sorted(results_root.iterdir()):
            if not d.is_dir():
                continue
            payloads = _iteration_payloads(d)
            out.append(_summarize_trial(d.name, payloads))
        # Most-recently-touched trials first.
        out.sort(key=lambda s: s.last_updated or 0, reverse=True)
        return out

    @router.get("/trials/{trial}", response_model=TrialDetail)
    def get_trial(trial: str) -> TrialDetail:
        d = _trial_dir(results_root, trial)
        if not d.exists():
            raise HTTPException(status_code=404, detail=f"trial {trial} not found")
        payloads = _iteration_payloads(d)
        summary = _summarize_trial(trial, payloads)
        iterations = [_to_iteration_summary(p) for p in payloads]
        return TrialDetail(**summary.model_dump(), iterations=iterations)

    @router.get("/trials/{trial}/iterations/{iteration}", response_model=IterationDetail)
    def get_iteration(trial: str, iteration: int) -> IterationDetail:
        d = _trial_dir(results_root, trial)
        if not d.exists():
            raise HTTPException(status_code=404, detail=f"trial {trial} not found")
        for p in d.glob(f"{iteration:04d}_*.json"):
            payload = json.loads(p.read_text())
            return IterationDetail(
                iteration=int(payload["iteration"]),
                timestamp=int(payload.get("timestamp", 0)),
                code_hash=str(payload.get("code_hash", "")),
                score=_safe_score(payload.get("score")),
                score_metric=str(payload.get("score_metric", "")),
                rebalance_count=int(payload.get("rebalance_count", 0)),
                error=payload.get("error"),  # full traceback on detail endpoint
                has_trajectory=bool(payload.get("has_trajectory", False)),
                primitives={
                    k: v
                    for k, v in (
                        (k, _safe_score(v)) for k, v in (payload.get("primitives") or {}).items()
                    )
                    if v is not None
                },
                strategy_code=str(payload.get("strategy_code", "")),
            )
        raise HTTPException(
            status_code=404, detail=f"iteration {iteration} not found in trial {trial}"
        )

    @router.get(
        "/trials/{trial}/iterations/{iteration}/trajectory",
        response_model=list[TrajectoryRow],
    )
    def get_trajectory(trial: str, iteration: int) -> list[TrajectoryRow]:
        d = _trial_dir(results_root, trial)
        if not d.exists():
            raise HTTPException(status_code=404, detail=f"trial {trial} not found")
        for p in d.glob(f"{iteration:04d}_*.parquet"):
            df = pl.read_parquet(p)
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
        raise HTTPException(
            status_code=404,
            detail=f"trajectory for iteration {iteration} in trial {trial} not found",
        )

    @router.post(
        "/trials/{trial}/iterations/{iteration}/build-action",
        response_model=BuildActionResponse,
    )
    def build_action(trial: str, iteration: int, req: BuildActionRequest) -> BuildActionResponse:
        """Run a stored iteration's strategy.initialize() against a live pool.

        Lets the frontend translate the strategy's "open at active ± half" intent
        to actual bin numbers on whatever pool the user is deploying to (devnet
        or otherwise). Returns the resolved OpenPosition action — frontend
        passes those bins to the Meteora SDK to build the on-chain tx.
        """
        d = _trial_dir(results_root, trial)
        if not d.exists():
            raise HTTPException(status_code=404, detail=f"trial {trial} not found")
        match = next(d.glob(f"{iteration:04d}_*.json"), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail=f"iteration {iteration} not found in trial {trial}",
            )
        payload = json.loads(match.read_text())
        if payload.get("error"):
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
            cls = _exec_strategy_code(str(payload["strategy_code"]))
            strategy = cls()
            # Build a PoolState pinned to the live pool's active bin. Static-fee
            # params here mirror our test fixture for SOL/USDC 10bps; they only
            # affect what the strategy sees during init, not what tx we'll build.
            pool = PoolState(
                active_bin=req.active_bin,
                bin_step=req.bin_step,
                mid_price=Decimal("1"),  # strategies don't typically read this in initialize
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
        )
        return status

    @router.get("/runs/{run_id}", response_model=RunStatus)
    def get_run(run_id: str) -> RunStatus:
        with _RUNS_LOCK:
            status = _RUNS.get(run_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        # Iterations land on disk while the worker is busy; reflect that here.
        with _RUNS_LOCK:
            current = _RUNS[run_id]
            if current.state == "running":
                trial_dir = _trial_dir(Path("agent/results"), current.trial)
                current.iterations_completed = (
                    len(list(trial_dir.glob("*.json"))) if trial_dir.exists() else 0
                )
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
) -> None:
    """Background worker — runs one tournament loop, mutates _RUNS state."""
    try:
        # Lazy imports so the API process doesn't pay the cost unless a run fires.
        from asteroid_belt.agent.llm import LLMClient
        from asteroid_belt.agent.tools import (
            data_summary,
            extract_python,
            history_summary,
            load_history,
            load_pool_dataset,
            read_strategy,
            run_candidate,
            save_experiment,
        )
        from asteroid_belt.data.adapters.base import TimeWindow

        dataset = load_pool_dataset(pool_dir)
        df = pl.read_parquet(dataset.parquet_path).sort("ts")
        first_ts = cast(int, df["ts"][0])
        window = TimeWindow(
            start_ms=int(first_ts),
            end_ms=int(first_ts) + 7 * 24 * 60 * 60 * 1000,
        )

        results_dir = Path("agent/results") / trial
        results_dir.mkdir(parents=True, exist_ok=True)

        prompt_path = Path(__file__).resolve().parents[1] / "agent" / "prompt.txt"
        system_prompt = prompt_path.read_text()
        worked_examples = {
            "precision_curve": read_strategy("precision_curve"),
            "multiday_cook_up": read_strategy("multiday_cook_up"),
        }

        llm = LLMClient()
        history = load_history(results_dir)
        start_iter = max((int(h.get("iteration", 0)) for h in history), default=-1) + 1

        for i in range(start_iter, start_iter + budget):
            history_text = history_summary(history)
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
            path = save_experiment(result, results_dir=results_dir)
            history.append(json.loads(path.read_text()))

            with _RUNS_LOCK:
                _RUNS[run_id].iterations_completed = len(history)

        with _RUNS_LOCK:
            _RUNS[run_id].state = "done"
            _RUNS[run_id].ended_at = int(time.time() * 1000)
    except Exception as exc:
        with _RUNS_LOCK:
            _RUNS[run_id].state = "failed"
            _RUNS[run_id].ended_at = int(time.time() * 1000)
            _RUNS[run_id].error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"

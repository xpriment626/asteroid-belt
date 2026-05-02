"""Agent-tournament adapter over the run store.

Maps the agent's mental model (trial → many iterations) onto the existing
schema:
- trial         → sessions row, session_kind = 'agent'
- iteration     → runs row, created_by = 'agent', session_id = trial
- trajectory    → run_artifacts row, kind = 'trajectory'
- strategy code → run_artifacts row, kind = 'source_code'

run_id is deterministic (`agent_<trial>_<iter:04d>`) so re-runs of migration
or replays don't create duplicates.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from asteroid_belt.store.runs import (
    ArtifactRecord,
    DuckDBRunStore,
    RunRecord,
    RunStore,
    SessionRecord,
)

AGENT_CREATED_BY = "agent"
AGENT_SESSION_KIND = "agent"
TRAJECTORY_KIND = "trajectory"
SOURCE_KIND = "source_code"

# Pinned constants for the demo. cost_model_version mirrors engine/cost.py;
# adapter_kind is fixed because we only run agent loops over bar_synth_5m today.
AGENT_COST_MODEL_VERSION = "v0.1.0-unverified"
AGENT_ADAPTER_KIND = "bar_synth_5m"
AGENT_TICK_SECS = 300
AGENT_STRATEGY_CLASS = "AgentMutated"


def agent_run_id(trial: str, iteration: int) -> str:
    """Deterministic run_id for an agent iteration. Stable for migration/replay."""
    return f"agent_{trial}_{iteration:04d}"


def _safe_score(raw: float | None) -> float | None:
    """Map -inf / nan to None so DuckDB stores a real NULL instead of a NaN double."""
    if raw is None:
        return None
    if not isinstance(raw, int | float):
        return None
    if math.isnan(raw) or math.isinf(raw):
        return None
    return float(raw)


def ensure_agent_session(
    store: RunStore,
    *,
    trial: str,
    pool_address: str,
    objective: str,
    budget: int,
    created_at: int | None = None,
) -> SessionRecord:
    """Create the trial's session row if missing; return existing or freshly-inserted."""
    try:
        return store.get_session(trial)
    except KeyError:
        session = SessionRecord(
            session_id=trial,
            label=f"Agent tournament — {pool_address[:8]}",
            created_at=created_at if created_at is not None else int(time.time() * 1000),
            closed_at=None,
            session_kind=AGENT_SESSION_KIND,
            goal_json={"pool_address": pool_address, "objective": objective, "budget": budget},
            outcome_json=None,
            notes=None,
        )
        store.insert_session(session)
        return session


def record_agent_iteration(
    store: RunStore,
    *,
    runs_dir: Path,
    trial: str,
    iteration: int,
    code_hash: str,
    strategy_code: str,
    pool_address: str,
    window_start: int,
    window_end: int,
    initial_x: int,
    initial_y: int,
    selection_metric: str,
    started_at: int,
    ended_at: int,
    status: str,
    score: float | None,
    primitives: dict[str, float] | None,
    error_msg: str | None,
    trajectory: pl.DataFrame | None,
) -> str:
    """Insert a runs row for one iteration + write strategy/trajectory artifacts.

    Idempotent: if `runs.run_id` already exists this raises a DuckDB constraint
    error — callers that want replay-safe writes should check via
    `store.get(agent_run_id(...))` first and skip.
    """
    run_id = agent_run_id(trial, iteration)

    run = RunRecord(
        run_id=run_id,
        config_hash=code_hash,
        parent_run_id=None,
        session_id=trial,
        created_by=AGENT_CREATED_BY,
        cost_model_version=AGENT_COST_MODEL_VERSION,
        schema_version="1.0",
        pool_address=pool_address,
        strategy_class=AGENT_STRATEGY_CLASS,
        strategy_params={"trial": trial, "iteration": iteration, "code_hash": code_hash},
        strategy_source_sha=hashlib.sha256(strategy_code.encode()).hexdigest(),
        adapter_kind=AGENT_ADAPTER_KIND,
        window_start=window_start,
        window_end=window_end,
        tick_secs=AGENT_TICK_SECS,
        initial_x=initial_x,
        initial_y=initial_y,
        selection_metric=selection_metric,
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        error_msg=error_msg,
        score=_safe_score(score),
        primitives=primitives,
        notes=None,
    )
    store.insert(run)

    out_dir = runs_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    code_path = out_dir / "strategy.py"
    code_bytes = strategy_code.encode()
    code_path.write_bytes(code_bytes)
    store.insert_artifact(
        ArtifactRecord(
            run_id=run_id,
            kind=SOURCE_KIND,
            path=str(code_path),
            sha256=hashlib.sha256(code_bytes).hexdigest(),
            bytes=len(code_bytes),
        )
    )

    if trajectory is not None and not trajectory.is_empty():
        traj_path = out_dir / "trajectory.parquet"
        trajectory.write_parquet(traj_path)
        store.insert_artifact(
            ArtifactRecord(
                run_id=run_id,
                kind=TRAJECTORY_KIND,
                path=str(traj_path),
                sha256=None,
                bytes=traj_path.stat().st_size,
            )
        )

    return run_id


# --- Read helpers ---------------------------------------------------------


@dataclass
class AgentIterationPayload:
    """Compatibility shape — matches the JSON payload the old flat-file path produced.

    Kept identical so the prompt builder + history summarizer don't have to change.
    """

    iteration: int
    timestamp: int
    code_hash: str
    score: float | None
    score_metric: str
    primitives: dict[str, float]
    rebalance_count: int
    error: str | None
    strategy_code: str
    has_trajectory: bool


def list_agent_trials(store: RunStore) -> list[SessionRecord]:
    """All sessions where session_kind = 'agent'. Most-recently-created first."""
    return store.list_sessions(kind=AGENT_SESSION_KIND)


def list_iterations(store: RunStore, *, trial: str) -> list[RunRecord]:
    """All iterations of a trial, sorted by iteration_index ascending."""
    runs = store.query(session_id=trial, created_by=AGENT_CREATED_BY)
    runs.sort(key=lambda r: int(r.strategy_params.get("iteration", 0)))
    return runs


def _strategy_code_from_artifact(artifact: ArtifactRecord) -> str:
    try:
        return Path(artifact.path).read_text()
    except (OSError, FileNotFoundError):
        return ""


def payload_from_run(run: RunRecord, *, store: RunStore) -> AgentIterationPayload:
    """Convert a RunRecord + its artifacts into the old JSON-payload shape."""
    artifacts = store.query_artifacts(run.run_id)
    by_kind = {a.kind: a for a in artifacts}
    strategy_code = (
        _strategy_code_from_artifact(by_kind[SOURCE_KIND]) if SOURCE_KIND in by_kind else ""
    )
    rebalance_count = int((run.primitives or {}).get("rebalance_count", 0))
    return AgentIterationPayload(
        iteration=int(run.strategy_params.get("iteration", 0)),
        timestamp=run.ended_at if run.ended_at is not None else run.started_at,
        code_hash=str(run.strategy_params.get("code_hash", run.config_hash)),
        score=run.score,
        score_metric=run.selection_metric,
        primitives=dict(run.primitives or {}),
        rebalance_count=rebalance_count,
        error=run.error_msg,
        strategy_code=strategy_code,
        has_trajectory=TRAJECTORY_KIND in by_kind,
    )


def list_iteration_payloads(store: RunStore, *, trial: str) -> list[AgentIterationPayload]:
    return [payload_from_run(r, store=store) for r in list_iterations(store, trial=trial)]


def get_iteration_payload(
    store: RunStore, *, trial: str, iteration: int
) -> AgentIterationPayload | None:
    run_id = agent_run_id(trial, iteration)
    try:
        run = store.get(run_id)
    except KeyError:
        return None
    return payload_from_run(run, store=store)


def get_iteration_trajectory(store: RunStore, *, trial: str, iteration: int) -> pl.DataFrame | None:
    """Return the trajectory parquet for one iteration, or None if absent."""
    run_id = agent_run_id(trial, iteration)
    for a in store.query_artifacts(run_id):
        if a.kind == TRAJECTORY_KIND:
            return pl.read_parquet(a.path)
    return None


def default_db_path(data_dir: Path) -> Path:
    return data_dir / "asteroid_belt.duckdb"


def open_default_store(data_dir: Path) -> DuckDBRunStore:
    """Open (and lazily init) the project-default DuckDB store."""
    db_path = default_db_path(data_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return DuckDBRunStore(db_path=db_path)

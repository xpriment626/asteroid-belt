"""Pydantic response models for FastAPI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class PoolSummary(BaseModel):
    address: str
    name: str | None = None
    bin_step: int | None = None
    bars_count: int


class PoolDetail(BaseModel):
    address: str
    name: str | None = None
    bin_step: int | None = None
    bars_count: int
    meta: dict[str, Any]


class Bar(BaseModel):
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume_x: int
    volume_y: int


# --- Trial / iteration / run schemas (autoresearch agent) ---


class IterationSummary(BaseModel):
    """One row in a trial leaderboard."""

    iteration: int
    timestamp: int
    code_hash: str
    score: float | None  # null when the iteration errored (raw -inf is not JSON-safe)
    score_metric: str
    rebalance_count: int
    error: str | None  # short error message if the iteration failed
    has_trajectory: bool
    primitives: dict[str, float]


class TrialSummary(BaseModel):
    """Top-level overview of a trial — what shows up in /trials list."""

    trial: str
    iteration_count: int
    success_count: int
    error_count: int
    degenerate_count: int  # successful but score == 0
    best_iteration: int | None
    best_score: float | None
    score_metric: str | None
    started_at: int | None  # ms epoch of earliest iteration
    last_updated: int | None  # ms epoch of latest iteration


class TrialDetail(TrialSummary):
    """Trial summary + the full leaderboard."""

    iterations: list[IterationSummary]


class IterationDetail(BaseModel):
    """One iteration in full — code + primitives + error + has_trajectory flag."""

    iteration: int
    timestamp: int
    code_hash: str
    score: float | None
    score_metric: str
    rebalance_count: int
    error: str | None
    has_trajectory: bool
    primitives: dict[str, float]
    strategy_code: str


class TrajectoryRow(BaseModel):
    ts: int
    price: float
    active_bin: int
    position_value_usd: float
    hodl_value_usd: float
    fees_value_usd: float
    il_cumulative: float
    in_range: bool
    capital_idle_usd: float


class RunStartRequest(BaseModel):
    pool: str
    trial: str
    budget: int = 10
    objective: str = "vol_capture"
    initial_x: int = 10_000_000_000
    initial_y: int = 1_000_000_000


class RunStatus(BaseModel):
    run_id: str
    trial: str
    state: str  # "running" | "done" | "failed"
    iterations_completed: int
    budget: int
    started_at: int
    ended_at: int | None
    error: str | None

"""BacktestResult and RebalanceRecord — engine output types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import polars as pl

RunStatus = Literal["running", "ok", "error", "timeout"]


@dataclass(frozen=True)
class RebalanceRecord:
    """One discrete rebalance event for the dashboard's table view."""

    ts: int
    trigger: str  # free-form; strategies tag the trigger that fired
    old_lower_bin: int
    old_upper_bin: int
    new_lower_bin: int
    new_upper_bin: int
    gas_lamports: int  # tx priority fees + rent paid (refundable rent on close)
    composition_fee_x: int
    composition_fee_y: int
    fees_claimed_x: int
    fees_claimed_y: int


@dataclass(frozen=True)
class BacktestResult:
    """The artifact produced by one backtest run.

    The trajectory DataFrame is persisted to data/runs/<run_id>/result.parquet.
    Rebalances are persisted to data/runs/<run_id>/rebalances.parquet.
    Primitives (all shipped metrics) are precomputed at result-build time so
    re-evaluating a run under a new metric never re-runs the backtest.
    """

    run_id: str
    config_hash: str
    schema_version: str
    started_at: int
    ended_at: int
    status: RunStatus
    trajectory: pl.DataFrame
    rebalances: list[RebalanceRecord]
    primitives: dict[str, float]
    score: float
    score_metric: str
    error_msg: str | None = field(default=None)

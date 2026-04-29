"""BacktestResult <-> parquet round-trip + manifest writer.

Per-run layout under data/runs/<run_id>/:
  result.parquet         # trajectory
  rebalances.parquet     # discrete rebalance events
  manifest.json          # config snapshot + primitives + score (portable)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import polars as pl

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord


def write_result(*, result: BacktestResult, runs_dir: Path) -> None:
    """Write trajectory + rebalances + manifest under runs_dir/<run_id>/."""
    out_dir = runs_dir / result.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Trajectory
    result.trajectory.write_parquet(out_dir / "result.parquet")

    # Rebalances
    if result.rebalances:
        reb_df = pl.DataFrame([asdict(r) for r in result.rebalances])
    else:
        reb_df = pl.DataFrame(
            {
                "ts": pl.Series([], dtype=pl.Int64),
                "trigger": pl.Series([], dtype=pl.Utf8),
                "old_lower_bin": pl.Series([], dtype=pl.Int32),
                "old_upper_bin": pl.Series([], dtype=pl.Int32),
                "new_lower_bin": pl.Series([], dtype=pl.Int32),
                "new_upper_bin": pl.Series([], dtype=pl.Int32),
                "gas_lamports": pl.Series([], dtype=pl.Int64),
                "composition_fee_x": pl.Series([], dtype=pl.Int64),
                "composition_fee_y": pl.Series([], dtype=pl.Int64),
                "fees_claimed_x": pl.Series([], dtype=pl.Int64),
                "fees_claimed_y": pl.Series([], dtype=pl.Int64),
            }
        )
    reb_df.write_parquet(out_dir / "rebalances.parquet")

    # Manifest (portable; lets you zip a run dir and replay elsewhere)
    manifest = {
        "run_id": result.run_id,
        "config_hash": result.config_hash,
        "schema_version": result.schema_version,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "status": result.status,
        "primitives": result.primitives,
        "score": result.score,
        "score_metric": result.score_metric,
        "error_msg": result.error_msg,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def read_trajectory(*, run_id: str, runs_dir: Path) -> pl.DataFrame:
    return pl.read_parquet(runs_dir / run_id / "result.parquet")


def read_rebalances(*, run_id: str, runs_dir: Path) -> list[RebalanceRecord]:
    df = pl.read_parquet(runs_dir / run_id / "rebalances.parquet")
    return [RebalanceRecord(**row) for row in df.iter_rows(named=True)]

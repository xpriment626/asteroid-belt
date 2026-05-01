"""Regenerate trajectory parquet files for an existing trial.

Re-runs each successful iteration's strategy code through the engine so we
can populate the trajectory artifact for trials saved before the parquet
output was added. Idempotent — skips iterations that already have a
trajectory file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import click
import polars as pl

from asteroid_belt.agent.tools import (
    PoolDataset,
    load_pool_dataset,
    run_candidate,
    save_experiment,
    trajectory_path_for,
)
from asteroid_belt.data.adapters.base import TimeWindow

_RESULTS_ROOT = Path("agent/results")


def regen_trial(
    *,
    trial: str,
    dataset: PoolDataset,
    window: TimeWindow,
    initial_x: int,
    initial_y: int,
) -> dict[str, int]:
    """Walk all JSONs in the trial dir; rerun successful ones to write trajectories.

    Returns a dict with counts: {regen, skipped_existing, skipped_errored}.
    """
    results_dir = _RESULTS_ROOT / trial
    if not results_dir.exists():
        raise click.ClickException(f"Trial dir not found: {results_dir}")

    counts = {"regen": 0, "skipped_existing": 0, "skipped_errored": 0}
    for json_path in sorted(results_dir.glob("*.json")):
        payload = json.loads(json_path.read_text())
        if payload.get("error"):
            counts["skipped_errored"] += 1
            continue
        traj_path = trajectory_path_for(
            results_dir,
            iteration=int(payload["iteration"]),
            code_hash=str(payload["code_hash"]),
        )
        if traj_path.exists():
            counts["skipped_existing"] += 1
            continue

        result = run_candidate(
            strategy_code=payload["strategy_code"],
            dataset=dataset,
            window=window,
            initial_x=initial_x,
            initial_y=initial_y,
            selection_metric=payload["score_metric"],
            iteration=int(payload["iteration"]),
        )
        if result.error or result.trajectory is None or result.trajectory.is_empty():
            counts["skipped_errored"] += 1
            continue
        # Overwrite the JSON's `has_trajectory` field via save_experiment so the UI
        # sees it as present. Strategy code/score are deterministic; we keep the
        # original timestamp from the historical payload.
        result.timestamp = int(payload["timestamp"])
        save_experiment(result, results_dir=results_dir)
        counts["regen"] += 1

    return counts


@click.command()
@click.option("--trial", required=True, help="Trial name (matches agent/results/<trial>/)")
@click.option("--pool", required=True, help="Pool address — must exist in data/pools/<addr>/")
@click.option("--data-dir", default="data", type=click.Path(exists=True))
@click.option("--initial-x", type=int, default=10_000_000_000)
@click.option("--initial-y", type=int, default=1_000_000_000)
@click.option("--window-start-ms", type=int, default=None)
@click.option("--window-end-ms", type=int, default=None)
def main(
    trial: str,
    pool: str,
    data_dir: str,
    initial_x: int,
    initial_y: int,
    window_start_ms: int | None,
    window_end_ms: int | None,
) -> None:
    """Re-run successful iterations of a trial to populate trajectory parquets."""
    pool_dir = Path(data_dir) / "pools" / pool
    if not pool_dir.exists():
        raise click.ClickException(f"Pool dir not found: {pool_dir}")
    dataset = load_pool_dataset(pool_dir)

    if window_start_ms is None or window_end_ms is None:
        df = pl.read_parquet(dataset.parquet_path).sort("ts")
        first_ts = cast(int, df["ts"][0])
        window_start_ms = window_start_ms or int(first_ts)
        window_end_ms = window_end_ms or (window_start_ms + 7 * 24 * 60 * 60 * 1000)
    window = TimeWindow(start_ms=window_start_ms, end_ms=window_end_ms)

    counts = regen_trial(
        trial=trial,
        dataset=dataset,
        window=window,
        initial_x=initial_x,
        initial_y=initial_y,
    )
    click.echo(
        f"trial={trial}  regen={counts['regen']}  skipped_existing={counts['skipped_existing']}  skipped_errored={counts['skipped_errored']}"
    )


if __name__ == "__main__":
    main()

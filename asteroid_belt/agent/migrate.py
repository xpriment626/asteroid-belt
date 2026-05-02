"""Migrate flat-file agent results into the DuckDB store.

Reads `agent/results/<trial>/<iter>_<hash>.{json,parquet}` and writes the
equivalent rows + artifacts via `store.agent_runs`. One-shot — once a trial
is migrated, future writes go directly to the DB.

Idempotent: skips iterations whose `run_id` is already present in the DB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import polars as pl

from asteroid_belt.store.agent_runs import (
    agent_run_id,
    ensure_agent_session,
    open_default_store,
    record_agent_iteration,
)


def _load_trial_payloads(trial_dir: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for p in sorted(trial_dir.glob("*.json")):
        try:
            payloads.append(json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    payloads.sort(key=lambda d: int(d.get("iteration", 0)))
    return payloads


def _trajectory_for(trial_dir: Path, *, iteration: int, code_hash: str) -> pl.DataFrame | None:
    p = trial_dir / f"{iteration:04d}_{code_hash}.parquet"
    if not p.exists():
        return None
    return pl.read_parquet(p)


def migrate_trial(
    *,
    trial: str,
    flat_results_root: Path,
    runs_dir: Path,
    db_path: Path,
    pool_address: str,
    objective: str,
    window_start: int,
    window_end: int,
    initial_x: int,
    initial_y: int,
) -> dict[str, int]:
    """Read flat files for one trial; insert into DB. Returns counts dict."""
    trial_dir = flat_results_root / trial
    if not trial_dir.exists():
        raise click.ClickException(f"Trial dir not found: {trial_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    from asteroid_belt.store.runs import DuckDBRunStore

    store = DuckDBRunStore(db_path=db_path)
    payloads = _load_trial_payloads(trial_dir)
    if not payloads:
        raise click.ClickException(f"No iteration JSONs found under {trial_dir}")

    earliest = min(int(p.get("timestamp", 0)) for p in payloads)
    ensure_agent_session(
        store,
        trial=trial,
        pool_address=pool_address,
        objective=objective,
        budget=len(payloads),
        created_at=earliest,
    )

    counts = {"inserted": 0, "skipped_existing": 0}
    for payload in payloads:
        iteration = int(payload["iteration"])
        run_id = agent_run_id(trial, iteration)
        try:
            store.get(run_id)
            counts["skipped_existing"] += 1
            continue
        except KeyError:
            pass

        code_hash = str(payload.get("code_hash", ""))
        trajectory = _trajectory_for(trial_dir, iteration=iteration, code_hash=code_hash)

        # Errored iterations have score = float('-inf') in the JSON; the helper
        # coerces -inf → None so DuckDB stores a NULL.
        raw_score = payload.get("score")
        score: float | None = float(raw_score) if isinstance(raw_score, int | float) else None

        record_agent_iteration(
            store,
            runs_dir=runs_dir,
            trial=trial,
            iteration=iteration,
            code_hash=code_hash,
            strategy_code=str(payload.get("strategy_code", "")),
            pool_address=pool_address,
            window_start=window_start,
            window_end=window_end,
            initial_x=initial_x,
            initial_y=initial_y,
            selection_metric=str(payload.get("score_metric", objective)),
            started_at=int(payload.get("timestamp", earliest)),
            ended_at=int(payload.get("timestamp", earliest)),
            status="error" if payload.get("error") else "ok",
            score=score,
            primitives={
                k: float(v)
                for k, v in (payload.get("primitives") or {}).items()
                if isinstance(v, int | float)
            },
            error_msg=payload.get("error"),
            trajectory=trajectory,
        )
        counts["inserted"] += 1

    return counts


@click.command()
@click.option("--trial", required=True, help="Trial name (matches agent/results/<trial>/)")
@click.option("--pool", required=True, help="Pool address — recorded on each runs row")
@click.option("--objective", default="vol_capture")
@click.option(
    "--data-dir", default="data", type=click.Path(exists=True), help="Data root for DB + runs/"
)
@click.option(
    "--flat-results-root",
    default="agent/results",
    type=click.Path(),
    help="Where the flat JSON+parquet files currently live (pre-DB era)",
)
@click.option("--initial-x", type=int, default=10_000_000_000)
@click.option("--initial-y", type=int, default=1_000_000_000)
@click.option("--window-start-ms", type=int, default=None)
@click.option("--window-end-ms", type=int, default=None)
def main(
    trial: str,
    pool: str,
    objective: str,
    data_dir: str,
    flat_results_root: str,
    initial_x: int,
    initial_y: int,
    window_start_ms: int | None,
    window_end_ms: int | None,
) -> None:
    """One-shot: backfill a flat-file trial into the DB store."""
    data_dir_path = Path(data_dir)

    # Default window: first 7 days of pool's 5m bars (matches what the agent
    # used at score time). Lets the migration record real numbers when the
    # original config wasn't preserved in the flat files.
    if window_start_ms is None or window_end_ms is None:
        bars_path = data_dir_path / "pools" / pool / "bars_5m.parquet"
        if bars_path.exists():
            df = pl.read_parquet(bars_path).sort("ts")
            first_ts = int(df["ts"][0])
            window_start_ms = window_start_ms or first_ts
            window_end_ms = window_end_ms or (window_start_ms + 7 * 24 * 60 * 60 * 1000)
        else:
            window_start_ms = window_start_ms or 0
            window_end_ms = window_end_ms or 0

    counts = migrate_trial(
        trial=trial,
        flat_results_root=Path(flat_results_root),
        runs_dir=data_dir_path / "runs",
        db_path=data_dir_path / "asteroid_belt.duckdb",
        pool_address=pool,
        objective=objective,
        window_start=window_start_ms,
        window_end=window_end_ms,
        initial_x=initial_x,
        initial_y=initial_y,
    )
    click.echo(
        f"trial={trial}  inserted={counts['inserted']}  "
        f"skipped_existing={counts['skipped_existing']}"
    )


# `open_default_store` re-exported for downstream / tests.
__all__ = ["main", "migrate_trial", "open_default_store"]


if __name__ == "__main__":
    main()

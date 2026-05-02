"""Tournament loop entry point.

    uv run belt agent --pool BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y \\
        --budget 20 --objective vol_capture --trial demo

Writes through the DuckDB run store (see store.agent_runs). Resumes from
existing iterations on the same trial automatically.
"""

from __future__ import annotations

import time
from pathlib import Path

import click

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
from asteroid_belt.metrics.primitives import (
    DEFAULT_SELECTION_METRIC,
    PRIMITIVE_REGISTRY,
)
from asteroid_belt.store.agent_runs import (
    ensure_agent_session,
    list_iteration_payloads,
    open_default_store,
    record_agent_iteration,
)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompt.txt"


def _build_user_prompt(
    *,
    objective: str,
    data_summary_text: str,
    history_text: str,
    worked_examples: dict[str, str],
) -> str:
    parts = [
        f"OBJECTIVE: maximize `{objective}`",
        "",
        "DATA SUMMARY:",
        data_summary_text,
        "",
        "PRIOR EXPERIMENTS:",
        history_text,
        "",
        "WORKED EXAMPLES (illustrative — mutate freely; do not just copy):",
    ]
    for name, code in worked_examples.items():
        parts.append(f"\n## {name}.py\n```python\n{code}\n```")
    parts.append(
        "\nNow produce ONE new candidate MyStrategy. Output only one "
        "```python ... ``` block. No prose."
    )
    return "\n".join(parts)


@click.command()
@click.option("--pool", required=True, help="Pool address — must exist in data/pools/<addr>/")
@click.option("--budget", type=int, default=10, help="Number of agent iterations")
@click.option(
    "--objective",
    default=DEFAULT_SELECTION_METRIC,
    type=click.Choice(sorted(PRIMITIVE_REGISTRY.keys())),
    help="Scalar metric to climb",
)
@click.option("--trial", required=True, help="Trial name — used as session_id in the run store")
@click.option("--data-dir", default="data", type=click.Path(exists=True), help="Root data dir")
@click.option("--initial-x", type=int, default=10_000_000_000, help="Initial X (raw)")
@click.option("--initial-y", type=int, default=1_000_000_000, help="Initial Y (raw)")
@click.option("--window-start-ms", type=int, default=None)
@click.option("--window-end-ms", type=int, default=None)
def main(
    pool: str,
    budget: int,
    objective: str,
    trial: str,
    data_dir: str,
    initial_x: int,
    initial_y: int,
    window_start_ms: int | None,
    window_end_ms: int | None,
) -> None:
    """Run the autoresearch tournament."""
    data_dir_path = Path(data_dir)
    pool_dir = data_dir_path / "pools" / pool
    if not pool_dir.exists():
        raise click.ClickException(f"Pool dir not found: {pool_dir}")

    dataset = load_pool_dataset(pool_dir)

    # Default window: first 7 days of available data.
    if window_start_ms is None or window_end_ms is None:
        import polars as pl

        df = pl.read_parquet(dataset.parquet_path).sort("ts")
        first_ts = int(df["ts"][0])
        window_start_ms = window_start_ms or first_ts
        window_end_ms = window_end_ms or (window_start_ms + 7 * 24 * 60 * 60 * 1000)
    window = TimeWindow(start_ms=window_start_ms, end_ms=window_end_ms)

    runs_dir = data_dir_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    store = open_default_store(data_dir_path)
    ensure_agent_session(store, trial=trial, pool_address=pool, objective=objective, budget=budget)

    system_prompt = _PROMPT_PATH.read_text()
    worked_examples = {
        "precision_curve": read_strategy("precision_curve"),
        "multiday_cook_up": read_strategy("multiday_cook_up"),
    }

    llm = LLMClient()

    click.echo(f"Trial: {trial}  pool: {pool}  objective: {objective}  budget: {budget}")
    click.echo(f"Window: [{window.start_ms}, {window.end_ms}]")
    click.echo(f"DB: {data_dir_path / 'asteroid_belt.duckdb'}")

    history_payloads = list_iteration_payloads(store, trial=trial)
    history_dicts = [
        {
            "iteration": p.iteration,
            "score": p.score,
            "score_metric": p.score_metric,
            "primitives": p.primitives,
            "rebalance_count": p.rebalance_count,
            "error": p.error,
        }
        for p in history_payloads
    ]
    start_iter = max((p.iteration for p in history_payloads), default=-1) + 1
    click.echo(f"Resuming from iteration {start_iter} ({len(history_dicts)} prior experiments)")

    best_so_far = max(
        (p.score for p in history_payloads if p.error is None and p.score is not None),
        default=float("-inf"),
    )

    for i in range(start_iter, start_iter + budget):
        click.echo(f"\n=== Iteration {i} ===")
        history_text = history_summary(history_dicts)
        user_prompt = _build_user_prompt(
            objective=objective,
            data_summary_text=data_summary(dataset, window),
            history_text=history_text,
            worked_examples=worked_examples,
        )

        click.echo("Calling LLM...")
        response = llm.complete(system=system_prompt, user=user_prompt)
        code = extract_python(response)

        click.echo("Running backtest...")
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
            pool_address=pool,
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

        if result.error:
            click.echo(f"  ERROR: {result.error.splitlines()[0][:120]}")
        else:
            new_best = result.score > best_so_far
            best_so_far = max(best_so_far, result.score)
            marker = " *** new best ***" if new_best else ""
            click.echo(
                f"  score={result.score:.4f} ({objective})  "
                f"rebalances={result.rebalance_count}{marker}"
            )

    click.echo(f"\nDone. Best score: {best_so_far:.4f}  ({len(history_dicts)} total experiments)")


if __name__ == "__main__":
    main()

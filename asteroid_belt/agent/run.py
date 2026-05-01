"""Tournament loop entry point.

    uv run python -m asteroid_belt.agent.run \\
        --pool BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y \\
        --budget 20 \\
        --objective vol_capture \\
        --trial demo
"""

from __future__ import annotations

import json
from pathlib import Path

import click

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
from asteroid_belt.metrics.primitives import (
    DEFAULT_SELECTION_METRIC,
    PRIMITIVE_REGISTRY,
)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompt.txt"
_RESULTS_ROOT = Path("agent/results")


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
@click.option("--trial", required=True, help="Trial name — used for results dir")
@click.option("--data-dir", default="data", type=click.Path(exists=True), help="Root data dir")
@click.option(
    "--initial-x",
    type=int,
    default=10_000_000_000,  # 10 SOL
    help="Initial X token raw amount",
)
@click.option(
    "--initial-y",
    type=int,
    default=1_000_000_000,  # 1000 USDC
    help="Initial Y token raw amount",
)
@click.option(
    "--window-start-ms",
    type=int,
    default=None,
    help="Backtest window start (ms epoch). Defaults to first 7 days of data.",
)
@click.option(
    "--window-end-ms",
    type=int,
    default=None,
    help="Backtest window end (ms epoch). Defaults to start + 7 days.",
)
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
    pool_dir = Path(data_dir) / "pools" / pool
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

    results_dir = _RESULTS_ROOT / trial
    results_dir.mkdir(parents=True, exist_ok=True)

    system_prompt = _PROMPT_PATH.read_text()
    worked_examples = {
        "precision_curve": read_strategy("precision_curve"),
        "multiday_cook_up": read_strategy("multiday_cook_up"),
    }

    llm = LLMClient()

    click.echo(f"Trial: {trial}  pool: {pool}  objective: {objective}  budget: {budget}")
    click.echo(f"Window: [{window.start_ms}, {window.end_ms}]")
    click.echo(f"Results dir: {results_dir}")

    history = load_history(results_dir)
    start_iter = max((int(h.get("iteration", 0)) for h in history), default=-1) + 1
    click.echo(f"Resuming from iteration {start_iter} ({len(history)} prior experiments)")

    best_so_far = max(
        (h.get("score", float("-inf")) for h in history if h.get("error") is None),
        default=float("-inf"),
    )

    for i in range(start_iter, start_iter + budget):
        click.echo(f"\n=== Iteration {i} ===")
        history_text = history_summary(history)
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
        path = save_experiment(result, results_dir=results_dir)
        history.append(json.loads(path.read_text()))

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

    click.echo(f"\nDone. Best score: {best_so_far:.4f}  ({len(history)} total experiments)")


if __name__ == "__main__":
    main()

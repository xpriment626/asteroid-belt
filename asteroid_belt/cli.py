"""asteroid-belt CLI (`belt`).

Commands (v1, post-Phase-3):
  belt ingest    --pool <addr> --start <iso> --end <iso>  [--data-dir DIR]

Phase 5 will add:
  belt run       --config <path.yaml>
  belt session   new / close
  belt run notes
  belt serve
"""

from __future__ import annotations

from pathlib import Path

import click

DEFAULT_DATA_DIR = Path("data")


@click.group()
def cli() -> None:
    """asteroid-belt: DLMM strategy research desk."""


@cli.command()
@click.option("--pool", required=True, help="Meteora pool address (base58)")
@click.option("--start", required=True, help="ISO-8601 start (e.g. 2024-05-01T00:00:00Z)")
@click.option("--end", required=True, help="ISO-8601 end")
@click.option(
    "--data-dir",
    default=str(DEFAULT_DATA_DIR),
    type=click.Path(),
    help="Root data directory (default: ./data)",
)
def ingest(pool: str, start: str, end: str, data_dir: str) -> None:
    """Ingest 1m OHLCV bars from Meteora into data/pools/<pool>/."""
    from asteroid_belt.data.ingest import ingest_meteora_ohlcv

    out_dir = Path(data_dir) / "pools"
    out_dir.mkdir(parents=True, exist_ok=True)
    ingest_meteora_ohlcv(pool=pool, start=start, end=end, out_dir=out_dir)
    click.echo(f"ingested {pool} for [{start}, {end}] -> {out_dir / pool}")


@cli.command(name="agent-regen")
@click.option("--trial", required=True)
@click.option("--pool", required=True)
@click.option("--data-dir", default="data", type=click.Path(exists=True))
@click.option("--initial-x", type=int, default=10_000_000_000)
@click.option("--initial-y", type=int, default=1_000_000_000)
@click.option("--window-start-ms", type=int, default=None)
@click.option("--window-end-ms", type=int, default=None)
@click.pass_context
def agent_regen(
    ctx: click.Context,
    trial: str,
    pool: str,
    data_dir: str,
    initial_x: int,
    initial_y: int,
    window_start_ms: int | None,
    window_end_ms: int | None,
) -> None:
    """Regenerate trajectory parquets for an existing trial."""
    from asteroid_belt.agent.regen import main as regen_main

    ctx.invoke(
        regen_main,
        trial=trial,
        pool=pool,
        data_dir=data_dir,
        initial_x=initial_x,
        initial_y=initial_y,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
    )


@cli.command()
@click.option("--pool", required=True)
@click.option("--budget", type=int, default=10)
@click.option("--objective", default="vol_capture")
@click.option("--trial", required=True)
@click.option("--data-dir", default="data", type=click.Path(exists=True))
@click.option("--initial-x", type=int, default=10_000_000_000)
@click.option("--initial-y", type=int, default=1_000_000_000)
@click.option("--window-start-ms", type=int, default=None)
@click.option("--window-end-ms", type=int, default=None)
@click.pass_context
def agent(
    ctx: click.Context,
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
    """Run the autoresearch tournament loop."""
    from asteroid_belt.agent.run import main as agent_main

    ctx.invoke(
        agent_main,
        pool=pool,
        budget=budget,
        objective=objective,
        trial=trial,
        data_dir=data_dir,
        initial_x=initial_x,
        initial_y=initial_y,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
    )


if __name__ == "__main__":
    cli()

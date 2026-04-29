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


if __name__ == "__main__":
    cli()

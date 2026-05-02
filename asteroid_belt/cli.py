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


@cli.command(name="agent-migrate")
@click.option("--trial", required=True)
@click.option("--pool", required=True)
@click.option("--objective", default="vol_capture")
@click.option("--data-dir", default="data", type=click.Path(exists=True))
@click.option(
    "--flat-results-root",
    default="agent/results",
    type=click.Path(),
    help=(
        "Path to legacy flat-file output (pre-DB migration). One-shot — once "
        "migrated, future iterations write directly to the run store."
    ),
)
@click.option("--initial-x", type=int, default=10_000_000_000)
@click.option("--initial-y", type=int, default=1_000_000_000)
@click.option("--window-start-ms", type=int, default=None)
@click.option("--window-end-ms", type=int, default=None)
@click.pass_context
def agent_migrate(
    ctx: click.Context,
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
    """One-shot: migrate a flat-file trial into the DuckDB store."""
    from asteroid_belt.agent.migrate import main as migrate_main

    ctx.invoke(
        migrate_main,
        trial=trial,
        pool=pool,
        objective=objective,
        data_dir=data_dir,
        flat_results_root=flat_results_root,
        initial_x=initial_x,
        initial_y=initial_y,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
    )


@cli.command()
@click.option("--api-port", type=int, default=8000, help="FastAPI backend port")
@click.option("--web-port", type=int, default=5173, help="SvelteKit dev server port")
@click.option("--api-only", is_flag=True, default=False, help="Skip the frontend")
def dev(api_port: int, web_port: int, api_only: bool) -> None:
    """Start the FastAPI backend + SvelteKit dev server side by side.

    Ctrl-C cleanly tears down both. If either process exits unexpectedly,
    the other is also stopped so you don't end up with orphans.
    """
    import shutil
    import signal
    import subprocess
    import sys
    import time

    web_dir = Path("web")
    if not api_only:
        if not web_dir.exists():
            raise click.ClickException(f"Frontend directory not found: {web_dir}")
        if not (web_dir / "node_modules").exists():
            raise click.ClickException(
                "web/node_modules is missing — run `cd web && pnpm install` first."
            )
        if shutil.which("pnpm") is None:
            raise click.ClickException("pnpm not found on PATH. Install via `brew install pnpm`.")

    procs: list[subprocess.Popen[bytes]] = []

    click.echo(f"[api] starting on http://127.0.0.1:{api_port}")
    procs.append(
        subprocess.Popen(
            [
                "uvicorn",
                "asteroid_belt.server.app:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ]
        )
    )

    if not api_only:
        click.echo(f"[web] starting on http://127.0.0.1:{web_port}")
        procs.append(
            subprocess.Popen(
                ["pnpm", "dev", "--port", str(web_port)],
                cwd=str(web_dir),
            )
        )

    def shutdown(*_: object) -> None:
        click.echo("\n[belt dev] shutting down…")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        deadline = time.time() + 5
        for p in procs:
            remaining = max(0.1, deadline - time.time())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    click.echo(
                        f"[belt dev] subprocess exited with code {p.returncode}; tearing down."
                    )
                    shutdown()
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()


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

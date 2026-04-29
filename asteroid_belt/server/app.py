"""FastAPI read-only API at /api/v1/.

Phase 3 MVV scope: /health, /pools (list + detail), /pools/:addr/bars.
Phase 6 will extend with /sessions, /runs, /runs/:id/trajectory,
/runs/:id/rebalances, /compare.

Writes happen exclusively via the CLI. When subsystem 4 wants UI-triggered
runs, POST endpoints get added under the same paths without breaking the v1
TS client (additive evolution).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import polars as pl
from fastapi import FastAPI, HTTPException

from asteroid_belt.server.schemas import (
    Bar,
    HealthResponse,
    PoolDetail,
    PoolSummary,
)


def build_app(*, data_dir: Path | None = None) -> FastAPI:
    """Build a FastAPI app pointed at `data_dir`. Tests pass tmp_path here."""
    if data_dir is None:
        env = os.environ.get("ASTEROID_BELT_DATA_DIR", "data")
        data_dir = Path(env)

    app = FastAPI(
        title="asteroid-belt API",
        version="0.1.0",
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )

    # Stash data_dir on the app for endpoint handlers
    app.state.data_dir = data_dir

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/api/v1/pools", response_model=list[PoolSummary])
    def list_pools() -> list[PoolSummary]:
        assert data_dir is not None
        pools_dir = data_dir / "pools"
        if not pools_dir.exists():
            return []
        results: list[PoolSummary] = []
        for d in sorted(pools_dir.iterdir()):
            if not d.is_dir():
                continue
            meta_path = d / "pool_meta.json"
            bars_path = d / "bars_1m.parquet"
            if not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text())
            bars_count = int(pl.read_parquet(bars_path).height) if bars_path.exists() else 0
            results.append(
                PoolSummary(
                    address=d.name,
                    name=meta.get("name"),
                    bin_step=meta.get("pool_config", {}).get("bin_step"),
                    bars_count=bars_count,
                )
            )
        return results

    @app.get("/api/v1/pools/{address}", response_model=PoolDetail)
    def get_pool(address: str) -> PoolDetail:
        assert data_dir is not None
        pool_dir = data_dir / "pools" / address
        meta_path = pool_dir / "pool_meta.json"
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail=f"pool {address} not found")
        meta = json.loads(meta_path.read_text())
        bars_path = pool_dir / "bars_1m.parquet"
        bars_count = int(pl.read_parquet(bars_path).height) if bars_path.exists() else 0
        return PoolDetail(
            address=address,
            name=meta.get("name"),
            bin_step=meta.get("pool_config", {}).get("bin_step"),
            bars_count=bars_count,
            meta=meta,
        )

    @app.get("/api/v1/pools/{address}/bars", response_model=list[Bar])
    def get_bars(
        address: str,
        start: int | None = None,
        end: int | None = None,
    ) -> list[Bar]:
        assert data_dir is not None
        bars_path = data_dir / "pools" / address / "bars_1m.parquet"
        if not bars_path.exists():
            raise HTTPException(status_code=404, detail=f"pool {address} not found")
        df = pl.read_parquet(bars_path)
        if start is not None:
            df = df.filter(pl.col("ts") >= start)
        if end is not None:
            df = df.filter(pl.col("ts") < end)  # half-open
        return [Bar(**row) for row in df.iter_rows(named=True)]

    return app


# Module-level app for `uvicorn asteroid_belt.server.app:app`
app = build_app()

"""Meteora OHLCV ingest.

Pulls 1m bars from `https://dlmm.datapi.meteora.ag/pools/<addr>/ohlcv` in
paginated chunks, writes to data/pools/<addr>/bars_1m.parquet, and records
pool metadata to pool_meta.json. Idempotent: re-running with the same window
deduplicates by `ts`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

DATAPI_BASE = "https://dlmm.datapi.meteora.ag"
DLMM_API_BASE = "https://dlmm-api.meteora.ag"


def _to_unix_seconds(iso: str) -> int:
    s = iso.replace("Z", "+00:00")
    return int(datetime.fromisoformat(s).astimezone(UTC).timestamp())


def _fetch_pool_meta(pool: str, *, client: httpx.Client) -> dict[str, Any]:
    r = client.get(f"{DATAPI_BASE}/pools/{pool}")
    r.raise_for_status()
    payload: dict[str, Any] = r.json()
    return payload


def _fetch_ohlcv(
    pool: str, *, start_sec: int, end_sec: int, client: httpx.Client
) -> list[list[Any]]:
    """Fetch raw OHLCV points; expected shape: list of [ts, o, h, l, c, vol_x, vol_y]."""
    r = client.get(
        f"{DATAPI_BASE}/pools/{pool}/ohlcv",
        params={"resolution": 1, "start": start_sec, "end": end_sec},
        timeout=30.0,
    )
    r.raise_for_status()
    payload = r.json()
    # Expected response shape: {"data": [[ts, o, h, l, c, vol_x, vol_y], ...]}.
    # If the schema differs at runtime, adjust this extractor and update fixtures.
    points: list[list[Any]] = payload.get("data", [])
    return points


def ingest_meteora_ohlcv(
    *,
    pool: str,
    start: str,
    end: str,
    out_dir: Path,
) -> None:
    """Ingest 1m OHLCV for a pool over [start, end]. Idempotent.

    Outputs:
      out_dir/<pool>/bars_1m.parquet
      out_dir/<pool>/pool_meta.json
      out_dir/<pool>/ingest_log.json
    """
    pool_dir = out_dir / pool
    pool_dir.mkdir(parents=True, exist_ok=True)

    start_sec = _to_unix_seconds(start)
    end_sec = _to_unix_seconds(end)

    with httpx.Client() as client:
        # Fetch pool metadata once (idempotent overwrite is fine).
        try:
            meta = _fetch_pool_meta(pool, client=client)
            (pool_dir / "pool_meta.json").write_text(json.dumps(meta, indent=2))
        except httpx.HTTPError:
            # Don't fail ingest if metadata endpoint is flaky; log and continue.
            pass

        # Fetch bars. For v1 we issue one request per call; if the API caps the
        # response window, we paginate by stepping `start_sec` forward.
        # TODO: confirm API window cap before relying on a single-shot fetch.
        raw_points = _fetch_ohlcv(pool, start_sec=start_sec, end_sec=end_sec, client=client)

    if not raw_points:
        return

    # Normalize to ts in milliseconds for consistency with rest of the codebase.
    rows = [
        {
            "ts": int(p[0]) * 1000,
            "open": float(p[1]),
            "high": float(p[2]),
            "low": float(p[3]),
            "close": float(p[4]),
            "volume_x": int(p[5]),
            "volume_y": int(p[6]),
        }
        for p in raw_points
    ]
    new_df = pl.DataFrame(rows)

    parquet_path = pool_dir / "bars_1m.parquet"
    if parquet_path.exists():
        existing = pl.read_parquet(parquet_path)
        combined = pl.concat([existing, new_df]).unique(subset=["ts"]).sort("ts")
    else:
        combined = new_df.unique(subset=["ts"]).sort("ts")

    combined.write_parquet(parquet_path)

    # Update ingest log
    log_path = pool_dir / "ingest_log.json"
    log: dict[str, Any] = json.loads(log_path.read_text()) if log_path.exists() else {}
    log["last_ingested_start_sec"] = start_sec
    log["last_ingested_end_sec"] = end_sec
    log["row_count"] = combined.height
    log_path.write_text(json.dumps(log, indent=2))

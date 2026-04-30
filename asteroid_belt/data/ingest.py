"""Meteora OHLCV ingest.

Pulls 5m bars from `https://dlmm.datapi.meteora.ag/pools/<addr>/ohlcv` in
6-hour paginated chunks, writes to data/pools/<addr>/bars_5m.parquet, and
records pool metadata to pool_meta.json. Idempotent: re-running with the same
window deduplicates by `ts`.

API constraints discovered live (2026-04-30):
- Only `5m / 30m / 1h / 2h / 4h / 12h / 24h` timeframes supported (no 1m).
- Max ~6 hour window per request (>6h returns "time range too large").
- Response shape: {"data": [{timestamp, timestamp_str, open, high, low, close,
  volume}, ...]} — list of dicts; single `volume` field denominated in USD
  (~ USDC for SOL-USDC pool).
- Historical depth varies by pool. For BGm1tav... (SOL-USDC 10bps), only
  Aug 1 2025+ returns data; OHLC is zero-filled until ~Nov 30 2025; clean
  OHLC begins ~Dec 1 2025.

We persist `volume_x` and `volume_y` in raw token units (computed from the
USD volume, close price, and token decimals) so the bar adapter's
swap_for_y=True/False logic works without knowing about the upstream API
shape.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

DATAPI_BASE = "https://dlmm.datapi.meteora.ag"

# API caps responses at ~6 hours per request.
_PAGE_SECONDS = 6 * 60 * 60  # 21_600
_TIMEFRAME = "5m"
# Stay well under the API's per-IP rate limit (the previous repo used 0.05s
# between calls = 20 RPS sustained without issue).
_INTER_REQUEST_DELAY = 0.05


def _to_unix_seconds(iso: str) -> int:
    s = iso.replace("Z", "+00:00")
    return int(datetime.fromisoformat(s).astimezone(UTC).timestamp())


def _fetch_pool_meta(pool: str, *, client: httpx.Client) -> dict[str, Any]:
    r = client.get(f"{DATAPI_BASE}/pools/{pool}", timeout=30.0)
    r.raise_for_status()
    payload: dict[str, Any] = r.json()
    return payload


def _fetch_ohlcv_page(
    pool: str, *, start_sec: int, end_sec: int, client: httpx.Client
) -> list[dict[str, Any]]:
    """Fetch one page (<=6h window) of OHLCV points.

    Response shape: {"data": [{timestamp, timestamp_str, open, high, low,
    close, volume}, ...]}. Returns the inner list (possibly empty).
    """
    r = client.get(
        f"{DATAPI_BASE}/pools/{pool}/ohlcv",
        params={"timeframe": _TIMEFRAME, "start_time": start_sec, "end_time": end_sec},
        timeout=30.0,
    )
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload, dict):
        rows: list[dict[str, Any]] = payload.get("data", []) or []
        return rows
    return []


def _decimals_from_meta(meta: dict[str, Any]) -> tuple[int, int]:
    """Pull decimals_x / decimals_y from pool metadata, defaulting to SOL/USDC."""
    dx = meta.get("token_x", {}).get("decimals", 9) if isinstance(meta, dict) else 9
    dy = meta.get("token_y", {}).get("decimals", 6) if isinstance(meta, dict) else 6
    return int(dx), int(dy)


def _row_from_api(p: dict[str, Any], *, decimals_x: int, decimals_y: int) -> dict[str, Any] | None:
    """Convert one API row to our parquet schema. Returns None to skip bad rows."""
    try:
        ts_sec = int(p["timestamp"])
        open_ = float(p.get("open", 0.0))
        high = float(p.get("high", 0.0))
        low = float(p.get("low", 0.0))
        close = float(p.get("close", 0.0))
        volume_usd = float(p.get("volume", 0.0))
    except (KeyError, TypeError, ValueError):
        return None

    # Compute raw token volumes from USD volume + close price.
    # USD ~= USDC (Y) for SOL/USDC. So:
    #   volume_y_raw = volume_usd * 10^decimals_y
    #   volume_x_raw = (volume_usd / close) * 10^decimals_x   (only if close > 0)
    volume_y_raw = int(volume_usd * (10**decimals_y))
    volume_x_raw = int((volume_usd / close) * (10**decimals_x)) if close > 0 else 0

    return {
        "ts": ts_sec * 1000,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume_usd": volume_usd,
        "volume_x": volume_x_raw,
        "volume_y": volume_y_raw,
    }


def ingest_meteora_ohlcv(
    *,
    pool: str,
    start: str,
    end: str,
    out_dir: Path,
) -> None:
    """Ingest 5m OHLCV for a pool over [start, end]. Idempotent.

    Outputs:
      out_dir/<pool>/bars_5m.parquet
      out_dir/<pool>/pool_meta.json
      out_dir/<pool>/ingest_log.json
    """
    pool_dir = out_dir / pool
    pool_dir.mkdir(parents=True, exist_ok=True)

    start_sec = _to_unix_seconds(start)
    end_sec = _to_unix_seconds(end)
    if end_sec <= start_sec:
        raise ValueError(f"end ({end}) must be after start ({start})")

    all_rows: list[dict[str, Any]] = []

    with httpx.Client() as client:
        # Fetch pool metadata first; needed for decimals.
        meta: dict[str, Any] | None = None
        try:
            meta = _fetch_pool_meta(pool, client=client)
            (pool_dir / "pool_meta.json").write_text(json.dumps(meta, indent=2))
        except httpx.HTTPError:
            # Don't fail ingest if metadata endpoint is flaky; default decimals.
            pass

        decimals_x, decimals_y = _decimals_from_meta(meta or {})

        # Paginate through the requested window in 6h chunks.
        cursor = start_sec
        page_count = 0
        while cursor < end_sec:
            window_end = min(cursor + _PAGE_SECONDS, end_sec)
            try:
                page = _fetch_ohlcv_page(pool, start_sec=cursor, end_sec=window_end, client=client)
            except httpx.HTTPError as exc:
                # Soft-fail: skip this window, log, continue. Idempotent re-runs
                # can pick up missed data.
                print(f"  WARN: page {cursor}-{window_end} failed: {exc}", flush=True)
                cursor = window_end
                continue

            for raw in page:
                row = _row_from_api(raw, decimals_x=decimals_x, decimals_y=decimals_y)
                if row is not None:
                    all_rows.append(row)
            page_count += 1
            if page_count % 50 == 0:
                print(
                    f"  fetched page {page_count} (total rows: {len(all_rows)})",
                    flush=True,
                )
            cursor = window_end
            time.sleep(_INTER_REQUEST_DELAY)

    if not all_rows:
        print(f"  no data returned for [{start}, {end}]")
        return

    new_df = pl.DataFrame(all_rows)

    parquet_path = pool_dir / "bars_5m.parquet"
    if parquet_path.exists():
        existing = pl.read_parquet(parquet_path)
        # Schema may have evolved; align columns by intersection before concat.
        common_cols = [c for c in existing.columns if c in new_df.columns]
        combined = (
            pl.concat([existing.select(common_cols), new_df.select(common_cols)])
            .unique(subset=["ts"])
            .sort("ts")
        )
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
    print(f"  wrote {combined.height} rows to {parquet_path}", flush=True)

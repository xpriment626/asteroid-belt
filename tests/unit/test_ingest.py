"""Ingest tests.

Mocks the real Meteora datapi response shape (list of dicts under `data`,
single USD `volume` field) and verifies we paginate, dedupe, and persist
correctly.
"""

import json
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx

from asteroid_belt.data.ingest import ingest_meteora_ohlcv

POOL = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"


def _row(ts_sec: int, close: float = 87.55, volume_usd: float = 100_000.0) -> dict:
    """Build one OHLCV row in the API's response shape."""
    return {
        "timestamp": ts_sec,
        "timestamp_str": "ignored",
        "open": close - 0.05,
        "high": close + 0.06,
        "low": close - 0.06,
        "close": close,
        "volume": volume_usd,
    }


def _meta() -> dict:
    return {
        "address": POOL,
        "name": "SOL-USDC",
        "token_x": {"address": "So11..", "decimals": 9, "symbol": "SOL"},
        "token_y": {"address": "EPjF..", "decimals": 6, "symbol": "USDC"},
        "pool_config": {"bin_step": 10, "base_fee_pct": 0.1},
    }


@respx.mock
def test_ingest_writes_parquet_with_5m_filename(tmp_path: Path) -> None:
    # 6-hour window means a single page covers the whole [start, end].
    start_sec = 1_754_006_400  # 2025-08-01T00:00:00Z
    end_sec = start_sec + 600  # 10 minutes - well under one 6h page
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}/ohlcv").mock(
        return_value=httpx.Response(
            200,
            json={
                "start_time": start_sec,
                "end_time": end_sec,
                "timeframe": "5m",
                "data": [_row(start_sec), _row(start_sec + 300)],
            },
        )
    )
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}").mock(
        return_value=httpx.Response(200, json=_meta())
    )

    ingest_meteora_ohlcv(
        pool=POOL,
        start="2025-08-01T00:00:00Z",
        end="2025-08-01T00:10:00Z",
        out_dir=tmp_path,
    )

    parquet_path = tmp_path / POOL / "bars_5m.parquet"
    assert parquet_path.exists()
    df = pl.read_parquet(parquet_path)
    assert df.height == 2
    assert set(
        ["ts", "open", "high", "low", "close", "volume_usd", "volume_x", "volume_y"]
    ).issubset(df.columns)
    # ts is in ms not sec
    assert df["ts"][0] == start_sec * 1000


@respx.mock
def test_ingest_paginates_across_6h_windows(tmp_path: Path) -> None:
    """A 13-hour window should result in 3 pages (6h + 6h + 1h)."""
    start_sec = 1_764_547_200  # 2025-12-01T00:00:00Z
    end_sec = start_sec + 13 * 3600

    page_calls: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        # Pull the start_time / end_time from the URL params.
        s = int(request.url.params.get("start_time", "0"))
        e = int(request.url.params.get("end_time", "0"))
        page_calls.append((s, e))
        # Return 1 row per page (timestamps don't need to match exactly for the test).
        return httpx.Response(
            200,
            json={"data": [_row(s)]},
        )

    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}/ohlcv").mock(side_effect=handler)
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}").mock(
        return_value=httpx.Response(200, json=_meta())
    )

    ingest_meteora_ohlcv(
        pool=POOL,
        start="2025-12-01T00:00:00Z",
        end="2025-12-01T13:00:00Z",
        out_dir=tmp_path,
    )

    # Three pages: 0-6h, 6h-12h, 12h-13h (clamped to end_sec)
    assert len(page_calls) == 3
    assert page_calls[0] == (start_sec, start_sec + 6 * 3600)
    assert page_calls[1] == (start_sec + 6 * 3600, start_sec + 12 * 3600)
    assert page_calls[2] == (start_sec + 12 * 3600, end_sec)


@respx.mock
def test_ingest_idempotent(tmp_path: Path) -> None:
    start_sec = 1_754_006_400
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}/ohlcv").mock(
        return_value=httpx.Response(
            200,
            json={"data": [_row(start_sec), _row(start_sec + 300)]},
        )
    )
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}").mock(
        return_value=httpx.Response(200, json=_meta())
    )

    ingest_meteora_ohlcv(
        pool=POOL,
        start="2025-08-01T00:00:00Z",
        end="2025-08-01T00:10:00Z",
        out_dir=tmp_path,
    )
    ingest_meteora_ohlcv(
        pool=POOL,
        start="2025-08-01T00:00:00Z",
        end="2025-08-01T00:10:00Z",
        out_dir=tmp_path,
    )
    df = pl.read_parquet(tmp_path / POOL / "bars_5m.parquet")
    assert df.height == 2  # not 4 — deduped on `ts`


@respx.mock
def test_ingest_writes_pool_meta(tmp_path: Path) -> None:
    start_sec = 1_754_006_400
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}/ohlcv").mock(
        return_value=httpx.Response(200, json={"data": [_row(start_sec)]})
    )
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}").mock(
        return_value=httpx.Response(200, json=_meta())
    )

    ingest_meteora_ohlcv(
        pool=POOL,
        start="2025-08-01T00:00:00Z",
        end="2025-08-01T00:10:00Z",
        out_dir=tmp_path,
    )
    meta = json.loads((tmp_path / POOL / "pool_meta.json").read_text())
    assert meta["address"] == POOL
    assert meta["pool_config"]["bin_step"] == 10


@respx.mock
def test_volume_decomposition(tmp_path: Path) -> None:
    """volume_x / volume_y are derived from USD volume, close price, decimals."""
    start_sec = 1_764_547_200
    # 1000 USDC volume at price 100 USDC/SOL with SOL=9d, USDC=6d:
    #   volume_y_raw = 1000 * 1e6 = 1_000_000_000  (1000 USDC)
    #   volume_x_raw = (1000 / 100) * 1e9 = 10_000_000_000  (10 SOL)
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}/ohlcv").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "timestamp": start_sec,
                        "open": 100.0,
                        "high": 100.0,
                        "low": 100.0,
                        "close": 100.0,
                        "volume": 1000.0,
                    }
                ],
            },
        )
    )
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{POOL}").mock(
        return_value=httpx.Response(200, json=_meta())
    )

    ingest_meteora_ohlcv(
        pool=POOL,
        start="2025-12-01T00:00:00Z",
        end="2025-12-01T00:05:00Z",
        out_dir=tmp_path,
    )
    df = pl.read_parquet(tmp_path / POOL / "bars_5m.parquet")
    assert df.height == 1
    row = df.row(0, named=True)
    assert row["volume_usd"] == pytest.approx(1000.0)
    assert row["volume_y"] == 1_000_000_000  # 1000 USDC in raw units
    assert row["volume_x"] == 10_000_000_000  # 10 SOL in raw units

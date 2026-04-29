import json
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx

from asteroid_belt.data.ingest import ingest_meteora_ohlcv


@pytest.fixture
def fake_meteora_response() -> dict:
    return {
        "data": [
            # Each point: ts (sec), open, high, low, close, volume_x, volume_y
            [1_700_000_000, 87.50, 87.56, 87.49, 87.55, 1_000_000, 87_550_000],
            [1_700_000_060, 87.55, 87.61, 87.54, 87.60, 1_500_000, 131_400_000],
        ]
    }


@respx.mock
def test_ingest_writes_parquet(tmp_path: Path, fake_meteora_response: dict) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}/ohlcv").mock(
        return_value=httpx.Response(200, json=fake_meteora_response)
    )
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}").mock(
        return_value=httpx.Response(200, json={"address": pool, "name": "SOL-USDC"})
    )

    ingest_meteora_ohlcv(
        pool=pool,
        start="2023-11-14T00:00:00Z",
        end="2023-11-14T00:02:00Z",
        out_dir=tmp_path,
    )

    parquet_path = tmp_path / pool / "bars_1m.parquet"
    assert parquet_path.exists()
    df = pl.read_parquet(parquet_path)
    assert df.height == 2
    assert "ts" in df.columns
    assert "open" in df.columns


@respx.mock
def test_ingest_idempotent(tmp_path: Path, fake_meteora_response: dict) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}/ohlcv").mock(
        return_value=httpx.Response(200, json=fake_meteora_response)
    )
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}").mock(
        return_value=httpx.Response(200, json={"address": pool, "name": "SOL-USDC"})
    )

    ingest_meteora_ohlcv(
        pool=pool,
        start="2023-11-14T00:00:00Z",
        end="2023-11-14T00:02:00Z",
        out_dir=tmp_path,
    )
    # Second call: same window, should not duplicate rows
    ingest_meteora_ohlcv(
        pool=pool,
        start="2023-11-14T00:00:00Z",
        end="2023-11-14T00:02:00Z",
        out_dir=tmp_path,
    )
    df = pl.read_parquet(tmp_path / pool / "bars_1m.parquet")
    assert df.height == 2  # not 4


@respx.mock
def test_ingest_writes_pool_meta(tmp_path: Path, fake_meteora_response: dict) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}/ohlcv").mock(
        return_value=httpx.Response(200, json=fake_meteora_response)
    )
    # Mock the pool-detail endpoint with full metadata
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}").mock(
        return_value=httpx.Response(
            200,
            json={
                "address": pool,
                "name": "SOL-USDC",
                "token_x": {"address": "x", "decimals": 9},
                "token_y": {"address": "y", "decimals": 6},
                "pool_config": {"bin_step": 10, "base_fee_pct": 0.1},
            },
        ),
    )

    ingest_meteora_ohlcv(
        pool=pool,
        start="2023-11-14T00:00:00Z",
        end="2023-11-14T00:02:00Z",
        out_dir=tmp_path,
    )
    meta = json.loads((tmp_path / pool / "pool_meta.json").read_text())
    assert meta["address"] == pool
    assert meta["pool_config"]["bin_step"] == 10

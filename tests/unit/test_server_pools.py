import json
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from asteroid_belt.server.app import build_app


@pytest.fixture
def staged_data(tmp_path: Path) -> Path:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    pool_dir = tmp_path / "pools" / pool
    pool_dir.mkdir(parents=True)
    (pool_dir / "pool_meta.json").write_text(
        json.dumps(
            {
                "address": pool,
                "name": "SOL-USDC",
                "pool_config": {"bin_step": 10},
                "token_x": {"decimals": 9, "symbol": "SOL"},
                "token_y": {"decimals": 6, "symbol": "USDC"},
            }
        )
    )
    pl.DataFrame(
        {
            "ts": [1, 2],
            "open": [1.0, 1.0],
            "high": [1.0, 1.0],
            "low": [1.0, 1.0],
            "close": [1.0, 1.0],
            "volume_x": [0, 0],
            "volume_y": [0, 0],
        }
    ).write_parquet(pool_dir / "bars_5m.parquet")
    return tmp_path


def test_list_pools(staged_data: Path) -> None:
    client = TestClient(build_app(data_dir=staged_data))
    r = client.get("/api/v1/pools")
    assert r.status_code == 200
    pools = r.json()
    assert len(pools) == 1
    assert pools[0]["address"] == "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"


def test_get_pool_detail(staged_data: Path) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    client = TestClient(build_app(data_dir=staged_data))
    r = client.get(f"/api/v1/pools/{pool}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["address"] == pool
    assert detail["bars_count"] == 2


def test_get_pool_404(staged_data: Path) -> None:
    client = TestClient(build_app(data_dir=staged_data))
    r = client.get("/api/v1/pools/nonexistent")
    assert r.status_code == 404

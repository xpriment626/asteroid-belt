import json
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from asteroid_belt.server.app import build_app


@pytest.fixture
def staged_bars(tmp_path: Path) -> Path:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    pool_dir = tmp_path / "pools" / pool
    pool_dir.mkdir(parents=True)
    (pool_dir / "pool_meta.json").write_text(json.dumps({"address": pool, "name": "SOL-USDC"}))
    # 5 minutes of 1m bars
    pl.DataFrame(
        {
            "ts": [1_700_000_000_000 + i * 60_000 for i in range(5)],
            "open": [87.0, 87.1, 87.2, 87.3, 87.4],
            "high": [87.2, 87.3, 87.4, 87.5, 87.6],
            "low": [86.8, 86.9, 87.0, 87.1, 87.2],
            "close": [87.1, 87.2, 87.3, 87.4, 87.5],
            "volume_x": [1000, 1100, 1200, 1300, 1400],
            "volume_y": [87100, 87200, 87300, 87400, 87500],
        }
    ).write_parquet(pool_dir / "bars_1m.parquet")
    return tmp_path


def test_get_bars_full_range(staged_bars: Path) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    client = TestClient(build_app(data_dir=staged_bars))
    r = client.get(f"/api/v1/pools/{pool}/bars")
    assert r.status_code == 200
    bars = r.json()
    assert len(bars) == 5
    assert bars[0]["close"] == 87.1


def test_get_bars_with_start_end_filter(staged_bars: Path) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    client = TestClient(build_app(data_dir=staged_bars))
    start = 1_700_000_000_000 + 60_000  # second bar
    end = 1_700_000_000_000 + 4 * 60_000  # exclude last
    r = client.get(f"/api/v1/pools/{pool}/bars", params={"start": start, "end": end})
    assert r.status_code == 200
    bars = r.json()
    assert len(bars) == 3  # bars 1, 2, 3 (half-open [start, end))


def test_get_bars_404_when_pool_missing(staged_bars: Path) -> None:
    client = TestClient(build_app(data_dir=staged_bars))
    r = client.get("/api/v1/pools/nonexistent/bars")
    assert r.status_code == 404

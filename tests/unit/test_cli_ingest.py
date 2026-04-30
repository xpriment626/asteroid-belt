from pathlib import Path

import httpx
import respx
from click.testing import CliRunner

from asteroid_belt.cli import cli


@respx.mock
def test_ingest_invokes_meteora(tmp_path: Path) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}/ohlcv").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "timestamp": 1_700_000_000,
                        "open": 87.5,
                        "high": 87.6,
                        "low": 87.4,
                        "close": 87.55,
                        "volume": 1000.0,
                    }
                ]
            },
        )
    )
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}").mock(
        return_value=httpx.Response(200, json={"address": pool})
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ingest",
            "--pool",
            pool,
            "--start",
            "2023-11-14T00:00:00Z",
            "--end",
            "2023-11-14T00:01:00Z",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "pools" / pool / "bars_5m.parquet").exists()

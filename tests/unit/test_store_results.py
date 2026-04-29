import json
from pathlib import Path

import polars as pl

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord
from asteroid_belt.store.results import (
    read_rebalances,
    read_trajectory,
    write_result,
)


def _result(run_id: str = "test_run") -> BacktestResult:
    df = pl.DataFrame(
        {
            "ts": [0, 1],
            "price": [1.0, 1.1],
            "active_bin": [0, 1],
            "position_value_usd": [100.0, 110.0],
            "hodl_value_usd": [100.0, 100.0],
            "fees_x_cumulative": [0, 100],
            "fees_y_cumulative": [0, 200],
            "il_cumulative": [0.0, 10.0],
            "in_range": [True, True],
            "capital_idle_usd": [0.0, 0.0],
        }
    )
    return BacktestResult(
        run_id=run_id,
        config_hash="h",
        schema_version="1.0",
        started_at=0,
        ended_at=1,
        status="ok",
        trajectory=df,
        rebalances=[
            RebalanceRecord(
                ts=500,
                trigger="drift",
                old_lower_bin=-30,
                old_upper_bin=30,
                new_lower_bin=-20,
                new_upper_bin=40,
                gas_lamports=10_000,
                composition_fee_x=0,
                composition_fee_y=5_000,
                fees_claimed_x=0,
                fees_claimed_y=2_000,
            ),
        ],
        primitives={"net_pnl": 10.0},
        score=10.0,
        score_metric="net_pnl",
    )


def test_write_then_read_trajectory(tmp_path: Path) -> None:
    r = _result()
    write_result(result=r, runs_dir=tmp_path)
    df = read_trajectory(run_id="test_run", runs_dir=tmp_path)
    assert df.height == 2


def test_write_then_read_rebalances(tmp_path: Path) -> None:
    r = _result()
    write_result(result=r, runs_dir=tmp_path)
    rebs = read_rebalances(run_id="test_run", runs_dir=tmp_path)
    assert len(rebs) == 1
    assert rebs[0].trigger == "drift"


def test_manifest_written(tmp_path: Path) -> None:
    r = _result()
    write_result(result=r, runs_dir=tmp_path)
    manifest_path = tmp_path / "test_run" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["run_id"] == "test_run"
    assert manifest["primitives"]["net_pnl"] == 10.0

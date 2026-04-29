import polars as pl

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord


def _empty_trajectory() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": pl.Series([], dtype=pl.Int64),
            "price": pl.Series([], dtype=pl.Float64),
            "active_bin": pl.Series([], dtype=pl.Int32),
            "position_value_usd": pl.Series([], dtype=pl.Float64),
            "hodl_value_usd": pl.Series([], dtype=pl.Float64),
            "fees_x_cumulative": pl.Series([], dtype=pl.Int64),
            "fees_y_cumulative": pl.Series([], dtype=pl.Int64),
            "il_cumulative": pl.Series([], dtype=pl.Float64),
            "in_range": pl.Series([], dtype=pl.Boolean),
            "capital_idle_usd": pl.Series([], dtype=pl.Float64),
        }
    )


def test_backtest_result_minimal() -> None:
    r = BacktestResult(
        run_id="20260429T000000_abc123",
        config_hash="abc123",
        schema_version="1.0",
        started_at=1_700_000_000_000,
        ended_at=1_700_000_001_000,
        status="ok",
        trajectory=_empty_trajectory(),
        rebalances=[],
        primitives={"net_pnl": 1.5},
        score=1.5,
        score_metric="net_pnl",
    )
    assert r.status == "ok"
    assert r.score == 1.5


def test_rebalance_record_basic() -> None:
    rec = RebalanceRecord(
        ts=1_700_000_000_000,
        trigger="active_bin_drift",
        old_lower_bin=-30,
        old_upper_bin=30,
        new_lower_bin=-20,
        new_upper_bin=40,
        gas_lamports=5_000_000,
        composition_fee_x=0,
        composition_fee_y=10_000,
        fees_claimed_x=100,
        fees_claimed_y=2_000,
    )
    assert rec.trigger == "active_bin_drift"

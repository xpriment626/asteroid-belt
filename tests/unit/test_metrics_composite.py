import polars as pl

from asteroid_belt.engine.result import BacktestResult
from asteroid_belt.metrics.composite import composite


def _result_with_primitives(primitives: dict[str, float]) -> BacktestResult:
    df = pl.DataFrame(
        {
            "ts": [0, 1],
            "price": [1.0, 1.0],
            "active_bin": [0, 0],
            "position_value_usd": [100.0, 110.0],
            "hodl_value_usd": [100.0, 100.0],
            "fees_x_cumulative": [0, 0],
            "fees_y_cumulative": [0, 0],
            "il_cumulative": [0.0, 0.0],
            "in_range": [True, True],
            "capital_idle_usd": [0.0, 0.0],
        }
    )
    return BacktestResult(
        run_id="t",
        config_hash="t",
        schema_version="1.0",
        started_at=0,
        ended_at=0,
        status="ok",
        trajectory=df,
        rebalances=[],
        primitives=primitives,
        score=0.0,
        score_metric="composite",
    )


def test_composite_simple_weighted_sum() -> None:
    r = _result_with_primitives({"net_pnl": 10.0, "rebalance_count": 5})
    score = composite(r, weights={"net_pnl": 1.0, "rebalance_count": -0.5})
    assert score == 10.0 - 2.5


def test_composite_unknown_primitive_ignored() -> None:
    r = _result_with_primitives({"net_pnl": 10.0})
    score = composite(r, weights={"net_pnl": 2.0, "nonexistent": 100.0})
    assert score == 20.0


def test_composite_empty_weights_returns_zero() -> None:
    r = _result_with_primitives({"net_pnl": 10.0})
    assert composite(r, weights={}) == 0.0

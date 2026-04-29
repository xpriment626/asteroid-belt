from pathlib import Path

import pytest

from asteroid_belt.store.runs import (
    DuckDBRunStore,
    RunRecord,
)


@pytest.fixture
def store(tmp_path: Path) -> DuckDBRunStore:
    db_path = tmp_path / "meta.duckdb"
    return DuckDBRunStore(db_path=db_path)


def _record(run_id: str, score: float = 0.0) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        config_hash="hash_" + run_id,
        parent_run_id=None,
        session_id=None,
        created_by="human",
        cost_model_version="v0.1.0-unverified",
        schema_version="1.0",
        pool_address="BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y",
        strategy_class="asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy",
        strategy_params={"bin_width": 69},
        strategy_source_sha=None,
        adapter_kind="bar",
        window_start=0,
        window_end=1000,
        tick_secs=300,
        initial_x=1_000_000_000,
        initial_y=8_000_000_000,
        selection_metric="sharpe",
        started_at=1,
        ended_at=2,
        status="ok",
        error_msg=None,
        score=score,
        primitives={"sharpe": score},
        notes=None,
    )


def test_insert_and_get(store: DuckDBRunStore) -> None:
    rec = _record("run_a")
    store.insert(rec)
    got = store.get("run_a")
    assert got.run_id == "run_a"
    assert got.config_hash == "hash_run_a"
    assert got.strategy_params == {"bin_width": 69}


def test_get_missing_raises(store: DuckDBRunStore) -> None:
    with pytest.raises(KeyError):
        store.get("nonexistent")


def test_update_status(store: DuckDBRunStore) -> None:
    rec = _record("run_b")
    rec_running = RunRecord(
        **{**rec.__dict__, "status": "running", "ended_at": None, "score": None}
    )
    store.insert(rec_running)
    store.update_status(
        "run_b",
        status="ok",
        ended_at=999,
        score=1.5,
        primitives={"sharpe": 1.5},
        error_msg=None,
    )
    got = store.get("run_b")
    assert got.status == "ok"
    assert got.ended_at == 999
    assert got.score == 1.5


def test_query_by_pool(store: DuckDBRunStore) -> None:
    store.insert(_record("run_a"))
    store.insert(_record("run_b"))
    results = store.query(pool_address="BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y")
    assert len(results) == 2


def test_query_by_score_range(store: DuckDBRunStore) -> None:
    store.insert(_record("run_a", score=1.0))
    store.insert(_record("run_b", score=2.0))
    store.insert(_record("run_c", score=3.0))
    results = store.query(score_min=1.5, score_max=2.5)
    assert len(results) == 1
    assert results[0].run_id == "run_b"


def test_dedup_check_by_config_hash(store: DuckDBRunStore) -> None:
    store.insert(_record("run_a"))
    existing = store.find_by_config_hash("hash_run_a")
    assert existing is not None
    assert existing.run_id == "run_a"
    missing = store.find_by_config_hash("nonexistent")
    assert missing is None

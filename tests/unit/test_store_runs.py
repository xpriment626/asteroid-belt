from pathlib import Path

import pytest

from asteroid_belt.store.runs import (
    ArtifactRecord,
    DuckDBRunStore,
    RunRecord,
    SessionRecord,
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


def test_delete_session_cascade_clears_runs_artifacts_and_session(
    store: DuckDBRunStore,
) -> None:
    store.insert_session(
        SessionRecord(
            session_id="sess_x",
            label="x",
            created_at=1,
            closed_at=None,
            session_kind="agent",
        )
    )
    store.insert_session(
        SessionRecord(
            session_id="sess_y",
            label="y",
            created_at=2,
            closed_at=None,
            session_kind="agent",
        )
    )
    rec_x1 = RunRecord(**{**_record("run_x1").__dict__, "session_id": "sess_x"})
    rec_x2 = RunRecord(**{**_record("run_x2").__dict__, "session_id": "sess_x"})
    rec_y1 = RunRecord(**{**_record("run_y1").__dict__, "session_id": "sess_y"})
    store.insert(rec_x1)
    store.insert(rec_x2)
    store.insert(rec_y1)
    store.insert_artifact(ArtifactRecord(run_id="run_x1", kind="source_code", path="/x1.py"))
    store.insert_artifact(ArtifactRecord(run_id="run_x2", kind="source_code", path="/x2.py"))
    store.insert_artifact(ArtifactRecord(run_id="run_y1", kind="source_code", path="/y1.py"))

    deleted = store.delete_session_cascade("sess_x")
    assert deleted == 2

    # sess_x rows gone, sess_y intact.
    assert store.list_sessions(kind="agent") == [
        s for s in store.list_sessions(kind="agent") if s.session_id == "sess_y"
    ]
    with pytest.raises(KeyError):
        store.get("run_x1")
    with pytest.raises(KeyError):
        store.get("run_x2")
    assert store.get("run_y1").run_id == "run_y1"
    assert store.query_artifacts("run_x1") == []
    assert store.query_artifacts("run_x2") == []
    assert len(store.query_artifacts("run_y1")) == 1


def test_delete_session_cascade_unknown_session_raises(store: DuckDBRunStore) -> None:
    with pytest.raises(KeyError):
        store.delete_session_cascade("nope")

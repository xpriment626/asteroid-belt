"""Tests for store.agent_runs — agent-tournament adapter over the run store."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from asteroid_belt.store.agent_runs import (
    AGENT_CREATED_BY,
    AGENT_SESSION_KIND,
    SOURCE_KIND,
    TRAJECTORY_KIND,
    agent_run_id,
    ensure_agent_session,
    get_iteration_payload,
    get_iteration_trajectory,
    list_agent_trials,
    list_iteration_payloads,
    list_iterations,
    record_agent_iteration,
)
from asteroid_belt.store.runs import DuckDBRunStore


def _store(tmp_path: Path) -> DuckDBRunStore:
    return DuckDBRunStore(db_path=tmp_path / "test.duckdb")


def _trajectory(rows: int = 3) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": list(range(rows)),
            "price": [100.0 + i for i in range(rows)],
            "active_bin": [0] * rows,
            "position_value_usd": [1000.0] * rows,
            "hodl_value_usd": [1000.0] * rows,
            "fees_x_cumulative": [0] * rows,
            "fees_y_cumulative": [0] * rows,
            "fees_value_usd": [float(i) for i in range(rows)],
            "il_cumulative": [0.0] * rows,
            "in_range": [True] * rows,
            "capital_idle_usd": [0.0] * rows,
        }
    )


def _record(
    store: DuckDBRunStore,
    runs_dir: Path,
    *,
    trial: str = "demo",
    iteration: int = 0,
    code_hash: str = "abc123def456",
    score: float | None = 100.0,
    error: str | None = None,
    with_trajectory: bool = True,
    rebalance_count: int = 0,
) -> str:
    primitives = (
        {"vol_capture": score, "rebalance_count": float(rebalance_count)}
        if score is not None
        else {}
    )
    return record_agent_iteration(
        store,
        runs_dir=runs_dir,
        trial=trial,
        iteration=iteration,
        code_hash=code_hash,
        strategy_code=f"# iter {iteration}\nclass MyStrategy(Strategy): pass\n",
        pool_address="pool_x",
        window_start=1_700_000_000_000,
        window_end=1_700_000_604_000,
        initial_x=10_000_000_000,
        initial_y=1_000_000_000,
        selection_metric="vol_capture",
        started_at=1_700_000_000_000 + iteration,
        ended_at=1_700_000_010_000 + iteration,
        status="ok" if error is None else "error",
        score=score,
        primitives=primitives if primitives else None,
        error_msg=error,
        trajectory=_trajectory() if with_trajectory else None,
    )


def test_agent_run_id_is_deterministic() -> None:
    assert agent_run_id("smoke", 0) == "agent_smoke_0000"
    assert agent_run_id("smoke", 11) == "agent_smoke_0011"


def test_ensure_agent_session_creates_then_reuses(tmp_path: Path) -> None:
    s = _store(tmp_path)
    sess = ensure_agent_session(
        s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=5
    )
    assert sess.session_id == "demo"
    assert sess.session_kind == AGENT_SESSION_KIND
    # Idempotent on second call — same row returned, no exception.
    sess2 = ensure_agent_session(
        s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=99
    )
    assert sess2.session_id == "demo"


def test_record_agent_iteration_writes_run_and_artifacts(tmp_path: Path) -> None:
    s = _store(tmp_path)
    runs_dir = tmp_path / "runs"
    ensure_agent_session(s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=5)
    run_id = _record(s, runs_dir, iteration=0, code_hash="aaaa")
    assert run_id == "agent_demo_0000"

    run = s.get(run_id)
    assert run.created_by == AGENT_CREATED_BY
    assert run.session_id == "demo"
    assert run.strategy_params["iteration"] == 0
    assert run.score == 100.0

    artifacts = s.query_artifacts(run_id)
    kinds = {a.kind for a in artifacts}
    assert kinds == {SOURCE_KIND, TRAJECTORY_KIND}

    code_path = next(a.path for a in artifacts if a.kind == SOURCE_KIND)
    assert "MyStrategy" in Path(code_path).read_text()


def test_record_iteration_with_error_skips_trajectory(tmp_path: Path) -> None:
    s = _store(tmp_path)
    runs_dir = tmp_path / "runs"
    ensure_agent_session(s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=5)
    _record(
        s,
        runs_dir,
        iteration=1,
        code_hash="bbbb",
        score=None,
        error="TypeError: bad",
        with_trajectory=False,
    )
    run = s.get("agent_demo_0001")
    assert run.status == "error"
    assert run.error_msg == "TypeError: bad"
    assert run.score is None  # -inf / None mapped to NULL in DB

    artifacts = s.query_artifacts("agent_demo_0001")
    kinds = {a.kind for a in artifacts}
    assert kinds == {SOURCE_KIND}  # source written, no trajectory


def test_record_iteration_drops_inf_score(tmp_path: Path) -> None:
    s = _store(tmp_path)
    runs_dir = tmp_path / "runs"
    ensure_agent_session(s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=5)
    _record(s, runs_dir, iteration=2, code_hash="cccc", score=float("-inf"), error="x")
    run = s.get("agent_demo_0002")
    assert run.score is None  # -inf coerced to NULL


def test_list_iterations_sorted_by_iteration(tmp_path: Path) -> None:
    s = _store(tmp_path)
    runs_dir = tmp_path / "runs"
    ensure_agent_session(s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=5)
    _record(s, runs_dir, iteration=2, code_hash="c2")
    _record(s, runs_dir, iteration=0, code_hash="c0")
    _record(s, runs_dir, iteration=1, code_hash="c1")
    runs = list_iterations(s, trial="demo")
    assert [r.strategy_params["iteration"] for r in runs] == [0, 1, 2]


def test_list_agent_trials_filters_to_kind(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ensure_agent_session(s, trial="t1", pool_address="p1", objective="vol_capture", budget=5)
    # Insert a non-agent session manually
    from asteroid_belt.store.runs import SessionRecord

    s.insert_session(
        SessionRecord(
            session_id="manual_session",
            label="human",
            created_at=0,
            closed_at=None,
            session_kind="manual",
        )
    )
    trials = list_agent_trials(s)
    assert {t.session_id for t in trials} == {"t1"}


def test_payload_round_trip(tmp_path: Path) -> None:
    """Old flat-file JSON shape is preserved when reading back from DB."""
    s = _store(tmp_path)
    runs_dir = tmp_path / "runs"
    ensure_agent_session(s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=5)
    _record(s, runs_dir, iteration=7, code_hash="hhhh", score=42.0, rebalance_count=3)

    payload = get_iteration_payload(s, trial="demo", iteration=7)
    assert payload is not None
    assert payload.iteration == 7
    assert payload.code_hash == "hhhh"
    assert payload.score == 42.0
    assert payload.score_metric == "vol_capture"
    assert payload.rebalance_count == 3
    assert payload.has_trajectory is True
    assert "MyStrategy" in payload.strategy_code


def test_get_iteration_trajectory_returns_dataframe(tmp_path: Path) -> None:
    s = _store(tmp_path)
    runs_dir = tmp_path / "runs"
    ensure_agent_session(s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=5)
    _record(s, runs_dir, iteration=0, code_hash="a")

    df = get_iteration_trajectory(s, trial="demo", iteration=0)
    assert df is not None
    assert df.height == 3
    assert "fees_value_usd" in df.columns


def test_get_missing_iteration_returns_none(tmp_path: Path) -> None:
    s = _store(tmp_path)
    assert get_iteration_payload(s, trial="missing", iteration=0) is None
    assert get_iteration_trajectory(s, trial="missing", iteration=0) is None


def test_list_iteration_payloads_includes_errored(tmp_path: Path) -> None:
    s = _store(tmp_path)
    runs_dir = tmp_path / "runs"
    ensure_agent_session(s, trial="demo", pool_address="pool_x", objective="vol_capture", budget=5)
    _record(s, runs_dir, iteration=0, code_hash="ok")
    _record(
        s,
        runs_dir,
        iteration=1,
        code_hash="er",
        score=None,
        error="oops",
        with_trajectory=False,
    )
    payloads = list_iteration_payloads(s, trial="demo")
    assert len(payloads) == 2
    assert payloads[0].error is None
    assert payloads[1].error == "oops"
    assert payloads[1].score is None

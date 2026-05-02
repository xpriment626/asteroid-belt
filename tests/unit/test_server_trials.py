"""Tests for the trial / iteration / trajectory FastAPI endpoints (DB-backed)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from fastapi.testclient import TestClient

from asteroid_belt.server.app import build_app
from asteroid_belt.store.agent_runs import (
    ensure_agent_session,
    record_agent_iteration,
)
from asteroid_belt.store.runs import DuckDBRunStore


def _trajectory() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": [1, 2, 3],
            "price": [100.0, 101.0, 102.0],
            "active_bin": [0, 1, 0],
            "position_value_usd": [1000.0, 1010.0, 1020.0],
            "hodl_value_usd": [1000.0, 1000.0, 1000.0],
            "fees_x_cumulative": [0, 0, 0],
            "fees_y_cumulative": [0, 0, 0],
            "fees_value_usd": [0.0, 5.0, 10.0],
            "il_cumulative": [0.0, 10.0, 20.0],
            "in_range": [True, True, False],
            "capital_idle_usd": [0.0, 0.0, 0.0],
        }
    )


def _seed_iteration(
    store: DuckDBRunStore,
    runs_dir: Path,
    *,
    trial: str,
    iteration: int,
    code_hash: str,
    score: float | None,
    error: str | None,
    rebalance_count: int = 0,
    has_trajectory: bool = False,
) -> None:
    primitives: dict[str, float] | None
    if score is None:
        primitives = None
    else:
        primitives = {
            "vol_capture": score,
            "sharpe": 1.0,
            "rebalance_count": float(rebalance_count),
        }
    record_agent_iteration(
        store,
        runs_dir=runs_dir,
        trial=trial,
        iteration=iteration,
        code_hash=code_hash,
        strategy_code="class MyStrategy(Strategy):\n    pass\n",
        pool_address="pool_x",
        window_start=1_700_000_000_000,
        window_end=1_700_000_604_000,
        initial_x=10_000_000_000,
        initial_y=1_000_000_000,
        selection_metric="vol_capture",
        started_at=1_700_000_000_000 + iteration,
        ended_at=1_700_000_010_000 + iteration,
        status="error" if error else "ok",
        score=score,
        primitives=primitives,
        error_msg=error,
        trajectory=_trajectory() if has_trajectory else None,
    )


def _setup(tmp_path: Path) -> tuple[TestClient, DuckDBRunStore]:
    data_dir = tmp_path / "data"
    (data_dir / "pools").mkdir(parents=True)
    runs_dir = data_dir / "runs"
    runs_dir.mkdir(parents=True)
    db_path = data_dir / "test.duckdb"
    store = DuckDBRunStore(db_path=db_path)
    app = build_app(data_dir=data_dir, store=store)
    return TestClient(app), store


def test_list_trials_empty(tmp_path: Path) -> None:
    c, _ = _setup(tmp_path)
    assert c.get("/api/v1/trials").json() == []


def test_list_trials_summarizes_counts(tmp_path: Path) -> None:
    c, store = _setup(tmp_path)
    runs_dir = tmp_path / "data" / "runs"
    ensure_agent_session(
        store, trial="demo", pool_address="pool_x", objective="vol_capture", budget=4
    )
    _seed_iteration(
        store,
        runs_dir,
        trial="demo",
        iteration=0,
        code_hash="abc1",
        score=100.0,
        error=None,
        has_trajectory=True,
    )
    _seed_iteration(
        store,
        runs_dir,
        trial="demo",
        iteration=1,
        code_hash="abc2",
        score=None,
        error="TypeError: bad",
    )
    _seed_iteration(
        store, runs_dir, trial="demo", iteration=2, code_hash="abc3", score=0.0, error=None
    )
    _seed_iteration(
        store,
        runs_dir,
        trial="demo",
        iteration=3,
        code_hash="abc4",
        score=200.0,
        error=None,
        rebalance_count=5,
    )

    r = c.get("/api/v1/trials").json()
    assert len(r) == 1
    s = r[0]
    assert s["trial"] == "demo"
    assert s["iteration_count"] == 4
    assert s["success_count"] == 3
    assert s["error_count"] == 1
    assert s["degenerate_count"] == 1
    assert s["best_iteration"] == 3
    assert s["best_score"] == 200.0


def test_get_trial_returns_leaderboard(tmp_path: Path) -> None:
    c, store = _setup(tmp_path)
    runs_dir = tmp_path / "data" / "runs"
    ensure_agent_session(
        store, trial="demo", pool_address="pool_x", objective="vol_capture", budget=2
    )
    _seed_iteration(
        store,
        runs_dir,
        trial="demo",
        iteration=0,
        code_hash="aaa",
        score=100.0,
        error=None,
        has_trajectory=True,
    )
    _seed_iteration(
        store, runs_dir, trial="demo", iteration=1, code_hash="bbb", score=None, error="oops"
    )

    r = c.get("/api/v1/trials/demo").json()
    assert len(r["iterations"]) == 2
    assert r["iterations"][0]["iteration"] == 0
    assert r["iterations"][0]["score"] == 100.0
    assert r["iterations"][1]["score"] is None  # errored -> null


def test_get_iteration_returns_full_code(tmp_path: Path) -> None:
    c, store = _setup(tmp_path)
    runs_dir = tmp_path / "data" / "runs"
    ensure_agent_session(
        store, trial="demo", pool_address="pool_x", objective="vol_capture", budget=1
    )
    _seed_iteration(
        store,
        runs_dir,
        trial="demo",
        iteration=7,
        code_hash="hhhh",
        score=42.0,
        error=None,
        has_trajectory=True,
    )

    r = c.get("/api/v1/trials/demo/iterations/7").json()
    assert r["iteration"] == 7
    assert r["score"] == 42.0
    assert "class MyStrategy" in r["strategy_code"]
    assert r["has_trajectory"] is True


def test_get_trajectory_returns_rows(tmp_path: Path) -> None:
    c, store = _setup(tmp_path)
    runs_dir = tmp_path / "data" / "runs"
    ensure_agent_session(
        store, trial="demo", pool_address="pool_x", objective="vol_capture", budget=1
    )
    _seed_iteration(
        store,
        runs_dir,
        trial="demo",
        iteration=7,
        code_hash="hhhh",
        score=42.0,
        error=None,
        has_trajectory=True,
    )

    r = c.get("/api/v1/trials/demo/iterations/7/trajectory").json()
    assert len(r) == 3
    assert r[0]["price"] == 100.0
    assert r[2]["in_range"] is False
    assert r[2]["fees_value_usd"] == 10.0


def test_404s(tmp_path: Path) -> None:
    c, _ = _setup(tmp_path)
    assert c.get("/api/v1/trials/missing").status_code == 404
    assert c.get("/api/v1/trials/missing/iterations/0").status_code == 404
    assert c.get("/api/v1/trials/missing/iterations/0/trajectory").status_code == 404


_OPEN_30_CURVE_CODE = """
class MyStrategy(Strategy):
    def initialize(self, pool, capital):
        return OpenPosition(
            lower_bin=pool.active_bin - 30,
            upper_bin=pool.active_bin + 30,
            distribution="curve",
        )
    def on_swap(self, event, pool, position):
        return NoOp()
"""


def _seed_iteration_with_code(
    store: DuckDBRunStore,
    runs_dir: Path,
    *,
    trial: str,
    iteration: int,
    code: str,
    error: str | None = None,
) -> None:
    record_agent_iteration(
        store,
        runs_dir=runs_dir,
        trial=trial,
        iteration=iteration,
        code_hash="z" * 12,
        strategy_code=code,
        pool_address="pool_x",
        window_start=1_700_000_000_000,
        window_end=1_700_000_604_000,
        initial_x=10_000_000_000,
        initial_y=1_000_000_000,
        selection_metric="vol_capture",
        started_at=1_700_000_000_000 + iteration,
        ended_at=1_700_000_010_000 + iteration,
        status="error" if error else "ok",
        score=None if error else 100.0,
        primitives=None if error else {"vol_capture": 100.0},
        error_msg=error,
        trajectory=None,
    )


def test_build_action_returns_open_position_centered_on_active_bin(tmp_path: Path) -> None:
    c, store = _setup(tmp_path)
    runs_dir = tmp_path / "data" / "runs"
    ensure_agent_session(
        store, trial="demo", pool_address="pool_x", objective="vol_capture", budget=1
    )
    _seed_iteration_with_code(store, runs_dir, trial="demo", iteration=0, code=_OPEN_30_CURVE_CODE)

    r = c.post(
        "/api/v1/trials/demo/iterations/0/build-action",
        json={
            "active_bin": 1234,
            "bin_step": 10,
            "initial_x": 100_000_000,
            "initial_y": 1_000_000,
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert j["action_type"] == "open_position"
    assert j["lower_bin"] == 1204
    assert j["upper_bin"] == 1264
    assert j["distribution"] == "curve"
    assert j["error"] is None


def test_build_action_rejects_errored_iteration(tmp_path: Path) -> None:
    c, store = _setup(tmp_path)
    runs_dir = tmp_path / "data" / "runs"
    ensure_agent_session(
        store, trial="demo", pool_address="pool_x", objective="vol_capture", budget=1
    )
    _seed_iteration_with_code(
        store, runs_dir, trial="demo", iteration=1, code=_OPEN_30_CURVE_CODE, error="TypeError: bad"
    )

    r = c.post(
        "/api/v1/trials/demo/iterations/1/build-action",
        json={"active_bin": 0, "bin_step": 10, "initial_x": 0, "initial_y": 0},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["action_type"] == "error"
    assert "errored" in (j["error"] or "")


def test_build_action_returns_no_op_when_strategy_returns_noop(tmp_path: Path) -> None:
    """Degenerate iterations whose initialize() returns NoOp can't be deployed."""
    c, store = _setup(tmp_path)
    runs_dir = tmp_path / "data" / "runs"
    ensure_agent_session(
        store, trial="demo", pool_address="pool_x", objective="vol_capture", budget=1
    )
    noop_code = """
class MyStrategy(Strategy):
    def initialize(self, pool, capital):
        return NoOp()
    def on_swap(self, event, pool, position):
        return NoOp()
"""
    _seed_iteration_with_code(store, runs_dir, trial="demo", iteration=2, code=noop_code)

    r = c.post(
        "/api/v1/trials/demo/iterations/2/build-action",
        json={"active_bin": 0, "bin_step": 10, "initial_x": 100, "initial_y": 100},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["action_type"] == "no_op"
    assert j["lower_bin"] is None

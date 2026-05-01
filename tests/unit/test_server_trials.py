"""Tests for the trial / iteration / trajectory FastAPI endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from fastapi.testclient import TestClient

from asteroid_belt.server.app import build_app


def _write_iteration(
    trial_dir: Path,
    *,
    iteration: int,
    code_hash: str,
    score: float | None,
    error: str | None,
    rebalance_count: int = 0,
    has_trajectory: bool = False,
) -> None:
    payload = {
        "iteration": iteration,
        "timestamp": 1_700_000_000_000 + iteration,
        "code_hash": code_hash,
        "score": score if score is not None else float("-inf"),
        "score_metric": "vol_capture",
        "primitives": {"vol_capture": score, "sharpe": 1.0} if score is not None else {},
        "rebalance_count": rebalance_count,
        "error": error,
        "strategy_code": "class MyStrategy(Strategy):\n    pass\n",
        "has_trajectory": has_trajectory,
    }
    base = trial_dir / f"{iteration:04d}_{code_hash}"
    base.with_suffix(".json").write_text(json.dumps(payload))
    if has_trajectory:
        df = pl.DataFrame(
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
        df.write_parquet(base.with_suffix(".parquet"))


def _client(tmp_path: Path) -> TestClient:
    results_root = tmp_path / "agent_results"
    data_dir = tmp_path / "data"
    (data_dir / "pools").mkdir(parents=True)
    results_root.mkdir()
    app = build_app(data_dir=data_dir, results_root=results_root)
    return TestClient(app)


def test_list_trials_empty(tmp_path: Path) -> None:
    c = _client(tmp_path)
    assert c.get("/api/v1/trials").json() == []


def test_list_trials_summarizes_counts(tmp_path: Path) -> None:
    results_root = tmp_path / "agent_results"
    data_dir = tmp_path / "data"
    (data_dir / "pools").mkdir(parents=True)
    results_root.mkdir()
    trial_dir = results_root / "demo"
    trial_dir.mkdir()

    _write_iteration(
        trial_dir, iteration=0, code_hash="abc1", score=100.0, error=None, has_trajectory=True
    )
    _write_iteration(trial_dir, iteration=1, code_hash="abc2", score=None, error="TypeError: bad")
    _write_iteration(trial_dir, iteration=2, code_hash="abc3", score=0.0, error=None)
    _write_iteration(
        trial_dir, iteration=3, code_hash="abc4", score=200.0, error=None, rebalance_count=5
    )

    app = build_app(data_dir=data_dir, results_root=results_root)
    c = TestClient(app)
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
    results_root = tmp_path / "agent_results"
    data_dir = tmp_path / "data"
    (data_dir / "pools").mkdir(parents=True)
    results_root.mkdir()
    trial_dir = results_root / "demo"
    trial_dir.mkdir()
    _write_iteration(
        trial_dir, iteration=0, code_hash="aaa", score=100.0, error=None, has_trajectory=True
    )
    _write_iteration(trial_dir, iteration=1, code_hash="bbb", score=None, error="oops")

    app = build_app(data_dir=data_dir, results_root=results_root)
    c = TestClient(app)
    r = c.get("/api/v1/trials/demo").json()
    assert len(r["iterations"]) == 2
    assert r["iterations"][0]["iteration"] == 0
    assert r["iterations"][0]["score"] == 100.0
    assert r["iterations"][1]["score"] is None  # errored -> null


def test_get_iteration_returns_full_code(tmp_path: Path) -> None:
    results_root = tmp_path / "agent_results"
    data_dir = tmp_path / "data"
    (data_dir / "pools").mkdir(parents=True)
    results_root.mkdir()
    trial_dir = results_root / "demo"
    trial_dir.mkdir()
    _write_iteration(
        trial_dir, iteration=7, code_hash="hhhh", score=42.0, error=None, has_trajectory=True
    )

    app = build_app(data_dir=data_dir, results_root=results_root)
    c = TestClient(app)
    r = c.get("/api/v1/trials/demo/iterations/7").json()
    assert r["iteration"] == 7
    assert r["score"] == 42.0
    assert "class MyStrategy" in r["strategy_code"]
    assert r["has_trajectory"] is True


def test_get_trajectory_returns_rows(tmp_path: Path) -> None:
    results_root = tmp_path / "agent_results"
    data_dir = tmp_path / "data"
    (data_dir / "pools").mkdir(parents=True)
    results_root.mkdir()
    trial_dir = results_root / "demo"
    trial_dir.mkdir()
    _write_iteration(
        trial_dir, iteration=7, code_hash="hhhh", score=42.0, error=None, has_trajectory=True
    )

    app = build_app(data_dir=data_dir, results_root=results_root)
    c = TestClient(app)
    r = c.get("/api/v1/trials/demo/iterations/7/trajectory").json()
    assert len(r) == 3
    assert r[0]["price"] == 100.0
    assert r[2]["in_range"] is False
    assert r[2]["fees_value_usd"] == 10.0


def test_404s(tmp_path: Path) -> None:
    c = _client(tmp_path)
    assert c.get("/api/v1/trials/missing").status_code == 404
    assert c.get("/api/v1/trials/missing/iterations/0").status_code == 404
    assert c.get("/api/v1/trials/missing/iterations/0/trajectory").status_code == 404

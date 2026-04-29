"""RunStore Protocol and DuckDB implementation.

Single-writer model: one CLI process at a time touches DuckDB. The Protocol
seam exists so future v2 implementations (queued, sharded for parallel agent
runs) can swap in mechanically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import duckdb

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@dataclass
class RunRecord:
    """Mirrors the `runs` table schema."""

    run_id: str
    config_hash: str
    parent_run_id: str | None
    session_id: str | None
    created_by: str
    cost_model_version: str
    schema_version: str
    pool_address: str
    strategy_class: str
    strategy_params: dict[str, Any]
    strategy_source_sha: str | None
    adapter_kind: str
    window_start: int
    window_end: int
    tick_secs: int
    initial_x: int
    initial_y: int
    selection_metric: str
    started_at: int
    ended_at: int | None
    status: str
    error_msg: str | None
    score: float | None
    primitives: dict[str, float] | None
    notes: str | None


@dataclass
class SessionRecord:
    """Mirrors the `sessions` table schema."""

    session_id: str
    label: str | None
    created_at: int
    closed_at: int | None
    session_kind: str = "manual"
    goal_json: dict[str, Any] | None = None
    outcome_json: dict[str, Any] | None = None
    notes: str | None = None


class RunStore(Protocol):
    """The seam: v1 = DuckDBRunStore. v2+ implementations swap in here."""

    def insert(self, run: RunRecord) -> None: ...
    def update_status(self, run_id: str, *, status: str, **fields: Any) -> None: ...
    def get(self, run_id: str) -> RunRecord: ...
    def find_by_config_hash(self, config_hash: str) -> RunRecord | None: ...
    def query(self, **filters: Any) -> list[RunRecord]: ...
    def insert_session(self, session: SessionRecord) -> None: ...
    def close_session(
        self, session_id: str, *, closed_at: int, outcome_json: dict[str, Any] | None
    ) -> None: ...
    def get_session(self, session_id: str) -> SessionRecord: ...


class DuckDBRunStore:
    """v1 implementation. Single-writer."""

    def __init__(self, *, db_path: Path) -> None:
        self.db_path = db_path
        # DuckDB creates file if absent
        self._con = duckdb.connect(str(db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        self._con.execute(_SCHEMA_PATH.read_text())

    def insert(self, run: RunRecord) -> None:
        self._con.execute(
            """
            INSERT INTO runs (
                run_id, config_hash, parent_run_id, session_id,
                created_by, cost_model_version, schema_version,
                pool_address, strategy_class, strategy_params, strategy_source_sha,
                adapter_kind, window_start, window_end, tick_secs,
                initial_x, initial_y, selection_metric,
                started_at, ended_at, status, error_msg,
                score, primitives, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run.run_id,
                run.config_hash,
                run.parent_run_id,
                run.session_id,
                run.created_by,
                run.cost_model_version,
                run.schema_version,
                run.pool_address,
                run.strategy_class,
                json.dumps(run.strategy_params),
                run.strategy_source_sha,
                run.adapter_kind,
                run.window_start,
                run.window_end,
                run.tick_secs,
                run.initial_x,
                run.initial_y,
                run.selection_metric,
                run.started_at,
                run.ended_at,
                run.status,
                run.error_msg,
                run.score,
                json.dumps(run.primitives) if run.primitives is not None else None,
                run.notes,
            ],
        )

    def update_status(self, run_id: str, *, status: str, **fields: Any) -> None:
        # Build dynamic UPDATE clause for the provided fields
        allowed = {"ended_at", "score", "primitives", "error_msg"}
        clauses = ["status = ?"]
        values: list[Any] = [status]
        for name, value in fields.items():
            if name not in allowed:
                raise ValueError(f"unsupported update field: {name}")
            clauses.append(f"{name} = ?")
            if name == "primitives" and value is not None:
                values.append(json.dumps(value))
            else:
                values.append(value)
        values.append(run_id)
        self._con.execute(
            f"UPDATE runs SET {', '.join(clauses)} WHERE run_id = ?",
            values,
        )

    def get(self, run_id: str) -> RunRecord:
        row = self._con.execute("SELECT * FROM runs WHERE run_id = ?", [run_id]).fetchone()
        if row is None:
            raise KeyError(run_id)
        return self._row_to_record(row)

    def find_by_config_hash(self, config_hash: str) -> RunRecord | None:
        row = self._con.execute(
            "SELECT * FROM runs WHERE config_hash = ? LIMIT 1", [config_hash]
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def query(self, **filters: Any) -> list[RunRecord]:
        clauses: list[str] = []
        values: list[Any] = []
        if "pool_address" in filters:
            clauses.append("pool_address = ?")
            values.append(filters["pool_address"])
        if "session_id" in filters and filters["session_id"] is not None:
            clauses.append("session_id = ?")
            values.append(filters["session_id"])
        if "status" in filters:
            clauses.append("status = ?")
            values.append(filters["status"])
        if "score_min" in filters:
            clauses.append("score >= ?")
            values.append(filters["score_min"])
        if "score_max" in filters:
            clauses.append("score <= ?")
            values.append(filters["score_max"])
        if "started_after" in filters:
            clauses.append("started_at >= ?")
            values.append(filters["started_after"])
        if "started_before" in filters:
            clauses.append("started_at <= ?")
            values.append(filters["started_before"])
        if "created_by" in filters:
            clauses.append("created_by = ?")
            values.append(filters["created_by"])
        if "strategy_class" in filters:
            clauses.append("strategy_class = ?")
            values.append(filters["strategy_class"])

        sql = "SELECT * FROM runs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC"
        if "limit" in filters:
            sql += " LIMIT ?"
            values.append(filters["limit"])

        rows = self._con.execute(sql, values).fetchall()
        return [self._row_to_record(r) for r in rows]

    def insert_session(self, session: SessionRecord) -> None:
        self._con.execute(
            """
            INSERT INTO sessions (
                session_id, label, created_at, closed_at,
                session_kind, goal_json, outcome_json, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                session.session_id,
                session.label,
                session.created_at,
                session.closed_at,
                session.session_kind,
                json.dumps(session.goal_json) if session.goal_json else None,
                json.dumps(session.outcome_json) if session.outcome_json else None,
                session.notes,
            ],
        )

    def close_session(
        self,
        session_id: str,
        *,
        closed_at: int,
        outcome_json: dict[str, Any] | None,
    ) -> None:
        self._con.execute(
            "UPDATE sessions SET closed_at = ?, outcome_json = ? WHERE session_id = ?",
            [
                closed_at,
                json.dumps(outcome_json) if outcome_json else None,
                session_id,
            ],
        )

    def get_session(self, session_id: str) -> SessionRecord:
        row = self._con.execute(
            (
                "SELECT session_id, label, created_at, closed_at, session_kind, "
                "goal_json, outcome_json, notes FROM sessions WHERE session_id = ?"
            ),
            [session_id],
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return SessionRecord(
            session_id=row[0],
            label=row[1],
            created_at=row[2],
            closed_at=row[3],
            session_kind=row[4],
            goal_json=json.loads(row[5]) if row[5] else None,
            outcome_json=json.loads(row[6]) if row[6] else None,
            notes=row[7],
        )

    @staticmethod
    def _row_to_record(row: tuple[Any, ...]) -> RunRecord:
        # Order matches `SELECT *` against runs table — preserve schema-order.
        return RunRecord(
            run_id=row[0],
            config_hash=row[1],
            parent_run_id=row[2],
            session_id=row[3],
            created_by=row[4],
            cost_model_version=row[5],
            schema_version=row[6],
            pool_address=row[7],
            strategy_class=row[8],
            strategy_params=json.loads(row[9]) if row[9] else {},
            strategy_source_sha=row[10],
            adapter_kind=row[11],
            window_start=row[12],
            window_end=row[13],
            tick_secs=row[14],
            initial_x=row[15],
            initial_y=row[16],
            selection_metric=row[17],
            started_at=row[18],
            ended_at=row[19],
            status=row[20],
            error_msg=row[21],
            score=row[22],
            primitives=json.loads(row[23]) if row[23] else None,
            notes=row[24],
        )

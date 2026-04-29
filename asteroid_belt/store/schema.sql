-- DuckDB schema for asteroid-belt v1.

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    label        TEXT,
    created_at   BIGINT NOT NULL,
    closed_at    BIGINT,
    session_kind TEXT NOT NULL DEFAULT 'manual',
    goal_json    JSON,
    outcome_json JSON,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    config_hash         TEXT NOT NULL,
    parent_run_id       TEXT,
    session_id          TEXT,
    created_by          TEXT NOT NULL DEFAULT 'human',
    cost_model_version  TEXT NOT NULL,
    schema_version      TEXT NOT NULL DEFAULT '1.0',

    pool_address        TEXT NOT NULL,
    strategy_class      TEXT NOT NULL,
    strategy_params     JSON NOT NULL,
    strategy_source_sha TEXT,
    adapter_kind        TEXT NOT NULL,
    window_start        BIGINT NOT NULL,
    window_end          BIGINT NOT NULL,
    tick_secs           INTEGER NOT NULL,
    initial_x           BIGINT NOT NULL,
    initial_y           BIGINT NOT NULL,
    selection_metric    TEXT NOT NULL,

    started_at          BIGINT NOT NULL,
    ended_at            BIGINT,
    status              TEXT NOT NULL,
    error_msg           TEXT,

    score               DOUBLE,
    primitives          JSON,

    notes               TEXT,
    FOREIGN KEY (session_id)    REFERENCES sessions(session_id),
    FOREIGN KEY (parent_run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS runs_session_idx     ON runs (session_id);
CREATE INDEX IF NOT EXISTS runs_config_hash_idx ON runs (config_hash);
CREATE INDEX IF NOT EXISTS runs_started_idx     ON runs (started_at);
CREATE INDEX IF NOT EXISTS runs_score_idx       ON runs (score);
CREATE INDEX IF NOT EXISTS runs_parent_idx      ON runs (parent_run_id);

CREATE TABLE IF NOT EXISTS run_artifacts (
    run_id   TEXT NOT NULL,
    kind     TEXT NOT NULL,
    path     TEXT NOT NULL,
    sha256   TEXT,
    bytes    BIGINT,
    PRIMARY KEY (run_id, kind),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

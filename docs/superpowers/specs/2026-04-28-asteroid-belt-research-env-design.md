# asteroid-belt — Research Environment Design (v1)

**Date:** 2026-04-28
**Status:** Draft, pending implementation plan
**Scope:** Subsystems 1–3 (data pipeline, backtest engine, strategy interface) + post-hoc dashboard

---

## 1. Executive summary

`asteroid-belt` is a personal research desk for optimizing DLMM (Dynamic Liquidity Market Maker) strategies on Meteora. The eventual product is a Karpathy-`autoresearch`-style agent loop that mutates strategy code against historical pool data to find better strategies, then hands the winning strategy to a separate live trading bot. This spec covers the **research environment** (subsystems 1–3) — the foundation the agent loop and live bot are built on. It does NOT cover the agent loop itself (subsystem 4) or the live bot (subsystem 5), which get their own specs later.

The research env is a Python package + thin FastAPI server + SvelteKit dashboard, all in this repo. It ingests Meteora pool history into parquet, replays history through candidate strategies via a deterministic backtest engine, persists every run to DuckDB, and exposes runs through a post-hoc dashboard with a compare view. The design is shaped by three constraints: backtest determinism (the future agent loop's keep/discard decisions need bit-identical reproducibility), pluggable layers as config (metric, adapter, mutation surface — a research desk lives or dies by optionality), and structural lookahead-bias guards (sealed holdout window the agent never sees, enforced at the filesystem layer rather than by trust).

The first target pool is SOL/USDC 10bps (`BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y`) — ~$7M TVL, ~$11M 24h volume, ~24 months of history. The framework is pool-agnostic: pool address is config, but the design assumes single-pool-per-run (no portfolio strategies, no cross-pool combinatorics).

---

## 2. Scope

### In scope (v1)

- Historical data ingest from Meteora's public OHLCV API → parquet
- Bar-synthesized backtest adapter (one synthetic swap per minute bar)
- Deterministic single-pass backtest engine with frozen DLMM math, frozen cost model, structural lookahead-bias guards
- `Strategy` ABC with two shipped baseline implementations: Precision Curve, Multiday Cook Up
- Pluggable metric layer with shipped primitives (net_pnl, sharpe, sortino, capital_efficiency, time_in_range_pct, …) and a generic composite
- DuckDB + parquet store for runs, sessions, artifacts
- FastAPI read-only API at `/api/v1/`
- SvelteKit dashboard: run list, run detail, compare view, session list, pool list
- CLI (`belt`) for ingest, run, serve, session management

### Out of scope (v1) — deferred to later specs

- **Subsystem 4 (autoresearch agent loop)** — the engine + interfaces are designed to support it without rewrites
- **Subsystem 5 (live trading bot)** — separate sibling directory, separate spec; consumes the strategy artifact this env produces
- **Swap-level adapter** — interface is in place; implementation is a follow-up
- **Walk-forward / purged k-fold CV** — single-split (18mo train + 6mo holdout) in v1; rolling CV is queued
- **HFL, Precision Bid-Ask, Multiday Ping Pong baselines** — queued as additive baseline implementations
- **Live/streaming dashboard** — post-hoc only
- **Auth, multi-user, cloud deploy of the research env** — single-user local tool
- **GC tooling** — runs accumulate forever in v1; tooling is a follow-up

### Out of scope, indefinitely

- Multi-protocol support (Orca, Raydium)
- Portfolio strategies (one strategy across N pools)
- Multi-asset positions

These would force partial rewrites; they are explicitly not anticipated.

---

## 3. Repo layout

```
autometeora/                            # local working dir (kept for backward compat)
├── pyproject.toml                      # name = "asteroid-belt"
├── package.json                        # top-level orchestration only (concurrently)
├── Makefile                            # `make dev`, `make test`, `make ingest|run|serve|api-gen`
├── README.md
│
├── asteroid_belt/                      # Python package
│   ├── cli.py                          # `belt ingest|run|serve|session …`
│   ├── config.py                       # Pydantic run-config models
│   │
│   ├── data/
│   │   ├── ingest.py                   # Meteora API → parquet
│   │   ├── adapters/
│   │   │   ├── base.py                 # Event types + AdapterProtocol
│   │   │   ├── bar.py                  # BarSynthesizedAdapter (v1)
│   │   │   └── swap.py                 # OnChainSwapAdapter (placeholder; raises NotImplementedError)
│   │   └── splits.py                   # Train/holdout windows; sealed-holdout invariant
│   │
│   ├── pool/                           # Frozen DLMM math
│   │   ├── bins.py                     # bin_id ↔ price; multi-bin swap walks
│   │   ├── fees.py                     # Base + variable fee with vParameters evolution
│   │   └── position.py                 # Position composition, MtM, IL vs HODL
│   │
│   ├── engine/                         # Frozen backtest engine
│   │   ├── runner.py                   # Backtest(strategy, adapter, config).run() → BacktestResult
│   │   ├── result.py                   # BacktestResult dataclass
│   │   ├── cost.py                     # Gas / composition fee / rent (frozen)
│   │   └── guards.py                   # Lookahead-bias enforcement + action validation
│   │
│   ├── strategies/                     # The single mutable surface
│   │   ├── base.py                     # Strategy ABC + Action union types
│   │   ├── precision_curve.py          # v1 baseline #1
│   │   └── multiday_cook_up.py         # v1 baseline #2
│   │
│   ├── metrics/                        # Pluggable metric layer
│   │   ├── primitives.py               # net_pnl, sharpe, sortino, capital_efficiency, …
│   │   └── composite.py                # weighted composite
│   │
│   ├── store/                          # DuckDB + parquet persistence
│   │   ├── runs.py                     # RunStore Protocol + DuckDBRunStore
│   │   ├── results.py                  # BacktestResult ↔ parquet
│   │   └── schema.sql                  # DuckDB DDL
│   │
│   └── server/                         # FastAPI read API
│       ├── app.py                      # routes mounted at /api/v1/
│       └── schemas.py                  # Pydantic response models
│
├── web/                                # SvelteKit frontend
│   ├── package.json
│   ├── svelte.config.js
│   └── src/
│       ├── routes/                     # /, /runs/[id], /compare, /sessions, /pools
│       ├── lib/
│       │   ├── api/                    # generated TS client (openapi-typescript)
│       │   ├── charts/                 # ECharts wrappers
│       │   └── ui/                     # Button, Card, Table, Filter (minimal shadcn-ish)
│       └── app.html
│
├── configs/                            # YAML run configs
│   ├── precision_curve_baseline.yaml
│   ├── multiday_cook_up_baseline.yaml
│   └── quickstart.yaml                 # small window for smoke testing
│
├── data/                               # gitignored runtime store
│   ├── pools/<address>/{bars_1m,bars_1m_holdout,swaps,swaps_holdout}.parquet
│   ├── pools/<address>/{pool_meta.json,ingest_log.json}
│   ├── runs/<run_id>/{result.parquet,rebalances.parquet,manifest.json}
│   └── meta.duckdb
│
├── docs/
│   └── superpowers/specs/              # design docs (this file)
│
└── tests/
    ├── unit/
    ├── integration/
    └── regression/golden/              # checkpointed trajectory hashes per baseline
```

**Local working directory** stays `/Users/bambozlor/Desktop/product-lab/autometeora` for backward compat. Project name, Python package, and repo are all `asteroid-belt` (Python module name `asteroid_belt`). CLI entry point is `belt`.

**Two language toolchains, one repo.** Python managed by `uv`; frontend by `pnpm`. Top-level `package.json` orchestrates `make dev` only. No circular deps; the SvelteKit app talks to FastAPI strictly over HTTP via a typed client generated from the OpenAPI schema.

**Engine boundary is clean for the future agent loop.** Subsystem 4 will sit next to `engine/` — it imports `Backtest`, `Strategy`, `metrics`, and the store, doesn't modify any of them. The frozen surfaces (`pool/`, `engine/cost.py`, `engine/guards.py`, `engine/runner.py`, `data/adapters/`) are the equivalent of Karpathy's `prepare.py` — agent can never touch them. The mutable surface is exactly `strategies/<name>.py` plus run configs.

---

## 4. Core interfaces

### 4.1 Events

```python
# data/adapters/base.py
@dataclass(frozen=True)
class SwapEvent:
    ts: int                              # ms since epoch
    signature: str                       # one user swap = N events with same signature
    event_index: int                     # ordering within signature
    swap_for_y: bool                     # matches Meteora SDK convention
    amount_in: int                       # raw token units (input side)
    amount_out: int
    fee_amount: int                      # total fee in input token denomination
    protocol_fee_amount: int             # carved out before LP share
    host_fee_amount: int                 # smaller carve-out
    price_after: Decimal                 # decoded from u64 Q64.64 fixed point
    bin_id_after: int                    # bin this event landed in

@dataclass(frozen=True)
class TimeTick:
    ts: int                              # synthetic, emitted at run-config cadence

Event = SwapEvent | TimeTick
```

**A single user swap that crosses N bins emits N `SwapEvent`s** with the same `signature` but different `event_index` and `bin_id_after`. The engine handles bin-traversal natively; `Strategy.on_swap` is called once per bin crossed.

The fee in a `SwapEvent` is denominated in the *input* token. LP fee for a single swap = `fee_amount - protocol_fee_amount - host_fee_amount`. Treating the entire `fee_amount` as LP-side overstates PnL by ~5% (Meteora's standard protocol share) — the engine respects this carve-out via the pro-rata distribution rule (see §5.4).

### 4.2 AdapterProtocol — the lookahead-bias seam

```python
# data/adapters/base.py
class AdapterProtocol(Protocol):
    pool: PoolKey

    def stream(self, window: TimeWindow) -> Iterator[SwapEvent]:
        """Chronological events within `window`. Implementation MUST NOT
        read past `window.end` or expose any state from outside the window
        to the engine."""
```

The lookahead guard is structural: the adapter is constructed with a window, and only that window's parquet rows are loaded. The engine has no path to data outside the window because it never gets the adapter's filesystem handles. **Holdout data lives at a different parquet path** (`bars_1m_holdout.parquet`) that the adapter for the agent's runs literally cannot reach — adapter constructor takes a path, not a flag.

### 4.3 Strategy ABC — the single mutable surface

```python
# strategies/base.py
class Strategy(ABC):
    @abstractmethod
    def initialize(self, pool: PoolState, capital: Capital) -> Action:
        """Called once at backtest start. Returns OpenPosition or NoOp."""

    @abstractmethod
    def on_swap(self, event: SwapEvent, pool: PoolState, position: PositionState) -> Action:
        """Per-swap decision point. Most strategies return NoOp here."""

    def on_tick(self, ts: int, pool: PoolState, position: PositionState) -> Action:
        """Optional time-based hook. Default: NoOp."""
        return NoOp()
```

Only `initialize` and `on_swap` are abstract. New lifecycle hooks added in future versions default to `NoOp` to preserve backward compatibility.

The strategy gets read-only `PoolState` and `PositionState` (snapshots taken before the call). It has **no path** to: future events, the adapter, the cost model, the clock outside what's handed in, the holdout data, or other strategies' state.

In `--mutation-surface code` mode (deferred to subsystem 4), this ABC is the only surface the agent can override. In `--mutation-surface params` mode (the v1 default), the ABC implementations are fixed and the agent only edits a `params` block consumed by `__init__`.

### 4.4 Action types

```python
@dataclass(frozen=True)
class OpenPosition:
    lower_bin: int
    upper_bin: int
    distribution: Literal["spot", "curve", "bid_ask"]
    capital_x_pct: float | None = None          # None = SDK-balanced via autoFill
    slippage_bps: int = 50

@dataclass(frozen=True)
class Rebalance:
    removes: list[BinRangeRemoval]              # per-bin partial remove (bps)
    adds: list[BinRangeAdd]                     # per-bin add with shape + amount
    max_active_bin_slippage: int = 0

@dataclass(frozen=True)
class AddLiquidity:
    bin_range: tuple[int, int]
    distribution: Literal["spot", "curve", "bid_ask"]
    amount_x: int
    amount_y: int

@dataclass(frozen=True)
class RemoveLiquidity:
    bin_range: tuple[int, int]
    bps: int                                    # 0..10000

@dataclass(frozen=True)
class ClosePosition: pass                       # implies fee claim

@dataclass(frozen=True)
class ClaimFees: pass                           # mid-position claim without close

@dataclass(frozen=True)
class NoOp: pass

Action = OpenPosition | Rebalance | AddLiquidity | RemoveLiquidity | ClosePosition | ClaimFees | NoOp
```

**No `skew` parameter.** Meteora's distribution shapes (Spot, Curve, BidAsk) are baked into the SDK's helpers — there is no on-chain curve-steepness knob. If skewed shapes ever matter, they're modelled as custom weight vectors via a separate action (out of scope for v1).

`Rebalance` is shaped after the SDK's `rebalanceLiquidity` instruction (program v0.12.0+). "Swapless" is emergent: if `sum(removes.x) == sum(adds.x)` and same for Y, no swap is needed.

`ClosePosition` implies fee claim at PnL time. `ClaimFees` is for mid-position claims without closing.

The engine validates every action (bin range ≤ 69, capital sufficient, distribution legal, slippage tolerance respected). Invalid actions become logged `NoOp`s with a warning, never crashes.

### 4.5 PoolState (read-only view to strategies)

```python
@dataclass(frozen=True)
class VolatilityState:                          # from LbPair.v_parameters
    volatility_accumulator: int
    volatility_reference: int
    index_reference: int
    last_update_timestamp: int

@dataclass(frozen=True)
class StaticFeeParams:                          # from LbPair.s_parameters
    base_factor: int
    filter_period: int
    decay_period: int
    reduction_factor: int
    variable_fee_control: int
    protocol_share: int
    max_volatility_accumulator: int

@dataclass(frozen=True)
class PoolState:
    active_bin: int
    bin_step: int
    mid_price: Decimal
    volatility: VolatilityState
    static_fee: StaticFeeParams
    bin_liquidity: dict[int, BinReserves]       # [active-N, active+N] window
    last_swap_ts: int                           # gates variable-fee decay; dead-pool detection
    reward_infos: list[RewardInfo]              # empty for SOL/USDC 10bps; schema-stable
```

`bin_liquidity` is materialized for `[active - N, active + N]` (N from run config; default 100). Strategies that reason about slippage / depth need this. Outside this window, lookups are not supported.

`volatility` and `static_fee` together let the engine reconstruct the variable fee at any moment via the LB whitepaper update rule.

### 4.6 PositionState (read-only view to strategies)

```python
@dataclass(frozen=True)
class PositionState:
    lower_bin: int
    upper_bin: int
    composition: dict[int, BinComposition]      # per-bin X/Y holdings
    fee_pending_x: int                          # aggregated pending, pre-claim
    fee_pending_y: int
    fee_pending_per_bin: dict[int, tuple[int, int]]
    total_claimed_x: int                        # lifetime claimed
    total_claimed_y: int
    fee_owner: PublicKey | None = None
    # in_range is derived: lower_bin <= active_bin <= upper_bin
```

**Pending fees are accumulated outside position liquidity.** Meteora doesn't auto-compound — fees only fold into capital on explicit `ClaimFees` or `Close`. Treating them as compounded silently overstates APR.

### 4.7 MetricFn protocol

```python
# metrics/primitives.py
MetricFn = Callable[[BacktestResult], float]

def net_pnl(r: BacktestResult) -> float: ...
def sharpe(r: BacktestResult, freq: str = "1D") -> float: ...
def sortino(r: BacktestResult, freq: str = "1D") -> float: ...
def calmar(r: BacktestResult) -> float: ...
def capital_efficiency(r: BacktestResult) -> float: ...
def time_in_range_pct(r: BacktestResult) -> float: ...

# metrics/composite.py
def composite(r: BacktestResult, weights: dict[str, float]) -> float: ...
```

Metrics are pure functions — no I/O, no side effects, no engine state. The run config selects one as `selection_metric` (the score the agent's gate reads). All shipped primitives are computed on every result regardless and stored in `BacktestResult.primitives` — every run is browseable through any lens, after the fact. New metrics can be added without re-running backtests; trajectories are the substrate, metrics derive scalars from them.

### 4.8 BacktestResult

```python
@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    config_hash: str
    schema_version: str = "1.0"
    started_at: int
    ended_at: int
    status: Literal["ok", "error", "timeout"]

    trajectory: pl.DataFrame                    # per-step; persisted to parquet
    rebalances: list[RebalanceRecord]           # discrete events for the dashboard

    primitives: dict[str, float]                # all shipped metrics, precomputed
    score: float                                # value of selection_metric
    score_metric: str                           # name of the selection_metric
```

Trajectory is persisted to `data/runs/<run_id>/result.parquet`. Resolution is always 1m regardless of adapter (the swap adapter, when built, will downsample to 1m at result-write time). Raw events for a run, when needed for forensics, are stored as a separate optional artifact `events.parquet` registered in `run_artifacts` with `kind="raw_events"`.

### 4.9 Invariants

1. Strategy never sees future data (enforced structurally at the adapter, not by trust).
2. Strategy never sees holdout data (holdout adapter is constructed by the *evaluator* process, not the agent's run; physically separate parquet path).
3. Cost model is frozen (`engine/cost.py`, agent cannot modify).
4. DLMM math is frozen (`pool/{bins,fees,position}.py`, callable but not modifiable).
5. Actions can't break the engine (every action validated; bad actions become logged `NoOp`s).
6. `BacktestResult` is immutable. Re-evaluating a run under a new metric never re-runs the backtest.
7. Same config + same input = bit-identical result. Determinism is non-negotiable; future agent loop relies on it.

---

## 5. Data pipeline + backtest engine

### 5.1 Storage layout (gitignored runtime)

```
data/
├── pools/<pool_address>/
│   ├── bars_1m.parquet                 # train: ts, o, h, l, c, vol_x, vol_y
│   ├── bars_1m_holdout.parquet         # NEVER opened by adapters in agent runs
│   ├── swaps.parquet                   # populated when swap adapter is built
│   ├── swaps_holdout.parquet
│   ├── pool_meta.json                  # bin_step, base_factor, decimals, etc.
│   └── ingest_log.json                 # last_ingested_ts per source
├── runs/<run_id>/
│   ├── result.parquet                  # trajectory
│   ├── rebalances.parquet              # discrete events
│   └── manifest.json                   # config snapshot + primitives + score (portable)
└── meta.duckdb                         # runs metadata, indexed by run_id
```

Holdout files live next to train files but at distinct paths. The adapter constructor takes a path. For agent runs it's instantiated from the train path. The holdout adapter is constructed only by the evaluator process, after the agent's session ends and the candidate strategy is frozen.

### 5.2 Ingest

```
belt ingest --pool <addr> --start 2024-05-01 --end 2026-04-30 --source meteora
```

For v1: hits Meteora's OHLCV endpoint (`https://dlmm.datapi.meteora.ag/pools/<addr>/ohlcv?resolution=1&start=…&end=…`) in paginated chunks, writes minute bars to `bars_1m.parquet`, splits into train/holdout files at the configured boundary (default Oct 31 2025), writes `pool_meta.json` from the `/pools/<addr>` endpoint, updates `ingest_log.json`. Idempotent.

Swap-level ingest (`--source bitquery|helius`) is stubbed in v1 — the CLI accepts the flag but raises `NotImplementedError`. Real implementation is a follow-up.

### 5.3 Bar synthesizer — explicit bias documented

`BarSynthesizedAdapter` turns each 1m OHLCV bar into a *single* synthetic `SwapEvent` at VWAP with full bar volume on the dominant side (`swap_for_y` set by the sign of `close - open`). Known biases:

- **Variable fee is understated** during high-volatility minutes (where intra-minute swap clustering would have driven `volatility_accumulator` higher). Engine compensates partially by evolving `vParameters` per synthetic event using the bar's high–low range as a proxy for intra-bar dispersion. Documented as approximation.
- **Bin-traversal granularity is lost.** A bar where price moved 5 bins emits one event landing in the destination bin; the engine distributes the bar's total LP fees across the traversed bin range as if they were one swap. Slightly favors strategies with wider ranges. Documented bias.
- **≤1440 events per backtest day** means backtests run fast (single-digit seconds for 18 months of history on the M4).

The swap adapter (when built) replaces this with real per-bin events and exact `vParameters` evolution. Same `Strategy` ABC, same engine, same metrics — only the adapter changes. Cross-validating bar-vs-swap on the same window directly measures these biases.

### 5.4 Engine main loop (pseudocode)

```python
# engine/runner.py
def run(strategy: Strategy, adapter: AdapterProtocol, config: RunConfig) -> BacktestResult:
    pool_state = bootstrap_pool_state(adapter.pool, config.window.start)
    capital = Capital(x=config.initial_x, y=config.initial_y)
    trajectory, rebalances = [], []

    action = strategy.initialize(read_only(pool_state), capital)
    position_state = apply_action(action, pool_state, capital, cost_model, log=rebalances)

    for event in interleave(adapter.stream(config.window), tick_cadence=config.tick_secs):
        # frozen rule: evolve volatility accumulator
        pool_state = evolve_v_params(pool_state, event)

        if isinstance(event, SwapEvent):
            # frozen rule: pro-rata fee distribution at swap time
            position_state = credit_lp_fees_pro_rata(position_state, pool_state, event)
            pool_state = apply_swap_to_pool(pool_state, event)
            action = strategy.on_swap(event, read_only(pool_state), read_only(position_state))
        else:  # TimeTick
            action = strategy.on_tick(event.ts, read_only(pool_state), read_only(position_state))

        # frozen rule: validate; bad actions become logged NoOps
        action = validate_action(action, pool_state, position_state, cost_model)
        position_state = apply_action(action, pool_state, position_state, cost_model, log=rebalances)

        trajectory.append(snapshot(event.ts, pool_state, position_state, capital))

    return build_result(config, trajectory, rebalances)
```

Single-pass, deterministic, no parallelism in v1.

### 5.5 Frozen rules (the agent's `prepare.py` equivalent)

These live in `engine/` and `pool/` and are off-limits to strategy code:

1. **Volatility accumulator evolution** (`pool/fees.py::evolve_v_params`) — implements the LB whitepaper update rule with `filter_period` / `decay_period` gates governed by `last_update_timestamp`.

2. **Pro-rata LP fee distribution** (`engine/runner.py::credit_lp_fees_pro_rata`) — at each `SwapEvent`, computes our position's share of `bin_liquidity[event.bin_id_after].liquidity_supply`, credits `(fee_amount - protocol_fee_amount - host_fee_amount) * our_share` to `position.fee_pending_*`. Multi-bin swaps walk the bin path emit-by-emit. **Explicitly handles JIT-bot fee dilution**: our share is computed against bin liquidity at swap time, including any other LPs (real or simulated). Without this, JIT activity in the historical record causes systematic over-attribution to our position.

3. **Cost model** (`engine/cost.py`) — gas estimates per action type, composition fee math per Meteora's formula. v1 numbers are explicit constants; updates are explicit code changes with justification. Each run records `cost_model_version` (sha of `engine/cost.py`) so the dashboard can warn when comparing runs across cost-model changes.

4. **Action validation** (`engine/guards.py::validate_action`) — bin range ≤ 69 (Meteora FAQ limit), capital sufficient, distribution legal, slippage tolerance respected. Failed actions become `NoOp` with a warning, never crashes.

### 5.6 Trajectory output

Per-step row written to `result.parquet`:

| col | type | meaning |
|---|---|---|
| ts | int64 | event timestamp |
| price | decimal | mid price |
| active_bin | int32 | active bin id |
| position_value_usd | decimal | position MtM at current price |
| hodl_value_usd | decimal | counterfactual: initial deposit MtM |
| fees_x_cumulative | int64 | lifetime fees in X (raw) |
| fees_y_cumulative | int64 | lifetime fees in Y (raw) |
| il_cumulative | decimal | `position_value - hodl_value` |
| in_range | bool | derived |
| capital_idle_usd | decimal | unallocated cash (pending fees, rebalance buffer) |

`BacktestResult.primitives` precomputes every shipped metric over the trajectory at result-build time.

---

## 6. Storage + run lifecycle

### 6.1 DuckDB schema (`meta.duckdb`)

```sql
CREATE TABLE sessions (
    session_id      TEXT PRIMARY KEY,
    label           TEXT,
    created_at      BIGINT NOT NULL,
    closed_at       BIGINT,
    session_kind    TEXT NOT NULL DEFAULT 'manual',  -- "manual" | "agent_search" | "evaluator_holdout" | "sweep"
    goal_json       JSON,                            -- structured intent (filled by agent runs)
    outcome_json    JSON,                            -- final candidate, holdout score, notes
    notes           TEXT
);

CREATE TABLE runs (
    run_id              TEXT PRIMARY KEY,            -- "{ISO_ts}_{config_hash[:6]}"
    config_hash         TEXT NOT NULL,
    parent_run_id       TEXT,                        -- subsystem 4: lineage
    session_id          TEXT,
    created_by          TEXT NOT NULL DEFAULT 'human', -- "human" | "agent:<id>" | "evaluator"
    cost_model_version  TEXT NOT NULL,               -- semver of engine/cost.py at run time
    schema_version      TEXT NOT NULL DEFAULT '1.0',

    pool_address        TEXT NOT NULL,
    strategy_class      TEXT NOT NULL,
    strategy_params     JSON NOT NULL,
    strategy_source_sha TEXT,                        -- NULL in params mode; set in code mode
    adapter_kind        TEXT NOT NULL,               -- "bar" | "swap"
    window_start        BIGINT NOT NULL,
    window_end          BIGINT NOT NULL,
    tick_secs           INT NOT NULL,
    initial_x           BIGINT NOT NULL,
    initial_y           BIGINT NOT NULL,
    selection_metric    TEXT NOT NULL,

    started_at          BIGINT NOT NULL,
    ended_at            BIGINT,
    status              TEXT NOT NULL,               -- "running" | "ok" | "error" | "timeout"
    error_msg           TEXT,

    score               DOUBLE,
    primitives          JSON,

    notes               TEXT,
    FOREIGN KEY (session_id)    REFERENCES sessions(session_id),
    FOREIGN KEY (parent_run_id) REFERENCES runs(run_id)
);
CREATE INDEX runs_session_idx     ON runs (session_id);
CREATE INDEX runs_config_hash_idx ON runs (config_hash);
CREATE INDEX runs_started_idx     ON runs (started_at);
CREATE INDEX runs_score_idx       ON runs (score);
CREATE INDEX runs_parent_idx      ON runs (parent_run_id);

CREATE TABLE run_artifacts (
    run_id   TEXT NOT NULL,
    kind     TEXT NOT NULL,                          -- "trajectory" | "rebalances" | "strategy_src" | "raw_events"
    path     TEXT NOT NULL,                          -- relative to data/
    sha256   TEXT,
    bytes    BIGINT,
    PRIMARY KEY (run_id, kind),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
```

### 6.2 Run identity + dedup

- **`run_id`**: human-readable, e.g. `20260428T143022_a3f9c2` (ISO-ish timestamp + first 6 of config_hash).
- **`config_hash`**: sha256 over canonical-JSON form of the run config (sorted keys, normalized numerics, plus the SHA of `engine/cost.py` and `engine/runner.py` so cost-model changes are visible). Two runs with the same hash produce identical trajectories. CLI refuses to re-run unless `--force`.
- **`strategy_source_sha`**: NULL in v1 params mode; set in future code-mutation mode.

### 6.3 Run lifecycle

```
$ belt run --config configs/precision_curve_baseline.yaml [--session <id>] [--force]
```

1. Load + validate YAML → `RunConfig` (Pydantic).
2. Compute `config_hash` over canonical form.
3. Check `runs.config_hash` for dedup; abort with hint unless `--force`.
4. Generate `run_id`. Insert row with `status="running"`, `started_at=now()`.
5. Construct adapter for `window` (train path; lookahead-guarded by construction).
6. Instantiate strategy with `strategy_params`.
7. Run engine. Trajectory streams to memory, written to parquet at end.
8. Compute primitives over trajectory (all shipped metrics).
9. Resolve `score = primitives[selection_metric]`.
10. Update row: `status="ok"`, `ended_at`, `score`, `primitives`. Write artifacts row.
11. On error: `status="error"` + `error_msg`. On timeout: `status="timeout"`. Partial trajectory persisted where possible.

### 6.4 Sessions

A session groups N runs. v1 use cases:

- Manual sweep: `belt session new --label "rebalance_trigger_sweep"` → pass `--session <id>` to N runs
- Subsystem 4 (deferred): the agent creates a session at start, attaches every experiment, closes the session at end with the final candidate's `run_id` recorded in `outcome_json`

The frontend's compare view filters by `session_id`. `belt session close <id>` is a metadata update only.

### 6.5 RunStore abstract interface

```python
# store/runs.py
class RunStore(Protocol):
    def insert(self, run: RunRecord) -> None: ...
    def update_status(self, run_id: str, status: str, **fields) -> None: ...
    def get(self, run_id: str) -> RunRecord: ...
    def query(self, filters: RunFilters, page: Page) -> list[RunRecord]: ...

class DuckDBRunStore(RunStore):
    """v1 implementation. Single-writer (DuckDB file lock)."""
```

Call sites use the Protocol. v2 swap to `QueuedDuckDBRunStore` (or sharded-per-branch storage for parallel agent runs) is mechanical.

### 6.6 Concurrency

Single writer, multiple readers. One `belt run` process at a time touches DuckDB; concurrent invocations error out clearly via DuckDB's file lock. FastAPI is read-only. Multiple dashboard tabs are fine.

### 6.7 Retention

Runs accumulate. v1 has no GC tooling; manual cleanup if needed. At v1 scale (a few hundred runs in early months, ~10 MB each) disk is a non-concern. Future `belt run gc --keep-best 100 --older-than 30d` is a ~50-line addition with no schema rework.

### 6.8 Determinism test

A test in `tests/integration/` runs the same config twice, sha256s the two trajectory parquets, asserts equality. Catches accidental non-determinism. Critical for the future agent loop — keep/discard decisions assume reproducibility.

---

## 7. HTTP API + frontend views

### 7.1 API stance

**Read-only, all under `/api/v1/`.** Writes go through the `belt` CLI exclusively. When subsystem 4 wants UI-triggered runs, `POST` methods get added under the same paths.

OpenAPI spec at `/api/v1/openapi.json`. Generated TS client lives in `web/src/lib/api/`. `make api-gen` regenerates after API changes.

### 7.2 Endpoint surface

```
GET  /api/v1/health
GET  /api/v1/pools
GET  /api/v1/pools/{address}
GET  /api/v1/sessions                          # paginated; filters: kind, status, date
GET  /api/v1/sessions/{id}
GET  /api/v1/runs                              # paginated; filters listed below
GET  /api/v1/runs/{id}
GET  /api/v1/runs/{id}/trajectory              # ?resolution=1m|5m|1h (server-side downsample)
GET  /api/v1/runs/{id}/rebalances
GET  /api/v1/runs/compare?ids=a,b,c            # max 6 runs
```

Run filters: `pool`, `session_id`, `status`, `selection_metric`, `score_min`, `score_max`, `started_after`, `started_before`, `strategy_class`, `created_by`, `parent_run_id`, `cost_model_version`. Pagination via `?page=&page_size=` (default 50, max 200).

The trajectory endpoint downsamples server-side via DuckDB when `resolution` is coarser than 1m. For 18-month runs at 1h resolution: ~13k points, ECharts renders smoothly without WASM.

### 7.3 Pages

```
web/src/routes/
├── +layout.svelte           # nav, dark theme, run-count badge
├── +page.svelte             # /  → run list (default landing)
├── runs/[id]/+page.svelte   # run detail
├── compare/+page.svelte     # /compare?ids=…
├── sessions/+page.svelte    # session list
├── sessions/[id]/+page.svelte
└── pools/+page.svelte       # pool list with ingest status
```

**Run list (`/`)**: sortable filterable table, click → run detail, bulk select → compare. Empty state prints the CLI command for the first run.

**Run detail (`/runs/[id]`)**: header (run_id, status, score with selection metric, pool, strategy, session) → collapsible config panel → main chart (price line + position range band + rebalance markers) → PnL pane (cumulative fees/IL/net PnL/HODL ref) → composition pane (stacked area X/Y/pending fees) → rebalances table → primitives panel (all metrics, selection metric highlighted). Notes display-only in v1.

**Compare view (`/compare?ids=…`)**: up to 6 runs. Three sections: primitives matrix (deltas vs first highlighted), PnL overlay chart, side-by-side YAML config diff.

### 7.4 Charting

ECharts via `svelte-echarts`. Reusable wrappers:

```
web/src/lib/charts/
├── PriceBinChart.svelte
├── PnlChart.svelte
├── CompositionChart.svelte
└── ComparisonOverlayChart.svelte
```

Each takes typed props matching API response shape. ECharts' built-in `dataZoom` handles browser-side panning/zooming. Downsampling is server-side via the `?resolution=` query param.

### 7.5 Styling

Tailwind for layout / typography. Lucide-svelte icons. Dark mode default. A small `ui/` folder with `Button`, `Card`, `Table`, `Filter` primitives — minimal, no library dependency.

### 7.6 Out of scope (UI v1)

Auth, WebSocket / live streaming, mobile responsive, theme toggle, PDF / CSV export, notifications, in-UI note editing, strategy source viewer.

---

## 8. Config + dev loop + testing

### 8.1 Run config (YAML)

```yaml
schema_version: "1.0"

pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y

window:
  start: "2024-05-01T00:00:00Z"
  end:   "2025-10-31T00:00:00Z"          # train upper bound; never crosses into holdout

adapter:
  kind: bar                              # bar | swap

strategy:
  class: asteroid_belt.strategies.PrecisionCurve
  params:
    bin_width: 69
    rebalance_trigger_bins: 10
    rebalance_cadence_secs: null
    auto_compound: true
    auto_claim_to_sol: false

engine:
  tick_secs: 300
  initial_x: 100000000                   # raw token units (lamports — 0.1 SOL)
  initial_y: 8800000000                  # raw token units (6 decimals — 8800 USDC)
  selection_metric: sharpe               # sharpe | net_pnl | sortino | capital_efficiency | composite
  timeout_secs: 600

session_id: null
notes: |
  Baseline Precision Curve, HawkFi prose-doc defaults.
```

Pydantic model in `asteroid_belt/config.py` with `extra="allow"` on read paths (forward-compat for future schema versions), strict on write.

`configs/` ships three files: `precision_curve_baseline.yaml`, `multiday_cook_up_baseline.yaml`, `quickstart.yaml` (small window for smoke testing).

### 8.2 Makefile

```makefile
.PHONY: install dev test ingest run serve api-gen

install:
	uv pip install -e .[dev]
	cd web && pnpm install

dev:
	npx concurrently \
		--names "api,web" --prefix-colors "blue,magenta" \
		"uvicorn asteroid_belt.server.app:app --reload --port 8000" \
		"cd web && pnpm dev --port 5173"

test:
	pytest tests/
	cd web && pnpm check && pnpm test

ingest:
	belt ingest --pool $(POOL) --start $(START) --end $(END)

run:
	belt run --config $(CONFIG)

serve:
	uvicorn asteroid_belt.server.app:app --port 8000

api-gen:
	cd web && pnpm openapi-typescript http://localhost:8000/api/v1/openapi.json \
		-o src/lib/api/types.ts
```

### 8.3 First-time setup

```
git clone …
make install
make ingest POOL=BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y \
            START=2024-05-01 END=2026-04-28
make run CONFIG=configs/quickstart.yaml
make dev
open http://localhost:5173
```

### 8.4 Testing

Three layers; CI runs all on PR + push to main.

**Unit (`tests/unit/`)**: `pool/{bins,fees,position}.py`, `engine/{cost,guards}.py`, `metrics/primitives.py`, `data/adapters/bar.py`, `store/runs.py`, `config.py`.

**Integration (`tests/integration/`)**:
- End-to-end smoke on a synthetic 7-day pool fixture, both baselines run to completion
- **Determinism** — same config twice, sha256 trajectory parquets, assert equality
- **Lookahead-bias guard** — malicious strategy that tries to read beyond `window.end` fails at the adapter layer
- **Holdout isolation** — holdout parquet path not reachable from strategy import context (FS-level)
- **Pro-rata fee distribution** — synthetic swap stream with JIT-bot adds/removes, assert our position credited only its bin-liquidity share at swap time
- **Schema version dispatch** — load `schema_version: "1.0"` and synthetic `"1.5"` (extra fields), assert v1 reader handles both correctly

**Regression (`tests/regression/`)**: one canary backtest per shipped baseline against the locked synthetic fixture; trajectory parquet sha256 checkpointed in `tests/regression/golden/`. CI fails on drift; intentional drifts require committing new sha + justification in the PR.

**Frontend (`web/tests/`)**: Playwright smoke that run list, run detail, compare pages render against fixture API responses. No deep visual regression in v1.

### 8.5 CI

GitHub Actions, single workflow on PR + push to main:
- Python: `ruff format --check` + `ruff check` + `mypy` + `pytest tests/`
- Frontend: `pnpm lint` + `pnpm check` + Playwright smoke
- Target: under 5 min cold, under 90s on cached PR pushes

### 8.6 Pre-commit hooks

`ruff format` + `ruff check`, `prettier`, `mypy`, a guard rejecting `data/runs/` or `data/pools/<addr>/*.parquet` in commits, `gitleaks` secret scan.

### 8.7 Documentation

`README.md` carries: one-paragraph project description, first-time setup, first-run walk-through ending at the dashboard URL, links to this spec and the memory notes, "Future work" pointing at queued items. Per-module docstrings are the only inline docs in v1; this spec is the source of truth for design intent.

---

## 9. Future-proofing patterns

Five patterns baked into v1 that make additive evolutions cheap and prevent migration debt:

1. **Schema versioning everywhere.** All JSON columns and YAML configs carry a `schema_version` field. Pydantic `extra="allow"` on read paths. v1.5/v2 add reader branches without breaking v1 runs.

2. **Forward-looking columns.** `runs.parent_run_id`, `runs.created_by`, `runs.cost_model_version`, `sessions.session_kind`, `sessions.goal_json`, `sessions.outcome_json` are all present from day one. Subsystem 4 fills them; v1 leaves them at NULL/default.

3. **`RunStore` abstract interface.** v1 = `DuckDBRunStore`. v2 = `QueuedDuckDBRunStore` or sharded-per-branch storage for parallel agent runs. Interface stable; implementation swap is mechanical.

4. **Trajectory at fixed 1m resolution.** Both adapters (bar v1, swap v1.5+) downsample to 1m at result-write time. Raw events for swap-level runs stored as separate optional artifact `events.parquet`. No breaking change when swap adapter ships.

5. **API path versioning.** All endpoints under `/api/v1/`. v2 contract changes coexist at `/api/v2/`. Frontend never blocked by API churn.

### What still forces a partial rewrite (acknowledged, indefinite-deferred)

- Multi-protocol (Orca, Raydium): `Action` union becomes protocol-tagged. **Out of scope.**
- Portfolio strategies: `PoolState` and `PositionState` plural. **Out of scope.**
- Live shadow mode: adapter "live tail." **Out of scope.**

These are real architectural shifts that no v1 design choice can dodge. They are explicitly not anticipated.

---

## 10. Verifications required before implementation

- **`Swap` event field order in the latest IDL.** Borsh decoder ordering matters — pull `idls/dlmm.json` from the deployed program (v0.12.0+) before writing the decoder.
- **`current_price: u64` Q64.64 conversion.** `price = current_price / 2^64 * 10^(decimals_y - decimals_x)`. Common decoding bug; verify against a few known on-chain swaps.
- **`rebalanceLiquidity` instruction shape** for the cost model — introduced in DLMM program v0.12.0 (~March 2026). Confirm whatever historical indexer we use targets that program version, otherwise the cost model needs a fork for older swaps.
- **Position max width = 69 bins** per Meteora FAQ — confirm against deployed program constant before hard-coding the validation limit.
- **`POSITION_FEE` and `BIN_ARRAY_FEE` rent values** — read directly from the deployed program before sizing transaction budgets in the cost model.

---

## 11. References

### Primary sources

- Meteora docs: https://docs.meteora.ag/
- Meteora DLMM SDK: https://github.com/MeteoraAg/dlmm-sdk
- Meteora public API (OHLCV): https://dlmm.datapi.meteora.ag/pools/<address>/ohlcv
- Meteora pair API: https://dlmm-api.meteora.ag/pair/<address>
- Trader Joe LB whitepaper: https://github.com/traderjoe-xyz/LB-Whitepaper
- HawkFi whitepaper / template prose: https://hawkfi.gitbook.io/whitepaper

### Karpathy autoresearch (the loop pattern this design draws from)

- https://github.com/karpathy/autoresearch
- Tweet threads: linked from repo README
- `program.md` (the agent prompt): https://github.com/karpathy/autoresearch/blob/master/program.md

### Reference implementations worth reading

- https://github.com/edwin-finance/meteora-liquidity-rebalancer — single-pool env-var-driven rebalancer
- https://github.com/DitherAI/MeteorShower — adaptive-span DLMM recenter bot
- https://github.com/WeShipHQ/lp-bot — Privy + Meteora + BullMQ stack (relevant for subsystem 5)

### Memory notes (project context)

- `~/.claude/projects/-Users-bambozlor-Desktop-product-lab-autometeora/memory/asteroid_belt_walkforward_followup.md` — walk-forward CV queued post-v1
- `~/.claude/projects/.../asteroid_belt_baselines_queued.md` — HFL, Precision Bid-Ask, Multiday Ping Pong queued
- `~/.claude/projects/.../user_strategy_interests.md` — vol-capture interest as post-v1 tiebreaker

---

## 12. Glossary

- **DLMM** — Dynamic Liquidity Market Maker, Meteora's binned-liquidity AMM
- **Bin** — discrete price range in a DLMM pool; constant-sum within
- **Bin step** — fixed bps width of each bin, set at pool creation
- **Active bin** — the only bin holding both X and Y; where swaps happen
- **HFL** — High Frequency Liquidity (HawkFi template, deferred)
- **IL** — Impermanent Loss; here computed vs HODL benchmark per Trader Joe LB whitepaper
- **JIT** — Just-In-Time liquidity; bots adding+removing in one block to capture single-swap fees
- **LP** — Liquidity Provider
- **vParameters** — volatility-accumulator state on the LbPair account
- **HODL benchmark** — counterfactual: what would the initial deposit be worth at current prices, no LPing

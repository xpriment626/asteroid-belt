# asteroid-belt

DLMM strategy research desk for Meteora pools. Backtest engine + LLM-driven
autoresearch tournament + SvelteKit UI for browsing run history. Ships with
a one-click "Deploy live (devnet)" path for landing the agent's best
strategy as a real Meteora LP transaction signed by Phantom.

For deeper internals, see `docs/superpowers/specs/` (design) and
`docs/superpowers/plans/` (implementation plan).

---

## Quickstart

Prerequisites:
- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node 20+** and **pnpm** (`brew install pnpm`)

```bash
# 1. Clone + install deps
git clone <repo-url>
cd autometeora
uv sync --extra dev          # Python deps
cd web && pnpm install && cd ..   # Frontend deps

# 2. Configure your OpenRouter API key (required for `belt agent`)
cp .env.example .env
# edit .env, paste your OPENROUTER_API_KEY (get one at https://openrouter.ai/keys)

# 3. Ingest some pool data (or use the sample if shipped)
uv run belt ingest \
  --pool BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y \
  --start 2025-12-01T00:00:00Z \
  --end 2026-04-30T00:00:00Z

# 4. Launch the dev environment
./launch.sh
```

Open `http://localhost:5173` — you should see an empty trial list. Click
**Start new run** in the top-right to kick off your first tournament, or
run one from the CLI (next section).

---

## The `belt` CLI

`belt` is a Python entry-point installed into the project's virtualenv at
`.venv/bin/belt`. Three ways to actually invoke it:

### Option A — `uv run belt …` (zero setup)

Always works, no venv juggling:
```bash
uv run belt agent --pool BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y --trial demo --budget 10
```

### Option B — Activate the venv (cleaner once you're working in the repo)

```bash
source .venv/bin/activate     # one-time per shell session
belt agent --pool ... --trial demo --budget 10
deactivate                     # when done, or just close the shell
```

### Option C — direnv (auto-activate when you `cd` in)

```bash
brew install direnv
echo 'source .venv/bin/activate' > .envrc
direnv allow
```
After this, `cd`-ing into the project activates the venv automatically. Zero
friction forever.

---

## Commands you'll actually use

### `belt agent` — run a tournament

LLM-driven search loop. Writes through to the run store; resumes
automatically if you re-invoke with the same `--trial`.

```bash
belt agent \
  --pool BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y \
  --trial my-first-run \
  --budget 10 \
  --objective vol_capture
```

| Flag | Default | Notes |
|---|---|---|
| `--pool` | (required) | Pool address. Must exist under `data/pools/<addr>/`. |
| `--trial` | (required) | Trial name. Becomes `sessions.session_id` in the DB. |
| `--budget` | `10` | Iteration count. Each iter is one LLM call (~30–60s) + one backtest. |
| `--objective` | `vol_capture` | One of: `vol_capture`, `info_ratio_vs_hodl`, `net_fee_yield`, `sharpe`, `calmar`. |
| `--initial-x` | `10_000_000_000` (10 SOL) | Raw token-X amount to start with. |
| `--initial-y` | `1_000_000_000` (1000 USDC) | Raw token-Y amount. |
| `--window-start-ms`, `--window-end-ms` | first 7 days of data | Backtest window. |

**Cost:** roughly $0.024 per iteration on DeepSeek V4 Pro via OpenRouter
(~$0.30 per 15-iter tournament).

### `belt ingest` — pull OHLCV bars from Meteora

```bash
belt ingest \
  --pool BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y \
  --start 2025-12-01T00:00:00Z \
  --end 2026-04-30T00:00:00Z
```

Writes to `data/pools/<addr>/bars_5m.parquet` + `pool_meta.json`. Idempotent;
re-running with the same window is a no-op for already-fetched bars.

### `belt agent-migrate` — one-shot file → DB migration

Only needed if you have legacy `agent/results/<trial>/*.{json,parquet}` from
before the DB-backed run store. Idempotent.

```bash
belt agent-migrate --trial smoke --pool BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
```

---

## Running the dev environment

`./launch.sh` starts both the FastAPI backend (port 8000) and the SvelteKit
dev server (port 5173) in parallel. Ctrl-C kills both.

If you've activated the venv (Option B or C above), `make dev` does the same
thing using `npx concurrently`.

For a single process at a time:
```bash
uv run uvicorn asteroid_belt.server.app:app --reload   # backend only
cd web && pnpm dev                                      # frontend only
```

---

## Configuration

`.env` (copy from `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | (required) | Get one at https://openrouter.ai/keys |
| `OPENROUTER_MODEL` | `deepseek/deepseek-v4-pro` | Any OpenRouter model id |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override for self-hosted gateways |
| `OPENROUTER_REASONING_EFFORT` | `high` | `low` / `medium` / `high` / `xhigh` |
| `ASTEROID_BELT_DATA_DIR` | `data` | Where pool bars + DB live |

The DuckDB store lives at `<data-dir>/asteroid_belt.duckdb`. Per-iteration
trajectory parquets and strategy code land under `<data-dir>/runs/<run_id>/`.

---

## Tests + lint

```bash
make test     # pytest + svelte-check
make lint     # ruff + mypy strict
make format   # ruff format + ruff --fix
make check    # lint + test
```

---

## Architecture at a glance

- **`asteroid_belt/engine/`** — single-pass deterministic backtest loop
- **`asteroid_belt/strategies/`** — Strategy ABC + thin reference baselines (`PrecisionCurve`, `MultidayCookUp`)
- **`asteroid_belt/agent/`** — autoresearch loop: prompt → LLM → exec → record
- **`asteroid_belt/metrics/`** — pure-function scorers (the 5 honest objectives)
- **`asteroid_belt/store/`** — DuckDB-backed run store + `agent_runs.py` adapter
- **`asteroid_belt/server/`** — FastAPI read-only API + tournament progress polling
- **`web/`** — SvelteKit UI (trials list, leaderboard timeline, iteration drilldown, devnet deploy modal)

Trial / iteration model:
```
trial         → sessions row     (session_kind='agent')
iteration     → runs row         (created_by='agent', session_id=trial)
trajectory    → run_artifacts    (kind='trajectory', parquet)
strategy code → run_artifacts    (kind='source_code', .py)
```

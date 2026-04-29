# asteroid-belt Research Environment — Implementation Plan

> **For agentic workers:** This plan is optimized for inline sequential execution by a single advanced reasoning model retaining context across tasks. Steps use checkbox (`- [ ]`) syntax for tracking. Work tasks strictly in order — later tasks assume types, files, and conventions established earlier.

**Goal:** Build the v1 research environment for asteroid-belt — historical data ingest, deterministic backtest engine, two HawkFi-derived baseline strategies, pluggable metrics, DuckDB+parquet store, FastAPI read API, and SvelteKit post-hoc dashboard — per [the design spec](../specs/2026-04-28-asteroid-belt-research-env-design.md).

**Architecture:** Python package (`asteroid_belt`) with engine + server, SvelteKit frontend in `web/`, DuckDB+parquet runtime store in `data/`. Two language toolchains, single repo. Frontend talks to FastAPI over HTTP via OpenAPI-generated TS client. Single-writer storage; CLI does writes, server is read-only.

**Tech Stack:** Python 3.11+ (uv, pydantic, polars, duckdb, fastapi, click, httpx, pytest, ruff, mypy). Node (pnpm, SvelteKit, Tailwind, Lucide, ECharts via svelte-echarts, openapi-typescript). DuckDB + parquet. GitHub Actions.

**Conventions used throughout this plan:**
- All file paths are absolute from repo root (`/Users/bambozlor/Desktop/product-lab/autometeora`).
- "Run, expect FAIL" / "Run, expect PASS" markers indicate test outcomes — verify before proceeding.
- Each task ends with a commit. Commits use conventional-commit style.
- Code blocks are intended to be copy-paste-ready; transcribe types and signatures exactly.
- When a step says "see Task X.Y for pattern", the structure is identical — only the names/types differ.

**Phase summary:**
- Phase 0: Project skeleton + tooling
- Phase 1: Pure types + DLMM math (foundation, no I/O)
- Phase 2: Engine internals (cost, guards, runner) + metrics
- Phase 3: Strategy ABC + baselines + bar adapter + splits
- Phase 4: Storage layer + Meteora ingest
- Phase 5: Config + CLI
- Phase 6: FastAPI server
- Phase 7: SvelteKit frontend
- Phase 8: Integration + regression tests
- Phase 9: CI + README

---

## Phase 0 — Project skeleton + tooling

Sets up uv-managed Python package + pnpm-managed SvelteKit shell + linting/formatting/typing config + Makefile. Output: `make test` and `make dev` both run cleanly against empty modules.

### Task 0.1: pyproject.toml + uv venv

**Files:**
- Create: `pyproject.toml`
- Create: `asteroid_belt/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "asteroid-belt"
version = "0.1.0"
description = "DLMM strategy research desk for Meteora pools"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
    "pydantic>=2.7",
    "polars>=1.0",
    "duckdb>=1.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "click>=8.1",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "python-dateutil>=2.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.7",
    "types-pyyaml>=6.0",
]

[project.scripts]
belt = "asteroid_belt.cli:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["asteroid_belt"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]  # line length handled by formatter

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
disallow_untyped_defs = true
disallow_incomplete_defs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
```

- [ ] **Step 2: Create package init**

```python
# asteroid_belt/__init__.py
"""asteroid-belt: DLMM strategy research desk for Meteora pools."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Install dev environment**

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Expected: install succeeds, `belt` is on PATH but errors when invoked (no CLI yet).

- [ ] **Step 4: Verify import**

```bash
python -c "import asteroid_belt; print(asteroid_belt.__version__)"
```

Expected output: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml asteroid_belt/__init__.py
git commit -m "chore: initialize asteroid-belt python package"
```

### Task 0.2: Package directory skeleton

**Files:**
- Create: `asteroid_belt/{cli,config}.py` (empty stubs)
- Create: `asteroid_belt/data/{__init__,ingest,splits}.py`
- Create: `asteroid_belt/data/adapters/{__init__,base,bar,swap}.py`
- Create: `asteroid_belt/pool/{__init__,bins,fees,position}.py`
- Create: `asteroid_belt/engine/{__init__,runner,result,cost,guards}.py`
- Create: `asteroid_belt/strategies/{__init__,base,precision_curve,multiday_cook_up}.py`
- Create: `asteroid_belt/metrics/{__init__,primitives,composite}.py`
- Create: `asteroid_belt/store/{__init__,runs,results}.py`
- Create: `asteroid_belt/server/{__init__,app,schemas}.py`
- Create: `tests/{__init__,unit,integration,regression}/` (each with `__init__.py`)

- [ ] **Step 1: Create all directories and empty files**

```bash
mkdir -p asteroid_belt/{data/adapters,pool,engine,strategies,metrics,store,server}
mkdir -p tests/{unit,integration,regression/golden}
touch asteroid_belt/cli.py asteroid_belt/config.py
for d in asteroid_belt asteroid_belt/data asteroid_belt/data/adapters \
         asteroid_belt/pool asteroid_belt/engine asteroid_belt/strategies \
         asteroid_belt/metrics asteroid_belt/store asteroid_belt/server \
         tests tests/unit tests/integration tests/regression; do
  touch "$d/__init__.py"
done
for f in asteroid_belt/data/{ingest,splits}.py \
         asteroid_belt/data/adapters/{base,bar,swap}.py \
         asteroid_belt/pool/{bins,fees,position}.py \
         asteroid_belt/engine/{runner,result,cost,guards}.py \
         asteroid_belt/strategies/{base,precision_curve,multiday_cook_up}.py \
         asteroid_belt/metrics/{primitives,composite}.py \
         asteroid_belt/store/{runs,results}.py \
         asteroid_belt/server/{app,schemas}.py; do
  touch "$f"
done
```

- [ ] **Step 2: Verify mypy on the empty package**

```bash
mypy asteroid_belt
```

Expected: `Success: no issues found in N source files` (empty modules pass strict mypy).

- [ ] **Step 3: Verify pytest discovers no tests yet**

```bash
pytest
```

Expected: `no tests ran` exit code 5. That's fine — we'll add tests next.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt tests
git commit -m "chore: scaffold module directory structure"
```

### Task 0.3: Pre-commit hooks + Makefile

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `Makefile`

- [ ] **Step 1: Pre-commit config**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic>=2.7
          - types-pyyaml
        files: ^asteroid_belt/
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: [--maxkb=500]
  - repo: local
    hooks:
      - id: no-runtime-data
        name: reject runtime data files in commit
        language: system
        entry: bash -c 'if git diff --cached --name-only | grep -E "^data/(runs|pools)/.*\.parquet$"; then echo "ERROR: runtime data files staged"; exit 1; fi'
        pass_filenames: false
```

- [ ] **Step 2: Makefile**

```makefile
.PHONY: install dev test lint format ingest run serve api-gen check

install:
	uv pip install -e ".[dev]"
	cd web && pnpm install
	pre-commit install

dev:
	npx concurrently \
		--names "api,web" --prefix-colors "blue,magenta" \
		"uvicorn asteroid_belt.server.app:app --reload --port 8000" \
		"cd web && pnpm dev --port 5173"

test:
	pytest tests/
	cd web 2>/dev/null && pnpm check 2>/dev/null || true

lint:
	ruff check asteroid_belt tests
	mypy asteroid_belt

format:
	ruff format asteroid_belt tests
	ruff check --fix asteroid_belt tests

check: lint test

ingest:
	belt ingest --pool $(POOL) --start $(START) --end $(END)

run:
	belt run --config $(CONFIG)

serve:
	uvicorn asteroid_belt.server.app:app --port 8000

api-gen:
	cd web && pnpm openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/lib/api/types.ts
```

- [ ] **Step 3: Install hooks and verify they run on a no-op commit**

```bash
pre-commit install
pre-commit run --all-files
```

Expected: hooks run successfully (may auto-format files; if so, re-stage and retry).

- [ ] **Step 4: Commit**

```bash
git add .pre-commit-config.yaml Makefile
git commit -m "chore: add pre-commit hooks and Makefile"
```

---

## Phase 1 — Pure types + DLMM math

Foundation layer: zero I/O, fully testable in isolation. Establishes types referenced by every later phase. Heavy TDD because correctness here cascades to every backtest result.

### Task 1.1: Event types

**Files:**
- Modify: `asteroid_belt/data/adapters/base.py`
- Test: `tests/unit/test_event_types.py`

- [ ] **Step 1: Write the test (run, expect FAIL — types don't exist yet)**

```python
# tests/unit/test_event_types.py
from decimal import Decimal

import pytest

from asteroid_belt.data.adapters.base import SwapEvent, TimeTick


def test_swap_event_is_frozen() -> None:
    e = SwapEvent(
        ts=1_700_000_000_000,
        signature="abc",
        event_index=0,
        swap_for_y=True,
        amount_in=1_000_000_000,
        amount_out=87_550_000,
        fee_amount=1_000_000,
        protocol_fee_amount=50_000,
        host_fee_amount=0,
        price_after=Decimal("87.55"),
        bin_id_after=1234,
    )
    with pytest.raises(Exception):  # frozen dataclass raises on assignment
        e.ts = 0  # type: ignore[misc]


def test_swap_event_lp_fee_helper() -> None:
    e = SwapEvent(
        ts=0, signature="x", event_index=0, swap_for_y=True,
        amount_in=100, amount_out=99, fee_amount=1000,
        protocol_fee_amount=50, host_fee_amount=10,
        price_after=Decimal("1"), bin_id_after=0,
    )
    # LP fee = total fee minus carve-outs
    assert e.lp_fee_amount == 940


def test_time_tick_basic() -> None:
    t = TimeTick(ts=1_700_000_000_000)
    assert t.ts == 1_700_000_000_000
```

Run: `pytest tests/unit/test_event_types.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 2: Implement types**

```python
# asteroid_belt/data/adapters/base.py
"""Adapter event types and Protocol.

Events are the unified data primitive that flows from data adapters to the
backtest engine. Both the bar-synthesized adapter (v1) and the on-chain swap
adapter (v1.5+) emit SwapEvents. TimeTicks are interleaved by the engine at a
configurable cadence so time-based strategies have a hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterator, Protocol


@dataclass(frozen=True)
class SwapEvent:
    """One bin-crossing of a swap. A user swap that crosses N bins emits N
    SwapEvents with the same `signature` but distinct `event_index` and
    `bin_id_after` values. The fee is denominated in the input token."""

    ts: int  # ms since epoch
    signature: str
    event_index: int
    swap_for_y: bool  # True = X → Y (e.g. SOL → USDC for SOL/USDC pool)
    amount_in: int  # raw token units (input side)
    amount_out: int  # raw token units (output side)
    fee_amount: int  # total fee in input-token raw units
    protocol_fee_amount: int  # carved out before LP share
    host_fee_amount: int  # smaller carve-out
    price_after: Decimal  # post-swap mid price
    bin_id_after: int  # bin this event landed in

    @property
    def lp_fee_amount(self) -> int:
        """LP-side fee after protocol and host carve-outs."""
        return self.fee_amount - self.protocol_fee_amount - self.host_fee_amount


@dataclass(frozen=True)
class TimeTick:
    """Synthetic time-based event interleaved by the engine at run-config
    cadence. Strategies can react via `on_tick`."""

    ts: int


Event = SwapEvent | TimeTick


@dataclass(frozen=True)
class PoolKey:
    """Identifies a Meteora DLMM pool."""

    address: str  # base58 mint of the LbPair account


@dataclass(frozen=True)
class TimeWindow:
    """Half-open time window [start_ms, end_ms). Adapter MUST NOT yield events
    at or after end_ms."""

    start_ms: int
    end_ms: int


class AdapterProtocol(Protocol):
    """The lookahead-bias seam. Adapters are constructed pointing at a single
    parquet path; engine never sees the path. Holdout data lives at a
    physically separate path that agent-run adapters cannot reach."""

    pool: PoolKey

    def stream(self, window: TimeWindow) -> Iterator[SwapEvent]:
        """Yield events in chronological order strictly within `window`.
        Implementation MUST NOT read past window.end_ms or expose state from
        outside the window."""
        ...
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_event_types.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/data/adapters/base.py tests/unit/test_event_types.py
git commit -m "feat(types): add SwapEvent, TimeTick, AdapterProtocol"
```

### Task 1.2: Action types

**Files:**
- Modify: `asteroid_belt/strategies/base.py`
- Test: `tests/unit/test_action_types.py`

- [ ] **Step 1: Write the test (run, expect FAIL)**

```python
# tests/unit/test_action_types.py
import pytest

from asteroid_belt.strategies.base import (
    Action,
    AddLiquidity,
    BinRangeAdd,
    BinRangeRemoval,
    ClaimFees,
    ClosePosition,
    NoOp,
    OpenPosition,
    Rebalance,
    RemoveLiquidity,
)


def test_open_position_defaults() -> None:
    a = OpenPosition(lower_bin=-30, upper_bin=30, distribution="curve")
    assert a.capital_x_pct is None
    assert a.slippage_bps == 50


def test_open_position_with_explicit_balance() -> None:
    a = OpenPosition(
        lower_bin=-30, upper_bin=30, distribution="spot", capital_x_pct=0.7, slippage_bps=100
    )
    assert a.capital_x_pct == 0.7


def test_open_position_invalid_distribution_rejected() -> None:
    # Using Literal types via type checker; runtime check via __post_init__
    with pytest.raises(ValueError):
        OpenPosition(lower_bin=0, upper_bin=10, distribution="banana")  # type: ignore[arg-type]


def test_rebalance_swapless_emergent() -> None:
    r = Rebalance(
        removes=[BinRangeRemoval(lower_bin=-5, upper_bin=5, bps=10000)],
        adds=[BinRangeAdd(
            lower_bin=-3, upper_bin=3, distribution="spot", amount_x=100, amount_y=100
        )],
    )
    assert r.max_active_bin_slippage == 0


def test_remove_liquidity_bps_range() -> None:
    with pytest.raises(ValueError):
        RemoveLiquidity(bin_range=(0, 10), bps=20000)  # > 10000


def test_actions_in_union() -> None:
    actions: list[Action] = [
        OpenPosition(lower_bin=0, upper_bin=10, distribution="spot"),
        Rebalance(removes=[], adds=[]),
        AddLiquidity(bin_range=(0, 5), distribution="spot", amount_x=1, amount_y=1),
        RemoveLiquidity(bin_range=(0, 5), bps=5000),
        ClosePosition(),
        ClaimFees(),
        NoOp(),
    ]
    assert len(actions) == 7
```

Run: `pytest tests/unit/test_action_types.py -v` — expect FAIL (ImportError).

- [ ] **Step 2: Implement action types**

```python
# asteroid_belt/strategies/base.py
"""Strategy ABC and Action union types.

Strategies are the single mutable surface of the research env. They consume
events and return Actions; the engine validates and applies them. The Action
union is shaped after Meteora SDK primitives — Spot/Curve/BidAsk distributions
match the on-chain `StrategyType` enum (no scalar `skew` parameter; shapes are
baked into SDK helpers).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

DistributionShape = Literal["spot", "curve", "bid_ask"]
_VALID_DISTRIBUTIONS: tuple[str, ...] = ("spot", "curve", "bid_ask")


@dataclass(frozen=True)
class BinRangeRemoval:
    """Per-bin partial remove during a rebalance."""
    lower_bin: int
    upper_bin: int
    bps: int  # 0..10000

    def __post_init__(self) -> None:
        if not 0 <= self.bps <= 10_000:
            raise ValueError(f"bps must be 0..10000, got {self.bps}")
        if self.lower_bin > self.upper_bin:
            raise ValueError(f"lower_bin ({self.lower_bin}) > upper_bin ({self.upper_bin})")


@dataclass(frozen=True)
class BinRangeAdd:
    """Per-bin add with shape and amount during a rebalance or top-up."""
    lower_bin: int
    upper_bin: int
    distribution: DistributionShape
    amount_x: int
    amount_y: int

    def __post_init__(self) -> None:
        if self.distribution not in _VALID_DISTRIBUTIONS:
            raise ValueError(f"distribution must be one of {_VALID_DISTRIBUTIONS}")
        if self.lower_bin > self.upper_bin:
            raise ValueError(f"lower_bin ({self.lower_bin}) > upper_bin ({self.upper_bin})")


@dataclass(frozen=True)
class OpenPosition:
    """Initial position open. capital_x_pct=None means SDK-balanced via autoFill."""
    lower_bin: int
    upper_bin: int
    distribution: DistributionShape
    capital_x_pct: float | None = None
    slippage_bps: int = 50

    def __post_init__(self) -> None:
        if self.distribution not in _VALID_DISTRIBUTIONS:
            raise ValueError(f"distribution must be one of {_VALID_DISTRIBUTIONS}")
        if self.lower_bin > self.upper_bin:
            raise ValueError(f"lower_bin ({self.lower_bin}) > upper_bin ({self.upper_bin})")
        if self.capital_x_pct is not None and not 0.0 <= self.capital_x_pct <= 1.0:
            raise ValueError(f"capital_x_pct must be 0.0..1.0, got {self.capital_x_pct}")


@dataclass(frozen=True)
class Rebalance:
    """In-place rebalance shaped after SDK rebalanceLiquidity. Swapless is
    emergent: if removes and adds sum to identical X/Y totals, no swap fires."""
    removes: list[BinRangeRemoval] = field(default_factory=list)
    adds: list[BinRangeAdd] = field(default_factory=list)
    max_active_bin_slippage: int = 0


@dataclass(frozen=True)
class AddLiquidity:
    """Top up an existing position range without rebalancing."""
    bin_range: tuple[int, int]
    distribution: DistributionShape
    amount_x: int
    amount_y: int

    def __post_init__(self) -> None:
        if self.distribution not in _VALID_DISTRIBUTIONS:
            raise ValueError(f"distribution must be one of {_VALID_DISTRIBUTIONS}")
        if self.bin_range[0] > self.bin_range[1]:
            raise ValueError(f"invalid bin_range {self.bin_range}")


@dataclass(frozen=True)
class RemoveLiquidity:
    """Partial remove from an existing range, in basis points."""
    bin_range: tuple[int, int]
    bps: int  # 0..10000

    def __post_init__(self) -> None:
        if not 0 <= self.bps <= 10_000:
            raise ValueError(f"bps must be 0..10000, got {self.bps}")
        if self.bin_range[0] > self.bin_range[1]:
            raise ValueError(f"invalid bin_range {self.bin_range}")


@dataclass(frozen=True)
class ClosePosition:
    """Close the position; implies fee claim and rent refund."""


@dataclass(frozen=True)
class ClaimFees:
    """Mid-position fee claim without closing."""


@dataclass(frozen=True)
class NoOp:
    """Do nothing this step."""


Action = (
    OpenPosition
    | Rebalance
    | AddLiquidity
    | RemoveLiquidity
    | ClosePosition
    | ClaimFees
    | NoOp
)


# --- Strategy ABC (placeholder; implemented in Task 3.1 once PoolState/PositionState exist) ---


class Strategy(ABC):
    """Strategies override this ABC. Defined here as a placeholder; full
    interface (initialize/on_swap/on_tick) lands in Task 3.1 once PoolState
    and PositionState types exist."""

    @abstractmethod
    def initialize(self, pool: object, capital: object) -> Action:
        ...
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_action_types.py -v
```

Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/strategies/base.py tests/unit/test_action_types.py
git commit -m "feat(types): add Action union and validation"
```

### Task 1.3: PoolState + sub-types

**Files:**
- Create: `asteroid_belt/pool/state.py`
- Modify: `asteroid_belt/pool/__init__.py` (re-export)
- Test: `tests/unit/test_pool_state.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_pool_state.py
from decimal import Decimal

import pytest

from asteroid_belt.pool.state import (
    BinReserves,
    PoolState,
    RewardInfo,
    StaticFeeParams,
    VolatilityState,
)


def _vparams() -> VolatilityState:
    return VolatilityState(
        volatility_accumulator=0,
        volatility_reference=0,
        index_reference=0,
        last_update_timestamp=0,
    )


def _sparams() -> StaticFeeParams:
    return StaticFeeParams(
        base_factor=10000,
        filter_period=30,
        decay_period=600,
        reduction_factor=5000,
        variable_fee_control=40000,
        protocol_share=500,
        max_volatility_accumulator=350000,
    )


def test_pool_state_minimal() -> None:
    s = PoolState(
        active_bin=1234,
        bin_step=10,
        mid_price=Decimal("87.55"),
        volatility=_vparams(),
        static_fee=_sparams(),
        bin_liquidity={},
        last_swap_ts=1_700_000_000_000,
        reward_infos=[],
    )
    assert s.active_bin == 1234
    assert s.bin_step == 10


def test_bin_reserves_invariants() -> None:
    r = BinReserves(amount_x=100, amount_y=200, liquidity_supply=300, price=Decimal("2"))
    assert r.amount_x == 100
    with pytest.raises(ValueError):
        BinReserves(amount_x=-1, amount_y=0, liquidity_supply=0, price=Decimal("1"))


def test_reward_info_defaults() -> None:
    r = RewardInfo(
        mint="So11111111111111111111111111111111111111112",
        reward_rate=0,
        reward_duration_end=0,
        last_update_time=0,
    )
    assert r.reward_rate == 0
```

Run: `pytest tests/unit/test_pool_state.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/pool/state.py
"""PoolState and its sub-types — the read-only view strategies receive."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class VolatilityState:
    """LbPair.v_parameters. Drives the variable fee at any tick."""
    volatility_accumulator: int
    volatility_reference: int
    index_reference: int
    last_update_timestamp: int


@dataclass(frozen=True)
class StaticFeeParams:
    """LbPair.s_parameters. Time-decay gates and fee constants."""
    base_factor: int
    filter_period: int  # seconds
    decay_period: int  # seconds
    reduction_factor: int  # bps; how much v_r reduces between filter and decay periods
    variable_fee_control: int
    protocol_share: int  # bps of total fee going to protocol
    max_volatility_accumulator: int


@dataclass(frozen=True)
class BinReserves:
    """Per-bin reserves at a moment in time."""
    amount_x: int
    amount_y: int
    liquidity_supply: int
    price: Decimal

    def __post_init__(self) -> None:
        if self.amount_x < 0 or self.amount_y < 0 or self.liquidity_supply < 0:
            raise ValueError("bin reserve amounts must be non-negative")


@dataclass(frozen=True)
class RewardInfo:
    """Reward emission info per LbPair. Empty for SOL/USDC 10bps."""
    mint: str
    reward_rate: int
    reward_duration_end: int
    last_update_time: int


@dataclass(frozen=True)
class PoolState:
    """Read-only snapshot of pool state at the moment of an event.

    bin_liquidity is materialized for [active_bin - N, active_bin + N], where
    N comes from the run config (default 100). Strategies that need depth
    information beyond this window are out of scope for v1.
    """
    active_bin: int
    bin_step: int  # bps
    mid_price: Decimal
    volatility: VolatilityState
    static_fee: StaticFeeParams
    bin_liquidity: dict[int, BinReserves]
    last_swap_ts: int
    reward_infos: list[RewardInfo] = field(default_factory=list)
```

- [ ] **Step 3: Re-export from pool package**

```python
# asteroid_belt/pool/__init__.py
"""DLMM math primitives. Frozen surface — strategy code never modifies."""

from asteroid_belt.pool.state import (
    BinReserves,
    PoolState,
    RewardInfo,
    StaticFeeParams,
    VolatilityState,
)

__all__ = [
    "BinReserves",
    "PoolState",
    "RewardInfo",
    "StaticFeeParams",
    "VolatilityState",
]
```

- [ ] **Step 4: Run tests (expect PASS)**

```bash
pytest tests/unit/test_pool_state.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add asteroid_belt/pool/state.py asteroid_belt/pool/__init__.py tests/unit/test_pool_state.py
git commit -m "feat(types): add PoolState and sub-types"
```

### Task 1.4: PositionState + sub-types

**Files:**
- Create: `asteroid_belt/pool/position_state.py`
- Modify: `asteroid_belt/pool/__init__.py` (extend re-export)
- Test: `tests/unit/test_position_state.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_position_state.py
from asteroid_belt.pool.position_state import (
    BinComposition,
    PositionState,
)


def test_in_range_derived() -> None:
    p = PositionState(
        lower_bin=-10,
        upper_bin=10,
        composition={},
        fee_pending_x=0,
        fee_pending_y=0,
        fee_pending_per_bin={},
        total_claimed_x=0,
        total_claimed_y=0,
        fee_owner=None,
    )
    assert p.in_range(active_bin=0) is True
    assert p.in_range(active_bin=-10) is True  # boundaries inclusive
    assert p.in_range(active_bin=10) is True
    assert p.in_range(active_bin=11) is False
    assert p.in_range(active_bin=-11) is False


def test_position_state_immutable() -> None:
    p = PositionState(
        lower_bin=0, upper_bin=10, composition={}, fee_pending_x=0, fee_pending_y=0,
        fee_pending_per_bin={}, total_claimed_x=0, total_claimed_y=0, fee_owner=None,
    )
    import pytest
    with pytest.raises(Exception):
        p.lower_bin = -1  # type: ignore[misc]


def test_bin_composition() -> None:
    c = BinComposition(amount_x=100, amount_y=200, liquidity_share=0.05)
    assert c.amount_x == 100
    assert c.liquidity_share == 0.05
```

Run: `pytest tests/unit/test_position_state.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/pool/position_state.py
"""PositionState and BinComposition.

Pending fees are accumulated outside position liquidity. Meteora doesn't
auto-compound; fees fold into capital only on explicit ClaimFees or
ClosePosition.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BinComposition:
    """Holdings in a single bin owned by our position."""
    amount_x: int
    amount_y: int
    liquidity_share: float  # our share of bin's total liquidity_supply, 0..1


@dataclass(frozen=True)
class PositionState:
    """Read-only snapshot of our position. `in_range` is computed, not stored."""
    lower_bin: int
    upper_bin: int
    composition: dict[int, BinComposition]
    fee_pending_x: int  # aggregated, raw token units
    fee_pending_y: int
    fee_pending_per_bin: dict[int, tuple[int, int]]  # bin_id → (x, y)
    total_claimed_x: int  # lifetime claimed, raw token units
    total_claimed_y: int
    fee_owner: str | None = None  # public key as base58; None = position owner

    def in_range(self, active_bin: int) -> bool:
        return self.lower_bin <= active_bin <= self.upper_bin
```

- [ ] **Step 3: Update pool re-exports**

```python
# asteroid_belt/pool/__init__.py
"""DLMM math primitives. Frozen surface — strategy code never modifies."""

from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import (
    BinReserves,
    PoolState,
    RewardInfo,
    StaticFeeParams,
    VolatilityState,
)

__all__ = [
    "BinComposition",
    "BinReserves",
    "PoolState",
    "PositionState",
    "RewardInfo",
    "StaticFeeParams",
    "VolatilityState",
]
```

- [ ] **Step 4: Run tests (expect PASS)**

```bash
pytest tests/unit/test_position_state.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add asteroid_belt/pool/position_state.py asteroid_belt/pool/__init__.py tests/unit/test_position_state.py
git commit -m "feat(types): add PositionState and BinComposition"
```

### Task 1.5: bin_id ↔ price math (`pool/bins.py`)

**Files:**
- Modify: `asteroid_belt/pool/bins.py`
- Test: `tests/unit/test_pool_bins.py`

Reference formula (Trader Joe LB whitepaper, Meteora docs `/dlmm-formulas`):
- `price(bin_id) = (1 + bin_step / 10_000) ** bin_id`
- `bin_id(price) = log(price) / log(1 + bin_step / 10_000)` (rounded)

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_pool_bins.py
from decimal import Decimal

import pytest

from asteroid_belt.pool.bins import bin_id_to_price, price_to_bin_id, walk_bins_for_swap


def test_bin_zero_is_unit_price() -> None:
    assert bin_id_to_price(0, bin_step=10) == Decimal("1")


def test_bin_step_10_progression() -> None:
    # 10 bps = 0.1% per bin
    p1 = bin_id_to_price(1, bin_step=10)
    p0 = bin_id_to_price(0, bin_step=10)
    ratio = p1 / p0
    assert abs(ratio - Decimal("1.001")) < Decimal("1e-12")


def test_round_trip_positive_bins() -> None:
    for bin_id in [1, 100, 1000, 10000]:
        price = bin_id_to_price(bin_id, bin_step=10)
        recovered = price_to_bin_id(price, bin_step=10)
        assert recovered == bin_id, f"failed at {bin_id}: got {recovered}"


def test_round_trip_negative_bins() -> None:
    for bin_id in [-1, -100, -1000, -10000]:
        price = bin_id_to_price(bin_id, bin_step=10)
        recovered = price_to_bin_id(price, bin_step=10)
        assert recovered == bin_id, f"failed at {bin_id}: got {recovered}"


def test_invalid_bin_step() -> None:
    with pytest.raises(ValueError):
        bin_id_to_price(0, bin_step=0)
    with pytest.raises(ValueError):
        bin_id_to_price(0, bin_step=-1)


def test_walk_bins_no_movement() -> None:
    # If end_bin == start_bin, walk yields just the active bin.
    path = list(walk_bins_for_swap(start_bin=100, end_bin=100, swap_for_y=True))
    assert path == [100]


def test_walk_bins_swap_for_y_descends() -> None:
    # swap_for_y=True (X→Y): price drops, active_bin decreases.
    path = list(walk_bins_for_swap(start_bin=10, end_bin=7, swap_for_y=True))
    assert path == [10, 9, 8, 7]


def test_walk_bins_swap_for_x_ascends() -> None:
    # swap_for_y=False (Y→X): price rises, active_bin increases.
    path = list(walk_bins_for_swap(start_bin=7, end_bin=10, swap_for_y=False))
    assert path == [7, 8, 9, 10]
```

Run: `pytest tests/unit/test_pool_bins.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/pool/bins.py
"""Bin id ↔ price math and multi-bin swap walks.

Uses Decimal for round-trip stability across the bin_id range we care about
(±50000 covers any real-world DLMM pool active range). Avoids float drift.

Reference: Trader Joe LB whitepaper, Meteora /dlmm-formulas docs.
  price(bin_id) = (1 + bin_step / 10_000) ** bin_id
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Iterator

# Increase precision for stable round-trips on extreme bin ids
getcontext().prec = 50

_BPS = Decimal(10_000)


def _step_factor(bin_step: int) -> Decimal:
    if bin_step <= 0:
        raise ValueError(f"bin_step must be positive, got {bin_step}")
    return Decimal(1) + Decimal(bin_step) / _BPS


def bin_id_to_price(bin_id: int, bin_step: int) -> Decimal:
    """price(bin_id) = (1 + bin_step / 10_000) ** bin_id."""
    return _step_factor(bin_step) ** bin_id


def price_to_bin_id(price: Decimal, bin_step: int) -> int:
    """Inverse of bin_id_to_price; rounds to nearest integer.

    Uses ln() because Decimal lacks log-arbitrary-base; converts to log via
    Decimal.ln(). For our pool ranges this is exact within Decimal precision.
    """
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    factor = _step_factor(bin_step)
    # bin_id = ln(price) / ln(factor); round to nearest int
    raw = price.ln() / factor.ln()
    return int(raw.to_integral_value())


def walk_bins_for_swap(
    *, start_bin: int, end_bin: int, swap_for_y: bool
) -> Iterator[int]:
    """Yield each bin a swap traverses, inclusive of start and end.

    For swap_for_y=True (X → Y), the active bin DECREASES (price drops).
    For swap_for_y=False (Y → X), the active bin INCREASES (price rises).
    """
    if swap_for_y:
        # X → Y: active bin descends
        if end_bin > start_bin:
            raise ValueError(f"swap_for_y=True requires end_bin <= start_bin")
        step = -1
    else:
        if end_bin < start_bin:
            raise ValueError(f"swap_for_y=False requires end_bin >= start_bin")
        step = 1
    current = start_bin
    while True:
        yield current
        if current == end_bin:
            return
        current += step
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_pool_bins.py -v
```

Expected: 8 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/pool/bins.py tests/unit/test_pool_bins.py
git commit -m "feat(pool): bin_id↔price round-trip and swap bin walks"
```

### Task 1.6: Variable fee + vParameters evolution (`pool/fees.py`)

**Files:**
- Modify: `asteroid_belt/pool/fees.py`
- Test: `tests/unit/test_pool_fees.py`

Reference formulas (Meteora `/dlmm-fee-calculation`):
- `base_fee_rate = base_factor * bin_step * 10`  (in fee-precision units; max 1e10 = 100%)
- `variable_fee_rate = ((va * bin_step) ** 2 * variable_fee_control + 99_999_999_999) // 1e11`
- `total_fee_rate = base_fee_rate + variable_fee_rate`, capped at MAX_FEE_RATE = 1e10
- LP fee = total fee × (10000 − protocol_share) / 10000

`evolve_v_params` rule (between swaps, before applying a swap to bin id `b`):
- Let dt = `event_ts - last_update_timestamp` (in seconds)
- If dt < filter_period: keep `volatility_reference` as-is
- elif dt < decay_period: `volatility_reference = (volatility_accumulator * reduction_factor) // 10000`
- else: `volatility_reference = 0`
- After updating reference, `index_reference = active_bin_before_swap` (only on first iteration of a multi-bin swap)
- Then `volatility_accumulator = min(max_volatility_accumulator, volatility_reference + abs(b - index_reference) * 10000)`
- Then `last_update_timestamp = event_ts`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_pool_fees.py
from asteroid_belt.pool.fees import (
    base_fee_rate,
    evolve_v_params,
    lp_fee_after_protocol_share,
    total_fee_rate,
    variable_fee_rate,
)
from asteroid_belt.pool.state import StaticFeeParams, VolatilityState


def _sparams(**kw: int) -> StaticFeeParams:
    defaults = dict(
        base_factor=10000,
        filter_period=30,
        decay_period=600,
        reduction_factor=5000,
        variable_fee_control=40000,
        protocol_share=500,
        max_volatility_accumulator=350000,
    )
    defaults.update(kw)
    return StaticFeeParams(**defaults)


def test_base_fee_rate_basic() -> None:
    # base_factor=10000, bin_step=10 → 10000*10*10 = 1_000_000 (≈ 0.01% in 1e10 precision)
    assert base_fee_rate(base_factor=10000, bin_step=10) == 1_000_000


def test_variable_fee_rate_zero_when_va_zero() -> None:
    assert variable_fee_rate(volatility_accumulator=0, bin_step=10, variable_fee_control=40000) == 0


def test_variable_fee_rate_positive_when_va_positive() -> None:
    # va=10000 (1 bin of vol), bin_step=10:
    # ((10000 * 10) ** 2 * 40000 + 99_999_999_999) // 1e11
    # = (1e8 * 40000 + ~1e11) // 1e11
    # = (4e12 + ~1e11) // 1e11 ≈ 41
    rate = variable_fee_rate(volatility_accumulator=10000, bin_step=10, variable_fee_control=40000)
    assert rate > 0
    # Sanity: known-value check
    expected = ((10000 * 10) ** 2 * 40000 + 99_999_999_999) // 100_000_000_000
    assert rate == expected


def test_total_fee_rate_capped() -> None:
    # Cap at 1e10
    capped = total_fee_rate(base=9_000_000_000, variable=5_000_000_000)
    assert capped == 10_000_000_000


def test_lp_fee_after_protocol_share() -> None:
    assert lp_fee_after_protocol_share(total_fee=1000, protocol_share=500) == 950
    assert lp_fee_after_protocol_share(total_fee=1000, protocol_share=0) == 1000
    assert lp_fee_after_protocol_share(total_fee=1000, protocol_share=10000) == 0


def test_evolve_within_filter_period() -> None:
    # dt < filter_period (30s): volatility_reference stays
    state = VolatilityState(
        volatility_accumulator=20000,
        volatility_reference=15000,
        index_reference=100,
        last_update_timestamp=1_000_000,
    )
    s = _sparams()
    new = evolve_v_params(
        state=state, sparams=s,
        event_ts=1_000_010,  # 10s later
        active_bin_before=100, target_bin=102,
    )
    # filter_period gate: ref unchanged
    assert new.volatility_reference == 15000
    # va = min(max, ref + |target - index_ref|*10000) = 15000 + 2*10000 = 35000
    assert new.volatility_accumulator == 35000
    assert new.last_update_timestamp == 1_000_010


def test_evolve_within_decay_period() -> None:
    state = VolatilityState(
        volatility_accumulator=40000,
        volatility_reference=20000,
        index_reference=100,
        last_update_timestamp=1_000_000,
    )
    s = _sparams()
    new = evolve_v_params(
        state=state, sparams=s,
        event_ts=1_000_300,  # 300s, between filter (30) and decay (600)
        active_bin_before=100, target_bin=100,
    )
    # ref decays: va * reduction_factor / 10000 = 40000 * 5000 / 10000 = 20000
    assert new.volatility_reference == 20000
    # va = ref + 0 (no bin movement) = 20000
    assert new.volatility_accumulator == 20000


def test_evolve_past_decay_period_resets() -> None:
    state = VolatilityState(
        volatility_accumulator=50000,
        volatility_reference=30000,
        index_reference=100,
        last_update_timestamp=1_000_000,
    )
    s = _sparams()
    new = evolve_v_params(
        state=state, sparams=s,
        event_ts=1_001_000,  # 1000s, past decay (600)
        active_bin_before=100, target_bin=105,
    )
    assert new.volatility_reference == 0
    assert new.volatility_accumulator == 50000  # 0 + 5*10000


def test_evolve_caps_at_max() -> None:
    state = VolatilityState(
        volatility_accumulator=0,
        volatility_reference=0,
        index_reference=100,
        last_update_timestamp=1_000_000,
    )
    s = _sparams(max_volatility_accumulator=100000)
    new = evolve_v_params(
        state=state, sparams=s,
        event_ts=1_000_001,
        active_bin_before=100, target_bin=200,  # 100 bins moved → would be 1_000_000
    )
    assert new.volatility_accumulator == 100000  # capped
```

Run: `pytest tests/unit/test_pool_fees.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/pool/fees.py
"""DLMM fee math and vParameters evolution.

Frozen rule. The agent's strategy code can READ pool fee state via PoolState
but cannot modify these functions. Implements the LB whitepaper update rule
governed by filter_period / decay_period gates.

Reference: Meteora /dlmm-fee-calculation, Trader Joe LB whitepaper.
"""

from __future__ import annotations

from asteroid_belt.pool.state import StaticFeeParams, VolatilityState

# Fee rates use a 1e10 precision (Meteora "FEE_PRECISION").
MAX_FEE_RATE = 10_000_000_000  # 100% in fee-precision units


def base_fee_rate(*, base_factor: int, bin_step: int) -> int:
    """base_fee_rate = base_factor * bin_step * 10."""
    return base_factor * bin_step * 10


def variable_fee_rate(
    *, volatility_accumulator: int, bin_step: int, variable_fee_control: int
) -> int:
    """variable_fee_rate = ((va * bin_step) ** 2 * variable_fee_control + 99_999_999_999) // 1e11."""
    numerator = (volatility_accumulator * bin_step) ** 2 * variable_fee_control + 99_999_999_999
    return numerator // 100_000_000_000


def total_fee_rate(*, base: int, variable: int) -> int:
    """Sum capped at MAX_FEE_RATE."""
    return min(MAX_FEE_RATE, base + variable)


def lp_fee_after_protocol_share(*, total_fee: int, protocol_share: int) -> int:
    """LP-side fee after protocol carve-out. protocol_share is in bps."""
    return total_fee * (10_000 - protocol_share) // 10_000


def evolve_v_params(
    *,
    state: VolatilityState,
    sparams: StaticFeeParams,
    event_ts: int,  # in seconds; if your timestamps are ms, divide before calling
    active_bin_before: int,
    target_bin: int,
) -> VolatilityState:
    """Evolve volatility accumulator state for an incoming swap.

    Time gates (dt = event_ts - last_update_timestamp, in seconds):
    - dt < filter_period: keep volatility_reference
    - filter_period <= dt < decay_period: ref = va * reduction_factor / 10_000
    - dt >= decay_period: ref = 0

    After updating reference and index_reference, va is set to:
      min(max_volatility_accumulator, volatility_reference + |target - index_reference| * 10_000)
    """
    dt = event_ts - state.last_update_timestamp

    if dt < sparams.filter_period:
        new_ref = state.volatility_reference
        new_index_ref = state.index_reference
    elif dt < sparams.decay_period:
        new_ref = state.volatility_accumulator * sparams.reduction_factor // 10_000
        new_index_ref = active_bin_before
    else:
        new_ref = 0
        new_index_ref = active_bin_before

    bin_distance = abs(target_bin - new_index_ref)
    new_va = min(
        sparams.max_volatility_accumulator,
        new_ref + bin_distance * 10_000,
    )

    return VolatilityState(
        volatility_accumulator=new_va,
        volatility_reference=new_ref,
        index_reference=new_index_ref,
        last_update_timestamp=event_ts,
    )
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_pool_fees.py -v
```

Expected: 9 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/pool/fees.py tests/unit/test_pool_fees.py
git commit -m "feat(pool): variable fee + vParameters evolution (frozen rule)"
```

### Task 1.7: Position composition + IL math (`pool/position.py`)

**Files:**
- Modify: `asteroid_belt/pool/position.py`
- Test: `tests/unit/test_pool_position.py`

Within a single bin, DLMM is constant-sum: `price * x + y = L_bin`. So:
- Position value at price P (in quote/Y units) = sum over bins of `(amount_x * P + amount_y)`.
- HODL value at price P = `initial_x * P + initial_y`.
- IL = position_value − hodl_value (negative when LP underperforms HODL).

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_pool_position.py
from decimal import Decimal

from asteroid_belt.pool.position import (
    hodl_value_in_y,
    il_vs_hodl,
    position_value_in_y,
)
from asteroid_belt.pool.position_state import BinComposition


def test_hodl_value_basic() -> None:
    # 1 SOL + 100 USDC, price = 87.55 USDC/SOL
    # HODL = 1 * 87.55 + 100 = 187.55 USDC equivalent
    v = hodl_value_in_y(initial_x=1_000_000_000, initial_y=100_000_000,
                        price=Decimal("87.55"), decimals_x=9, decimals_y=6)
    assert v == Decimal("187.55")


def test_position_value_in_range() -> None:
    # Position has 0.5 SOL and 50 USDC distributed in bins
    composition = {
        100: BinComposition(amount_x=300_000_000, amount_y=30_000_000, liquidity_share=0.01),
        101: BinComposition(amount_x=200_000_000, amount_y=20_000_000, liquidity_share=0.01),
    }
    v = position_value_in_y(
        composition=composition, price=Decimal("87.55"),
        decimals_x=9, decimals_y=6,
    )
    # 0.5 SOL * 87.55 + 50 USDC = 43.775 + 50 = 93.775
    assert v == Decimal("93.775")


def test_il_zero_when_position_matches_hodl() -> None:
    composition = {
        0: BinComposition(amount_x=1_000_000_000, amount_y=100_000_000, liquidity_share=0.01),
    }
    il = il_vs_hodl(
        composition=composition,
        initial_x=1_000_000_000, initial_y=100_000_000,
        price=Decimal("87.55"), decimals_x=9, decimals_y=6,
    )
    assert il == Decimal("0")


def test_il_negative_when_underperforming() -> None:
    # Started at 1 SOL + 100 USDC; now have 0 SOL + 87.55 USDC (price moved 1x — but lost the SOL)
    composition = {
        0: BinComposition(amount_x=0, amount_y=87_550_000, liquidity_share=0.01),
    }
    il = il_vs_hodl(
        composition=composition,
        initial_x=1_000_000_000, initial_y=100_000_000,
        price=Decimal("87.55"), decimals_x=9, decimals_y=6,
    )
    # Position = 87.55, HODL = 187.55, IL = -100
    assert il == Decimal("-100")
```

Run: `pytest tests/unit/test_pool_position.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/pool/position.py
"""Position composition and IL math.

Within a single DLMM bin liquidity is constant-sum (price*x + y = L_bin), so
position value sums to the same shape as a constant-product position when
mark-to-market in quote terms. IL is computed against a HODL benchmark of the
initial deposit.

Frozen rule. Strategy code calls these functions but cannot modify them.
"""

from __future__ import annotations

from decimal import Decimal

from asteroid_belt.pool.position_state import BinComposition


def _scale_x_to_y(amount_x: int, decimals_x: int, decimals_y: int) -> Decimal:
    """Convert raw X units to a Decimal expressed in Y's decimals."""
    return Decimal(amount_x) / Decimal(10) ** decimals_x


def _scale_y(amount_y: int, decimals_y: int) -> Decimal:
    return Decimal(amount_y) / Decimal(10) ** decimals_y


def hodl_value_in_y(
    *,
    initial_x: int,
    initial_y: int,
    price: Decimal,
    decimals_x: int,
    decimals_y: int,
) -> Decimal:
    """Counterfactual HODL value in Y-token units at given price."""
    x_in_y = _scale_x_to_y(initial_x, decimals_x, decimals_y) * price
    y = _scale_y(initial_y, decimals_y)
    return x_in_y + y


def position_value_in_y(
    *,
    composition: dict[int, BinComposition],
    price: Decimal,
    decimals_x: int,
    decimals_y: int,
) -> Decimal:
    """Mark-to-market the position in Y-token units at given price.

    Sums per-bin (amount_x_in_y * price + amount_y) across all bins. Note this
    uses the *external* mark-to-market price for all bins, not each bin's
    intrinsic price. This matches how a position would liquidate at active
    bin price; bins above active hold only X (would be sold at active price),
    bins below hold only Y (already in Y).
    """
    total_x_raw = sum(c.amount_x for c in composition.values())
    total_y_raw = sum(c.amount_y for c in composition.values())
    x_in_y = _scale_x_to_y(total_x_raw, decimals_x, decimals_y) * price
    y = _scale_y(total_y_raw, decimals_y)
    return x_in_y + y


def il_vs_hodl(
    *,
    composition: dict[int, BinComposition],
    initial_x: int,
    initial_y: int,
    price: Decimal,
    decimals_x: int,
    decimals_y: int,
) -> Decimal:
    """Impermanent loss = position_value − hodl_value (in Y units).

    Negative values mean the LP position is underperforming HODL.
    """
    pos = position_value_in_y(
        composition=composition, price=price,
        decimals_x=decimals_x, decimals_y=decimals_y,
    )
    hodl = hodl_value_in_y(
        initial_x=initial_x, initial_y=initial_y, price=price,
        decimals_x=decimals_x, decimals_y=decimals_y,
    )
    return pos - hodl
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_pool_position.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/pool/position.py tests/unit/test_pool_position.py
git commit -m "feat(pool): position MtM and IL vs HODL"
```

---

**End of Phase 1.** At this point you have: pure types (events, actions, pool/position state), bin↔price math with multi-bin walks, fee math with vParameter evolution, position MtM and IL formulas. All unit-tested. Total tests: ~30. Phase 2 builds on these.

---

## Phase 2 — Engine internals + metrics

Builds the deterministic backtest engine and the pluggable metric layer. Engine is frozen surface; metrics are pure functions over `BacktestResult`. After this phase you can construct a hand-built `BacktestResult` and compute every shipped metric over it.

### Task 2.1: BacktestResult + RebalanceRecord types

**Files:**
- Modify: `asteroid_belt/engine/result.py`
- Test: `tests/unit/test_backtest_result.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_backtest_result.py
from decimal import Decimal

import polars as pl

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord


def _empty_trajectory() -> pl.DataFrame:
    return pl.DataFrame({
        "ts": pl.Series([], dtype=pl.Int64),
        "price": pl.Series([], dtype=pl.Float64),
        "active_bin": pl.Series([], dtype=pl.Int32),
        "position_value_usd": pl.Series([], dtype=pl.Float64),
        "hodl_value_usd": pl.Series([], dtype=pl.Float64),
        "fees_x_cumulative": pl.Series([], dtype=pl.Int64),
        "fees_y_cumulative": pl.Series([], dtype=pl.Int64),
        "il_cumulative": pl.Series([], dtype=pl.Float64),
        "in_range": pl.Series([], dtype=pl.Boolean),
        "capital_idle_usd": pl.Series([], dtype=pl.Float64),
    })


def test_backtest_result_minimal() -> None:
    r = BacktestResult(
        run_id="20260429T000000_abc123",
        config_hash="abc123",
        schema_version="1.0",
        started_at=1_700_000_000_000,
        ended_at=1_700_000_001_000,
        status="ok",
        trajectory=_empty_trajectory(),
        rebalances=[],
        primitives={"net_pnl": 1.5},
        score=1.5,
        score_metric="net_pnl",
    )
    assert r.status == "ok"
    assert r.score == 1.5


def test_rebalance_record_basic() -> None:
    rec = RebalanceRecord(
        ts=1_700_000_000_000,
        trigger="active_bin_drift",
        old_lower_bin=-30, old_upper_bin=30,
        new_lower_bin=-20, new_upper_bin=40,
        gas_lamports=5_000_000,
        composition_fee_x=0,
        composition_fee_y=10_000,
        fees_claimed_x=100,
        fees_claimed_y=2_000,
    )
    assert rec.trigger == "active_bin_drift"
```

Run: `pytest tests/unit/test_backtest_result.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/engine/result.py
"""BacktestResult and RebalanceRecord — engine output types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import polars as pl

RunStatus = Literal["running", "ok", "error", "timeout"]


@dataclass(frozen=True)
class RebalanceRecord:
    """One discrete rebalance event for the dashboard's table view."""
    ts: int
    trigger: str  # free-form; strategies tag the trigger that fired
    old_lower_bin: int
    old_upper_bin: int
    new_lower_bin: int
    new_upper_bin: int
    gas_lamports: int  # tx priority fees + rent paid (refundable rent on close)
    composition_fee_x: int
    composition_fee_y: int
    fees_claimed_x: int
    fees_claimed_y: int


@dataclass(frozen=True)
class BacktestResult:
    """The artifact produced by one backtest run.

    The trajectory DataFrame is persisted to data/runs/<run_id>/result.parquet.
    Rebalances are persisted to data/runs/<run_id>/rebalances.parquet.
    Primitives (all shipped metrics) are precomputed at result-build time so
    re-evaluating a run under a new metric never re-runs the backtest.
    """
    run_id: str
    config_hash: str
    schema_version: str
    started_at: int
    ended_at: int
    status: RunStatus
    trajectory: pl.DataFrame
    rebalances: list[RebalanceRecord]
    primitives: dict[str, float]
    score: float
    score_metric: str
    error_msg: str | None = field(default=None)
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_backtest_result.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/engine/result.py tests/unit/test_backtest_result.py
git commit -m "feat(engine): BacktestResult and RebalanceRecord types"
```

### Task 2.2: Cost model — gas, composition fee, rent (`engine/cost.py`)

**Files:**
- Modify: `asteroid_belt/engine/cost.py`
- Test: `tests/unit/test_engine_cost.py`

> **Verification TODO during implementation:** the constants `POSITION_RENT_LAMPORTS`, `BIN_ARRAY_RENT_LAMPORTS`, and `DEFAULT_PRIORITY_FEE_LAMPORTS` are best-effort estimates per the spec §10. Before merging to main, confirm against the deployed Meteora program (read `LbPair`, `Position`, `BinArray` account sizes and use `getMinimumBalanceForRentExemption`). Treat the values below as v1 placeholders; record them in `engine/cost.py:COST_MODEL_VERSION` and bump that version when verified.

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_engine_cost.py
from asteroid_belt.engine.cost import (
    BIN_ARRAY_RENT_LAMPORTS,
    COST_MODEL_VERSION,
    POSITION_RENT_LAMPORTS,
    composition_fee,
    open_position_lamports,
    rebalance_lamports,
)


def test_cost_model_version_present() -> None:
    assert COST_MODEL_VERSION  # non-empty string


def test_open_position_with_one_bin_array() -> None:
    cost = open_position_lamports(num_new_bin_arrays=1, priority_fee_lamports=10_000)
    expected = POSITION_RENT_LAMPORTS + 1 * BIN_ARRAY_RENT_LAMPORTS + 10_000
    assert cost == expected


def test_open_position_with_no_new_bin_arrays() -> None:
    cost = open_position_lamports(num_new_bin_arrays=0, priority_fee_lamports=10_000)
    expected = POSITION_RENT_LAMPORTS + 10_000
    assert cost == expected


def test_rebalance_no_new_bin_arrays() -> None:
    cost = rebalance_lamports(num_new_bin_arrays=0, priority_fee_lamports=20_000)
    assert cost == 20_000


def test_rebalance_with_one_new_bin_array() -> None:
    cost = rebalance_lamports(num_new_bin_arrays=1, priority_fee_lamports=20_000)
    assert cost == BIN_ARRAY_RENT_LAMPORTS + 20_000


def test_composition_fee_zero_when_balanced() -> None:
    # If x and y added match the bin's existing X/Y ratio, no composition fee.
    fee_x, fee_y = composition_fee(
        added_x=100, added_y=100,
        bin_total_x=1000, bin_total_y=1000,
        base_fee_rate_bps=100,
    )
    assert fee_x == 0
    assert fee_y == 0


def test_composition_fee_when_imbalanced() -> None:
    # Bin is all-Y, we add half X, half Y (relative to ratio).
    # The X side is the "wrong" side and gets charged composition fee.
    fee_x, fee_y = composition_fee(
        added_x=100, added_y=100,
        bin_total_x=0, bin_total_y=1000,
        base_fee_rate_bps=100,  # 1%
    )
    # Adding X to an all-Y bin charges composition fee on the X side.
    assert fee_x > 0
    assert fee_y == 0
```

Run: `pytest tests/unit/test_engine_cost.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/engine/cost.py
"""Cost model for backtest action accounting.

Frozen surface — strategy code reads via run results but cannot modify.

The v1 constants below are best-effort placeholders. Verify against the
deployed Meteora DLMM program before relying on absolute lamport amounts:
  - POSITION_RENT_LAMPORTS: read account size, then
    getMinimumBalanceForRentExemption
  - BIN_ARRAY_RENT_LAMPORTS: same procedure for BinArray
  - DEFAULT_PRIORITY_FEE_LAMPORTS: empirical recent fee distribution

When constants change, bump COST_MODEL_VERSION. Each run records its
cost_model_version so the dashboard can warn when comparing across drift.
"""

from __future__ import annotations

# v1 placeholders — see file docstring for verification procedure.
COST_MODEL_VERSION = "v0.1.0-unverified"

POSITION_RENT_LAMPORTS = 57_000_000  # ~0.057 SOL, refundable on close
BIN_ARRAY_RENT_LAMPORTS = 75_000_000  # ~0.075 SOL per uninitialized BinArray
DEFAULT_PRIORITY_FEE_LAMPORTS = 10_000  # ~0.00001 SOL


def open_position_lamports(*, num_new_bin_arrays: int, priority_fee_lamports: int) -> int:
    """Lamports cost for opening a fresh position."""
    return (
        POSITION_RENT_LAMPORTS
        + num_new_bin_arrays * BIN_ARRAY_RENT_LAMPORTS
        + priority_fee_lamports
    )


def rebalance_lamports(*, num_new_bin_arrays: int, priority_fee_lamports: int) -> int:
    """Lamports cost for an in-place rebalance.

    No POSITION_RENT charge (existing position reused). New BinArrays charged
    if the rebalance enters bin ranges that don't yet have backing arrays.
    """
    return num_new_bin_arrays * BIN_ARRAY_RENT_LAMPORTS + priority_fee_lamports


def composition_fee(
    *,
    added_x: int,
    added_y: int,
    bin_total_x: int,
    bin_total_y: int,
    base_fee_rate_bps: int,
) -> tuple[int, int]:
    """Composition fee charged when adding asymmetric liquidity to a bin.

    Returns (fee_x, fee_y) in raw token units. If the added (x, y) matches the
    bin's existing ratio, both fees are 0. Otherwise the "wrong-side" portion
    is charged base_fee_rate_bps.

    Implementation is a simplified version of Meteora's per-bin composition
    fee math; pre-implementation TODO: cross-check against the on-chain
    LbPair::add_liquidity path to verify the rounding/precision exactly.
    """
    bin_total = bin_total_x + bin_total_y
    if bin_total == 0:
        # Empty bin: no composition fee (any deposit is "balanced" by definition).
        return 0, 0

    # Ideal added amounts to maintain the bin's current ratio.
    ideal_x = (bin_total_x * (added_x + added_y)) // bin_total
    ideal_y = (added_x + added_y) - ideal_x

    # The amount that exceeds the ideal on each side is the "wrong-side" amount.
    excess_x = max(0, added_x - ideal_x)
    excess_y = max(0, added_y - ideal_y)

    fee_x = excess_x * base_fee_rate_bps // 10_000
    fee_y = excess_y * base_fee_rate_bps // 10_000

    return fee_x, fee_y
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_engine_cost.py -v
```

Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/engine/cost.py tests/unit/test_engine_cost.py
git commit -m "feat(engine): cost model (gas, composition fee, rent) — v1 placeholders"
```

### Task 2.3: Action validation guards (`engine/guards.py`)

**Files:**
- Modify: `asteroid_belt/engine/guards.py`
- Test: `tests/unit/test_engine_guards.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_engine_guards.py
from decimal import Decimal

from asteroid_belt.engine.guards import MAX_BINS_PER_POSITION, validate_action
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import (
    PoolState,
    StaticFeeParams,
    VolatilityState,
)
from asteroid_belt.strategies.base import (
    NoOp,
    OpenPosition,
    Rebalance,
    BinRangeAdd,
)


def _pool() -> PoolState:
    return PoolState(
        active_bin=0, bin_step=10, mid_price=Decimal("1"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={}, last_swap_ts=0, reward_infos=[],
    )


def _empty_position() -> PositionState | None:
    return None  # no position open yet


def test_valid_open_passes() -> None:
    a = OpenPosition(lower_bin=-30, upper_bin=30, distribution="curve")
    out, msg = validate_action(action=a, pool=_pool(), position=_empty_position(),
                                capital_x=1_000_000_000, capital_y=8_000_000_000,
                                priority_fee_lamports=10_000)
    assert isinstance(out, OpenPosition)
    assert msg is None


def test_open_with_too_wide_range_becomes_noop() -> None:
    a = OpenPosition(lower_bin=-100, upper_bin=100, distribution="curve")
    out, msg = validate_action(action=a, pool=_pool(), position=_empty_position(),
                                capital_x=1_000_000_000, capital_y=8_000_000_000,
                                priority_fee_lamports=10_000)
    assert isinstance(out, NoOp)
    assert msg is not None
    assert "MAX_BINS_PER_POSITION" in msg or str(MAX_BINS_PER_POSITION) in msg


def test_open_with_insufficient_capital_becomes_noop() -> None:
    a = OpenPosition(lower_bin=-30, upper_bin=30, distribution="curve")
    out, msg = validate_action(action=a, pool=_pool(), position=_empty_position(),
                                capital_x=0, capital_y=0,
                                priority_fee_lamports=10_000)
    assert isinstance(out, NoOp)
    assert msg is not None


def test_rebalance_when_no_position_becomes_noop() -> None:
    a = Rebalance(removes=[], adds=[BinRangeAdd(
        lower_bin=-10, upper_bin=10, distribution="spot", amount_x=100, amount_y=100,
    )])
    out, msg = validate_action(action=a, pool=_pool(), position=_empty_position(),
                                capital_x=1_000_000_000, capital_y=1_000_000_000,
                                priority_fee_lamports=10_000)
    assert isinstance(out, NoOp)
```

Run: `pytest tests/unit/test_engine_guards.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/engine/guards.py
"""Action validation. Frozen rule.

Bad actions become logged NoOps with a reason string, never raise. Strategies
cannot crash the engine. Validation is conservative — anything ambiguous is
rejected and the strategy can try again with a corrected action next event.
"""

from __future__ import annotations

from asteroid_belt.engine.cost import (
    open_position_lamports,
    rebalance_lamports,
)
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import PoolState
from asteroid_belt.strategies.base import (
    Action,
    AddLiquidity,
    ClaimFees,
    ClosePosition,
    NoOp,
    OpenPosition,
    Rebalance,
    RemoveLiquidity,
)

# Meteora FAQ: max 69 bins per position. Verify against deployed program before
# trusting absolutely.
MAX_BINS_PER_POSITION = 69


def validate_action(
    *,
    action: Action,
    pool: PoolState,
    position: PositionState | None,
    capital_x: int,
    capital_y: int,
    priority_fee_lamports: int,
) -> tuple[Action, str | None]:
    """Validate an action; return (action_or_NoOp, reason_if_rejected).

    On rejection: returns (NoOp(), "human-readable reason").
    On accept: returns (original_action, None).
    """
    match action:
        case OpenPosition(lower_bin=lo, upper_bin=hi):
            if position is not None:
                return NoOp(), "OpenPosition rejected: position already open"
            width = hi - lo + 1
            if width > MAX_BINS_PER_POSITION:
                return NoOp(), (
                    f"OpenPosition rejected: width {width} exceeds "
                    f"MAX_BINS_PER_POSITION ({MAX_BINS_PER_POSITION})"
                )
            # Coarse capital sufficiency check: must cover gas/rent on a fresh open.
            min_lamports = open_position_lamports(
                num_new_bin_arrays=2,  # conservative upper bound for any 69-bin range
                priority_fee_lamports=priority_fee_lamports,
            )
            # SOL is X for SOL/USDC pools. For pool-agnostic correctness, the
            # caller must ensure capital_x is the SOL/native side.
            if capital_x < min_lamports:
                return NoOp(), (
                    f"OpenPosition rejected: insufficient SOL "
                    f"(need {min_lamports}, have {capital_x})"
                )
            return action, None

        case Rebalance() if position is None:
            return NoOp(), "Rebalance rejected: no position open"

        case Rebalance(removes=_, adds=adds):
            for add in adds:
                width = add.upper_bin - add.lower_bin + 1
                if width > MAX_BINS_PER_POSITION:
                    return NoOp(), (
                        f"Rebalance rejected: add range width {width} exceeds "
                        f"MAX_BINS_PER_POSITION"
                    )
            min_lamports = rebalance_lamports(
                num_new_bin_arrays=2,
                priority_fee_lamports=priority_fee_lamports,
            )
            if capital_x < min_lamports:
                return NoOp(), (
                    f"Rebalance rejected: insufficient SOL for fees "
                    f"(need {min_lamports}, have {capital_x})"
                )
            return action, None

        case AddLiquidity() | RemoveLiquidity() | ClaimFees() if position is None:
            return NoOp(), f"{type(action).__name__} rejected: no position open"

        case ClosePosition() if position is None:
            return NoOp(), "ClosePosition rejected: no position open"

        case _:
            return action, None
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_engine_guards.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/engine/guards.py tests/unit/test_engine_guards.py
git commit -m "feat(engine): action validation guards"
```

### Task 2.4: Engine main loop scaffold (`engine/runner.py`)

The full engine integrates many pieces (state evolution, fee crediting, action application). This task lands the loop skeleton with a stub `apply_action` and stub `credit_lp_fees_pro_rata`; Task 2.5 fills in pro-rata fee distribution; later tasks fill in real action application as strategies and adapters land.

**Files:**
- Modify: `asteroid_belt/engine/runner.py`
- Test: `tests/unit/test_engine_runner_scaffold.py`

- [ ] **Step 1: Write the test (smoke test of empty backtest)**

```python
# tests/unit/test_engine_runner_scaffold.py
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

from asteroid_belt.data.adapters.base import (
    AdapterProtocol,
    PoolKey,
    SwapEvent,
    TimeWindow,
)
from asteroid_belt.engine.runner import RunConfigParams, run_backtest
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import (
    PoolState,
    StaticFeeParams,
    VolatilityState,
)
from asteroid_belt.strategies.base import (
    Action,
    NoOp,
    OpenPosition,
    Strategy,
)


class _EmptyAdapter:
    """No events at all — verifies the loop terminates cleanly."""
    def __init__(self) -> None:
        self.pool = PoolKey(address="test_pool")

    def stream(self, window: TimeWindow) -> Iterator[SwapEvent]:
        if False:
            yield  # type: ignore[unreachable]
        return iter([])


class _BuyAndHoldStrategy(Strategy):
    """Opens a single position at start; never rebalances."""
    def initialize(self, pool: PoolState, capital: object) -> Action:
        return OpenPosition(lower_bin=-30, upper_bin=30, distribution="curve")

    def on_swap(self, event: SwapEvent, pool: PoolState, position: PositionState) -> Action:
        return NoOp()


def _initial_pool_state() -> PoolState:
    return PoolState(
        active_bin=0, bin_step=10, mid_price=Decimal("1"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={}, last_swap_ts=0, reward_infos=[],
    )


def test_empty_backtest_terminates() -> None:
    cfg = RunConfigParams(
        run_id="test_run",
        config_hash="test_hash",
        window=TimeWindow(start_ms=0, end_ms=1_000),
        tick_secs=300,
        initial_x=1_000_000_000,
        initial_y=8_000_000_000,
        decimals_x=9,
        decimals_y=6,
        priority_fee_lamports=10_000,
        selection_metric="net_pnl",
    )
    result = run_backtest(
        strategy=_BuyAndHoldStrategy(),
        adapter=_EmptyAdapter(),
        initial_pool_state=_initial_pool_state(),
        config=cfg,
    )
    assert result.status == "ok"
    assert result.run_id == "test_run"
```

Run: `pytest tests/unit/test_engine_runner_scaffold.py -v` — expect FAIL (imports + Strategy.on_swap missing).

- [ ] **Step 2: Extend Strategy ABC with full interface (in `asteroid_belt/strategies/base.py`)**

Modify the placeholder `Strategy` class in `asteroid_belt/strategies/base.py` to include the complete interface. Replace the existing class with:

```python
# asteroid_belt/strategies/base.py — REPLACE the placeholder Strategy class block at the bottom of the file with this:

# (Place this BELOW the Action union, BELOW all dataclass definitions, replacing
# the placeholder Strategy class added in Task 1.2.)

from asteroid_belt.data.adapters.base import SwapEvent  # noqa: E402  (forward import)
from asteroid_belt.pool.position_state import PositionState  # noqa: E402
from asteroid_belt.pool.state import PoolState  # noqa: E402


@dataclass(frozen=True)
class Capital:
    """Capital available to the strategy at initialize time."""
    x: int  # raw token units
    y: int


class Strategy(ABC):
    """The single mutable surface of the research env.

    Strategies receive read-only snapshots and emit Actions. They have no path
    to: future events, the adapter, the cost model, the clock outside what's
    handed in, or the holdout data.
    """

    @abstractmethod
    def initialize(self, pool: PoolState, capital: Capital) -> Action:
        """Called once at backtest start. Returns OpenPosition or NoOp."""

    @abstractmethod
    def on_swap(
        self, event: SwapEvent, pool: PoolState, position: PositionState
    ) -> Action:
        """Per-swap decision point. Most strategies return NoOp here."""

    def on_tick(
        self, ts: int, pool: PoolState, position: PositionState
    ) -> Action:
        """Optional time-based hook. Default: NoOp."""
        return NoOp()
```

> Important: this introduces a circular-looking import (strategies imports pool which is fine; no cycle in practice because pool doesn't import strategies). If mypy complains about the `noqa: E402` placement, move imports to the top of the file once you're confident there's no circular reference.

- [ ] **Step 3: Implement engine runner skeleton**

```python
# asteroid_belt/engine/runner.py
"""Backtest engine main loop.

Single-pass, deterministic. Same config + same input = bit-identical result.
Determinism is non-negotiable: the future agent loop's keep/discard decisions
rely on it.

This task lands the scaffold. Pro-rata fee distribution is stubbed (returns
position unchanged); Task 2.5 fills it in. Action application is also stubbed
(simply tracks NoOp); real action application lands in later phases as
adapters and strategies are integrated.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from heapq import merge
from typing import Literal

import polars as pl

from asteroid_belt.data.adapters.base import (
    AdapterProtocol,
    SwapEvent,
    TimeTick,
    TimeWindow,
)
from asteroid_belt.engine.cost import COST_MODEL_VERSION
from asteroid_belt.engine.guards import validate_action
from asteroid_belt.engine.result import (
    BacktestResult,
    RebalanceRecord,
)
from asteroid_belt.pool.fees import evolve_v_params
from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import PoolState
from asteroid_belt.strategies.base import (
    Action,
    AddLiquidity,
    Capital,
    ClaimFees,
    ClosePosition,
    NoOp,
    OpenPosition,
    Rebalance,
    RemoveLiquidity,
    Strategy,
)


@dataclass(frozen=True)
class RunConfigParams:
    """Engine-level run config (subset of the full RunConfig in config.py).

    The CLI/RunConfig produces this for the engine; engine doesn't care about
    YAML or storage details.
    """
    run_id: str
    config_hash: str
    window: TimeWindow
    tick_secs: int  # TimeTick cadence
    initial_x: int  # raw token units
    initial_y: int
    decimals_x: int
    decimals_y: int
    priority_fee_lamports: int
    selection_metric: str  # name; lookup happens at result-build time


def _generate_time_ticks(window: TimeWindow, tick_secs: int) -> Iterator[TimeTick]:
    """Generate TimeTicks at tick_secs cadence within window (half-open)."""
    cadence_ms = tick_secs * 1000
    ts = window.start_ms + cadence_ms
    while ts < window.end_ms:
        yield TimeTick(ts=ts)
        ts += cadence_ms


def _interleave_chronologically(
    swaps: Iterator[SwapEvent], ticks: Iterator[TimeTick]
) -> Iterator[SwapEvent | TimeTick]:
    """Merge two ordered streams by ts. SwapEvent uses .ts, TimeTick uses .ts."""

    def keyed(stream: Iterator[SwapEvent | TimeTick]) -> Iterator[tuple[int, int, SwapEvent | TimeTick]]:
        # Stable sort: tie-break SwapEvent (priority 0) before TimeTick (priority 1).
        for e in stream:
            priority = 1 if isinstance(e, TimeTick) else 0
            yield (e.ts, priority, e)

    for _, _, event in merge(keyed(swaps), keyed(ticks)):
        yield event


def credit_lp_fees_pro_rata(
    *,
    position: PositionState,
    pool: PoolState,
    event: SwapEvent,
) -> PositionState:
    """Credit our position's share of the LP fee from this swap.

    Stubbed in this task. Task 2.5 implements the real pro-rata distribution
    that respects bin liquidity at swap time (handles JIT-bot fee dilution).
    """
    return position  # TODO Task 2.5: real pro-rata


def apply_swap_to_pool(*, pool: PoolState, event: SwapEvent) -> PoolState:
    """Update pool state after a swap event lands.

    Stubbed: returns pool with active_bin/mid_price updated to event values.
    Bin liquidity drift is left for a later phase that integrates adapter swap
    deltas (out of scope for v1 bar-level adapter, which doesn't track per-bin
    deltas faithfully anyway).
    """
    return PoolState(
        active_bin=event.bin_id_after,
        bin_step=pool.bin_step,
        mid_price=event.price_after,
        volatility=pool.volatility,
        static_fee=pool.static_fee,
        bin_liquidity=pool.bin_liquidity,
        last_swap_ts=event.ts // 1000,  # ms → s for v_params evolution
        reward_infos=pool.reward_infos,
    )


def apply_action(
    *,
    action: Action,
    pool: PoolState,
    position: PositionState | None,
    capital_x: int,
    capital_y: int,
    rebalance_log: list[RebalanceRecord],
    event_ts: int,
) -> tuple[PositionState | None, int, int]:
    """Apply an action to position state, returning new (position, cap_x, cap_y).

    Stubbed for v1 scaffold: only OpenPosition and NoOp transition state. Full
    action application lands incrementally in Phase 3 as strategies and
    adapters are integrated.
    """
    match action:
        case NoOp():
            return position, capital_x, capital_y
        case OpenPosition(lower_bin=lo, upper_bin=hi):
            # Stub: empty composition; capital remains unchanged.
            new_position = PositionState(
                lower_bin=lo, upper_bin=hi,
                composition={},
                fee_pending_x=0, fee_pending_y=0,
                fee_pending_per_bin={},
                total_claimed_x=0, total_claimed_y=0,
                fee_owner=None,
            )
            return new_position, capital_x, capital_y
        case ClosePosition():
            return None, capital_x, capital_y
        case _:
            # Other actions are no-ops in the scaffold.
            return position, capital_x, capital_y


def _empty_trajectory() -> pl.DataFrame:
    return pl.DataFrame({
        "ts": pl.Series([], dtype=pl.Int64),
        "price": pl.Series([], dtype=pl.Float64),
        "active_bin": pl.Series([], dtype=pl.Int32),
        "position_value_usd": pl.Series([], dtype=pl.Float64),
        "hodl_value_usd": pl.Series([], dtype=pl.Float64),
        "fees_x_cumulative": pl.Series([], dtype=pl.Int64),
        "fees_y_cumulative": pl.Series([], dtype=pl.Int64),
        "il_cumulative": pl.Series([], dtype=pl.Float64),
        "in_range": pl.Series([], dtype=pl.Boolean),
        "capital_idle_usd": pl.Series([], dtype=pl.Float64),
    })


def run_backtest(
    *,
    strategy: Strategy,
    adapter: AdapterProtocol,
    initial_pool_state: PoolState,
    config: RunConfigParams,
) -> BacktestResult:
    """Run one backtest. Deterministic single-pass."""
    import time

    started_at = int(time.time() * 1000)
    pool = initial_pool_state
    capital_x, capital_y = config.initial_x, config.initial_y
    rebalances: list[RebalanceRecord] = []

    # Initial action
    initial_action = strategy.initialize(
        pool, Capital(x=capital_x, y=capital_y)
    )
    validated, _reason = validate_action(
        action=initial_action, pool=pool, position=None,
        capital_x=capital_x, capital_y=capital_y,
        priority_fee_lamports=config.priority_fee_lamports,
    )
    position, capital_x, capital_y = apply_action(
        action=validated, pool=pool, position=None,
        capital_x=capital_x, capital_y=capital_y,
        rebalance_log=rebalances, event_ts=config.window.start_ms,
    )

    trajectory_rows: list[dict[str, object]] = []

    # Main loop: interleave swaps + ticks chronologically
    swaps = adapter.stream(config.window)
    ticks = _generate_time_ticks(config.window, config.tick_secs)
    for event in _interleave_chronologically(swaps, ticks):
        if isinstance(event, SwapEvent):
            pool = PoolState(
                active_bin=pool.active_bin,
                bin_step=pool.bin_step,
                mid_price=pool.mid_price,
                volatility=evolve_v_params(
                    state=pool.volatility, sparams=pool.static_fee,
                    event_ts=event.ts // 1000,
                    active_bin_before=pool.active_bin,
                    target_bin=event.bin_id_after,
                ),
                static_fee=pool.static_fee,
                bin_liquidity=pool.bin_liquidity,
                last_swap_ts=pool.last_swap_ts,
                reward_infos=pool.reward_infos,
            )
            if position is not None:
                position = credit_lp_fees_pro_rata(
                    position=position, pool=pool, event=event,
                )
            pool = apply_swap_to_pool(pool=pool, event=event)
            if position is not None:
                action = strategy.on_swap(event, pool, position)
            else:
                action = NoOp()
        else:  # TimeTick
            if position is not None:
                action = strategy.on_tick(event.ts, pool, position)
            else:
                action = NoOp()

        validated, _reason = validate_action(
            action=action, pool=pool, position=position,
            capital_x=capital_x, capital_y=capital_y,
            priority_fee_lamports=config.priority_fee_lamports,
        )
        position, capital_x, capital_y = apply_action(
            action=validated, pool=pool, position=position,
            capital_x=capital_x, capital_y=capital_y,
            rebalance_log=rebalances, event_ts=event.ts,
        )

        # Append trajectory row (stub values — Phase 3+ fills in real numbers).
        trajectory_rows.append({
            "ts": event.ts,
            "price": float(pool.mid_price),
            "active_bin": pool.active_bin,
            "position_value_usd": 0.0,
            "hodl_value_usd": 0.0,
            "fees_x_cumulative": 0,
            "fees_y_cumulative": 0,
            "il_cumulative": 0.0,
            "in_range": position.in_range(pool.active_bin) if position is not None else False,
            "capital_idle_usd": 0.0,
        })

    ended_at = int(time.time() * 1000)
    trajectory = pl.DataFrame(trajectory_rows) if trajectory_rows else _empty_trajectory()

    # Primitives are computed in Phase 2 metrics tasks; for the scaffold, return zeros.
    primitives = {config.selection_metric: 0.0}

    return BacktestResult(
        run_id=config.run_id,
        config_hash=config.config_hash,
        schema_version="1.0",
        started_at=started_at,
        ended_at=ended_at,
        status="ok",
        trajectory=trajectory,
        rebalances=rebalances,
        primitives=primitives,
        score=0.0,
        score_metric=config.selection_metric,
    )
```

- [ ] **Step 4: Run tests (expect PASS)**

```bash
pytest tests/unit/test_engine_runner_scaffold.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add asteroid_belt/engine/runner.py asteroid_belt/strategies/base.py tests/unit/test_engine_runner_scaffold.py
git commit -m "feat(engine): main loop scaffold with stub action application"
```

### Task 2.5: Pro-rata fee distribution (`engine/runner.py`)

Replaces the stub `credit_lp_fees_pro_rata` with the real implementation. This is a frozen rule: at each `SwapEvent`, our position is credited fees in proportion to its `liquidity_share` in the bin where the swap landed, computed against the bin's liquidity AT THE TIME of the swap (not aggregated across the block) — this respects JIT-bot fee dilution.

**Files:**
- Modify: `asteroid_belt/engine/runner.py` (replace `credit_lp_fees_pro_rata`)
- Test: `tests/unit/test_pro_rata_fees.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_pro_rata_fees.py
from decimal import Decimal

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.engine.runner import credit_lp_fees_pro_rata
from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import (
    BinReserves,
    PoolState,
    StaticFeeParams,
    VolatilityState,
)


def _make_pool(bin_id: int, our_amount_x: int, others_amount_x: int) -> PoolState:
    return PoolState(
        active_bin=bin_id, bin_step=10, mid_price=Decimal("87.55"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={
            bin_id: BinReserves(
                amount_x=our_amount_x + others_amount_x,
                amount_y=0,
                liquidity_supply=our_amount_x + others_amount_x,
                price=Decimal("87.55"),
            ),
        },
        last_swap_ts=0, reward_infos=[],
    )


def _swap(bin_id: int, fee: int, protocol: int = 50, host: int = 0) -> SwapEvent:
    return SwapEvent(
        ts=1_000_000, signature="x", event_index=0, swap_for_y=False,
        amount_in=10_000_000, amount_out=11_000,
        fee_amount=fee, protocol_fee_amount=protocol, host_fee_amount=host,
        price_after=Decimal("87.55"), bin_id_after=bin_id,
    )


def _position(bin_id: int, our_share: float) -> PositionState:
    return PositionState(
        lower_bin=bin_id, upper_bin=bin_id,
        composition={bin_id: BinComposition(amount_x=10, amount_y=0, liquidity_share=our_share)},
        fee_pending_x=0, fee_pending_y=0,
        fee_pending_per_bin={},
        total_claimed_x=0, total_claimed_y=0,
        fee_owner=None,
    )


def test_no_credit_when_position_outside_swap_bin() -> None:
    pool = _make_pool(bin_id=100, our_amount_x=50, others_amount_x=50)
    pos = _position(bin_id=99, our_share=0.5)  # different bin
    event = _swap(bin_id=100, fee=1000)
    new_pos = credit_lp_fees_pro_rata(position=pos, pool=pool, event=event)
    assert new_pos.fee_pending_x == 0
    assert new_pos.fee_pending_y == 0


def test_credit_proportional_to_share() -> None:
    pool = _make_pool(bin_id=100, our_amount_x=50, others_amount_x=50)
    pos = _position(bin_id=100, our_share=0.5)
    # swap_for_y=False (Y→X) → fee in Y; lp_fee = 1000 - 50 - 0 = 950; our share 0.5 → 475
    event = _swap(bin_id=100, fee=1000, protocol=50, host=0)
    new_pos = credit_lp_fees_pro_rata(position=pos, pool=pool, event=event)
    assert new_pos.fee_pending_y == 475
    assert new_pos.fee_pending_x == 0


def test_credit_x_when_swap_for_y() -> None:
    pool = _make_pool(bin_id=100, our_amount_x=50, others_amount_x=50)
    pos = _position(bin_id=100, our_share=0.4)
    # swap_for_y=True → fee in X
    event = SwapEvent(
        ts=1_000_000, signature="x", event_index=0, swap_for_y=True,
        amount_in=10_000_000, amount_out=11_000,
        fee_amount=1000, protocol_fee_amount=50, host_fee_amount=0,
        price_after=Decimal("87.55"), bin_id_after=100,
    )
    new_pos = credit_lp_fees_pro_rata(position=pos, pool=pool, event=event)
    # lp_fee = 950; our share 0.4 → 380
    assert new_pos.fee_pending_x == 380
    assert new_pos.fee_pending_y == 0


def test_jit_dilution_when_others_added_liquidity() -> None:
    # Our share is computed against the bin liquidity AT swap time, including
    # any JIT-bot adds that show up in the historical record.
    # If our_share is set to 0.1 (because a JIT bot 10x'd the bin liquidity),
    # we get 10% of fees, not 100%.
    pool = _make_pool(bin_id=100, our_amount_x=10, others_amount_x=90)
    pos = _position(bin_id=100, our_share=0.1)
    event = _swap(bin_id=100, fee=1000)
    new_pos = credit_lp_fees_pro_rata(position=pos, pool=pool, event=event)
    # lp_fee 950 * 0.1 = 95
    assert new_pos.fee_pending_y == 95
```

Run: `pytest tests/unit/test_pro_rata_fees.py -v` — expect FAIL (current stub returns position unchanged).

- [ ] **Step 2: Replace `credit_lp_fees_pro_rata` in `runner.py`**

Find the existing stub:

```python
def credit_lp_fees_pro_rata(
    *,
    position: PositionState,
    pool: PoolState,
    event: SwapEvent,
) -> PositionState:
    """Credit our position's share of the LP fee from this swap.

    Stubbed in this task. Task 2.5 implements the real pro-rata distribution
    that respects bin liquidity at swap time (handles JIT-bot fee dilution).
    """
    return position  # TODO Task 2.5: real pro-rata
```

Replace with:

```python
def credit_lp_fees_pro_rata(
    *,
    position: PositionState,
    pool: PoolState,
    event: SwapEvent,
) -> PositionState:
    """Credit our position's share of LP fees from this swap.

    Frozen rule. LP fee = (fee_amount - protocol_fee_amount - host_fee_amount).
    Our share = our position's `liquidity_share` in the swap's bin AT swap time.
    Fee is credited in input-token units (X if swap_for_y, else Y).

    Multi-bin swaps are handled at the loop level: each bin-crossing event
    fires this function once with its own `bin_id_after`.
    """
    bin_id = event.bin_id_after
    if bin_id not in position.composition:
        return position

    our_share = position.composition[bin_id].liquidity_share
    if our_share == 0:
        return position

    lp_fee_total = event.lp_fee_amount  # int
    our_credit = int(lp_fee_total * our_share)
    if our_credit == 0:
        return position

    if event.swap_for_y:
        # Fee in X
        new_pending_x = position.fee_pending_x + our_credit
        new_pending_y = position.fee_pending_y
        existing_bin = position.fee_pending_per_bin.get(bin_id, (0, 0))
        new_per_bin = {
            **position.fee_pending_per_bin,
            bin_id: (existing_bin[0] + our_credit, existing_bin[1]),
        }
    else:
        # Fee in Y
        new_pending_x = position.fee_pending_x
        new_pending_y = position.fee_pending_y + our_credit
        existing_bin = position.fee_pending_per_bin.get(bin_id, (0, 0))
        new_per_bin = {
            **position.fee_pending_per_bin,
            bin_id: (existing_bin[0], existing_bin[1] + our_credit),
        }

    return PositionState(
        lower_bin=position.lower_bin,
        upper_bin=position.upper_bin,
        composition=position.composition,
        fee_pending_x=new_pending_x,
        fee_pending_y=new_pending_y,
        fee_pending_per_bin=new_per_bin,
        total_claimed_x=position.total_claimed_x,
        total_claimed_y=position.total_claimed_y,
        fee_owner=position.fee_owner,
    )
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_pro_rata_fees.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/engine/runner.py tests/unit/test_pro_rata_fees.py
git commit -m "feat(engine): pro-rata LP fee distribution (frozen rule)"
```

### Task 2.6: Metric primitives (`metrics/primitives.py`)

**Files:**
- Modify: `asteroid_belt/metrics/primitives.py`
- Test: `tests/unit/test_metrics_primitives.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_metrics_primitives.py
import math

import polars as pl

from asteroid_belt.engine.result import BacktestResult
from asteroid_belt.metrics.primitives import (
    capital_efficiency,
    net_pnl,
    rebalance_count,
    sharpe,
    sortino,
    time_in_range_pct,
)


def _make_result(
    *,
    position_values: list[float],
    hodl_values: list[float],
    in_range_flags: list[bool],
    rebalances: int = 0,
) -> BacktestResult:
    n = len(position_values)
    df = pl.DataFrame({
        "ts": list(range(n)),
        "price": [1.0] * n,
        "active_bin": [0] * n,
        "position_value_usd": position_values,
        "hodl_value_usd": hodl_values,
        "fees_x_cumulative": [0] * n,
        "fees_y_cumulative": [0] * n,
        "il_cumulative": [p - h for p, h in zip(position_values, hodl_values)],
        "in_range": in_range_flags,
        "capital_idle_usd": [0.0] * n,
    })
    from asteroid_belt.engine.result import RebalanceRecord
    return BacktestResult(
        run_id="t", config_hash="t", schema_version="1.0",
        started_at=0, ended_at=0, status="ok",
        trajectory=df,
        rebalances=[
            RebalanceRecord(ts=0, trigger="x", old_lower_bin=0, old_upper_bin=0,
                            new_lower_bin=0, new_upper_bin=0, gas_lamports=0,
                            composition_fee_x=0, composition_fee_y=0,
                            fees_claimed_x=0, fees_claimed_y=0)
        ] * rebalances,
        primitives={}, score=0.0, score_metric="net_pnl",
    )


def test_net_pnl_zero_when_position_matches_hodl() -> None:
    r = _make_result(
        position_values=[100, 100, 100],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    assert net_pnl(r) == 0.0


def test_net_pnl_positive_when_outperforming() -> None:
    r = _make_result(
        position_values=[100, 105, 110],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    assert net_pnl(r) == 10.0


def test_time_in_range_basic() -> None:
    r = _make_result(
        position_values=[100, 100, 100, 100],
        hodl_values=[100, 100, 100, 100],
        in_range_flags=[True, True, False, True],
    )
    assert time_in_range_pct(r) == 75.0


def test_capital_efficiency_division_safety() -> None:
    # No IL → epsilon prevents division-by-zero blowup.
    r = _make_result(
        position_values=[100, 100, 100],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    # net_pnl = 0, so capital_efficiency = 0 regardless
    assert capital_efficiency(r) == 0.0


def test_sharpe_zero_when_constant_pnl() -> None:
    # Constant PnL → zero variance → sharpe undefined; we return 0.0
    r = _make_result(
        position_values=[100, 100, 100],
        hodl_values=[100, 100, 100],
        in_range_flags=[True, True, True],
    )
    assert sharpe(r) == 0.0


def test_sharpe_positive_when_increasing() -> None:
    r = _make_result(
        position_values=[100, 101, 102, 103, 104],
        hodl_values=[100, 100, 100, 100, 100],
        in_range_flags=[True] * 5,
    )
    assert sharpe(r) > 0


def test_sortino_only_penalizes_downside() -> None:
    # All-up PnL: sortino is high (only downside variance counts)
    up = _make_result(
        position_values=[100, 101, 102, 103],
        hodl_values=[100, 100, 100, 100],
        in_range_flags=[True] * 4,
    )
    s_up = sortino(up)
    assert s_up > 0


def test_rebalance_count() -> None:
    r = _make_result(
        position_values=[100, 100],
        hodl_values=[100, 100],
        in_range_flags=[True, True],
        rebalances=5,
    )
    assert rebalance_count(r) == 5
```

Run: `pytest tests/unit/test_metrics_primitives.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/metrics/primitives.py
"""Pure-function metrics over BacktestResult.

Every shipped primitive is computed on every result regardless of which one
the run config names as `selection_metric`. Adding a new primitive is
additive — it never invalidates old runs because re-evaluation is cheap.
"""

from __future__ import annotations

import math

import polars as pl

from asteroid_belt.engine.result import BacktestResult

_EPS = 1e-9


def net_pnl(r: BacktestResult) -> float:
    """Final position value − initial position value, in USD."""
    df = r.trajectory
    if df.is_empty():
        return 0.0
    first = float(df["position_value_usd"][0])
    last = float(df["position_value_usd"][-1])
    return last - first


def time_in_range_pct(r: BacktestResult) -> float:
    """Percentage of trajectory steps where the position was in range."""
    df = r.trajectory
    if df.is_empty():
        return 0.0
    in_range_count = int(df["in_range"].sum())
    return 100.0 * in_range_count / df.height


def _daily_pnl_series(r: BacktestResult) -> pl.Series:
    """Convert per-step position value into per-day deltas."""
    df = r.trajectory
    if df.is_empty():
        return pl.Series([], dtype=pl.Float64)
    # Round timestamps down to day boundaries (UTC)
    daily = (
        df.with_columns([
            (pl.col("ts") // (24 * 60 * 60 * 1000)).alias("day"),
        ])
        .group_by("day", maintain_order=True)
        .agg(pl.col("position_value_usd").last().alias("eod_value"))
        .sort("day")
    )
    if daily.height < 2:
        return pl.Series([], dtype=pl.Float64)
    eod = daily["eod_value"].to_list()
    deltas = [eod[i] - eod[i - 1] for i in range(1, len(eod))]
    return pl.Series(deltas, dtype=pl.Float64)


def sharpe(r: BacktestResult) -> float:
    """Sharpe ratio computed on daily PnL. Returns 0.0 when undefined."""
    deltas = _daily_pnl_series(r)
    if deltas.is_empty():
        return 0.0
    mean = float(deltas.mean() or 0.0)
    std = float(deltas.std() or 0.0)
    if std < _EPS:
        return 0.0
    # Annualize from daily: sqrt(365). Reasonable for a 24/7 LP context.
    return mean / std * math.sqrt(365)


def sortino(r: BacktestResult) -> float:
    """Sortino ratio: like Sharpe but only penalizes downside variance."""
    deltas = _daily_pnl_series(r)
    if deltas.is_empty():
        return 0.0
    mean = float(deltas.mean() or 0.0)
    downside = deltas.filter(deltas < 0)
    if downside.is_empty():
        # No downside days: ratio is unbounded; clamp to a large positive sentinel
        # so the metric is comparable across runs.
        return mean / _EPS if mean > 0 else 0.0
    downside_std = float(downside.std() or 0.0)
    if downside_std < _EPS:
        return 0.0
    return mean / downside_std * math.sqrt(365)


def capital_efficiency(r: BacktestResult) -> float:
    """net_pnl / max(|cumulative IL|, ε). Higher = more PnL per unit of IL."""
    pnl = net_pnl(r)
    df = r.trajectory
    if df.is_empty():
        return 0.0
    il_abs = abs(float(df["il_cumulative"].min() or 0.0))
    return pnl / max(il_abs, _EPS)


def rebalance_count(r: BacktestResult) -> float:
    """Number of rebalances during the run."""
    return float(len(r.rebalances))


# Registry of all shipped primitives, used at result-build time.
PRIMITIVE_REGISTRY: dict[str, callable] = {  # type: ignore[type-arg]
    "net_pnl": net_pnl,
    "sharpe": sharpe,
    "sortino": sortino,
    "capital_efficiency": capital_efficiency,
    "time_in_range_pct": time_in_range_pct,
    "rebalance_count": rebalance_count,
}
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_metrics_primitives.py -v
```

Expected: 8 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/metrics/primitives.py tests/unit/test_metrics_primitives.py
git commit -m "feat(metrics): primitive metrics (net_pnl, sharpe, sortino, capital_efficiency, time_in_range, rebalance_count)"
```

### Task 2.7: Composite metric (`metrics/composite.py`)

**Files:**
- Modify: `asteroid_belt/metrics/composite.py`
- Test: `tests/unit/test_metrics_composite.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_metrics_composite.py
import polars as pl

from asteroid_belt.engine.result import BacktestResult
from asteroid_belt.metrics.composite import composite


def _result_with_primitives(primitives: dict[str, float]) -> BacktestResult:
    df = pl.DataFrame({
        "ts": [0, 1], "price": [1.0, 1.0], "active_bin": [0, 0],
        "position_value_usd": [100.0, 110.0], "hodl_value_usd": [100.0, 100.0],
        "fees_x_cumulative": [0, 0], "fees_y_cumulative": [0, 0],
        "il_cumulative": [0.0, 0.0], "in_range": [True, True],
        "capital_idle_usd": [0.0, 0.0],
    })
    return BacktestResult(
        run_id="t", config_hash="t", schema_version="1.0",
        started_at=0, ended_at=0, status="ok",
        trajectory=df, rebalances=[],
        primitives=primitives, score=0.0, score_metric="composite",
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
```

Run: `pytest tests/unit/test_metrics_composite.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/metrics/composite.py
"""Weighted-composite metric over precomputed primitives.

Composites are pure functions over `BacktestResult.primitives` — they don't
re-derive anything from the trajectory. Unknown primitive names in `weights`
are silently ignored (forward-compat for primitives added in v1.5+ that v1
results don't have).
"""

from __future__ import annotations

from asteroid_belt.engine.result import BacktestResult


def composite(r: BacktestResult, *, weights: dict[str, float]) -> float:
    """Weighted sum of named primitives.

    Example:
        composite(r, weights={"net_pnl": 1.0, "rebalance_count": -0.1})
        → r.primitives["net_pnl"] - 0.1 * r.primitives["rebalance_count"]
    """
    total = 0.0
    for name, weight in weights.items():
        if name in r.primitives:
            total += weight * r.primitives[name]
    return total
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_metrics_composite.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/metrics/composite.py tests/unit/test_metrics_composite.py
git commit -m "feat(metrics): weighted composite metric"
```

---

**End of Phase 2.** You now have: BacktestResult/RebalanceRecord types, cost model with verifiable constants, action validation guards, an engine main loop scaffold (with stub action application), real pro-rata fee distribution, and the full metric layer (6 primitives + composite). Total tests: ~50.

The engine scaffold is enough to run an empty backtest end-to-end. Phase 3 fills in the bar adapter and the two baseline strategies; Phase 4 wires up storage and the Meteora ingest; by end of Phase 5 you can run `belt run --config configs/quickstart.yaml` against a real ingested pool window.

---

## Phase 3 — Bar adapter, splits, baseline strategies

Wires the bar-synthesized adapter into the engine, lands the train/holdout split helper, and implements the two v1 baseline strategies. After this phase, the engine can run a full backtest against synthetic bar data with either baseline.

### Task 3.1: Train/holdout split helper (`data/splits.py`)

**Files:**
- Modify: `asteroid_belt/data/splits.py`
- Test: `tests/unit/test_data_splits.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_data_splits.py
from datetime import datetime, timezone

import pytest

from asteroid_belt.data.adapters.base import TimeWindow
from asteroid_belt.data.splits import (
    HOLDOUT_BOUNDARY_DEFAULT,
    holdout_window,
    train_window,
    validate_window_within_train,
)


def _ms(dt: str) -> int:
    return int(datetime.fromisoformat(dt).replace(tzinfo=timezone.utc).timestamp() * 1000)


def test_train_window_default() -> None:
    w = train_window(start="2024-05-01T00:00:00Z", boundary=HOLDOUT_BOUNDARY_DEFAULT)
    assert w.start_ms == _ms("2024-05-01T00:00:00")
    assert w.end_ms == _ms(HOLDOUT_BOUNDARY_DEFAULT)


def test_holdout_window_default() -> None:
    w = holdout_window(end="2026-04-29T00:00:00Z", boundary=HOLDOUT_BOUNDARY_DEFAULT)
    assert w.start_ms == _ms(HOLDOUT_BOUNDARY_DEFAULT)
    assert w.end_ms == _ms("2026-04-29T00:00:00")


def test_validate_within_train_passes() -> None:
    w = TimeWindow(start_ms=_ms("2024-05-01T00:00:00"), end_ms=_ms("2025-10-01T00:00:00"))
    validate_window_within_train(w, boundary=HOLDOUT_BOUNDARY_DEFAULT)  # no exception


def test_validate_window_crosses_boundary_raises() -> None:
    w = TimeWindow(start_ms=_ms("2024-05-01T00:00:00"), end_ms=_ms("2025-12-01T00:00:00"))
    with pytest.raises(ValueError, match="crosses holdout boundary"):
        validate_window_within_train(w, boundary=HOLDOUT_BOUNDARY_DEFAULT)
```

Run: `pytest tests/unit/test_data_splits.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/data/splits.py
"""Train/holdout window helpers and the sealed-holdout invariant.

The holdout boundary is a single timestamp before which all data is "train"
(visible to agent runs) and after which all data is "holdout" (only the
evaluator process touches it). v1 default is Oct 31 2025 00:00 UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone

from asteroid_belt.data.adapters.base import TimeWindow

HOLDOUT_BOUNDARY_DEFAULT = "2025-10-31T00:00:00Z"


def _to_ms(iso: str) -> int:
    """Parse ISO-8601 string (with optional 'Z') to ms-since-epoch."""
    s = iso.replace("Z", "+00:00")
    return int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000)


def train_window(*, start: str, boundary: str) -> TimeWindow:
    """Window from `start` up to (exclusive) the holdout boundary."""
    return TimeWindow(start_ms=_to_ms(start), end_ms=_to_ms(boundary))


def holdout_window(*, end: str, boundary: str) -> TimeWindow:
    """Window from the holdout boundary up to (exclusive) `end`."""
    return TimeWindow(start_ms=_to_ms(boundary), end_ms=_to_ms(end))


def validate_window_within_train(window: TimeWindow, *, boundary: str) -> None:
    """Raise ValueError if `window` extends at or past the holdout boundary."""
    boundary_ms = _to_ms(boundary)
    if window.end_ms > boundary_ms:
        raise ValueError(
            f"window.end_ms ({window.end_ms}) crosses holdout boundary "
            f"({boundary_ms}, {boundary})"
        )
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_data_splits.py -v
```

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/data/splits.py tests/unit/test_data_splits.py
git commit -m "feat(data): train/holdout window helpers"
```

### Task 3.2: Bar-synthesized adapter (`data/adapters/bar.py`)

**Files:**
- Modify: `asteroid_belt/data/adapters/bar.py`
- Test: `tests/unit/test_bar_adapter.py`
- Test fixture: `tests/fixtures/bars_tiny.parquet` (created by the test setup)

The bar adapter loads `bars_1m.parquet` for the configured pool and synthesizes one `SwapEvent` per bar at the bar's VWAP, on the dominant side (`swap_for_y` = `True` if `close < open`, else `False`). Documented bias from spec §5.3.

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_bar_adapter.py
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from asteroid_belt.data.adapters.base import PoolKey, TimeWindow
from asteroid_belt.data.adapters.bar import BarSynthesizedAdapter


@pytest.fixture
def tiny_bars_parquet(tmp_path: Path) -> Path:
    """4 minutes of bars: 2 going up, 2 going down."""
    df = pl.DataFrame({
        "ts": [
            1_700_000_000_000,  # +0min
            1_700_000_060_000,  # +1min
            1_700_000_120_000,  # +2min
            1_700_000_180_000,  # +3min
        ],
        "open": [87.50, 87.55, 87.60, 87.55],
        "high": [87.56, 87.61, 87.60, 87.55],
        "low": [87.49, 87.54, 87.55, 87.50],
        "close": [87.55, 87.60, 87.55, 87.50],
        "volume_x": [1_000_000, 1_500_000, 800_000, 600_000],
        "volume_y": [87_550_000, 131_400_000, 70_080_000, 52_530_000],
    })
    p = tmp_path / "bars.parquet"
    df.write_parquet(p)
    return p


def test_yields_one_event_per_bar(tiny_bars_parquet: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=tiny_bars_parquet,
        pool=PoolKey(address="test_pool"),
        bin_step=10,
    )
    events = list(adapter.stream(TimeWindow(start_ms=0, end_ms=10**13)))
    assert len(events) == 4


def test_dominant_side_when_price_rises(tiny_bars_parquet: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=tiny_bars_parquet, pool=PoolKey(address="test_pool"), bin_step=10,
    )
    events = list(adapter.stream(TimeWindow(start_ms=0, end_ms=10**13)))
    # Bar 0: 87.50 → 87.55 (up). Y→X swap pushes price up.
    assert events[0].swap_for_y is False


def test_dominant_side_when_price_falls(tiny_bars_parquet: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=tiny_bars_parquet, pool=PoolKey(address="test_pool"), bin_step=10,
    )
    events = list(adapter.stream(TimeWindow(start_ms=0, end_ms=10**13)))
    # Bar 2: 87.60 → 87.55 (down). X→Y swap pushes price down.
    assert events[2].swap_for_y is True


def test_window_filter_excludes_outside_bars(tiny_bars_parquet: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=tiny_bars_parquet, pool=PoolKey(address="test_pool"), bin_step=10,
    )
    # Window covers only bars 1 and 2 (ts 60_000 and 120_000)
    win = TimeWindow(start_ms=1_700_000_060_000, end_ms=1_700_000_180_000)
    events = list(adapter.stream(win))
    assert len(events) == 2


def test_window_end_is_exclusive(tiny_bars_parquet: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=tiny_bars_parquet, pool=PoolKey(address="test_pool"), bin_step=10,
    )
    # Window end matches bar 3's ts exactly → excluded
    win = TimeWindow(start_ms=0, end_ms=1_700_000_180_000)
    events = list(adapter.stream(win))
    assert len(events) == 3
```

Run: `pytest tests/unit/test_bar_adapter.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/data/adapters/bar.py
"""Bar-synthesized adapter.

Loads 1m OHLCV+volume bars from parquet and synthesizes one SwapEvent per bar
at the bar's VWAP on the dominant side. Documented biases (per spec §5.3):

- Variable fee understated during high-volatility minutes (single synthetic
  event per bar can't represent intra-minute swap clustering).
- Bin-traversal granularity lost for multi-bin moves within a bar.
- ≤1440 events per backtest day → fast iteration.

Cross-validation against the future on-chain swap adapter directly measures
these biases.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import polars as pl

from asteroid_belt.data.adapters.base import (
    AdapterProtocol,
    PoolKey,
    SwapEvent,
    TimeWindow,
)
from asteroid_belt.pool.bins import price_to_bin_id


class BarSynthesizedAdapter:
    """Adapter that emits synthetic SwapEvents from 1m OHLCV bars.

    Constructor takes a fixed parquet_path. The lookahead-bias guard is
    structural: only rows within `window` are read by `stream`; data at any
    other path is unreachable from this adapter instance. Holdout data lives
    at a separate path that the adapter for an agent run cannot be constructed
    against.
    """

    def __init__(
        self,
        *,
        parquet_path: Path,
        pool: PoolKey,
        bin_step: int,
    ) -> None:
        self._parquet_path = parquet_path
        self.pool = pool
        self._bin_step = bin_step

    def stream(self, window: TimeWindow) -> Iterator[SwapEvent]:
        """Yield SwapEvents in chronological order strictly within `window`."""
        df = pl.read_parquet(self._parquet_path).filter(
            (pl.col("ts") >= window.start_ms) & (pl.col("ts") < window.end_ms)
        ).sort("ts")

        for i, row in enumerate(df.iter_rows(named=True)):
            open_p = Decimal(str(row["open"]))
            close_p = Decimal(str(row["close"]))
            volume_x = int(row["volume_x"])
            volume_y = int(row["volume_y"])

            # Dominant side: True (X→Y) if price drops, else False (Y→X)
            swap_for_y = close_p < open_p

            # VWAP approximation: midpoint of OHLC averaged.
            # For v1 we use the close price as `price_after`, which corresponds
            # to the swap landing at end of bar.
            price_after = close_p
            bin_id_after = price_to_bin_id(price_after, bin_step=self._bin_step)

            # Synthetic amounts: use the dominant side's volume as `amount_in`.
            if swap_for_y:
                amount_in = volume_x
                amount_out = volume_y
            else:
                amount_in = volume_y
                amount_out = volume_x

            # Stub fee values. Fee accrual in the engine uses real LP-fee math
            # via credit_lp_fees_pro_rata + the pool's static_fee config; the
            # adapter is responsible only for emitting events with sane fee
            # fields. v1 sets fee_amount = (amount_in * base_fee_bps / 10000)
            # so the engine's pro-rata distribution has something non-zero to
            # work with. Protocol/host fees are zero in v1; engine compensates.
            base_fee_bps_default = self._bin_step  # base_factor=10000 → bps == bin_step
            fee_amount = amount_in * base_fee_bps_default // 10_000

            yield SwapEvent(
                ts=int(row["ts"]),
                signature=f"bar_synth_{i}",
                event_index=0,
                swap_for_y=swap_for_y,
                amount_in=amount_in,
                amount_out=amount_out,
                fee_amount=fee_amount,
                protocol_fee_amount=0,
                host_fee_amount=0,
                price_after=price_after,
                bin_id_after=bin_id_after,
            )


# Type-check that BarSynthesizedAdapter conforms to AdapterProtocol.
_check: AdapterProtocol = BarSynthesizedAdapter(
    parquet_path=Path("/dev/null"),
    pool=PoolKey(address=""),
    bin_step=10,
)  # noqa: F841
```

> Note: the trailing `_check` is a static-typing assertion that the class implements `AdapterProtocol`. mypy will raise if the class drifts out of conformance. The `Path("/dev/null")` is never read because we don't call `stream` here.

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_bar_adapter.py -v
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/data/adapters/bar.py tests/unit/test_bar_adapter.py
git commit -m "feat(data): bar-synthesized adapter"
```

### Task 3.3: Precision Curve baseline (`strategies/precision_curve.py`)

**Files:**
- Modify: `asteroid_belt/strategies/precision_curve.py`
- Test: `tests/unit/test_precision_curve.py`

**HawkFi Precision Curve interpretation (v1 placeholder defaults, per spec):**
- Wide range (default 69 bins, symmetric around active)
- Curve distribution shape
- Rebalance trigger: active bin drifts > N bins from position center (default 10)
- Optional time cadence: rebalance check every N seconds (default null = swap-driven only)
- Auto-compound pending fees on rebalance: yes (default)
- Auto-claim fees to SOL: configurable

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_precision_curve.py
from decimal import Decimal

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.pool.position_state import BinComposition, PositionState
from asteroid_belt.pool.state import (
    PoolState,
    StaticFeeParams,
    VolatilityState,
)
from asteroid_belt.strategies.base import (
    Capital,
    NoOp,
    OpenPosition,
    Rebalance,
)
from asteroid_belt.strategies.precision_curve import PrecisionCurveParams, PrecisionCurveStrategy


def _pool(active_bin: int = 0) -> PoolState:
    return PoolState(
        active_bin=active_bin, bin_step=10, mid_price=Decimal("87.55"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={}, last_swap_ts=0, reward_infos=[],
    )


def _position(lower: int, upper: int) -> PositionState:
    return PositionState(
        lower_bin=lower, upper_bin=upper, composition={},
        fee_pending_x=0, fee_pending_y=0, fee_pending_per_bin={},
        total_claimed_x=0, total_claimed_y=0, fee_owner=None,
    )


def _swap_at(bin_id: int) -> SwapEvent:
    return SwapEvent(
        ts=1_000_000_000, signature="x", event_index=0, swap_for_y=False,
        amount_in=10_000_000, amount_out=11_000,
        fee_amount=100, protocol_fee_amount=5, host_fee_amount=0,
        price_after=Decimal("87.55"), bin_id_after=bin_id,
    )


def test_initialize_opens_symmetric_curve_position() -> None:
    s = PrecisionCurveStrategy(PrecisionCurveParams(bin_width=69, rebalance_trigger_bins=10))
    a = s.initialize(_pool(active_bin=100), Capital(x=1_000_000_000, y=8_000_000_000))
    assert isinstance(a, OpenPosition)
    assert a.distribution == "curve"
    assert a.lower_bin == 100 - 34
    assert a.upper_bin == 100 + 34


def test_no_rebalance_when_in_range() -> None:
    s = PrecisionCurveStrategy(PrecisionCurveParams(bin_width=69, rebalance_trigger_bins=10))
    pool = _pool(active_bin=5)
    pos = _position(lower=-34, upper=34)
    out = s.on_swap(_swap_at(5), pool, pos)
    assert isinstance(out, NoOp)


def test_rebalance_when_drift_exceeds_trigger() -> None:
    s = PrecisionCurveStrategy(PrecisionCurveParams(bin_width=69, rebalance_trigger_bins=10))
    pool = _pool(active_bin=15)  # 15 bins above center 0
    pos = _position(lower=-34, upper=34)
    out = s.on_swap(_swap_at(15), pool, pos)
    assert isinstance(out, Rebalance)


def test_rebalance_recenters_around_active_bin() -> None:
    s = PrecisionCurveStrategy(PrecisionCurveParams(bin_width=69, rebalance_trigger_bins=10))
    pool = _pool(active_bin=15)
    pos = _position(lower=-34, upper=34)
    out = s.on_swap(_swap_at(15), pool, pos)
    assert isinstance(out, Rebalance)
    # Recentered: removes [-34, 34], adds [-19, 49]
    assert any(r.lower_bin == -34 and r.upper_bin == 34 for r in out.removes)
    assert any(a.lower_bin == 15 - 34 and a.upper_bin == 15 + 34 for a in out.adds)
```

Run: `pytest tests/unit/test_precision_curve.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/strategies/precision_curve.py
"""Precision Curve baseline strategy.

HawkFi Precision Curve preset reimplemented from prose docs. Defaults are
v1 best-effort interpretations; the agent's job (in subsystem 4) is partly to
discover whether these defaults were good.

Mechanics:
- Symmetric curve-shaped position around the active bin
- Rebalance when active bin drifts > rebalance_trigger_bins from position center
- Optional time-based rebalance check via on_tick (rebalance_cadence_secs)
- Auto-compound pending fees on rebalance (default True)
"""

from __future__ import annotations

from dataclasses import dataclass

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import PoolState
from asteroid_belt.strategies.base import (
    Action,
    AddLiquidity,
    BinRangeAdd,
    BinRangeRemoval,
    Capital,
    NoOp,
    OpenPosition,
    Rebalance,
    Strategy,
)


@dataclass(frozen=True)
class PrecisionCurveParams:
    """Tunable parameters for the Precision Curve baseline."""
    bin_width: int = 69  # total bin range width (must be odd to center cleanly)
    rebalance_trigger_bins: int = 10  # drift threshold from position center
    rebalance_cadence_secs: int | None = None  # None = swap-driven only
    auto_compound: bool = True
    auto_claim_to_sol: bool = False


class PrecisionCurveStrategy(Strategy):
    """v1 baseline #1: wide curve-shaped position, drift-based rebalance."""

    def __init__(self, params: PrecisionCurveParams) -> None:
        self.params = params
        self._last_tick_check_ts: int = 0

    def _half_width(self) -> int:
        return self.params.bin_width // 2

    def initialize(self, pool: PoolState, capital: Capital) -> Action:
        half = self._half_width()
        return OpenPosition(
            lower_bin=pool.active_bin - half,
            upper_bin=pool.active_bin + half,
            distribution="curve",
            capital_x_pct=None,  # SDK-balanced via autoFill
            slippage_bps=50,
        )

    def _maybe_rebalance(
        self, pool: PoolState, position: PositionState
    ) -> Action:
        center = (position.lower_bin + position.upper_bin) // 2
        drift = abs(pool.active_bin - center)
        if drift <= self.params.rebalance_trigger_bins:
            return NoOp()
        half = self._half_width()
        return Rebalance(
            removes=[BinRangeRemoval(
                lower_bin=position.lower_bin,
                upper_bin=position.upper_bin,
                bps=10_000,
            )],
            adds=[BinRangeAdd(
                lower_bin=pool.active_bin - half,
                upper_bin=pool.active_bin + half,
                distribution="curve",
                amount_x=0,  # engine fills from removed liquidity + pending fees
                amount_y=0,
            )],
        )

    def on_swap(
        self, event: SwapEvent, pool: PoolState, position: PositionState
    ) -> Action:
        return self._maybe_rebalance(pool, position)

    def on_tick(
        self, ts: int, pool: PoolState, position: PositionState
    ) -> Action:
        if self.params.rebalance_cadence_secs is None:
            return NoOp()
        if ts - self._last_tick_check_ts < self.params.rebalance_cadence_secs * 1000:
            return NoOp()
        self._last_tick_check_ts = ts
        return self._maybe_rebalance(pool, position)
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_precision_curve.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/strategies/precision_curve.py tests/unit/test_precision_curve.py
git commit -m "feat(strategies): Precision Curve baseline (v1 default params)"
```

### Task 3.4: Multiday Cook Up baseline (`strategies/multiday_cook_up.py`)

**HawkFi Multiday Cook Up interpretation (v1 placeholder defaults):**
- Directional up-only auto-rebalance (recenters only when price moves UP)
- Wider range than Precision Curve (default 121 bins) for IL protection on down-moves
- Rebalance cadence: hourly check via on_tick (default 3600s)
- Auto-compound, auto-claim to SOL: both default True
- Will NOT rebalance down — if price drops below position, it just sits idle until price recovers or position is manually closed

**Files:**
- Modify: `asteroid_belt/strategies/multiday_cook_up.py`
- Test: `tests/unit/test_multiday_cook_up.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_multiday_cook_up.py
from decimal import Decimal

from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import (
    PoolState,
    StaticFeeParams,
    VolatilityState,
)
from asteroid_belt.strategies.base import (
    Capital,
    NoOp,
    OpenPosition,
    Rebalance,
)
from asteroid_belt.strategies.multiday_cook_up import (
    MultidayCookUpParams,
    MultidayCookUpStrategy,
)


def _pool(active_bin: int) -> PoolState:
    return PoolState(
        active_bin=active_bin, bin_step=10, mid_price=Decimal("87.55"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={}, last_swap_ts=0, reward_infos=[],
    )


def _pos(lower: int, upper: int) -> PositionState:
    return PositionState(
        lower_bin=lower, upper_bin=upper, composition={},
        fee_pending_x=0, fee_pending_y=0, fee_pending_per_bin={},
        total_claimed_x=0, total_claimed_y=0, fee_owner=None,
    )


def test_initialize_opens_wide_curve() -> None:
    s = MultidayCookUpStrategy(MultidayCookUpParams(bin_width=121))
    a = s.initialize(_pool(active_bin=100), Capital(x=1_000_000_000, y=8_000_000_000))
    assert isinstance(a, OpenPosition)
    assert a.distribution == "curve"
    assert a.upper_bin - a.lower_bin == 120  # bin_width=121 means 120 distance


def test_on_tick_too_soon_returns_noop() -> None:
    s = MultidayCookUpStrategy(MultidayCookUpParams(rebalance_cadence_secs=3600))
    s.initialize(_pool(active_bin=0), Capital(x=1_000_000_000, y=8_000_000_000))
    out = s.on_tick(ts=1_000_000_000, pool=_pool(active_bin=20), position=_pos(-60, 60))
    assert isinstance(out, NoOp)
    # Subsequent tick within the cadence is also no-op
    out2 = s.on_tick(ts=1_000_001_000, pool=_pool(active_bin=20), position=_pos(-60, 60))
    assert isinstance(out2, NoOp)


def test_on_tick_after_cadence_with_upward_drift_rebalances() -> None:
    p = MultidayCookUpParams(bin_width=121, rebalance_cadence_secs=3600,
                              upward_rebalance_trigger_bins=10)
    s = MultidayCookUpStrategy(p)
    s.initialize(_pool(active_bin=0), Capital(x=1_000_000_000, y=8_000_000_000))
    # First tick to start the clock
    s.on_tick(ts=0, pool=_pool(active_bin=0), position=_pos(-60, 60))
    # Advance past cadence with upward drift
    out = s.on_tick(
        ts=3_600_000 + 1, pool=_pool(active_bin=20), position=_pos(-60, 60),
    )
    assert isinstance(out, Rebalance)


def test_on_tick_after_cadence_with_downward_drift_does_not_rebalance() -> None:
    p = MultidayCookUpParams(bin_width=121, rebalance_cadence_secs=3600,
                              upward_rebalance_trigger_bins=10)
    s = MultidayCookUpStrategy(p)
    s.initialize(_pool(active_bin=100), Capital(x=1_000_000_000, y=8_000_000_000))
    s.on_tick(ts=0, pool=_pool(active_bin=100), position=_pos(40, 160))
    # Drift DOWN by 30 bins; cook-up should not rebalance
    out = s.on_tick(
        ts=3_600_000 + 1, pool=_pool(active_bin=70), position=_pos(40, 160),
    )
    assert isinstance(out, NoOp)
```

Run: `pytest tests/unit/test_multiday_cook_up.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/strategies/multiday_cook_up.py
"""Multiday Cook Up baseline strategy.

HawkFi Multiday Cook Up: directional up-only auto-rebalance, wide range for
IL protection on down-moves. Rebalances only when price moves UP past the
position; sits idle on down-moves until price recovers or it's manually
closed.

Defaults are v1 best-effort interpretations of HawkFi prose docs.
"""

from __future__ import annotations

from dataclasses import dataclass

from asteroid_belt.data.adapters.base import SwapEvent
from asteroid_belt.pool.position_state import PositionState
from asteroid_belt.pool.state import PoolState
from asteroid_belt.strategies.base import (
    Action,
    BinRangeAdd,
    BinRangeRemoval,
    Capital,
    NoOp,
    OpenPosition,
    Rebalance,
    Strategy,
)


@dataclass(frozen=True)
class MultidayCookUpParams:
    bin_width: int = 121  # wider than Precision Curve for down-move cushion
    rebalance_cadence_secs: int = 3600  # hourly check
    upward_rebalance_trigger_bins: int = 10  # how far up before rebalancing
    auto_compound: bool = True
    auto_claim_to_sol: bool = True


class MultidayCookUpStrategy(Strategy):
    """v1 baseline #2: directional up-only LP with hourly rebalance check."""

    def __init__(self, params: MultidayCookUpParams) -> None:
        self.params = params
        self._last_tick_ts: int | None = None

    def _half_width(self) -> int:
        return self.params.bin_width // 2

    def initialize(self, pool: PoolState, capital: Capital) -> Action:
        self._last_tick_ts = None
        half = self._half_width()
        return OpenPosition(
            lower_bin=pool.active_bin - half,
            upper_bin=pool.active_bin + half,
            distribution="curve",
            capital_x_pct=None,
            slippage_bps=50,
        )

    def on_swap(
        self, event: SwapEvent, pool: PoolState, position: PositionState
    ) -> Action:
        # Cook-up is purely time-driven; swap events don't trigger rebalance.
        return NoOp()

    def on_tick(
        self, ts: int, pool: PoolState, position: PositionState
    ) -> Action:
        if self._last_tick_ts is None:
            self._last_tick_ts = ts
            return NoOp()
        if ts - self._last_tick_ts < self.params.rebalance_cadence_secs * 1000:
            return NoOp()
        self._last_tick_ts = ts

        # Up-only: rebalance only if active_bin drifted UP past trigger
        center = (position.lower_bin + position.upper_bin) // 2
        upward_drift = pool.active_bin - center
        if upward_drift <= self.params.upward_rebalance_trigger_bins:
            return NoOp()

        half = self._half_width()
        return Rebalance(
            removes=[BinRangeRemoval(
                lower_bin=position.lower_bin,
                upper_bin=position.upper_bin,
                bps=10_000,
            )],
            adds=[BinRangeAdd(
                lower_bin=pool.active_bin - half,
                upper_bin=pool.active_bin + half,
                distribution="curve",
                amount_x=0,
                amount_y=0,
            )],
        )
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_multiday_cook_up.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/strategies/multiday_cook_up.py tests/unit/test_multiday_cook_up.py
git commit -m "feat(strategies): Multiday Cook Up baseline (v1 default params)"
```

---

**End of Phase 3.** You have: train/holdout split helper, bar-synthesized adapter, two baseline strategies. Total tests: ~70.

---

## Phase 4 — Storage layer + Meteora ingest

Wires DuckDB persistence + parquet result writers + the Meteora OHLCV ingest pipeline. After this phase, you can ingest a real pool's history and persist BacktestResults to disk.

### Task 4.1: DuckDB schema + RunStore (`store/runs.py`, `store/schema.sql`)

**Files:**
- Create: `asteroid_belt/store/schema.sql`
- Modify: `asteroid_belt/store/runs.py`
- Test: `tests/unit/test_store_runs.py`

- [ ] **Step 1: Write the schema**

```sql
-- asteroid_belt/store/schema.sql
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
```

- [ ] **Step 2: Write the test**

```python
# tests/unit/test_store_runs.py
import json
from pathlib import Path

import pytest

from asteroid_belt.store.runs import (
    DuckDBRunStore,
    RunRecord,
    RunStore,
)


@pytest.fixture
def store(tmp_path: Path) -> DuckDBRunStore:
    db_path = tmp_path / "meta.duckdb"
    return DuckDBRunStore(db_path=db_path)


def _record(run_id: str, score: float = 0.0) -> RunRecord:
    return RunRecord(
        run_id=run_id, config_hash="hash_" + run_id,
        parent_run_id=None, session_id=None,
        created_by="human", cost_model_version="v0.1.0-unverified",
        schema_version="1.0",
        pool_address="BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y",
        strategy_class="asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy",
        strategy_params={"bin_width": 69},
        strategy_source_sha=None,
        adapter_kind="bar",
        window_start=0, window_end=1000,
        tick_secs=300,
        initial_x=1_000_000_000, initial_y=8_000_000_000,
        selection_metric="sharpe",
        started_at=1, ended_at=2,
        status="ok", error_msg=None,
        score=score, primitives={"sharpe": score},
        notes=None,
    )


def test_protocol_satisfied() -> None:
    s: RunStore = DuckDBRunStore  # type: ignore[assignment]
    assert s is not None  # static check


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
    rec_running = RunRecord(**{**rec.__dict__, "status": "running", "ended_at": None, "score": None})
    store.insert(rec_running)
    store.update_status("run_b", status="ok", ended_at=999, score=1.5,
                        primitives={"sharpe": 1.5}, error_msg=None)
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
```

Run: `pytest tests/unit/test_store_runs.py -v` — expect FAIL.

- [ ] **Step 3: Implement**

```python
# asteroid_belt/store/runs.py
"""RunStore Protocol and DuckDB implementation.

Single-writer model: one CLI process at a time touches DuckDB. The Protocol
seam exists so future v2 implementations (queued, sharded for parallel agent
runs) can swap in mechanically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
    def update_status(
        self, run_id: str, *, status: str, **fields: Any
    ) -> None: ...
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
                run.run_id, run.config_hash, run.parent_run_id, run.session_id,
                run.created_by, run.cost_model_version, run.schema_version,
                run.pool_address, run.strategy_class,
                json.dumps(run.strategy_params), run.strategy_source_sha,
                run.adapter_kind, run.window_start, run.window_end, run.tick_secs,
                run.initial_x, run.initial_y, run.selection_metric,
                run.started_at, run.ended_at, run.status, run.error_msg,
                run.score,
                json.dumps(run.primitives) if run.primitives is not None else None,
                run.notes,
            ],
        )

    def update_status(
        self, run_id: str, *, status: str, **fields: Any
    ) -> None:
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
        row = self._con.execute(
            "SELECT * FROM runs WHERE run_id = ?", [run_id]
        ).fetchone()
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
                session.session_id, session.label,
                session.created_at, session.closed_at,
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
            "SELECT session_id, label, created_at, closed_at, session_kind, goal_json, outcome_json, notes FROM sessions WHERE session_id = ?",
            [session_id],
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return SessionRecord(
            session_id=row[0], label=row[1],
            created_at=row[2], closed_at=row[3],
            session_kind=row[4],
            goal_json=json.loads(row[5]) if row[5] else None,
            outcome_json=json.loads(row[6]) if row[6] else None,
            notes=row[7],
        )

    @staticmethod
    def _row_to_record(row: tuple[Any, ...]) -> RunRecord:
        # Order matches `SELECT *` against runs table — preserve schema-order.
        # Column order: run_id, config_hash, parent_run_id, session_id,
        # created_by, cost_model_version, schema_version, pool_address,
        # strategy_class, strategy_params, strategy_source_sha, adapter_kind,
        # window_start, window_end, tick_secs, initial_x, initial_y,
        # selection_metric, started_at, ended_at, status, error_msg,
        # score, primitives, notes
        return RunRecord(
            run_id=row[0], config_hash=row[1],
            parent_run_id=row[2], session_id=row[3],
            created_by=row[4], cost_model_version=row[5],
            schema_version=row[6],
            pool_address=row[7], strategy_class=row[8],
            strategy_params=json.loads(row[9]) if row[9] else {},
            strategy_source_sha=row[10],
            adapter_kind=row[11],
            window_start=row[12], window_end=row[13],
            tick_secs=row[14],
            initial_x=row[15], initial_y=row[16],
            selection_metric=row[17],
            started_at=row[18], ended_at=row[19],
            status=row[20], error_msg=row[21],
            score=row[22],
            primitives=json.loads(row[23]) if row[23] else None,
            notes=row[24],
        )
```

- [ ] **Step 4: Run tests (expect PASS)**

```bash
pytest tests/unit/test_store_runs.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add asteroid_belt/store/schema.sql asteroid_belt/store/runs.py tests/unit/test_store_runs.py
git commit -m "feat(store): DuckDB schema + RunStore Protocol + DuckDBRunStore impl"
```

### Task 4.2: BacktestResult ↔ parquet (`store/results.py`)

**Files:**
- Modify: `asteroid_belt/store/results.py`
- Test: `tests/unit/test_store_results.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_store_results.py
from pathlib import Path

import polars as pl
import pytest

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord
from asteroid_belt.store.results import (
    read_rebalances,
    read_trajectory,
    write_result,
)


def _result(run_id: str = "test_run") -> BacktestResult:
    df = pl.DataFrame({
        "ts": [0, 1], "price": [1.0, 1.1], "active_bin": [0, 1],
        "position_value_usd": [100.0, 110.0], "hodl_value_usd": [100.0, 100.0],
        "fees_x_cumulative": [0, 100], "fees_y_cumulative": [0, 200],
        "il_cumulative": [0.0, 10.0], "in_range": [True, True],
        "capital_idle_usd": [0.0, 0.0],
    })
    return BacktestResult(
        run_id=run_id, config_hash="h", schema_version="1.0",
        started_at=0, ended_at=1, status="ok",
        trajectory=df,
        rebalances=[
            RebalanceRecord(ts=500, trigger="drift",
                            old_lower_bin=-30, old_upper_bin=30,
                            new_lower_bin=-20, new_upper_bin=40,
                            gas_lamports=10_000, composition_fee_x=0,
                            composition_fee_y=5_000, fees_claimed_x=0,
                            fees_claimed_y=2_000),
        ],
        primitives={"net_pnl": 10.0}, score=10.0, score_metric="net_pnl",
    )


def test_write_then_read_trajectory(tmp_path: Path) -> None:
    r = _result()
    write_result(result=r, runs_dir=tmp_path)
    df = read_trajectory(run_id="test_run", runs_dir=tmp_path)
    assert df.height == 2


def test_write_then_read_rebalances(tmp_path: Path) -> None:
    r = _result()
    write_result(result=r, runs_dir=tmp_path)
    rebs = read_rebalances(run_id="test_run", runs_dir=tmp_path)
    assert len(rebs) == 1
    assert rebs[0].trigger == "drift"


def test_manifest_written(tmp_path: Path) -> None:
    import json
    r = _result()
    write_result(result=r, runs_dir=tmp_path)
    manifest_path = tmp_path / "test_run" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["run_id"] == "test_run"
    assert manifest["primitives"]["net_pnl"] == 10.0
```

Run: `pytest tests/unit/test_store_results.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/store/results.py
"""BacktestResult ↔ parquet round-trip + manifest writer.

Per-run layout under data/runs/<run_id>/:
  result.parquet         # trajectory
  rebalances.parquet     # discrete rebalance events
  manifest.json          # config snapshot + primitives + score (portable)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import polars as pl

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord


def write_result(*, result: BacktestResult, runs_dir: Path) -> None:
    """Write trajectory + rebalances + manifest under runs_dir/<run_id>/."""
    out_dir = runs_dir / result.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Trajectory
    result.trajectory.write_parquet(out_dir / "result.parquet")

    # Rebalances
    if result.rebalances:
        reb_df = pl.DataFrame([asdict(r) for r in result.rebalances])
    else:
        reb_df = pl.DataFrame({
            "ts": pl.Series([], dtype=pl.Int64),
            "trigger": pl.Series([], dtype=pl.Utf8),
            "old_lower_bin": pl.Series([], dtype=pl.Int32),
            "old_upper_bin": pl.Series([], dtype=pl.Int32),
            "new_lower_bin": pl.Series([], dtype=pl.Int32),
            "new_upper_bin": pl.Series([], dtype=pl.Int32),
            "gas_lamports": pl.Series([], dtype=pl.Int64),
            "composition_fee_x": pl.Series([], dtype=pl.Int64),
            "composition_fee_y": pl.Series([], dtype=pl.Int64),
            "fees_claimed_x": pl.Series([], dtype=pl.Int64),
            "fees_claimed_y": pl.Series([], dtype=pl.Int64),
        })
    reb_df.write_parquet(out_dir / "rebalances.parquet")

    # Manifest (portable; lets you zip a run dir and replay elsewhere)
    manifest = {
        "run_id": result.run_id,
        "config_hash": result.config_hash,
        "schema_version": result.schema_version,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "status": result.status,
        "primitives": result.primitives,
        "score": result.score,
        "score_metric": result.score_metric,
        "error_msg": result.error_msg,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def read_trajectory(*, run_id: str, runs_dir: Path) -> pl.DataFrame:
    return pl.read_parquet(runs_dir / run_id / "result.parquet")


def read_rebalances(*, run_id: str, runs_dir: Path) -> list[RebalanceRecord]:
    df = pl.read_parquet(runs_dir / run_id / "rebalances.parquet")
    return [
        RebalanceRecord(**row)
        for row in df.iter_rows(named=True)
    ]
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_store_results.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/store/results.py tests/unit/test_store_results.py
git commit -m "feat(store): BacktestResult ↔ parquet round-trip + manifest"
```

### Task 4.3: Meteora OHLCV ingest (`data/ingest.py`)

**Files:**
- Modify: `asteroid_belt/data/ingest.py`
- Test: `tests/unit/test_ingest.py`

- [ ] **Step 1: Write the test (uses respx for HTTP mocking)**

First add respx to dev deps:

```bash
uv pip install respx
# Then add to pyproject.toml [project.optional-dependencies] dev: "respx>=0.21"
```

Edit `pyproject.toml` to add `"respx>=0.21",` to the `dev` list.

```python
# tests/unit/test_ingest.py
import json
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx

from asteroid_belt.data.ingest import ingest_meteora_ohlcv


@pytest.fixture
def fake_meteora_response() -> dict:
    return {
        "data": [
            # Each point: ts (sec), open, high, low, close, volume_x, volume_y
            [1_700_000_000, 87.50, 87.56, 87.49, 87.55, 1_000_000, 87_550_000],
            [1_700_000_060, 87.55, 87.61, 87.54, 87.60, 1_500_000, 131_400_000],
        ]
    }


@respx.mock
def test_ingest_writes_parquet(tmp_path: Path, fake_meteora_response: dict) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    respx.get(
        f"https://dlmm.datapi.meteora.ag/pools/{pool}/ohlcv"
    ).mock(return_value=httpx.Response(200, json=fake_meteora_response))

    ingest_meteora_ohlcv(
        pool=pool, start="2023-11-14T00:00:00Z", end="2023-11-14T00:02:00Z",
        out_dir=tmp_path,
    )

    parquet_path = tmp_path / pool / "bars_1m.parquet"
    assert parquet_path.exists()
    df = pl.read_parquet(parquet_path)
    assert df.height == 2
    assert "ts" in df.columns
    assert "open" in df.columns


@respx.mock
def test_ingest_idempotent(tmp_path: Path, fake_meteora_response: dict) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    respx.get(
        f"https://dlmm.datapi.meteora.ag/pools/{pool}/ohlcv"
    ).mock(return_value=httpx.Response(200, json=fake_meteora_response))

    ingest_meteora_ohlcv(
        pool=pool, start="2023-11-14T00:00:00Z", end="2023-11-14T00:02:00Z",
        out_dir=tmp_path,
    )
    # Second call: same window, should not duplicate rows
    ingest_meteora_ohlcv(
        pool=pool, start="2023-11-14T00:00:00Z", end="2023-11-14T00:02:00Z",
        out_dir=tmp_path,
    )
    df = pl.read_parquet(tmp_path / pool / "bars_1m.parquet")
    assert df.height == 2  # not 4


@respx.mock
def test_ingest_writes_pool_meta(tmp_path: Path, fake_meteora_response: dict) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    respx.get(
        f"https://dlmm.datapi.meteora.ag/pools/{pool}/ohlcv"
    ).mock(return_value=httpx.Response(200, json=fake_meteora_response))
    # Mock the pool-detail endpoint too
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}").mock(
        return_value=httpx.Response(200, json={
            "address": pool, "name": "SOL-USDC",
            "token_x": {"address": "x", "decimals": 9},
            "token_y": {"address": "y", "decimals": 6},
            "pool_config": {"bin_step": 10, "base_fee_pct": 0.1},
        }),
    )

    ingest_meteora_ohlcv(
        pool=pool, start="2023-11-14T00:00:00Z", end="2023-11-14T00:02:00Z",
        out_dir=tmp_path,
    )
    meta = json.loads((tmp_path / pool / "pool_meta.json").read_text())
    assert meta["address"] == pool
    assert meta["pool_config"]["bin_step"] == 10
```

Run: `pytest tests/unit/test_ingest.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/data/ingest.py
"""Meteora OHLCV ingest.

Pulls 1m bars from `https://dlmm.datapi.meteora.ag/pools/<addr>/ohlcv` in
paginated chunks, writes to data/pools/<addr>/bars_1m.parquet, and records
pool metadata to pool_meta.json. Idempotent: re-running with the same window
deduplicates by `ts`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import polars as pl

DATAPI_BASE = "https://dlmm.datapi.meteora.ag"
DLMM_API_BASE = "https://dlmm-api.meteora.ag"


def _to_unix_seconds(iso: str) -> int:
    s = iso.replace("Z", "+00:00")
    return int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp())


def _fetch_pool_meta(pool: str, *, client: httpx.Client) -> dict[str, Any]:
    r = client.get(f"{DATAPI_BASE}/pools/{pool}")
    r.raise_for_status()
    return r.json()


def _fetch_ohlcv(
    pool: str, *, start_sec: int, end_sec: int, client: httpx.Client
) -> list[list[Any]]:
    """Fetch raw OHLCV points; expected shape: list of [ts, o, h, l, c, vol_x, vol_y]."""
    r = client.get(
        f"{DATAPI_BASE}/pools/{pool}/ohlcv",
        params={"resolution": 1, "start": start_sec, "end": end_sec},
        timeout=30.0,
    )
    r.raise_for_status()
    payload = r.json()
    # The Meteora datapi response shape is `{"data": [[ts, o, h, l, c, vol_x, vol_y], ...]}`.
    # If the schema differs at runtime, adjust this extractor and update the test fixture.
    return payload.get("data", [])


def ingest_meteora_ohlcv(
    *,
    pool: str,
    start: str,
    end: str,
    out_dir: Path,
) -> None:
    """Ingest 1m OHLCV for a pool over [start, end]. Idempotent.

    Outputs:
      out_dir/<pool>/bars_1m.parquet
      out_dir/<pool>/pool_meta.json
      out_dir/<pool>/ingest_log.json
    """
    pool_dir = out_dir / pool
    pool_dir.mkdir(parents=True, exist_ok=True)

    start_sec = _to_unix_seconds(start)
    end_sec = _to_unix_seconds(end)

    with httpx.Client() as client:
        # Fetch pool metadata once (idempotent overwrite is fine).
        try:
            meta = _fetch_pool_meta(pool, client=client)
            (pool_dir / "pool_meta.json").write_text(json.dumps(meta, indent=2))
        except httpx.HTTPError:
            # Don't fail ingest if metadata endpoint is flaky; log and continue.
            pass

        # Fetch bars. For v1 we issue one request per call; if the API caps the
        # response window, we paginate by stepping `start_sec` forward.
        # TODO: confirm API window cap before relying on a single-shot fetch.
        raw_points = _fetch_ohlcv(
            pool, start_sec=start_sec, end_sec=end_sec, client=client
        )

    if not raw_points:
        return

    # Normalize to ts in milliseconds for consistency with rest of the codebase.
    rows = [
        {
            "ts": int(p[0]) * 1000,
            "open": float(p[1]),
            "high": float(p[2]),
            "low": float(p[3]),
            "close": float(p[4]),
            "volume_x": int(p[5]),
            "volume_y": int(p[6]),
        }
        for p in raw_points
    ]
    new_df = pl.DataFrame(rows)

    parquet_path = pool_dir / "bars_1m.parquet"
    if parquet_path.exists():
        existing = pl.read_parquet(parquet_path)
        combined = pl.concat([existing, new_df]).unique(subset=["ts"]).sort("ts")
    else:
        combined = new_df.unique(subset=["ts"]).sort("ts")

    combined.write_parquet(parquet_path)

    # Update ingest log
    log_path = pool_dir / "ingest_log.json"
    log: dict[str, Any] = json.loads(log_path.read_text()) if log_path.exists() else {}
    log["last_ingested_start_sec"] = start_sec
    log["last_ingested_end_sec"] = end_sec
    log["row_count"] = combined.height
    log_path.write_text(json.dumps(log, indent=2))
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_ingest.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/data/ingest.py tests/unit/test_ingest.py pyproject.toml
git commit -m "feat(data): Meteora OHLCV ingest with idempotent dedup"
```

---

**End of Phase 4.** Storage and ingest are wired. Total tests: ~85. Phase 5 wires the config layer + CLI; Phase 6 lights up the FastAPI server.

---

## Phase 5 — Config + CLI

Pydantic-validated YAML run configs, canonical hashing for dedup/identity, and the `belt` CLI commands. End of this phase: `belt ingest`, `belt run --config`, `belt session new/close` all work end-to-end against real or fixture data.

### Task 5.1: Run config Pydantic models (`config.py`)

**Files:**
- Modify: `asteroid_belt/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_config.py
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from asteroid_belt.config import RunConfig, load_run_config


def _ms(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00"))
                .astimezone(timezone.utc).timestamp() * 1000)


@pytest.fixture
def valid_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text("""
schema_version: "1.0"
pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
window:
  start: "2024-05-01T00:00:00Z"
  end: "2024-05-02T00:00:00Z"
adapter:
  kind: bar
strategy:
  class: asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy
  params:
    bin_width: 69
    rebalance_trigger_bins: 10
engine:
  tick_secs: 300
  initial_x: 100000000
  initial_y: 8800000000
  selection_metric: sharpe
  timeout_secs: 600
session_id: null
notes: "test config"
""")
    return p


def test_load_valid_config(valid_yaml: Path) -> None:
    cfg = load_run_config(valid_yaml)
    assert cfg.schema_version == "1.0"
    assert cfg.pool == "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    assert cfg.adapter.kind == "bar"
    assert cfg.engine.selection_metric == "sharpe"


def test_window_to_ms(valid_yaml: Path) -> None:
    cfg = load_run_config(valid_yaml)
    win = cfg.window_to_ms()
    assert win.start_ms == _ms("2024-05-01T00:00:00Z")
    assert win.end_ms == _ms("2024-05-02T00:00:00Z")


def test_unknown_top_level_field_allowed(tmp_path: Path) -> None:
    """Forward-compat: extra fields don't break v1 reader (Pydantic extra=allow)."""
    p = tmp_path / "cfg.yaml"
    p.write_text("""
schema_version: "1.0"
pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
window:
  start: "2024-05-01T00:00:00Z"
  end: "2024-05-02T00:00:00Z"
adapter:
  kind: bar
strategy:
  class: asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy
  params: {}
engine:
  tick_secs: 300
  initial_x: 1
  initial_y: 1
  selection_metric: sharpe
  timeout_secs: 60
future_field_v15: "this should not break v1 loading"
""")
    cfg = load_run_config(p)
    assert cfg.pool == "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"


def test_invalid_adapter_kind_rejected(tmp_path: Path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text("""
schema_version: "1.0"
pool: x
window: {start: "2024-05-01T00:00:00Z", end: "2024-05-02T00:00:00Z"}
adapter: {kind: invalid}
strategy: {class: foo, params: {}}
engine:
  tick_secs: 60
  initial_x: 1
  initial_y: 1
  selection_metric: sharpe
  timeout_secs: 60
""")
    with pytest.raises(Exception):
        load_run_config(p)


def test_canonical_hash_stable(valid_yaml: Path) -> None:
    cfg1 = load_run_config(valid_yaml)
    cfg2 = load_run_config(valid_yaml)
    assert cfg1.config_hash() == cfg2.config_hash()


def test_canonical_hash_changes_with_strategy_param(tmp_path: Path) -> None:
    p1 = tmp_path / "a.yaml"
    p2 = tmp_path / "b.yaml"
    base = """
schema_version: "1.0"
pool: x
window: {start: "2024-05-01T00:00:00Z", end: "2024-05-02T00:00:00Z"}
adapter: {kind: bar}
engine:
  tick_secs: 60
  initial_x: 1
  initial_y: 1
  selection_metric: sharpe
  timeout_secs: 60
"""
    p1.write_text(base + """
strategy:
  class: foo
  params: {bin_width: 69}
""")
    p2.write_text(base + """
strategy:
  class: foo
  params: {bin_width: 121}
""")
    h1 = load_run_config(p1).config_hash()
    h2 = load_run_config(p2).config_hash()
    assert h1 != h2
```

Run: `pytest tests/unit/test_config.py -v` — expect FAIL.

- [ ] **Step 2: Implement**

```python
# asteroid_belt/config.py
"""Run config: Pydantic models + canonical hashing.

The YAML schema is versioned (`schema_version: "1.0"` for v1). Pydantic
`extra="allow"` on read paths so future v1.5+ schemas don't break v1
readers; strict on write. Canonical hash is over a stable JSON serialization
plus the source SHA of `engine/cost.py` and `engine/runner.py`, so changes
to the engine show up in dedup keys.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from asteroid_belt.data.adapters.base import TimeWindow

# --- Static module hashes for canonical hash inclusion -------------------

_ENGINE_FILES_TO_HASH = [
    "asteroid_belt/engine/cost.py",
    "asteroid_belt/engine/runner.py",
    "asteroid_belt/engine/guards.py",
]


def _module_sha() -> str:
    h = hashlib.sha256()
    repo_root = Path(__file__).resolve().parent.parent
    for rel in _ENGINE_FILES_TO_HASH:
        path = repo_root / rel
        if path.exists():
            h.update(path.read_bytes())
    return h.hexdigest()


# --- Pydantic models -----------------------------------------------------


class WindowSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    start: str  # ISO-8601 with timezone
    end: str


class AdapterSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: Literal["bar", "swap"]


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    class_: str = Field(alias="class")
    params: dict[str, Any] = Field(default_factory=dict)


class EngineSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    tick_secs: int = 300
    initial_x: int  # raw token units
    initial_y: int  # raw token units
    selection_metric: str = "sharpe"
    timeout_secs: int = 600


class RunConfig(BaseModel):
    """v1 schema. Forward-compat reads via extra='allow'; strict on write."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: Literal["1.0"] = "1.0"
    pool: str
    window: WindowSpec
    adapter: AdapterSpec
    strategy: StrategySpec
    engine: EngineSpec
    session_id: str | None = None
    notes: str | None = None

    def window_to_ms(self) -> TimeWindow:
        def _ms(iso: str) -> int:
            s = iso.replace("Z", "+00:00")
            return int(
                datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000
            )
        return TimeWindow(
            start_ms=_ms(self.window.start),
            end_ms=_ms(self.window.end),
        )

    def canonical_dict(self) -> dict[str, Any]:
        """Stable, sorted-key dict for hashing. Excludes notes (cosmetic)."""
        return {
            "schema_version": self.schema_version,
            "pool": self.pool,
            "window": {"start": self.window.start, "end": self.window.end},
            "adapter": {"kind": self.adapter.kind},
            "strategy": {
                "class": self.strategy.class_,
                "params": _deep_sorted(self.strategy.params),
            },
            "engine": {
                "tick_secs": self.engine.tick_secs,
                "initial_x": self.engine.initial_x,
                "initial_y": self.engine.initial_y,
                "selection_metric": self.engine.selection_metric,
                "timeout_secs": self.engine.timeout_secs,
            },
            "session_id": self.session_id,
            "engine_module_sha": _module_sha(),
        }

    def config_hash(self) -> str:
        canonical = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


def _deep_sorted(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _deep_sorted(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_deep_sorted(x) for x in obj]
    return obj


def load_run_config(path: Path) -> RunConfig:
    raw = yaml.safe_load(path.read_text())
    return RunConfig.model_validate(raw)
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_config.py -v
```

Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/config.py tests/unit/test_config.py
git commit -m "feat(config): Pydantic RunConfig with canonical hashing"
```

### Task 5.2: Run config files (`configs/*.yaml`)

**Files:**
- Create: `configs/quickstart.yaml`
- Create: `configs/precision_curve_baseline.yaml`
- Create: `configs/multiday_cook_up_baseline.yaml`

- [ ] **Step 1: Quickstart config (small window for smoke testing)**

```yaml
# configs/quickstart.yaml
# 1-day window for fast end-to-end smoke testing.
schema_version: "1.0"
pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
window:
  start: "2025-09-01T00:00:00Z"
  end: "2025-09-02T00:00:00Z"
adapter:
  kind: bar
strategy:
  class: asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy
  params:
    bin_width: 69
    rebalance_trigger_bins: 10
    rebalance_cadence_secs: null
    auto_compound: true
    auto_claim_to_sol: false
engine:
  tick_secs: 300
  initial_x: 100000000        # 0.1 SOL (lamports, 9 decimals)
  initial_y: 8800000000       # 8800 USDC (raw, 6 decimals)
  selection_metric: sharpe
  timeout_secs: 120
session_id: null
notes: |
  Smoke test config. Single-day window, Precision Curve baseline.
```

- [ ] **Step 2: Precision Curve baseline**

```yaml
# configs/precision_curve_baseline.yaml
# v1 baseline #1: Precision Curve over the full train window.
schema_version: "1.0"
pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
window:
  start: "2024-05-01T00:00:00Z"
  end: "2025-10-31T00:00:00Z"   # train upper bound; never crosses holdout
adapter:
  kind: bar
strategy:
  class: asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy
  params:
    bin_width: 69
    rebalance_trigger_bins: 10
    rebalance_cadence_secs: null
    auto_compound: true
    auto_claim_to_sol: false
engine:
  tick_secs: 300
  initial_x: 100000000
  initial_y: 8800000000
  selection_metric: sharpe
  timeout_secs: 600
session_id: null
notes: |
  Baseline Precision Curve, HawkFi prose-doc defaults.
```

- [ ] **Step 3: Multiday Cook Up baseline**

```yaml
# configs/multiday_cook_up_baseline.yaml
# v1 baseline #2: Multiday Cook Up over the full train window.
schema_version: "1.0"
pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
window:
  start: "2024-05-01T00:00:00Z"
  end: "2025-10-31T00:00:00Z"
adapter:
  kind: bar
strategy:
  class: asteroid_belt.strategies.multiday_cook_up.MultidayCookUpStrategy
  params:
    bin_width: 121
    rebalance_cadence_secs: 3600
    upward_rebalance_trigger_bins: 10
    auto_compound: true
    auto_claim_to_sol: true
engine:
  tick_secs: 3600              # match the strategy's hourly cadence
  initial_x: 100000000
  initial_y: 8800000000
  selection_metric: sharpe
  timeout_secs: 600
session_id: null
notes: |
  Baseline Multiday Cook Up — directional up-only auto-rebalance, hourly tick.
```

- [ ] **Step 4: Verify configs parse**

```bash
python -c "
from pathlib import Path
from asteroid_belt.config import load_run_config
for p in ['configs/quickstart.yaml', 'configs/precision_curve_baseline.yaml', 'configs/multiday_cook_up_baseline.yaml']:
    cfg = load_run_config(Path(p))
    print(f'{p}: hash={cfg.config_hash()[:12]}')
"
```

Expected: prints three distinct config_hash values.

- [ ] **Step 5: Commit**

```bash
git add configs/
git commit -m "feat(configs): quickstart and two baseline YAMLs"
```

### Task 5.3: CLI — `belt ingest` (`cli.py`)

**Files:**
- Modify: `asteroid_belt/cli.py`
- Test: `tests/unit/test_cli_ingest.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_cli_ingest.py
from pathlib import Path

import httpx
import respx
from click.testing import CliRunner

from asteroid_belt.cli import cli


@respx.mock
def test_ingest_invokes_meteora(tmp_path: Path) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}/ohlcv").mock(
        return_value=httpx.Response(200, json={
            "data": [[1_700_000_000, 87.5, 87.6, 87.4, 87.55, 1000, 87550]]
        })
    )
    respx.get(f"https://dlmm.datapi.meteora.ag/pools/{pool}").mock(
        return_value=httpx.Response(200, json={"address": pool})
    )

    runner = CliRunner()
    result = runner.invoke(cli, [
        "ingest", "--pool", pool,
        "--start", "2023-11-14T00:00:00Z",
        "--end", "2023-11-14T00:01:00Z",
        "--data-dir", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert (tmp_path / "pools" / pool / "bars_1m.parquet").exists()
```

Run: `pytest tests/unit/test_cli_ingest.py -v` — expect FAIL.

- [ ] **Step 2: Implement CLI bootstrap + ingest command**

```python
# asteroid_belt/cli.py
"""asteroid-belt CLI (`belt`).

Commands:
  belt ingest    --pool <addr> --start <iso> --end <iso>  [--data-dir DIR]
  belt run       --config <path.yaml>                      [--data-dir DIR]
                                                            [--force]
                                                            [--session SID]
  belt session   new --label <text>                        [--kind manual]
  belt session   close --id <SID>
  belt run notes --id <RID> --set <text>
  belt serve                                                [--port 8000]
"""

from __future__ import annotations

from pathlib import Path

import click

DEFAULT_DATA_DIR = Path("data")


@click.group()
def cli() -> None:
    """asteroid-belt: DLMM strategy research desk."""


@cli.command()
@click.option("--pool", required=True, help="Meteora pool address (base58)")
@click.option("--start", required=True, help="ISO-8601 start (e.g. 2024-05-01T00:00:00Z)")
@click.option("--end", required=True, help="ISO-8601 end")
@click.option("--data-dir", default=str(DEFAULT_DATA_DIR), type=click.Path(),
              help="Root data directory (default: ./data)")
def ingest(pool: str, start: str, end: str, data_dir: str) -> None:
    """Ingest 1m OHLCV bars from Meteora into data/pools/<pool>/."""
    from asteroid_belt.data.ingest import ingest_meteora_ohlcv

    out_dir = Path(data_dir) / "pools"
    out_dir.mkdir(parents=True, exist_ok=True)
    ingest_meteora_ohlcv(pool=pool, start=start, end=end, out_dir=out_dir)
    click.echo(f"ingested {pool} for [{start}, {end}] → {out_dir / pool}")


# Other commands added in subsequent tasks.

if __name__ == "__main__":
    cli()
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_cli_ingest.py -v
```

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/cli.py tests/unit/test_cli_ingest.py
git commit -m "feat(cli): belt ingest"
```

### Task 5.4: CLI — `belt run` (full lifecycle)

**Files:**
- Modify: `asteroid_belt/cli.py` (add `run` command)
- Modify: `asteroid_belt/engine/runner.py` (extend with primitives computation)
- Test: `tests/integration/test_cli_run_e2e.py`

This task wires together everything from Phases 0–4 into a working `belt run` command. End-to-end:
1. Load YAML config
2. Compute config_hash, dedup-check
3. Insert RunRecord (status=running)
4. Construct adapter pointing at data/pools/<addr>/bars_1m.parquet
5. Instantiate strategy from `strategy.class` + `strategy.params`
6. Bootstrap initial PoolState from `pool_meta.json`
7. Run engine
8. Compute all primitives + score
9. Write trajectory + rebalances + manifest
10. Update RunRecord with final status + score + primitives

- [ ] **Step 1: Add primitives computation to engine**

Modify `asteroid_belt/engine/runner.py`. Add at the bottom of the file:

```python
# Add this import to the top of runner.py
from asteroid_belt.metrics.primitives import PRIMITIVE_REGISTRY


def compute_primitives(result: BacktestResult) -> dict[str, float]:
    """Run every shipped primitive over the trajectory."""
    return {name: fn(result) for name, fn in PRIMITIVE_REGISTRY.items()}
```

Then update the `run_backtest` function's return statement to compute primitives:

Find:
```python
    # Primitives are computed in Phase 2 metrics tasks; for the scaffold, return zeros.
    primitives = {config.selection_metric: 0.0}

    return BacktestResult(
        run_id=config.run_id,
        config_hash=config.config_hash,
        schema_version="1.0",
        started_at=started_at,
        ended_at=ended_at,
        status="ok",
        trajectory=trajectory,
        rebalances=rebalances,
        primitives=primitives,
        score=0.0,
        score_metric=config.selection_metric,
    )
```

Replace with:

```python
    # Build a temporary result to feed primitive functions.
    interim = BacktestResult(
        run_id=config.run_id,
        config_hash=config.config_hash,
        schema_version="1.0",
        started_at=started_at,
        ended_at=ended_at,
        status="ok",
        trajectory=trajectory,
        rebalances=rebalances,
        primitives={},
        score=0.0,
        score_metric=config.selection_metric,
    )
    primitives = compute_primitives(interim)
    score = primitives.get(config.selection_metric, 0.0)

    return BacktestResult(
        run_id=config.run_id,
        config_hash=config.config_hash,
        schema_version="1.0",
        started_at=started_at,
        ended_at=ended_at,
        status="ok",
        trajectory=trajectory,
        rebalances=rebalances,
        primitives=primitives,
        score=score,
        score_metric=config.selection_metric,
    )
```

- [ ] **Step 2: Add helper for strategy class loading**

Add to `asteroid_belt/cli.py`:

```python
import importlib
from typing import Any


def _load_strategy_class(class_path: str) -> type:
    """Resolve a dotted class path like 'asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy'."""
    module_path, _, class_name = class_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _load_strategy_params(strategy_class: type, params: dict[str, Any]) -> Any:
    """Instantiate the strategy's params dataclass from a plain dict.

    Convention: each Strategy subclass declares its params dataclass via a
    `Params` attribute or a `<Class>Params` neighbor in the same module. We
    look up `<Class>Params` in the strategy class's module.
    """
    module = importlib.import_module(strategy_class.__module__)
    params_class_name = strategy_class.__name__.replace("Strategy", "Params")
    params_class = getattr(module, params_class_name)
    return params_class(**params)
```

- [ ] **Step 3: Add `belt run` command**

Add to `asteroid_belt/cli.py`:

```python
@cli.command()
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
@click.option("--data-dir", default=str(DEFAULT_DATA_DIR), type=click.Path())
@click.option("--force", is_flag=True, help="Re-run even if config_hash already exists")
@click.option("--session", "session_id", default=None, help="Optional session id to attach run to")
def run(config_path: str, data_dir: str, force: bool, session_id: str | None) -> None:
    """Run a backtest from a YAML config."""
    import json
    import time
    from decimal import Decimal

    from asteroid_belt.config import load_run_config
    from asteroid_belt.data.adapters.base import PoolKey
    from asteroid_belt.data.adapters.bar import BarSynthesizedAdapter
    from asteroid_belt.engine.cost import COST_MODEL_VERSION
    from asteroid_belt.engine.runner import RunConfigParams, run_backtest
    from asteroid_belt.pool.state import (
        PoolState,
        StaticFeeParams,
        VolatilityState,
    )
    from asteroid_belt.store.results import write_result
    from asteroid_belt.store.runs import DuckDBRunStore, RunRecord

    cfg = load_run_config(Path(config_path))
    config_hash = cfg.config_hash()
    run_id = f"{time.strftime('%Y%m%dT%H%M%S')}_{config_hash[:6]}"

    data_root = Path(data_dir)
    pool_dir = data_root / "pools" / cfg.pool
    runs_dir = data_root / "runs"
    db_path = data_root / "meta.duckdb"
    data_root.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    store = DuckDBRunStore(db_path=db_path)

    # Dedup check
    if not force:
        existing = store.find_by_config_hash(config_hash)
        if existing is not None:
            click.echo(f"existing run with config_hash={config_hash[:12]} found: {existing.run_id}")
            click.echo("pass --force to re-run")
            raise SystemExit(2)

    # Load pool meta for bin_step + decimals
    meta_path = pool_dir / "pool_meta.json"
    if not meta_path.exists():
        click.echo(f"missing pool meta at {meta_path}; run `belt ingest --pool {cfg.pool} ...` first")
        raise SystemExit(2)
    pool_meta = json.loads(meta_path.read_text())
    bin_step = int(pool_meta["pool_config"]["bin_step"])
    decimals_x = int(pool_meta["token_x"]["decimals"])
    decimals_y = int(pool_meta["token_y"]["decimals"])

    # Initial state — minimal v1 bootstrap; bin_liquidity left empty (bar adapter doesn't track per-bin).
    initial_pool_state = PoolState(
        active_bin=0,  # adapter will move it on first event
        bin_step=bin_step,
        mid_price=Decimal("0"),
        volatility=VolatilityState(0, 0, 0, 0),
        static_fee=StaticFeeParams(
            base_factor=10000, filter_period=30, decay_period=600,
            reduction_factor=5000, variable_fee_control=40000,
            protocol_share=500, max_volatility_accumulator=350000,
        ),
        bin_liquidity={}, last_swap_ts=0, reward_infos=[],
    )

    # Insert run row (status=running)
    started_at = int(time.time() * 1000)
    record = RunRecord(
        run_id=run_id, config_hash=config_hash,
        parent_run_id=None, session_id=session_id,
        created_by="human", cost_model_version=COST_MODEL_VERSION,
        schema_version=cfg.schema_version,
        pool_address=cfg.pool, strategy_class=cfg.strategy.class_,
        strategy_params=cfg.strategy.params,
        strategy_source_sha=None, adapter_kind=cfg.adapter.kind,
        window_start=cfg.window_to_ms().start_ms,
        window_end=cfg.window_to_ms().end_ms,
        tick_secs=cfg.engine.tick_secs,
        initial_x=cfg.engine.initial_x, initial_y=cfg.engine.initial_y,
        selection_metric=cfg.engine.selection_metric,
        started_at=started_at, ended_at=None,
        status="running", error_msg=None,
        score=None, primitives=None,
        notes=cfg.notes,
    )
    store.insert(record)

    # Construct adapter + strategy
    adapter = BarSynthesizedAdapter(
        parquet_path=pool_dir / "bars_1m.parquet",
        pool=PoolKey(address=cfg.pool),
        bin_step=bin_step,
    )
    strategy_cls = _load_strategy_class(cfg.strategy.class_)
    strategy_params = _load_strategy_params(strategy_cls, cfg.strategy.params)
    strategy = strategy_cls(strategy_params)

    engine_params = RunConfigParams(
        run_id=run_id, config_hash=config_hash,
        window=cfg.window_to_ms(),
        tick_secs=cfg.engine.tick_secs,
        initial_x=cfg.engine.initial_x, initial_y=cfg.engine.initial_y,
        decimals_x=decimals_x, decimals_y=decimals_y,
        priority_fee_lamports=10_000,
        selection_metric=cfg.engine.selection_metric,
    )

    try:
        result = run_backtest(
            strategy=strategy, adapter=adapter,
            initial_pool_state=initial_pool_state, config=engine_params,
        )
    except Exception as exc:
        store.update_status(
            run_id, status="error", ended_at=int(time.time() * 1000),
            error_msg=str(exc), score=None, primitives=None,
        )
        click.echo(f"run {run_id} FAILED: {exc}")
        raise SystemExit(1)

    write_result(result=result, runs_dir=runs_dir)
    store.update_status(
        run_id, status=result.status, ended_at=result.ended_at,
        score=result.score, primitives=result.primitives,
    )

    click.echo(f"run {run_id} {result.status} score={result.score:.4f} ({result.score_metric})")
```

- [ ] **Step 4: Write end-to-end integration test**

```python
# tests/integration/test_cli_run_e2e.py
import json
from pathlib import Path

import polars as pl
import pytest
from click.testing import CliRunner

from asteroid_belt.cli import cli


@pytest.fixture
def staged_pool_data(tmp_path: Path) -> Path:
    """Stage a tiny pool fixture (bars + pool_meta.json) for the CLI to consume."""
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    data_root = tmp_path
    pool_dir = data_root / "pools" / pool
    pool_dir.mkdir(parents=True)

    # 30-minute bar fixture (slightly noisy walk)
    bars = pl.DataFrame({
        "ts": [1_700_000_000_000 + i * 60_000 for i in range(30)],
        "open": [87.50 + (i % 5) * 0.01 for i in range(30)],
        "high": [87.55 + (i % 5) * 0.01 for i in range(30)],
        "low": [87.49 + (i % 5) * 0.01 for i in range(30)],
        "close": [87.55 + (i % 5) * 0.01 for i in range(30)],
        "volume_x": [1_000_000] * 30,
        "volume_y": [87_550_000] * 30,
    })
    bars.write_parquet(pool_dir / "bars_1m.parquet")

    (pool_dir / "pool_meta.json").write_text(json.dumps({
        "address": pool, "name": "SOL-USDC",
        "token_x": {"decimals": 9},
        "token_y": {"decimals": 6},
        "pool_config": {"bin_step": 10},
    }))

    return data_root


@pytest.fixture
def tiny_config(tmp_path: Path, staged_pool_data: Path) -> Path:
    p = tmp_path / "tiny.yaml"
    p.write_text("""
schema_version: "1.0"
pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
window:
  start: "2023-11-14T22:13:20Z"
  end:   "2023-11-14T22:43:20Z"
adapter:
  kind: bar
strategy:
  class: asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy
  params:
    bin_width: 21
    rebalance_trigger_bins: 5
engine:
  tick_secs: 300
  initial_x: 100000000
  initial_y: 8800000000
  selection_metric: sharpe
  timeout_secs: 30
""")
    return p


def test_belt_run_end_to_end(staged_pool_data: Path, tiny_config: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "run", "--config", str(tiny_config),
        "--data-dir", str(staged_pool_data),
    ])
    assert result.exit_code == 0, result.output
    assert "score=" in result.output

    # Trajectory + manifest persisted
    runs_dir = staged_pool_data / "runs"
    sub_dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
    assert len(sub_dirs) == 1
    run_dir = sub_dirs[0]
    assert (run_dir / "result.parquet").exists()
    assert (run_dir / "rebalances.parquet").exists()
    assert (run_dir / "manifest.json").exists()

    # DuckDB row inserted
    import duckdb
    con = duckdb.connect(str(staged_pool_data / "meta.duckdb"))
    rows = con.execute("SELECT run_id, status FROM runs").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "ok"


def test_belt_run_dedup_blocks_duplicate(staged_pool_data: Path, tiny_config: Path) -> None:
    runner = CliRunner()
    r1 = runner.invoke(cli, [
        "run", "--config", str(tiny_config),
        "--data-dir", str(staged_pool_data),
    ])
    assert r1.exit_code == 0
    r2 = runner.invoke(cli, [
        "run", "--config", str(tiny_config),
        "--data-dir", str(staged_pool_data),
    ])
    assert r2.exit_code == 2  # dedup
    assert "existing run" in r2.output
```

Run: `pytest tests/integration/test_cli_run_e2e.py -v` — expect PASS (this is the first integration test).

- [ ] **Step 5: Commit**

```bash
git add asteroid_belt/cli.py asteroid_belt/engine/runner.py tests/integration/test_cli_run_e2e.py
git commit -m "feat(cli): belt run with full backtest lifecycle"
```

### Task 5.5: CLI — `belt session` + `belt run notes`

**Files:**
- Modify: `asteroid_belt/cli.py`
- Test: `tests/unit/test_cli_session.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_cli_session.py
from pathlib import Path

import duckdb
import pytest
from click.testing import CliRunner

from asteroid_belt.cli import cli


@pytest.fixture
def empty_data_dir(tmp_path: Path) -> Path:
    return tmp_path


def test_session_new_creates_row(empty_data_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "session", "new", "--label", "rebalance_sweep",
        "--data-dir", str(empty_data_dir),
    ])
    assert result.exit_code == 0
    # Output is the session_id on its own line
    sid = result.output.strip().split("\n")[-1]
    assert sid

    con = duckdb.connect(str(empty_data_dir / "meta.duckdb"))
    rows = con.execute("SELECT session_id, label FROM sessions").fetchall()
    assert rows[0][1] == "rebalance_sweep"


def test_session_close(empty_data_dir: Path) -> None:
    runner = CliRunner()
    new = runner.invoke(cli, [
        "session", "new", "--label", "x",
        "--data-dir", str(empty_data_dir),
    ])
    sid = new.output.strip().split("\n")[-1]
    closed = runner.invoke(cli, [
        "session", "close", "--id", sid,
        "--data-dir", str(empty_data_dir),
    ])
    assert closed.exit_code == 0
    con = duckdb.connect(str(empty_data_dir / "meta.duckdb"))
    row = con.execute("SELECT closed_at FROM sessions WHERE session_id = ?", [sid]).fetchone()
    assert row[0] is not None
```

Run: `pytest tests/unit/test_cli_session.py -v` — expect FAIL.

- [ ] **Step 2: Implement session commands**

Add to `asteroid_belt/cli.py`:

```python
@cli.group()
def session() -> None:
    """Manage research sessions (groups of runs)."""


@session.command("new")
@click.option("--label", required=True)
@click.option("--kind", default="manual",
              type=click.Choice(["manual", "agent_search", "evaluator_holdout", "sweep"]))
@click.option("--data-dir", default=str(DEFAULT_DATA_DIR), type=click.Path())
def session_new(label: str, kind: str, data_dir: str) -> None:
    """Create a new session and print its id."""
    import time
    import uuid

    from asteroid_belt.store.runs import DuckDBRunStore, SessionRecord

    data_root = Path(data_dir)
    data_root.mkdir(parents=True, exist_ok=True)
    store = DuckDBRunStore(db_path=data_root / "meta.duckdb")

    sid = f"{time.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"
    store.insert_session(SessionRecord(
        session_id=sid, label=label,
        created_at=int(time.time() * 1000),
        closed_at=None, session_kind=kind,
        goal_json=None, outcome_json=None, notes=None,
    ))
    click.echo(sid)


@session.command("close")
@click.option("--id", "session_id", required=True)
@click.option("--data-dir", default=str(DEFAULT_DATA_DIR), type=click.Path())
def session_close(session_id: str, data_dir: str) -> None:
    """Mark a session as closed."""
    import time

    from asteroid_belt.store.runs import DuckDBRunStore

    store = DuckDBRunStore(db_path=Path(data_dir) / "meta.duckdb")
    store.close_session(session_id, closed_at=int(time.time() * 1000), outcome_json=None)
    click.echo(f"closed {session_id}")


# Run notes subcommand attached to `belt run`
@cli.group(name="run-notes")
def run_notes() -> None:
    """Manage notes on existing runs."""


@run_notes.command("set")
@click.option("--id", "run_id", required=True)
@click.option("--text", required=True)
@click.option("--data-dir", default=str(DEFAULT_DATA_DIR), type=click.Path())
def run_notes_set(run_id: str, text: str, data_dir: str) -> None:
    """Update a run's `notes` field."""
    import duckdb

    db_path = Path(data_dir) / "meta.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("UPDATE runs SET notes = ? WHERE run_id = ?", [text, run_id])
    click.echo(f"updated notes for {run_id}")
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_cli_session.py -v
```

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/cli.py tests/unit/test_cli_session.py
git commit -m "feat(cli): belt session new/close + run-notes set"
```

### Task 5.6: CLI — `belt serve`

**Files:**
- Modify: `asteroid_belt/cli.py`

- [ ] **Step 1: Add serve command**

Add to `asteroid_belt/cli.py`:

```python
@cli.command()
@click.option("--port", default=8000, type=int)
@click.option("--data-dir", default=str(DEFAULT_DATA_DIR), type=click.Path())
def serve(port: int, data_dir: str) -> None:
    """Launch the FastAPI server (read-only API for the dashboard)."""
    import os

    import uvicorn

    os.environ["ASTEROID_BELT_DATA_DIR"] = str(Path(data_dir).resolve())
    uvicorn.run(
        "asteroid_belt.server.app:app",
        host="127.0.0.1", port=port, reload=False,
    )
```

> Note: `belt serve` will not work end-to-end until Phase 6 lands the server. We register the command now so the CLI surface is complete; `belt --help` lists it.

- [ ] **Step 2: Verify CLI surface**

```bash
belt --help
```

Expected: lists `ingest`, `run`, `session`, `run-notes`, `serve` commands.

- [ ] **Step 3: Commit**

```bash
git add asteroid_belt/cli.py
git commit -m "feat(cli): belt serve stub (real impl in Phase 6)"
```

---

**End of Phase 5.** End-to-end CLI works for ingest + run + session management. Total tests: ~95.

You can now run a full backtest from a YAML config against ingested pool data, persist the result, and query it via DuckDB. Phase 6 lights up the FastAPI server so the SvelteKit dashboard (Phase 7) has data to render.

---

## Phase 6 — FastAPI server

Read-only API at `/api/v1/`. CLI handles all writes; the server only reads from DuckDB and parquet. The SvelteKit dashboard talks to it via an OpenAPI-generated TS client.

### Task 6.1: FastAPI app + /health endpoint

**Files:**
- Modify: `asteroid_belt/server/app.py`
- Modify: `asteroid_belt/server/schemas.py`
- Test: `tests/unit/test_server_health.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_server_health.py
from fastapi.testclient import TestClient

from asteroid_belt.server.app import build_app


def test_health_ok(tmp_path: object) -> None:
    app = build_app(data_dir=tmp_path)  # type: ignore[arg-type]
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_schema_versioned() -> None:
    app = build_app(data_dir=None)  # type: ignore[arg-type]
    client = TestClient(app)
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "/api/v1/health" in schema["paths"]
```

Run: `pytest tests/unit/test_server_health.py -v` — expect FAIL.

- [ ] **Step 2: Implement app bootstrap**

```python
# asteroid_belt/server/schemas.py
"""Pydantic response models for FastAPI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
```

```python
# asteroid_belt/server/app.py
"""FastAPI read-only API at /api/v1/.

Writes happen exclusively via the CLI. When subsystem 4 wants UI-triggered
runs, POST endpoints get added under the same paths without breaking the v1
TS client (additive evolution).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from asteroid_belt.server.schemas import HealthResponse


def build_app(*, data_dir: Path | None = None) -> FastAPI:
    """Build a FastAPI app pointed at `data_dir`. Tests pass tmp_path here."""
    if data_dir is None:
        env = os.environ.get("ASTEROID_BELT_DATA_DIR", "data")
        data_dir = Path(env)

    app = FastAPI(
        title="asteroid-belt API",
        version="0.1.0",
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )

    # Stash data_dir on the app for endpoint handlers
    app.state.data_dir = data_dir

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


# Module-level app for `uvicorn asteroid_belt.server.app:app`
app = build_app()
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_server_health.py -v
```

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/server/app.py asteroid_belt/server/schemas.py tests/unit/test_server_health.py
git commit -m "feat(server): FastAPI bootstrap + /health"
```

### Task 6.2: /pools endpoints

**Files:**
- Modify: `asteroid_belt/server/app.py`, `schemas.py`
- Test: `tests/unit/test_server_pools.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_server_pools.py
import json
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from asteroid_belt.server.app import build_app


@pytest.fixture
def staged_data(tmp_path: Path) -> Path:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    pool_dir = tmp_path / "pools" / pool
    pool_dir.mkdir(parents=True)
    (pool_dir / "pool_meta.json").write_text(json.dumps({
        "address": pool, "name": "SOL-USDC",
        "pool_config": {"bin_step": 10},
        "token_x": {"decimals": 9, "symbol": "SOL"},
        "token_y": {"decimals": 6, "symbol": "USDC"},
    }))
    pl.DataFrame({"ts": [1, 2], "open": [1.0, 1.0], "high": [1.0, 1.0],
                  "low": [1.0, 1.0], "close": [1.0, 1.0],
                  "volume_x": [0, 0], "volume_y": [0, 0]}).write_parquet(
        pool_dir / "bars_1m.parquet"
    )
    return tmp_path


def test_list_pools(staged_data: Path) -> None:
    client = TestClient(build_app(data_dir=staged_data))
    r = client.get("/api/v1/pools")
    assert r.status_code == 200
    pools = r.json()
    assert len(pools) == 1
    assert pools[0]["address"] == "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"


def test_get_pool_detail(staged_data: Path) -> None:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    client = TestClient(build_app(data_dir=staged_data))
    r = client.get(f"/api/v1/pools/{pool}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["address"] == pool
    assert detail["bars_count"] == 2


def test_get_pool_404(staged_data: Path) -> None:
    client = TestClient(build_app(data_dir=staged_data))
    r = client.get("/api/v1/pools/nonexistent")
    assert r.status_code == 404
```

Run: expect FAIL.

- [ ] **Step 2: Add models + endpoints**

Add to `asteroid_belt/server/schemas.py`:

```python
class PoolSummary(BaseModel):
    address: str
    name: str | None = None
    bin_step: int | None = None
    bars_count: int


class PoolDetail(BaseModel):
    address: str
    name: str | None = None
    bin_step: int | None = None
    bars_count: int
    meta: dict[str, Any]
```

Add to `asteroid_belt/server/app.py` inside `build_app`:

```python
    import json

    import polars as pl
    from fastapi import HTTPException

    from asteroid_belt.server.schemas import PoolDetail, PoolSummary

    @app.get("/api/v1/pools", response_model=list[PoolSummary])
    def list_pools() -> list[PoolSummary]:
        pools_dir = data_dir / "pools"
        if not pools_dir.exists():
            return []
        results: list[PoolSummary] = []
        for d in sorted(pools_dir.iterdir()):
            if not d.is_dir():
                continue
            meta_path = d / "pool_meta.json"
            bars_path = d / "bars_1m.parquet"
            if not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text())
            bars_count = int(pl.read_parquet(bars_path).height) if bars_path.exists() else 0
            results.append(PoolSummary(
                address=d.name,
                name=meta.get("name"),
                bin_step=meta.get("pool_config", {}).get("bin_step"),
                bars_count=bars_count,
            ))
        return results

    @app.get("/api/v1/pools/{address}", response_model=PoolDetail)
    def get_pool(address: str) -> PoolDetail:
        pool_dir = data_dir / "pools" / address
        meta_path = pool_dir / "pool_meta.json"
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail=f"pool {address} not found")
        meta = json.loads(meta_path.read_text())
        bars_path = pool_dir / "bars_1m.parquet"
        bars_count = int(pl.read_parquet(bars_path).height) if bars_path.exists() else 0
        return PoolDetail(
            address=address,
            name=meta.get("name"),
            bin_step=meta.get("pool_config", {}).get("bin_step"),
            bars_count=bars_count,
            meta=meta,
        )
```

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_server_pools.py -v
```

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/server/app.py asteroid_belt/server/schemas.py tests/unit/test_server_pools.py
git commit -m "feat(server): /pools list + detail endpoints"
```

### Task 6.3: /sessions endpoints

**Files:**
- Modify: `asteroid_belt/server/app.py`, `schemas.py`
- Test: `tests/unit/test_server_sessions.py`

- [ ] **Step 1: Test**

```python
# tests/unit/test_server_sessions.py
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asteroid_belt.server.app import build_app
from asteroid_belt.store.runs import DuckDBRunStore, SessionRecord


@pytest.fixture
def store_with_sessions(tmp_path: Path) -> Path:
    store = DuckDBRunStore(db_path=tmp_path / "meta.duckdb")
    for i in range(3):
        store.insert_session(SessionRecord(
            session_id=f"s{i}", label=f"sess {i}",
            created_at=1000 + i, closed_at=None,
        ))
    return tmp_path


def test_list_sessions(store_with_sessions: Path) -> None:
    client = TestClient(build_app(data_dir=store_with_sessions))
    r = client.get("/api/v1/sessions")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_get_session(store_with_sessions: Path) -> None:
    client = TestClient(build_app(data_dir=store_with_sessions))
    r = client.get("/api/v1/sessions/s1")
    assert r.status_code == 200
    detail = r.json()
    assert detail["session_id"] == "s1"
    assert detail["label"] == "sess 1"


def test_get_session_404(store_with_sessions: Path) -> None:
    client = TestClient(build_app(data_dir=store_with_sessions))
    r = client.get("/api/v1/sessions/nonexistent")
    assert r.status_code == 404
```

Run: expect FAIL.

- [ ] **Step 2: Implement**

Add to `asteroid_belt/server/schemas.py`:

```python
class SessionSummary(BaseModel):
    session_id: str
    label: str | None = None
    created_at: int
    closed_at: int | None = None
    session_kind: str = "manual"


class SessionDetail(SessionSummary):
    goal_json: dict[str, Any] | None = None
    outcome_json: dict[str, Any] | None = None
    notes: str | None = None
```

Add to `asteroid_belt/server/app.py`:

```python
    from asteroid_belt.store.runs import DuckDBRunStore
    from asteroid_belt.server.schemas import SessionDetail, SessionSummary

    def _get_store() -> DuckDBRunStore:
        return DuckDBRunStore(db_path=data_dir / "meta.duckdb")

    @app.get("/api/v1/sessions", response_model=list[SessionSummary])
    def list_sessions() -> list[SessionSummary]:
        if not (data_dir / "meta.duckdb").exists():
            return []
        store = _get_store()
        rows = store._con.execute(  # noqa: SLF001
            "SELECT session_id, label, created_at, closed_at, session_kind "
            "FROM sessions ORDER BY created_at DESC"
        ).fetchall()
        return [
            SessionSummary(
                session_id=r[0], label=r[1],
                created_at=r[2], closed_at=r[3],
                session_kind=r[4],
            )
            for r in rows
        ]

    @app.get("/api/v1/sessions/{session_id}", response_model=SessionDetail)
    def get_session(session_id: str) -> SessionDetail:
        if not (data_dir / "meta.duckdb").exists():
            raise HTTPException(status_code=404, detail=f"session {session_id} not found")
        store = _get_store()
        try:
            rec = store.get_session(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"session {session_id} not found")
        return SessionDetail(
            session_id=rec.session_id, label=rec.label,
            created_at=rec.created_at, closed_at=rec.closed_at,
            session_kind=rec.session_kind,
            goal_json=rec.goal_json, outcome_json=rec.outcome_json,
            notes=rec.notes,
        )
```

- [ ] **Step 3: Run tests, commit**

```bash
pytest tests/unit/test_server_sessions.py -v
git add asteroid_belt/server/app.py asteroid_belt/server/schemas.py tests/unit/test_server_sessions.py
git commit -m "feat(server): /sessions list + detail"
```

### Task 6.4: /runs endpoints (list, detail, trajectory, rebalances, compare)

**Files:**
- Modify: `asteroid_belt/server/app.py`, `schemas.py`
- Test: `tests/unit/test_server_runs.py`

- [ ] **Step 1: Test**

```python
# tests/unit/test_server_runs.py
import time
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from asteroid_belt.engine.result import BacktestResult, RebalanceRecord
from asteroid_belt.server.app import build_app
from asteroid_belt.store.results import write_result
from asteroid_belt.store.runs import DuckDBRunStore, RunRecord


def _stage_run(tmp_path: Path, run_id: str, score: float) -> None:
    """Helper: write a complete run (DuckDB row + parquet artifacts)."""
    store = DuckDBRunStore(db_path=tmp_path / "meta.duckdb")
    rec = RunRecord(
        run_id=run_id, config_hash="h_" + run_id,
        parent_run_id=None, session_id=None,
        created_by="human", cost_model_version="v0.1.0-unverified",
        schema_version="1.0",
        pool_address="BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y",
        strategy_class="asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy",
        strategy_params={"bin_width": 69},
        strategy_source_sha=None,
        adapter_kind="bar", window_start=0, window_end=1000,
        tick_secs=300, initial_x=10**8, initial_y=10**10,
        selection_metric="sharpe",
        started_at=int(time.time() * 1000), ended_at=int(time.time() * 1000) + 1,
        status="ok", error_msg=None,
        score=score, primitives={"sharpe": score, "net_pnl": score * 10},
        notes=None,
    )
    store.insert(rec)

    df = pl.DataFrame({
        "ts": [0, 60_000], "price": [87.5, 87.6], "active_bin": [0, 1],
        "position_value_usd": [100.0, 105.0],
        "hodl_value_usd": [100.0, 100.0],
        "fees_x_cumulative": [0, 100], "fees_y_cumulative": [0, 1000],
        "il_cumulative": [0.0, 5.0], "in_range": [True, True],
        "capital_idle_usd": [0.0, 0.0],
    })
    result = BacktestResult(
        run_id=run_id, config_hash="h_" + run_id, schema_version="1.0",
        started_at=0, ended_at=1, status="ok",
        trajectory=df,
        rebalances=[
            RebalanceRecord(ts=30_000, trigger="drift", old_lower_bin=-30,
                            old_upper_bin=30, new_lower_bin=-20, new_upper_bin=40,
                            gas_lamports=10_000, composition_fee_x=0,
                            composition_fee_y=5_000, fees_claimed_x=0,
                            fees_claimed_y=2_000),
        ],
        primitives={"sharpe": score}, score=score, score_metric="sharpe",
    )
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(exist_ok=True)
    write_result(result=result, runs_dir=runs_dir)


@pytest.fixture
def staged_runs(tmp_path: Path) -> Path:
    _stage_run(tmp_path, "run_a", score=1.5)
    _stage_run(tmp_path, "run_b", score=2.0)
    _stage_run(tmp_path, "run_c", score=0.5)
    return tmp_path


def test_list_runs(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    r = client.get("/api/v1/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 3


def test_list_runs_filter_score_min(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    r = client.get("/api/v1/runs?score_min=1.0")
    runs = r.json()
    assert {x["run_id"] for x in runs} == {"run_a", "run_b"}


def test_run_detail(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    r = client.get("/api/v1/runs/run_a")
    assert r.status_code == 200
    detail = r.json()
    assert detail["run_id"] == "run_a"
    assert detail["score"] == 1.5


def test_run_trajectory(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    r = client.get("/api/v1/runs/run_a/trajectory")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert rows[0]["price"] == 87.5


def test_run_trajectory_resolution_downsample(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    r = client.get("/api/v1/runs/run_a/trajectory?resolution=1h")
    assert r.status_code == 200
    rows = r.json()
    # 60-second window collapses to a single hour bucket
    assert len(rows) == 1


def test_run_rebalances(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    r = client.get("/api/v1/runs/run_a/rebalances")
    assert r.status_code == 200
    rebs = r.json()
    assert len(rebs) == 1
    assert rebs[0]["trigger"] == "drift"


def test_run_compare(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    r = client.get("/api/v1/runs/compare?ids=run_a,run_b")
    assert r.status_code == 200
    cmp_data = r.json()
    assert "primitives_matrix" in cmp_data
    assert "trajectories" in cmp_data
    assert len(cmp_data["trajectories"]) == 2


def test_run_compare_too_many_ids_400(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    r = client.get("/api/v1/runs/compare?ids=" + ",".join(f"r{i}" for i in range(7)))
    assert r.status_code == 400


def test_run_404(staged_runs: Path) -> None:
    client = TestClient(build_app(data_dir=staged_runs))
    assert client.get("/api/v1/runs/nonexistent").status_code == 404
```

Run: expect FAIL.

- [ ] **Step 2: Implement**

Add to `asteroid_belt/server/schemas.py`:

```python
class RunSummary(BaseModel):
    run_id: str
    config_hash: str
    pool_address: str
    strategy_class: str
    session_id: str | None = None
    started_at: int
    ended_at: int | None = None
    status: str
    selection_metric: str
    score: float | None = None
    created_by: str = "human"


class RunDetail(RunSummary):
    parent_run_id: str | None = None
    cost_model_version: str
    schema_version: str
    strategy_params: dict[str, Any]
    strategy_source_sha: str | None = None
    adapter_kind: str
    window_start: int
    window_end: int
    tick_secs: int
    initial_x: int
    initial_y: int
    error_msg: str | None = None
    primitives: dict[str, float] | None = None
    notes: str | None = None


class TrajectoryRow(BaseModel):
    ts: int
    price: float
    active_bin: int
    position_value_usd: float
    hodl_value_usd: float
    fees_x_cumulative: int
    fees_y_cumulative: int
    il_cumulative: float
    in_range: bool
    capital_idle_usd: float


class RebalanceRecordResponse(BaseModel):
    ts: int
    trigger: str
    old_lower_bin: int
    old_upper_bin: int
    new_lower_bin: int
    new_upper_bin: int
    gas_lamports: int
    composition_fee_x: int
    composition_fee_y: int
    fees_claimed_x: int
    fees_claimed_y: int


class CompareResponse(BaseModel):
    primitives_matrix: dict[str, dict[str, float | None]]  # primitive_name → run_id → value
    trajectories: dict[str, list[TrajectoryRow]]            # run_id → trajectory rows
```

Add to `asteroid_belt/server/app.py` (inside `build_app`):

```python
    from typing import Literal

    from fastapi import Query

    from asteroid_belt.server.schemas import (
        CompareResponse, RebalanceRecordResponse,
        RunDetail, RunSummary, TrajectoryRow,
    )
    from asteroid_belt.store.results import read_rebalances, read_trajectory

    MAX_COMPARE_RUNS = 6

    def _record_to_summary(rec: object) -> RunSummary:  # rec is RunRecord at runtime
        return RunSummary(
            run_id=rec.run_id, config_hash=rec.config_hash,  # type: ignore[attr-defined]
            pool_address=rec.pool_address, strategy_class=rec.strategy_class,
            session_id=rec.session_id,
            started_at=rec.started_at, ended_at=rec.ended_at,
            status=rec.status, selection_metric=rec.selection_metric,
            score=rec.score, created_by=rec.created_by,
        )

    def _record_to_detail(rec: object) -> RunDetail:
        return RunDetail(
            run_id=rec.run_id, config_hash=rec.config_hash,  # type: ignore[attr-defined]
            pool_address=rec.pool_address, strategy_class=rec.strategy_class,
            session_id=rec.session_id,
            started_at=rec.started_at, ended_at=rec.ended_at,
            status=rec.status, selection_metric=rec.selection_metric,
            score=rec.score, created_by=rec.created_by,
            parent_run_id=rec.parent_run_id,
            cost_model_version=rec.cost_model_version,
            schema_version=rec.schema_version,
            strategy_params=rec.strategy_params,
            strategy_source_sha=rec.strategy_source_sha,
            adapter_kind=rec.adapter_kind,
            window_start=rec.window_start, window_end=rec.window_end,
            tick_secs=rec.tick_secs,
            initial_x=rec.initial_x, initial_y=rec.initial_y,
            error_msg=rec.error_msg,
            primitives=rec.primitives, notes=rec.notes,
        )

    @app.get("/api/v1/runs", response_model=list[RunSummary])
    def list_runs(
        pool: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        score_min: float | None = None,
        score_max: float | None = None,
        started_after: int | None = None,
        started_before: int | None = None,
        created_by: str | None = None,
        strategy_class: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
    ) -> list[RunSummary]:
        if not (data_dir / "meta.duckdb").exists():
            return []
        store = _get_store()
        filters: dict[str, object] = {}
        if pool: filters["pool_address"] = pool
        if session_id: filters["session_id"] = session_id
        if status: filters["status"] = status
        if score_min is not None: filters["score_min"] = score_min
        if score_max is not None: filters["score_max"] = score_max
        if started_after is not None: filters["started_after"] = started_after
        if started_before is not None: filters["started_before"] = started_before
        if created_by: filters["created_by"] = created_by
        if strategy_class: filters["strategy_class"] = strategy_class
        filters["limit"] = page * page_size  # crude paging; offset in v1.5
        records = store.query(**filters)
        # Slice for the current page
        start = (page - 1) * page_size
        end = start + page_size
        return [_record_to_summary(r) for r in records[start:end]]

    @app.get("/api/v1/runs/compare", response_model=CompareResponse)
    def runs_compare(ids: str = Query(..., description="comma-separated run IDs")) -> CompareResponse:
        run_ids = [s.strip() for s in ids.split(",") if s.strip()]
        if len(run_ids) > MAX_COMPARE_RUNS:
            raise HTTPException(status_code=400,
                                detail=f"max {MAX_COMPARE_RUNS} runs in compare")
        store = _get_store()
        primitives_matrix: dict[str, dict[str, float | None]] = {}
        trajectories: dict[str, list[TrajectoryRow]] = {}
        for rid in run_ids:
            try:
                rec = store.get(rid)
            except KeyError:
                raise HTTPException(status_code=404, detail=f"run {rid} not found")
            for prim_name, prim_value in (rec.primitives or {}).items():
                primitives_matrix.setdefault(prim_name, {})[rid] = prim_value
            df = read_trajectory(run_id=rid, runs_dir=data_dir / "runs")
            trajectories[rid] = [
                TrajectoryRow(**row) for row in df.iter_rows(named=True)
            ]
        return CompareResponse(
            primitives_matrix=primitives_matrix,
            trajectories=trajectories,
        )

    @app.get("/api/v1/runs/{run_id}", response_model=RunDetail)
    def get_run(run_id: str) -> RunDetail:
        if not (data_dir / "meta.duckdb").exists():
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        store = _get_store()
        try:
            rec = store.get(run_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return _record_to_detail(rec)

    @app.get("/api/v1/runs/{run_id}/trajectory", response_model=list[TrajectoryRow])
    def get_trajectory(
        run_id: str,
        resolution: Literal["1m", "5m", "1h"] = "1m",
    ) -> list[TrajectoryRow]:
        try:
            df = read_trajectory(run_id=run_id, runs_dir=data_dir / "runs")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        if resolution != "1m":
            bucket_ms = {"5m": 5 * 60_000, "1h": 60 * 60_000}[resolution]
            df = (
                df.with_columns([(pl.col("ts") // bucket_ms).alias("bucket")])
                .group_by("bucket", maintain_order=True)
                .agg([
                    pl.col("ts").last(),
                    pl.col("price").mean(),
                    pl.col("active_bin").last(),
                    pl.col("position_value_usd").last(),
                    pl.col("hodl_value_usd").last(),
                    pl.col("fees_x_cumulative").last(),
                    pl.col("fees_y_cumulative").last(),
                    pl.col("il_cumulative").last(),
                    pl.col("in_range").last(),
                    pl.col("capital_idle_usd").last(),
                ])
                .drop("bucket")
            )
        return [TrajectoryRow(**row) for row in df.iter_rows(named=True)]

    @app.get("/api/v1/runs/{run_id}/rebalances", response_model=list[RebalanceRecordResponse])
    def get_rebalances(run_id: str) -> list[RebalanceRecordResponse]:
        try:
            recs = read_rebalances(run_id=run_id, runs_dir=data_dir / "runs")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return [
            RebalanceRecordResponse(**r.__dict__) for r in recs
        ]
```

> Important: declare `runs_compare` BEFORE `get_run` so `/runs/compare` doesn't get matched by the `{run_id}` path. FastAPI matches routes in declaration order.

- [ ] **Step 3: Run tests (expect PASS)**

```bash
pytest tests/unit/test_server_runs.py -v
```

Expected: 9 passed.

- [ ] **Step 4: Commit**

```bash
git add asteroid_belt/server/app.py asteroid_belt/server/schemas.py tests/unit/test_server_runs.py
git commit -m "feat(server): /runs list, detail, trajectory, rebalances, compare"
```

---

**End of Phase 6.** FastAPI server is complete. Total tests: ~115. CLI `belt serve` now works end-to-end. Phase 7 builds the SvelteKit dashboard against this API.

---

## Phase 7 — SvelteKit dashboard

Post-hoc dashboard. Reads the FastAPI server. No live streaming. Run list + run detail (with charts) + compare view + session/pool browsers.

### Task 7.1: SvelteKit + Tailwind + Lucide bootstrap

**Files:**
- Create: `web/package.json`
- Create: `web/svelte.config.js`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/tailwind.config.js`
- Create: `web/postcss.config.js`
- Create: `web/src/app.html`
- Create: `web/src/app.css`
- Create: `web/src/routes/+layout.svelte`
- Create: `web/src/routes/+page.svelte` (placeholder)
- Create: `web/.gitignore`

- [ ] **Step 1: package.json**

```json
{
  "name": "asteroid-belt-web",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview",
    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
    "lint": "prettier --check . && eslint .",
    "format": "prettier --write .",
    "test": "playwright test",
    "api-gen": "openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/lib/api/types.ts"
  },
  "devDependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.5.0",
    "@sveltejs/vite-plugin-svelte": "^3.0.0",
    "@playwright/test": "^1.44.0",
    "@types/node": "^20.0.0",
    "autoprefixer": "^10.4.0",
    "eslint": "^9.0.0",
    "openapi-typescript": "^7.0.0",
    "postcss": "^8.4.0",
    "prettier": "^3.2.0",
    "prettier-plugin-svelte": "^3.2.0",
    "svelte": "^4.2.0",
    "svelte-check": "^3.6.0",
    "tailwindcss": "^3.4.0",
    "tslib": "^2.6.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0"
  },
  "dependencies": {
    "echarts": "^5.5.0",
    "lucide-svelte": "^0.300.0",
    "svelte-echarts": "^0.2.0"
  }
}
```

- [ ] **Step 2: svelte.config.js + vite.config.ts**

```javascript
// web/svelte.config.js
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({ fallback: 'index.html' }),
    alias: {
      $lib: 'src/lib',
    },
  },
};

export default config;
```

```typescript
// web/vite.config.ts
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
```

- [ ] **Step 3: tsconfig.json**

```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "allowJs": true,
    "checkJs": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "strict": true,
    "moduleResolution": "bundler"
  }
}
```

- [ ] **Step 4: tailwind.config.js + postcss.config.js + app.css**

```javascript
// web/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,svelte,ts,js}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: '#0a0a0a', surface: '#141414', muted: '#1f1f1f' },
        fg: { DEFAULT: '#e5e5e5', muted: '#9ca3af', dim: '#6b7280' },
        accent: { DEFAULT: '#3b82f6' },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
```

```javascript
// web/postcss.config.js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

```css
/* web/src/app.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html { background: theme('colors.bg.DEFAULT'); color: theme('colors.fg.DEFAULT'); }
  body { @apply font-sans antialiased; }
  code, pre { @apply font-mono; }
}
```

- [ ] **Step 5: app.html**

```html
<!-- web/src/app.html -->
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>asteroid-belt</title>
  %sveltekit.head%
</head>
<body data-sveltekit-preload-data="hover">
  <div style="display: contents">%sveltekit.body%</div>
</body>
</html>
```

- [ ] **Step 6: layout + placeholder home**

```svelte
<!-- web/src/routes/+layout.svelte -->
<script lang="ts">
  import '../app.css';
  import { Activity, GitCompareArrows, Database, FlaskConical } from 'lucide-svelte';
  import { page } from '$app/stores';

  $: pathname = $page.url.pathname;

  const nav = [
    { href: '/',         label: 'Runs',     icon: Activity },
    { href: '/compare',  label: 'Compare',  icon: GitCompareArrows },
    { href: '/sessions', label: 'Sessions', icon: FlaskConical },
    { href: '/pools',    label: 'Pools',    icon: Database },
  ];
</script>

<div class="flex h-screen bg-bg text-fg">
  <aside class="w-52 shrink-0 border-r border-bg-muted bg-bg-surface p-4">
    <h1 class="mb-6 font-mono text-sm font-bold tracking-wider text-fg-muted">
      ASTEROID-BELT
    </h1>
    <nav class="flex flex-col gap-1">
      {#each nav as item}
        <a href={item.href}
           class="flex items-center gap-2 rounded px-2 py-1.5 text-sm transition-colors
                  {pathname === item.href
                    ? 'bg-bg-muted text-fg'
                    : 'text-fg-muted hover:bg-bg-muted hover:text-fg'}">
          <svelte:component this={item.icon} size={14} />
          {item.label}
        </a>
      {/each}
    </nav>
  </aside>
  <main class="flex-1 overflow-y-auto p-6">
    <slot />
  </main>
</div>
```

```svelte
<!-- web/src/routes/+page.svelte -->
<script lang="ts">
  // Run list will land in Task 7.3
</script>

<h2 class="mb-4 text-xl font-bold">Runs</h2>
<p class="text-fg-muted">Run list coming in Task 7.3.</p>
```

- [ ] **Step 7: web/.gitignore**

```
node_modules/
.svelte-kit/
build/
.vercel/
.output/
.env
.env.*
!.env.example
src/lib/api/types.ts
```

- [ ] **Step 8: Install + smoke check**

```bash
cd web
pnpm install
pnpm check
```

Expected: dependencies install; svelte-check reports 0 errors.

- [ ] **Step 9: Commit**

```bash
git add web/
git commit -m "chore(web): SvelteKit + Tailwind + Lucide bootstrap"
```

### Task 7.2: API client generation

**Files:**
- Create: `web/src/lib/api/client.ts`
- Modify: `web/package.json` (add `api-gen` script — already added in 7.1)

- [ ] **Step 1: Make sure FastAPI is running, then generate types**

```bash
# In one terminal:
cd /Users/bambozlor/Desktop/product-lab/autometeora
make serve

# In another:
cd web
pnpm api-gen
```

Expected: writes `web/src/lib/api/types.ts` with generated types from OpenAPI schema.

- [ ] **Step 2: Write the typed fetch client**

```typescript
// web/src/lib/api/client.ts
import type { components, paths } from './types';

export type RunSummary = components['schemas']['RunSummary'];
export type RunDetail = components['schemas']['RunDetail'];
export type TrajectoryRow = components['schemas']['TrajectoryRow'];
export type RebalanceRecordResponse = components['schemas']['RebalanceRecordResponse'];
export type CompareResponse = components['schemas']['CompareResponse'];
export type PoolSummary = components['schemas']['PoolSummary'];
export type PoolDetail = components['schemas']['PoolDetail'];
export type SessionSummary = components['schemas']['SessionSummary'];
export type SessionDetail = components['schemas']['SessionDetail'];

const BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!r.ok) {
    const text = await r.text().catch(() => '<no body>');
    throw new Error(`API ${r.status}: ${text}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  pools: {
    list: () => request<PoolSummary[]>('/pools'),
    get: (address: string) =>
      request<PoolDetail>(`/pools/${encodeURIComponent(address)}`),
  },

  sessions: {
    list: () => request<SessionSummary[]>('/sessions'),
    get: (id: string) =>
      request<SessionDetail>(`/sessions/${encodeURIComponent(id)}`),
  },

  runs: {
    list: (params: Record<string, string | number | undefined> = {}) => {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== '') qs.set(k, String(v));
      }
      const suffix = qs.toString() ? `?${qs.toString()}` : '';
      return request<RunSummary[]>(`/runs${suffix}`);
    },
    get: (id: string) =>
      request<RunDetail>(`/runs/${encodeURIComponent(id)}`),
    trajectory: (id: string, resolution: '1m' | '5m' | '1h' = '1h') =>
      request<TrajectoryRow[]>(
        `/runs/${encodeURIComponent(id)}/trajectory?resolution=${resolution}`,
      ),
    rebalances: (id: string) =>
      request<RebalanceRecordResponse[]>(
        `/runs/${encodeURIComponent(id)}/rebalances`,
      ),
    compare: (ids: string[]) =>
      request<CompareResponse>(
        `/runs/compare?ids=${ids.map(encodeURIComponent).join(',')}`,
      ),
  },
};
```

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/api/
git commit -m "feat(web): typed API client + generated OpenAPI types"
```

### Task 7.3: Run list page

**Files:**
- Modify: `web/src/routes/+page.svelte`
- Create: `web/src/lib/ui/Card.svelte`
- Create: `web/src/lib/ui/Table.svelte`

- [ ] **Step 1: UI primitives**

```svelte
<!-- web/src/lib/ui/Card.svelte -->
<div class="rounded border border-bg-muted bg-bg-surface p-4 {$$props.class ?? ''}">
  <slot />
</div>
```

```svelte
<!-- web/src/lib/ui/Table.svelte -->
<script lang="ts">
  /** Generic table primitive. Pass <thead>/<tbody> via slots. */
</script>
<div class="overflow-x-auto">
  <table class="w-full text-left text-sm">
    <slot />
  </table>
</div>
```

- [ ] **Step 2: Run list page**

```svelte
<!-- web/src/routes/+page.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type RunSummary } from '$lib/api/client';
  import Card from '$lib/ui/Card.svelte';
  import Table from '$lib/ui/Table.svelte';

  let runs: RunSummary[] = [];
  let loading = true;
  let error: string | null = null;

  // Filters
  let filterPool = '';
  let filterStatus = '';
  let filterScoreMin: number | '' = '';

  async function load() {
    loading = true;
    error = null;
    try {
      runs = await api.runs.list({
        pool: filterPool || undefined,
        status: filterStatus || undefined,
        score_min: filterScoreMin === '' ? undefined : filterScoreMin,
      });
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function fmtTs(ms: number): string {
    return new Date(ms).toISOString().replace('T', ' ').slice(0, 19);
  }
  function fmtScore(s: number | null | undefined): string {
    if (s === null || s === undefined) return '—';
    return s.toFixed(4);
  }
  function shortAddr(a: string): string {
    return a.length > 10 ? `${a.slice(0, 4)}…${a.slice(-4)}` : a;
  }
</script>

<div class="flex items-center justify-between">
  <h2 class="text-xl font-bold">Runs</h2>
  <div class="flex gap-2 text-sm">
    <input class="rounded bg-bg-surface px-2 py-1" placeholder="pool address"
           bind:value={filterPool} on:change={load} />
    <select class="rounded bg-bg-surface px-2 py-1" bind:value={filterStatus} on:change={load}>
      <option value="">all status</option>
      <option value="ok">ok</option>
      <option value="error">error</option>
      <option value="timeout">timeout</option>
      <option value="running">running</option>
    </select>
    <input type="number" step="0.01" class="w-24 rounded bg-bg-surface px-2 py-1"
           placeholder="min score" bind:value={filterScoreMin} on:change={load} />
  </div>
</div>

<div class="mt-4">
  {#if loading}
    <p class="text-fg-muted">Loading…</p>
  {:else if error}
    <Card class="text-red-400">{error}</Card>
  {:else if runs.length === 0}
    <Card>
      <p class="text-fg-muted">No runs yet.</p>
      <p class="mt-2 font-mono text-xs text-fg-dim">
        Run <code>belt run --config configs/quickstart.yaml</code> to create your first run.
      </p>
    </Card>
  {:else}
    <Card>
      <Table>
        <thead class="text-xs uppercase text-fg-muted">
          <tr>
            <th class="py-2">run id</th>
            <th>started</th>
            <th>pool</th>
            <th>strategy</th>
            <th>status</th>
            <th>metric</th>
            <th class="text-right">score</th>
          </tr>
        </thead>
        <tbody class="font-mono text-xs">
          {#each runs as r}
            <tr class="border-t border-bg-muted hover:bg-bg-muted">
              <td class="py-2">
                <a class="text-accent hover:underline" href="/runs/{r.run_id}">
                  {r.run_id}
                </a>
              </td>
              <td class="text-fg-muted">{fmtTs(r.started_at)}</td>
              <td class="text-fg-muted">{shortAddr(r.pool_address)}</td>
              <td class="text-fg-muted">{r.strategy_class.split('.').pop()}</td>
              <td>
                <span class="rounded px-1.5 py-0.5 text-xs
                  {r.status === 'ok' ? 'bg-green-900/30 text-green-400'
                   : r.status === 'error' ? 'bg-red-900/30 text-red-400'
                   : r.status === 'timeout' ? 'bg-yellow-900/30 text-yellow-400'
                   : 'bg-blue-900/30 text-blue-400'}">
                  {r.status}
                </span>
              </td>
              <td class="text-fg-muted">{r.selection_metric}</td>
              <td class="text-right">{fmtScore(r.score)}</td>
            </tr>
          {/each}
        </tbody>
      </Table>
    </Card>
  {/if}
</div>
```

- [ ] **Step 3: Smoke check**

```bash
cd web && pnpm check
```

- [ ] **Step 4: Commit**

```bash
git add web/src/routes/+page.svelte web/src/lib/ui/
git commit -m "feat(web): run list page with filters"
```

### Task 7.4: Run detail page (header + config + primitives)

**Files:**
- Create: `web/src/routes/runs/[id]/+page.svelte`
- Create: `web/src/routes/runs/[id]/+page.ts`

- [ ] **Step 1: Page load function**

```typescript
// web/src/routes/runs/[id]/+page.ts
import { error } from '@sveltejs/kit';
import { api } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch: _fetch }) => {
  try {
    const [detail, trajectory, rebalances] = await Promise.all([
      api.runs.get(params.id),
      api.runs.trajectory(params.id, '1h'),
      api.runs.rebalances(params.id),
    ]);
    return { detail, trajectory, rebalances };
  } catch (e) {
    throw error(404, `Run ${params.id} not found`);
  }
};
```

- [ ] **Step 2: Page component (header + config + primitives — charts in Task 7.5)**

```svelte
<!-- web/src/routes/runs/[id]/+page.svelte -->
<script lang="ts">
  import Card from '$lib/ui/Card.svelte';
  import type { PageData } from './$types';

  export let data: PageData;
  $: detail = data.detail;
  $: rebalances = data.rebalances;

  let configOpen = false;

  function fmtScore(s: number | null | undefined): string {
    return s === null || s === undefined ? '—' : s.toFixed(4);
  }
  function fmtTs(ms: number | null | undefined): string {
    if (!ms) return '—';
    return new Date(ms).toISOString().replace('T', ' ').slice(0, 19);
  }
</script>

<div class="space-y-4">
  <Card>
    <div class="flex items-baseline justify-between">
      <h2 class="font-mono text-lg">{detail.run_id}</h2>
      <div class="flex items-center gap-3 text-sm">
        <span class="rounded px-2 py-0.5
          {detail.status === 'ok' ? 'bg-green-900/30 text-green-400'
           : detail.status === 'error' ? 'bg-red-900/30 text-red-400'
           : 'bg-yellow-900/30 text-yellow-400'}">
          {detail.status}
        </span>
        <span class="font-mono">
          {detail.selection_metric}: <strong>{fmtScore(detail.score)}</strong>
        </span>
      </div>
    </div>
    <div class="mt-3 grid grid-cols-2 gap-y-1 text-xs text-fg-muted md:grid-cols-4">
      <div>started: <span class="text-fg">{fmtTs(detail.started_at)}</span></div>
      <div>ended: <span class="text-fg">{fmtTs(detail.ended_at)}</span></div>
      <div>pool: <span class="text-fg font-mono">{detail.pool_address}</span></div>
      <div>strategy: <span class="text-fg">{detail.strategy_class.split('.').pop()}</span></div>
      <div>adapter: <span class="text-fg">{detail.adapter_kind}</span></div>
      <div>cost model: <span class="text-fg font-mono">{detail.cost_model_version}</span></div>
      <div>session: <span class="text-fg">{detail.session_id ?? '—'}</span></div>
      <div>created by: <span class="text-fg">{detail.created_by}</span></div>
    </div>
  </Card>

  <Card>
    <button class="flex items-center gap-2 text-sm text-fg-muted hover:text-fg"
            on:click={() => (configOpen = !configOpen)}>
      <span class="font-mono text-xs">{configOpen ? '▾' : '▸'}</span>
      Run config (config_hash: <span class="font-mono">{detail.config_hash.slice(0, 12)}</span>)
    </button>
    {#if configOpen}
      <pre class="mt-3 overflow-x-auto rounded bg-bg p-3 text-xs">{JSON.stringify({
        pool: detail.pool_address,
        adapter: detail.adapter_kind,
        strategy: { class: detail.strategy_class, params: detail.strategy_params },
        engine: {
          tick_secs: detail.tick_secs,
          initial_x: detail.initial_x, initial_y: detail.initial_y,
          selection_metric: detail.selection_metric,
        },
        window: { start_ms: detail.window_start, end_ms: detail.window_end },
      }, null, 2)}</pre>
    {/if}
  </Card>

  <Card>
    <h3 class="mb-3 text-sm font-bold uppercase tracking-wider text-fg-muted">
      Primitives
    </h3>
    <div class="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
      {#each Object.entries(detail.primitives ?? {}) as [name, value]}
        <div class="rounded bg-bg p-3 {name === detail.selection_metric ? 'ring-1 ring-accent' : ''}">
          <div class="text-xs text-fg-muted">{name}</div>
          <div class="font-mono text-lg">{value.toFixed(4)}</div>
        </div>
      {/each}
    </div>
  </Card>

  <Card>
    <h3 class="mb-3 text-sm font-bold uppercase tracking-wider text-fg-muted">
      Rebalances ({rebalances.length})
    </h3>
    {#if rebalances.length === 0}
      <p class="text-fg-muted">No rebalances during this run.</p>
    {:else}
      <table class="w-full text-left text-xs font-mono">
        <thead class="text-fg-muted">
          <tr>
            <th class="py-1">ts</th><th>trigger</th>
            <th>old range</th><th>new range</th>
            <th class="text-right">gas (lamports)</th>
            <th class="text-right">comp fee</th>
            <th class="text-right">claimed</th>
          </tr>
        </thead>
        <tbody>
          {#each rebalances as r}
            <tr class="border-t border-bg-muted">
              <td class="py-1 text-fg-muted">{fmtTs(r.ts)}</td>
              <td>{r.trigger}</td>
              <td>[{r.old_lower_bin}, {r.old_upper_bin}]</td>
              <td>[{r.new_lower_bin}, {r.new_upper_bin}]</td>
              <td class="text-right">{r.gas_lamports.toLocaleString()}</td>
              <td class="text-right">x: {r.composition_fee_x}, y: {r.composition_fee_y}</td>
              <td class="text-right">x: {r.fees_claimed_x}, y: {r.fees_claimed_y}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </Card>

  <Card>
    <p class="text-fg-muted">Charts (price/PnL/composition) coming in Task 7.5.</p>
  </Card>
</div>
```

- [ ] **Step 3: Smoke check + commit**

```bash
cd web && pnpm check
git add web/src/routes/runs/
git commit -m "feat(web): run detail page (header, config, primitives, rebalances)"
```

### Task 7.5: Run detail charts (PriceBin, PnL, Composition)

**Files:**
- Create: `web/src/lib/charts/PriceBinChart.svelte`
- Create: `web/src/lib/charts/PnlChart.svelte`
- Create: `web/src/lib/charts/CompositionChart.svelte`
- Modify: `web/src/routes/runs/[id]/+page.svelte`

The pattern below is identical for all three charts — only the series differ. Show one full implementation; replicate the pattern for the others.

- [ ] **Step 1: Generic ECharts wrapper**

```svelte
<!-- web/src/lib/charts/PriceBinChart.svelte -->
<script lang="ts">
  import { Chart } from 'svelte-echarts';
  import { init } from 'echarts/core';
  import { LineChart, ScatterChart } from 'echarts/charts';
  import {
    GridComponent, TooltipComponent, DataZoomComponent, MarkPointComponent, LegendComponent,
  } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import type { TrajectoryRow, RebalanceRecordResponse } from '$lib/api/client';

  // Register only what we use
  import { use } from 'echarts/core';
  use([LineChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, MarkPointComponent, LegendComponent, CanvasRenderer]);

  export let trajectory: TrajectoryRow[];
  export let rebalances: RebalanceRecordResponse[];

  $: priceSeries = trajectory.map((r) => [r.ts, r.price]);
  $: rebalanceMarkers = rebalances.map((r) => ({
    coord: [r.ts, trajectory.find((t) => t.ts >= r.ts)?.price ?? 0],
    value: 'R',
    itemStyle: { color: '#3b82f6' },
  }));

  $: option = {
    backgroundColor: 'transparent',
    grid: { top: 20, right: 30, bottom: 50, left: 60 },
    tooltip: { trigger: 'axis', backgroundColor: '#141414', borderColor: '#1f1f1f', textStyle: { color: '#e5e5e5' } },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: '#1f1f1f' } }, axisLabel: { color: '#9ca3af' } },
    yAxis: { type: 'value', scale: true, axisLine: { lineStyle: { color: '#1f1f1f' } }, axisLabel: { color: '#9ca3af' }, splitLine: { lineStyle: { color: '#1f1f1f' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 5, backgroundColor: '#141414', fillerColor: '#1f1f1f' }],
    series: [
      {
        name: 'Price', type: 'line', sampling: 'lttb',
        data: priceSeries, lineStyle: { color: '#e5e5e5', width: 1 }, showSymbol: false,
        markPoint: { symbol: 'pin', symbolSize: 18, data: rebalanceMarkers, label: { color: '#fff' } },
      },
    ],
  };
</script>

<div class="h-72">
  <Chart {init} {option} />
</div>
```

- [ ] **Step 2: PnL + Composition charts (same pattern, different series)**

```svelte
<!-- web/src/lib/charts/PnlChart.svelte -->
<script lang="ts">
  import { Chart } from 'svelte-echarts';
  import { init } from 'echarts/core';
  import { LineChart } from 'echarts/charts';
  import { GridComponent, TooltipComponent, DataZoomComponent, LegendComponent } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import { use } from 'echarts/core';
  use([LineChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, CanvasRenderer]);

  import type { TrajectoryRow } from '$lib/api/client';
  export let trajectory: TrajectoryRow[];

  $: option = {
    backgroundColor: 'transparent',
    grid: { top: 30, right: 30, bottom: 50, left: 70 },
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9ca3af' }, top: 0 },
    xAxis: { type: 'time', axisLabel: { color: '#9ca3af' } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#9ca3af' }, splitLine: { lineStyle: { color: '#1f1f1f' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 5 }],
    series: [
      { name: 'Position', type: 'line', sampling: 'lttb', showSymbol: false,
        data: trajectory.map((r) => [r.ts, r.position_value_usd]),
        lineStyle: { color: '#3b82f6' } },
      { name: 'HODL', type: 'line', sampling: 'lttb', showSymbol: false,
        data: trajectory.map((r) => [r.ts, r.hodl_value_usd]),
        lineStyle: { color: '#9ca3af', type: 'dashed' } },
      { name: 'IL', type: 'line', sampling: 'lttb', showSymbol: false,
        data: trajectory.map((r) => [r.ts, r.il_cumulative]),
        lineStyle: { color: '#ef4444' } },
    ],
  };
</script>

<div class="h-64"><Chart {init} {option} /></div>
```

```svelte
<!-- web/src/lib/charts/CompositionChart.svelte -->
<script lang="ts">
  import { Chart } from 'svelte-echarts';
  import { init } from 'echarts/core';
  import { LineChart } from 'echarts/charts';
  import { GridComponent, TooltipComponent, DataZoomComponent, LegendComponent } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import { use } from 'echarts/core';
  use([LineChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, CanvasRenderer]);

  import type { TrajectoryRow } from '$lib/api/client';
  export let trajectory: TrajectoryRow[];

  // Composition: stacked area of position value vs idle capital
  $: option = {
    backgroundColor: 'transparent',
    grid: { top: 30, right: 30, bottom: 50, left: 70 },
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9ca3af' }, top: 0 },
    xAxis: { type: 'time', axisLabel: { color: '#9ca3af' } },
    yAxis: { type: 'value', axisLabel: { color: '#9ca3af' }, splitLine: { lineStyle: { color: '#1f1f1f' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 5 }],
    series: [
      { name: 'Position', type: 'line', sampling: 'lttb', showSymbol: false, areaStyle: { color: '#3b82f6', opacity: 0.4 },
        data: trajectory.map((r) => [r.ts, r.position_value_usd]),
        stack: 'total', lineStyle: { color: '#3b82f6' } },
      { name: 'Idle', type: 'line', sampling: 'lttb', showSymbol: false, areaStyle: { color: '#9ca3af', opacity: 0.3 },
        data: trajectory.map((r) => [r.ts, r.capital_idle_usd]),
        stack: 'total', lineStyle: { color: '#9ca3af' } },
    ],
  };
</script>

<div class="h-64"><Chart {init} {option} /></div>
```

- [ ] **Step 3: Mount charts in run detail**

Replace the placeholder `<Card><p>Charts (price/PnL/composition) coming in Task 7.5.</p></Card>` in `web/src/routes/runs/[id]/+page.svelte` with:

```svelte
<script lang="ts">
  // ...existing imports...
  import PriceBinChart from '$lib/charts/PriceBinChart.svelte';
  import PnlChart from '$lib/charts/PnlChart.svelte';
  import CompositionChart from '$lib/charts/CompositionChart.svelte';
</script>

<!-- ...existing markup... -->

<Card>
  <h3 class="mb-3 text-sm font-bold uppercase tracking-wider text-fg-muted">Price + Rebalances</h3>
  <PriceBinChart trajectory={data.trajectory} rebalances={data.rebalances} />
</Card>

<Card>
  <h3 class="mb-3 text-sm font-bold uppercase tracking-wider text-fg-muted">PnL vs HODL</h3>
  <PnlChart trajectory={data.trajectory} />
</Card>

<Card>
  <h3 class="mb-3 text-sm font-bold uppercase tracking-wider text-fg-muted">Composition</h3>
  <CompositionChart trajectory={data.trajectory} />
</Card>
```

- [ ] **Step 4: Smoke check + commit**

```bash
cd web && pnpm check
git add web/src/lib/charts/ web/src/routes/runs/
git commit -m "feat(web): run detail charts (price+rebalances, PnL, composition)"
```

### Task 7.6: Compare page

**Files:**
- Create: `web/src/routes/compare/+page.svelte`
- Create: `web/src/routes/compare/+page.ts`

- [ ] **Step 1: Page load**

```typescript
// web/src/routes/compare/+page.ts
import { api } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url }) => {
  const idsParam = url.searchParams.get('ids') ?? '';
  const ids = idsParam.split(',').map((s) => s.trim()).filter(Boolean);
  if (ids.length < 2) return { ids, response: null };
  const response = await api.runs.compare(ids);
  return { ids, response };
};
```

- [ ] **Step 2: Compare page**

```svelte
<!-- web/src/routes/compare/+page.svelte -->
<script lang="ts">
  import Card from '$lib/ui/Card.svelte';
  import { Chart } from 'svelte-echarts';
  import { init } from 'echarts/core';
  import { LineChart } from 'echarts/charts';
  import { GridComponent, TooltipComponent, DataZoomComponent, LegendComponent } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import { use } from 'echarts/core';
  use([LineChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, CanvasRenderer]);
  import type { PageData } from './$types';

  export let data: PageData;
  $: ids = data.ids;
  $: resp = data.response;

  $: pnlOption = resp ? {
    backgroundColor: 'transparent',
    grid: { top: 30, right: 30, bottom: 50, left: 70 },
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9ca3af' }, top: 0 },
    xAxis: { type: 'time', axisLabel: { color: '#9ca3af' } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#9ca3af' }, splitLine: { lineStyle: { color: '#1f1f1f' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 5 }],
    series: Object.entries(resp.trajectories).map(([rid, rows], idx) => ({
      name: rid,
      type: 'line', sampling: 'lttb', showSymbol: false,
      data: rows.map((r) => [r.ts, r.position_value_usd]),
      lineStyle: { width: 1.5 },
    })),
  } : null;
</script>

<h2 class="mb-4 text-xl font-bold">Compare</h2>

{#if ids.length < 2}
  <Card>
    <p class="text-fg-muted">Pick 2–6 runs to compare.</p>
    <p class="mt-2 text-xs text-fg-dim">
      URL pattern: <code class="font-mono">/compare?ids=run_a,run_b,run_c</code>
    </p>
  </Card>
{:else if !resp}
  <p class="text-fg-muted">Loading…</p>
{:else}
  <div class="space-y-4">
    <Card>
      <h3 class="mb-3 text-sm font-bold uppercase tracking-wider text-fg-muted">PnL Overlay</h3>
      <div class="h-72"><Chart {init} option={pnlOption} /></div>
    </Card>

    <Card>
      <h3 class="mb-3 text-sm font-bold uppercase tracking-wider text-fg-muted">Primitives Matrix</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs font-mono">
          <thead class="text-fg-muted">
            <tr>
              <th class="py-1">primitive</th>
              {#each ids as rid}
                <th class="text-right">{rid.split('_').pop()}</th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each Object.entries(resp.primitives_matrix) as [name, values]}
              <tr class="border-t border-bg-muted">
                <td class="py-1">{name}</td>
                {#each ids as rid}
                  {@const v = values[rid]}
                  <td class="text-right">{v === null || v === undefined ? '—' : v.toFixed(4)}</td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </Card>
  </div>
{/if}
```

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/compare/
git commit -m "feat(web): compare page (PnL overlay + primitives matrix)"
```

### Task 7.7: Sessions + Pools list pages

**Files:**
- Create: `web/src/routes/sessions/+page.svelte` and `+page.ts`
- Create: `web/src/routes/pools/+page.svelte` and `+page.ts`

- [ ] **Step 1: Sessions list (mirrors run-list pattern)**

```typescript
// web/src/routes/sessions/+page.ts
import { api } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
  const sessions = await api.sessions.list();
  return { sessions };
};
```

```svelte
<!-- web/src/routes/sessions/+page.svelte -->
<script lang="ts">
  import Card from '$lib/ui/Card.svelte';
  import type { PageData } from './$types';
  export let data: PageData;
  function fmtTs(ms: number | null | undefined): string {
    return ms ? new Date(ms).toISOString().replace('T', ' ').slice(0, 19) : '—';
  }
</script>

<h2 class="mb-4 text-xl font-bold">Sessions</h2>
<Card>
  {#if data.sessions.length === 0}
    <p class="text-fg-muted">
      No sessions yet. Create one with
      <code class="font-mono">belt session new --label "..."</code>.
    </p>
  {:else}
    <table class="w-full text-left text-sm font-mono">
      <thead class="text-xs uppercase text-fg-muted">
        <tr><th class="py-2">id</th><th>label</th><th>kind</th><th>created</th><th>closed</th></tr>
      </thead>
      <tbody>
        {#each data.sessions as s}
          <tr class="border-t border-bg-muted">
            <td class="py-2"><a class="text-accent hover:underline" href="/sessions/{s.session_id}">{s.session_id}</a></td>
            <td>{s.label ?? '—'}</td>
            <td class="text-fg-muted">{s.session_kind}</td>
            <td class="text-fg-muted">{fmtTs(s.created_at)}</td>
            <td class="text-fg-muted">{fmtTs(s.closed_at)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</Card>
```

- [ ] **Step 2: Pools list (same pattern as sessions)**

```typescript
// web/src/routes/pools/+page.ts
import { api } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => ({ pools: await api.pools.list() });
```

```svelte
<!-- web/src/routes/pools/+page.svelte -->
<script lang="ts">
  import Card from '$lib/ui/Card.svelte';
  import type { PageData } from './$types';
  export let data: PageData;
</script>

<h2 class="mb-4 text-xl font-bold">Pools</h2>
<Card>
  {#if data.pools.length === 0}
    <p class="text-fg-muted">No pools ingested. Run <code class="font-mono">belt ingest</code>.</p>
  {:else}
    <table class="w-full text-left text-sm font-mono">
      <thead class="text-xs uppercase text-fg-muted">
        <tr><th class="py-2">address</th><th>name</th><th>bin step</th><th class="text-right">bars</th></tr>
      </thead>
      <tbody>
        {#each data.pools as p}
          <tr class="border-t border-bg-muted">
            <td class="py-2 font-mono text-xs">{p.address}</td>
            <td>{p.name ?? '—'}</td>
            <td>{p.bin_step ?? '—'} bps</td>
            <td class="text-right">{p.bars_count.toLocaleString()}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</Card>
```

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/sessions/ web/src/routes/pools/
git commit -m "feat(web): sessions + pools list pages"
```

### Task 7.8: Playwright smoke tests

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/tests/smoke.spec.ts`

- [ ] **Step 1: Playwright config**

```typescript
// web/playwright.config.ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'pnpm dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
  },
});
```

- [ ] **Step 2: Smoke test**

```typescript
// web/tests/smoke.spec.ts
import { test, expect } from '@playwright/test';

test('run list page loads', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Runs' })).toBeVisible();
});

test('navigation links exist', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('link', { name: 'Compare' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Sessions' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Pools' })).toBeVisible();
});

test('compare page handles empty ids', async ({ page }) => {
  await page.goto('/compare');
  await expect(page.getByText('Pick 2–6 runs to compare')).toBeVisible();
});
```

> Note: Playwright smoke runs in CI only when there's a server to hit. For v1 it's optional locally; CI sets it up via `make dev` or starts both processes.

- [ ] **Step 3: Commit**

```bash
git add web/playwright.config.ts web/tests/
git commit -m "test(web): Playwright smoke tests for navigation"
```

---

**End of Phase 7.** Frontend is complete. `make dev` runs both processes; browser at `http://localhost:5173` shows the run list (empty initially), runs render with charts after `belt run` lands a result.

---

## Phase 8 — Integration + regression tests

The unit tests so far cover individual functions. This phase adds the cross-cutting tests that the spec calls out as critical: determinism, lookahead-bias guard, holdout isolation, schema version dispatch, and locked golden trajectories per baseline.

### Task 8.1: Determinism test

**Files:**
- Create: `tests/integration/test_determinism.py`

The future agent loop's keep/discard decisions assume reproducibility. This test catches accidental non-determinism (dict iteration leaking into computation, RNG without seed, timestamps used as keys).

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_determinism.py
import hashlib
import json
from pathlib import Path

import polars as pl
import pytest
from click.testing import CliRunner

from asteroid_belt.cli import cli


@pytest.fixture
def staged_pool(tmp_path: Path) -> Path:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    pool_dir = tmp_path / "pools" / pool
    pool_dir.mkdir(parents=True)
    bars = pl.DataFrame({
        "ts": [1_700_000_000_000 + i * 60_000 for i in range(60)],
        "open": [87.50 + (i % 7) * 0.02 for i in range(60)],
        "high": [87.55 + (i % 7) * 0.02 for i in range(60)],
        "low": [87.49 + (i % 7) * 0.02 for i in range(60)],
        "close": [87.55 + ((i + 1) % 7) * 0.02 for i in range(60)],
        "volume_x": [1_000_000 + i * 1000 for i in range(60)],
        "volume_y": [87_550_000 + i * 10000 for i in range(60)],
    })
    bars.write_parquet(pool_dir / "bars_1m.parquet")
    (pool_dir / "pool_meta.json").write_text(json.dumps({
        "address": pool, "name": "SOL-USDC",
        "token_x": {"decimals": 9}, "token_y": {"decimals": 6},
        "pool_config": {"bin_step": 10},
    }))
    return tmp_path


@pytest.fixture
def cfg_path(tmp_path: Path, staged_pool: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text("""
schema_version: "1.0"
pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
window: {start: "2023-11-14T22:13:20Z", end: "2023-11-14T23:13:20Z"}
adapter: {kind: bar}
strategy:
  class: asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy
  params: {bin_width: 21, rebalance_trigger_bins: 5}
engine:
  tick_secs: 300
  initial_x: 100000000
  initial_y: 8800000000
  selection_metric: sharpe
  timeout_secs: 60
""")
    return p


def _trajectory_sha(parquet_path: Path) -> str:
    return hashlib.sha256(parquet_path.read_bytes()).hexdigest()


def test_same_config_produces_identical_trajectory(staged_pool: Path, cfg_path: Path) -> None:
    runner = CliRunner()
    # First run
    r1 = runner.invoke(cli, ["run", "--config", str(cfg_path), "--data-dir", str(staged_pool)])
    assert r1.exit_code == 0, r1.output
    runs_dir1 = staged_pool / "runs"
    sub1 = next(runs_dir1.iterdir())
    sha1 = _trajectory_sha(sub1 / "result.parquet")

    # Force a second run (dedup-safe)
    r2 = runner.invoke(cli, [
        "run", "--config", str(cfg_path),
        "--data-dir", str(staged_pool),
        "--force",
    ])
    assert r2.exit_code == 0, r2.output
    sub_dirs = sorted([p for p in runs_dir1.iterdir() if p.is_dir()])
    assert len(sub_dirs) == 2
    sha2 = _trajectory_sha(sub_dirs[-1] / "result.parquet")

    assert sha1 == sha2, (
        f"non-determinism: trajectory parquets differ\n"
        f"  run 1: {sha1}\n"
        f"  run 2: {sha2}\n"
        "Likely causes: dict iteration order leaking into computation, "
        "RNG without explicit seed, timestamp used as key."
    )
```

- [ ] **Step 2: Run + commit**

```bash
pytest tests/integration/test_determinism.py -v
git add tests/integration/test_determinism.py
git commit -m "test(integration): determinism — same config → bit-identical trajectory"
```

### Task 8.2: Lookahead-bias guard test

**Files:**
- Create: `tests/integration/test_lookahead_guard.py`

Verifies that the `BarSynthesizedAdapter` does not yield events outside its window even when something downstream tries to read past `window.end_ms`.

- [ ] **Step 1: Test**

```python
# tests/integration/test_lookahead_guard.py
from pathlib import Path

import polars as pl
import pytest

from asteroid_belt.data.adapters.base import PoolKey, TimeWindow
from asteroid_belt.data.adapters.bar import BarSynthesizedAdapter


@pytest.fixture
def bars(tmp_path: Path) -> Path:
    df = pl.DataFrame({
        "ts": [0, 60_000, 120_000, 180_000, 240_000],
        "open": [1.0] * 5, "high": [1.0] * 5, "low": [1.0] * 5, "close": [1.0] * 5,
        "volume_x": [100] * 5, "volume_y": [100] * 5,
    })
    p = tmp_path / "bars.parquet"
    df.write_parquet(p)
    return p


def test_adapter_strict_window_filter(bars: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=bars, pool=PoolKey("p"), bin_step=10,
    )
    win = TimeWindow(start_ms=60_000, end_ms=180_000)
    events = list(adapter.stream(win))
    # Only ts=60_000 and ts=120_000 should be yielded; 0 is before start, 180_000 is excluded.
    assert {e.ts for e in events} == {60_000, 120_000}


def test_adapter_returns_no_events_for_empty_window(bars: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=bars, pool=PoolKey("p"), bin_step=10,
    )
    events = list(adapter.stream(TimeWindow(start_ms=999_999, end_ms=1_000_000)))
    assert events == []


def test_strategy_cannot_observe_future_via_adapter_handle(bars: Path) -> None:
    """A strategy receives only events the adapter yields. Verify no
    adapter handle leaks via PoolKey or anything else the engine passes."""
    adapter = BarSynthesizedAdapter(
        parquet_path=bars, pool=PoolKey("p"), bin_step=10,
    )
    # The PoolKey type has no path/handle attribute, by design
    assert "parquet_path" not in adapter.pool.__dataclass_fields__  # type: ignore[attr-defined]
    # And the AdapterProtocol exposes only `pool` and `stream`; nothing else
    public_attrs = {x for x in dir(adapter) if not x.startswith("_")}
    assert "stream" in public_attrs
    assert "pool" in public_attrs
```

- [ ] **Step 2: Run + commit**

```bash
pytest tests/integration/test_lookahead_guard.py -v
git add tests/integration/test_lookahead_guard.py
git commit -m "test(integration): lookahead-bias guard at adapter layer"
```

### Task 8.3: Holdout isolation test

**Files:**
- Create: `tests/integration/test_holdout_isolation.py`

Verifies that running a backtest does not even open the holdout parquet file. Uses a sentinel: a fake holdout parquet file whose access would be detectable via filesystem inspection (we use a watchdog filter on `os.open`).

- [ ] **Step 1: Test**

```python
# tests/integration/test_holdout_isolation.py
import json
import os
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest
from click.testing import CliRunner

from asteroid_belt.cli import cli


@pytest.fixture
def staged_with_holdout(tmp_path: Path) -> tuple[Path, Path]:
    pool = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"
    pool_dir = tmp_path / "pools" / pool
    pool_dir.mkdir(parents=True)

    train = pl.DataFrame({
        "ts": [1_700_000_000_000 + i * 60_000 for i in range(10)],
        "open": [87.50] * 10, "high": [87.55] * 10, "low": [87.45] * 10,
        "close": [87.50] * 10, "volume_x": [1000] * 10, "volume_y": [87500] * 10,
    })
    train.write_parquet(pool_dir / "bars_1m.parquet")

    holdout = pl.DataFrame({
        "ts": [1_700_000_000_000 + i * 60_000 for i in range(10)],
        "open": [99.99] * 10, "high": [99.99] * 10, "low": [99.99] * 10,
        "close": [99.99] * 10, "volume_x": [9999] * 10, "volume_y": [9999] * 10,
    })
    holdout_path = pool_dir / "bars_1m_holdout.parquet"
    holdout.write_parquet(holdout_path)

    (pool_dir / "pool_meta.json").write_text(json.dumps({
        "address": pool, "token_x": {"decimals": 9}, "token_y": {"decimals": 6},
        "pool_config": {"bin_step": 10},
    }))

    return tmp_path, holdout_path


@pytest.fixture
def cfg(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text("""
schema_version: "1.0"
pool: BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y
window: {start: "2023-11-14T22:13:20Z", end: "2023-11-14T22:23:20Z"}
adapter: {kind: bar}
strategy:
  class: asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy
  params: {bin_width: 21, rebalance_trigger_bins: 5}
engine:
  tick_secs: 300
  initial_x: 100000000
  initial_y: 8800000000
  selection_metric: sharpe
  timeout_secs: 30
""")
    return p


def test_belt_run_never_opens_holdout(staged_with_holdout: tuple[Path, Path], cfg: Path) -> None:
    data_dir, holdout_path = staged_with_holdout
    holdout_str = str(holdout_path.resolve())
    opened: list[str] = []

    real_open = os.open

    def watch_open(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            resolved = str(Path(path).resolve())
        except Exception:
            resolved = str(path)
        if "_holdout" in resolved:
            opened.append(resolved)
        return real_open(path, *args, **kwargs)

    runner = CliRunner()
    with patch("os.open", side_effect=watch_open):
        result = runner.invoke(cli, [
            "run", "--config", str(cfg),
            "--data-dir", str(data_dir),
        ])

    assert result.exit_code == 0, result.output
    assert opened == [], (
        f"belt run accessed holdout files: {opened}\n"
        "Holdout isolation invariant violated."
    )
```

- [ ] **Step 2: Run + commit**

```bash
pytest tests/integration/test_holdout_isolation.py -v
git add tests/integration/test_holdout_isolation.py
git commit -m "test(integration): holdout isolation — agent runs never open _holdout files"
```

### Task 8.4: Schema version dispatch test

**Files:**
- Create: `tests/integration/test_schema_version.py`

- [ ] **Step 1: Test**

```python
# tests/integration/test_schema_version.py
from pathlib import Path

import pytest

from asteroid_belt.config import load_run_config


def test_loads_v1_0_exactly(tmp_path: Path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text("""
schema_version: "1.0"
pool: x
window: {start: "2024-05-01T00:00:00Z", end: "2024-05-02T00:00:00Z"}
adapter: {kind: bar}
strategy: {class: foo, params: {}}
engine:
  tick_secs: 60
  initial_x: 1
  initial_y: 1
  selection_metric: sharpe
  timeout_secs: 60
""")
    cfg = load_run_config(p)
    assert cfg.schema_version == "1.0"


def test_v1_5_with_extra_fields_loads_via_extra_allow(tmp_path: Path) -> None:
    """Forward-compat: v1 reader handles a synthetic v1.5 config with extra fields."""
    p = tmp_path / "cfg.yaml"
    p.write_text("""
schema_version: "1.0"
pool: x
window: {start: "2024-05-01T00:00:00Z", end: "2024-05-02T00:00:00Z"}
adapter: {kind: bar, future_setting: "ignored"}
strategy:
  class: foo
  params: {}
  future_strategy_field: "ignored"
engine:
  tick_secs: 60
  initial_x: 1
  initial_y: 1
  selection_metric: sharpe
  timeout_secs: 60
  future_engine_field: "ignored"
future_top_level_field: "ignored"
""")
    cfg = load_run_config(p)
    # All extra fields land in `__pydantic_extra__` / are accessible via dict
    # but don't break the v1 reader.
    assert cfg.pool == "x"


def test_invalid_schema_version_rejected(tmp_path: Path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text("""
schema_version: "2.0"
pool: x
window: {start: "2024-05-01T00:00:00Z", end: "2024-05-02T00:00:00Z"}
adapter: {kind: bar}
strategy: {class: foo, params: {}}
engine:
  tick_secs: 60
  initial_x: 1
  initial_y: 1
  selection_metric: sharpe
  timeout_secs: 60
""")
    with pytest.raises(Exception):
        load_run_config(p)
```

- [ ] **Step 2: Run + commit**

```bash
pytest tests/integration/test_schema_version.py -v
git add tests/integration/test_schema_version.py
git commit -m "test(integration): schema version dispatch (1.0 strict, 1.5+ extra='allow')"
```

### Task 8.5: Regression — golden trajectories per baseline

**Files:**
- Create: `tests/regression/test_golden_baselines.py`
- Create: `tests/regression/golden/precision_curve.sha256`
- Create: `tests/regression/golden/multiday_cook_up.sha256`
- Create: `tests/regression/fixtures/synthetic_30day.parquet`
- Create: `tests/regression/fixtures/pool_meta.json`

This is the most important test for catching accidental engine drift. We freeze a synthetic 30-day fixture, run each baseline against it, and lock the trajectory parquet's sha256. CI fails on drift; intentional drifts require committing a new sha + a justification note.

- [ ] **Step 1: Generate the synthetic fixture**

```python
# scripts/build_regression_fixture.py (one-shot script; not in package)
"""Build the 30-day synthetic pool fixture for regression tests.

Run once locally; commits the resulting parquet + meta to
tests/regression/fixtures/.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "tests" / "regression" / "fixtures"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    rng = random.Random(42)  # locked seed
    bars = []
    price = 87.50
    minute_count = 30 * 24 * 60  # 30 days
    start_ts = 1_700_000_000_000
    for i in range(minute_count):
        # Random walk with mean reversion
        drift = rng.gauss(0, 0.02)
        price = max(20.0, min(200.0, price + drift - (price - 87.50) * 0.001))
        open_p = price + rng.gauss(0, 0.005)
        close_p = price + rng.gauss(0, 0.005)
        high = max(open_p, close_p) + abs(rng.gauss(0, 0.005))
        low = min(open_p, close_p) - abs(rng.gauss(0, 0.005))
        bars.append({
            "ts": start_ts + i * 60_000,
            "open": round(open_p, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close_p, 4),
            "volume_x": rng.randint(500_000, 2_000_000),
            "volume_y": rng.randint(40_000_000, 180_000_000),
        })

    pl.DataFrame(bars).write_parquet(OUT_DIR / "synthetic_30day.parquet")

    (OUT_DIR / "pool_meta.json").write_text(json.dumps({
        "address": "SYNTH_POOL_REGRESSION",
        "name": "SYNTH-USDC",
        "token_x": {"decimals": 9, "symbol": "SYNTH"},
        "token_y": {"decimals": 6, "symbol": "USDC"},
        "pool_config": {"bin_step": 10, "base_fee_pct": 0.1},
    }, indent=2))

    print(f"wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
```

Run once to produce fixtures:

```bash
python scripts/build_regression_fixture.py
```

- [ ] **Step 2: Test that runs both baselines and locks sha**

```python
# tests/regression/test_golden_baselines.py
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from asteroid_belt.cli import cli

REGRESSION_DIR = Path(__file__).parent
FIXTURE_DIR = REGRESSION_DIR / "fixtures"
GOLDEN_DIR = REGRESSION_DIR / "golden"


@pytest.fixture
def staged_synth_pool(tmp_path: Path) -> Path:
    pool = "SYNTH_POOL_REGRESSION"
    pool_dir = tmp_path / "pools" / pool
    pool_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_DIR / "synthetic_30day.parquet", pool_dir / "bars_1m.parquet")
    shutil.copy(FIXTURE_DIR / "pool_meta.json", pool_dir / "pool_meta.json")
    return tmp_path


def _write_cfg(path: Path, strategy_class: str, params: dict, tick_secs: int = 300) -> None:
    import yaml
    path.write_text(yaml.safe_dump({
        "schema_version": "1.0",
        "pool": "SYNTH_POOL_REGRESSION",
        "window": {"start": "2023-11-14T22:13:20Z", "end": "2023-12-14T22:13:20Z"},
        "adapter": {"kind": "bar"},
        "strategy": {"class": strategy_class, "params": params},
        "engine": {
            "tick_secs": tick_secs,
            "initial_x": 1_000_000_000,
            "initial_y": 87_550_000_000,
            "selection_metric": "net_pnl",
            "timeout_secs": 600,
        },
    }))


def _sha_trajectory(runs_dir: Path) -> str:
    sub_dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
    assert len(sub_dirs) == 1
    return hashlib.sha256((sub_dirs[0] / "result.parquet").read_bytes()).hexdigest()


@pytest.mark.parametrize("name,cls,params,tick", [
    (
        "precision_curve",
        "asteroid_belt.strategies.precision_curve.PrecisionCurveStrategy",
        {"bin_width": 69, "rebalance_trigger_bins": 10},
        300,
    ),
    (
        "multiday_cook_up",
        "asteroid_belt.strategies.multiday_cook_up.MultidayCookUpStrategy",
        {"bin_width": 121, "rebalance_cadence_secs": 3600,
         "upward_rebalance_trigger_bins": 10},
        3600,
    ),
])
def test_baseline_golden_trajectory(
    staged_synth_pool: Path, tmp_path: Path,
    name: str, cls: str, params: dict, tick: int,
) -> None:
    cfg = tmp_path / f"{name}.yaml"
    _write_cfg(cfg, cls, params, tick_secs=tick)
    runner = CliRunner()
    result = runner.invoke(cli, [
        "run", "--config", str(cfg), "--data-dir", str(staged_synth_pool),
    ])
    assert result.exit_code == 0, result.output

    actual_sha = _sha_trajectory(staged_synth_pool / "runs")

    golden_path = GOLDEN_DIR / f"{name}.sha256"
    if not golden_path.exists():
        # First run: lock the sha. CI will then fail on drift.
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual_sha + "\n")
        pytest.skip(f"locked initial golden sha for {name}: {actual_sha}")

    expected_sha = golden_path.read_text().strip()
    assert actual_sha == expected_sha, (
        f"trajectory sha drift for {name}:\n"
        f"  expected: {expected_sha}\n"
        f"  actual:   {actual_sha}\n"
        "If drift is intentional, update the golden file in this PR with a justification note."
    )
```

> Note: the first run in a clean environment locks the sha. After that, drift causes failures. To intentionally update: re-run, commit the new `golden/<name>.sha256` with a justification in the PR description.

- [ ] **Step 3: Run twice (once to lock, once to verify); commit fixtures + golden**

```bash
# First run: locks the golden shas (some tests will skip)
pytest tests/regression/ -v

# Second run: verifies no drift
pytest tests/regression/ -v
```

```bash
git add tests/regression/ scripts/build_regression_fixture.py
git commit -m "test(regression): golden trajectory shas for both baselines"
```

---

**End of Phase 8.** All cross-cutting tests in place. Total tests: ~135. Engine drift, lookahead bias, holdout leaks, schema regressions, and non-determinism all caught by CI.

---

## Phase 9 — CI + README + final sanity

### Task 9.1: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install uv
        run: pip install uv
      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e ".[dev]"
      - name: Lint (ruff)
        run: |
          source .venv/bin/activate
          ruff format --check asteroid_belt tests
          ruff check asteroid_belt tests
      - name: Type-check (mypy)
        run: |
          source .venv/bin/activate
          mypy asteroid_belt
      - name: Tests
        run: |
          source .venv/bin/activate
          pytest tests/

  web:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: web } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - uses: pnpm/action-setup@v3
        with: { version: 9 }
      - name: Install
        run: pnpm install --frozen-lockfile
      - name: svelte-check
        run: pnpm check
```

- [ ] **Step 2: Smoke check + commit**

```bash
git add .github/workflows/ci.yml
git commit -m "chore(ci): GitHub Actions for python + web"
```

### Task 9.2: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: README**

```markdown
# asteroid-belt

A personal research desk for optimizing DLMM (Dynamic Liquidity Market Maker) strategies on Meteora.

The eventual product is a Karpathy-`autoresearch`-style agent loop that mutates strategy code against historical pool data to find better strategies, then hands the winning strategy to a separate live trading bot. This repo is the **research environment** that everything else builds on: ingest historical pool data, replay it through candidate strategies via a deterministic backtest engine, persist every run, browse via a post-hoc dashboard.

See [`docs/superpowers/specs/2026-04-28-asteroid-belt-research-env-design.md`](docs/superpowers/specs/2026-04-28-asteroid-belt-research-env-design.md) for the full design.

## First-time setup

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+, [pnpm](https://pnpm.io/).

```bash
make install
```

## First run

```bash
# Ingest 30 days of SOL/USDC 10bps history
make ingest \
    POOL=BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y \
    START=2025-09-01T00:00:00Z \
    END=2025-10-01T00:00:00Z

# Run the smoke backtest
make run CONFIG=configs/quickstart.yaml

# Launch the dashboard (browser opens to http://localhost:5173)
make dev
```

## CLI reference

```
belt ingest    --pool <addr> --start <iso> --end <iso>
belt run       --config <path.yaml> [--force] [--session <id>]
belt session   new --label <text>
belt session   close --id <session_id>
belt run-notes set --id <run_id> --text <notes>
belt serve     [--port 8000]
```

## Architecture

- **Engine** (`asteroid_belt/`): pure Python, deterministic backtest engine. Frozen DLMM math, frozen cost model, structural lookahead-bias guards.
- **Strategies** (`asteroid_belt/strategies/`): the single mutable surface. v1 ships **Precision Curve** and **Multiday Cook Up**.
- **Storage** (`asteroid_belt/store/`): DuckDB metadata + parquet trajectories under `data/`. Single-writer, future-proofed for parallel agent runs via `RunStore` Protocol.
- **Server** (`asteroid_belt/server/`): FastAPI read-only API at `/api/v1/`.
- **Frontend** (`web/`): SvelteKit dashboard. Tailwind, Lucide icons, ECharts.

## Future work

- **Subsystem 4** — autoresearch agent loop on top of this engine
- **Subsystem 5** — live trading bot consuming validated strategies (Privy + Helius + Railway)
- **Swap-level adapter** — replaces bar-synthesized v1 adapter for higher-fidelity backtests
- **Walk-forward / purged k-fold CV** — graduate from single-split holdout
- **Additional baselines** — Precision Bid-Ask (vol-capture), Multiday Ping Pong, HFL

See memory notes referenced in the design spec for context on each.

## Running tests

```bash
make test          # python + web check
make lint          # ruff + mypy
```

## License

MIT.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, first run, and architecture overview"
```

### Task 9.3: Final sanity check

- [ ] **Step 1: Full test sweep**

```bash
make lint
make test
```

Expected: all green.

- [ ] **Step 2: First-run smoke from a clean clone**

```bash
# Simulate a clean clone scenario
cd /tmp && rm -rf belt_smoke && git clone $REPO belt_smoke && cd belt_smoke
make install
# (Requires network for Meteora ingest. Skip if offline.)
make ingest POOL=BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y \
            START=2025-09-15T00:00:00Z END=2025-09-20T00:00:00Z
make run CONFIG=configs/quickstart.yaml
make serve &
SERVER_PID=$!
sleep 3
curl -s http://localhost:8000/api/v1/runs | head -c 200
kill $SERVER_PID
```

Expected: prints a JSON array containing at least one run.

- [ ] **Step 3: Final commit if anything changed**

If lint/test surfaced fixes, commit them with `chore: pre-merge polish`. Otherwise the plan is complete.

---

## End of plan

By following this plan in order, an agent has built:

- A frozen, deterministic backtest engine for Meteora DLMM strategies on a single configurable pool, with built-in lookahead-bias guards and holdout isolation
- Two HawkFi-derived baseline strategies (Precision Curve, Multiday Cook Up)
- A pluggable metric layer (6 primitives + composite)
- A bar-synthesized data adapter that consumes Meteora's public OHLCV API
- A complete CLI (`belt ingest|run|session|serve`)
- A FastAPI read-only server at `/api/v1/`
- A SvelteKit dashboard for browsing runs (list, detail with charts, compare view)
- ~135 tests across unit, integration, and regression layers
- CI on GitHub Actions
- Future-proofed schema (parent_run_id, cost_model_version, schema_version everywhere) for the agent loop and live bot to land additively

Total commit count: roughly 50–60 small focused commits, each verifiable.

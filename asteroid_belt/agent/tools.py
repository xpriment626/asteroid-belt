"""Agent tools — execute candidate strategies, manage results history.

Strategies are arbitrary Python that defines `class MyStrategy(Strategy)`.
Code is exec'd in-process (per checkpoint decision: demo, not sandboxed).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import traceback
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl

import asteroid_belt.strategies.base as strategy_base
from asteroid_belt.data.adapters.bar import BarSynthesizedAdapter
from asteroid_belt.data.adapters.base import PoolKey, TimeWindow
from asteroid_belt.engine.runner import RunConfigParams, run_backtest
from asteroid_belt.pool.bins import price_to_bin_id
from asteroid_belt.pool.state import PoolState, StaticFeeParams, VolatilityState
from asteroid_belt.strategies.base import Strategy

_STRATEGIES_DIR = Path(__file__).resolve().parents[1] / "strategies"


@dataclass(frozen=True)
class PoolDataset:
    """A loaded pool dataset ready to feed the engine."""

    pool_key: PoolKey
    parquet_path: Path
    bin_step: int
    decimals_x: int
    decimals_y: int
    initial_price: Decimal


def load_pool_dataset(pool_dir: Path) -> PoolDataset:
    """Read pool_meta.json + bars_5m.parquet from a `data/pools/<addr>/` dir."""
    meta = json.loads((pool_dir / "pool_meta.json").read_text())
    bin_step = int(meta["pool_config"]["bin_step"])
    decimals_x = int(meta["token_x"]["decimals"])
    decimals_y = int(meta["token_y"]["decimals"])
    bars = pl.read_parquet(pool_dir / "bars_5m.parquet").sort("ts")
    initial_price = Decimal(str(bars["close"][0]))
    return PoolDataset(
        pool_key=PoolKey(address=meta["address"]),
        parquet_path=pool_dir / "bars_5m.parquet",
        bin_step=bin_step,
        decimals_x=decimals_x,
        decimals_y=decimals_y,
        initial_price=initial_price,
    )


def _initial_pool_state(dataset: PoolDataset) -> PoolState:
    """Build a PoolState pinned to the dataset's first bar."""
    return PoolState(
        active_bin=price_to_bin_id(dataset.initial_price, bin_step=dataset.bin_step),
        bin_step=dataset.bin_step,
        mid_price=dataset.initial_price,
        volatility=VolatilityState(0, 0, 0, 0),
        # base_factor=10000 + bin_step=10 -> 10 bps base fee
        # filter/decay periods + var_fee_control are pool-level constants;
        # values mirror the existing test fixture for 10bps SOL-USDC.
        static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
        bin_liquidity={},
        last_swap_ts=0,
        reward_infos=[],
    )


_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)\n```", re.DOTALL)


def extract_python(text: str) -> str:
    """Pull the first ```python ... ``` block from an LLM response.

    Falls back to the whole text if no fence is present (handles models that
    sometimes omit the fence).
    """
    m = _CODE_FENCE_RE.search(text)
    return m.group(1).strip() if m else text.strip()


@dataclass
class ExperimentResult:
    iteration: int
    timestamp: int
    strategy_code: str
    code_hash: str
    score: float
    score_metric: str
    primitives: dict[str, float]
    rebalance_count: int
    error: str | None
    trajectory: pl.DataFrame | None = None  # not in the JSON; persisted as parquet


def _exec_strategy_code(code: str) -> type[Strategy]:
    """Exec strategy code in a namespace seeded with strategies.base symbols.

    The namespace exposes the Strategy ABC and Action classes so the candidate
    code can `from asteroid_belt.strategies.base import ...` OR rely on
    pre-injected names.
    """
    import math as _math

    injected = {
        # Strategy ABC + actions
        "Strategy": strategy_base.Strategy,
        "Capital": strategy_base.Capital,
        "OpenPosition": strategy_base.OpenPosition,
        "AddLiquidity": strategy_base.AddLiquidity,
        "RemoveLiquidity": strategy_base.RemoveLiquidity,
        "Rebalance": strategy_base.Rebalance,
        "ClaimFees": strategy_base.ClaimFees,
        "ClosePosition": strategy_base.ClosePosition,
        "NoOp": strategy_base.NoOp,
        "BinRangeAdd": strategy_base.BinRangeAdd,
        "BinRangeRemoval": strategy_base.BinRangeRemoval,
        # Stdlib helpers strategies commonly need
        "Decimal": Decimal,  # pool.mid_price is a Decimal — strategies often compute against it
        "math": _math,
    }
    namespace: dict[str, Any] = {"__builtins__": __builtins__, **injected}
    exec(code, namespace)
    cls = namespace.get("MyStrategy")
    if cls is None or not isinstance(cls, type) or not issubclass(cls, Strategy):
        raise ValueError("Candidate code must define `class MyStrategy(Strategy)`.")
    return cls  # type: ignore[no-any-return]


def run_candidate(
    *,
    strategy_code: str,
    dataset: PoolDataset,
    window: TimeWindow,
    initial_x: int,
    initial_y: int,
    selection_metric: str,
    iteration: int,
) -> ExperimentResult:
    """Compile + run one candidate strategy. Catches exceptions and records them."""
    code_hash = hashlib.sha256(strategy_code.encode()).hexdigest()[:12]
    try:
        cls = _exec_strategy_code(strategy_code)
        strategy = cls()
        adapter = BarSynthesizedAdapter(
            parquet_path=dataset.parquet_path,
            pool=dataset.pool_key,
            bin_step=dataset.bin_step,
        )
        result = run_backtest(
            strategy=strategy,
            adapter=adapter,
            initial_pool_state=PoolState(
                active_bin=_initial_pool_state(dataset).active_bin,
                bin_step=dataset.bin_step,
                mid_price=dataset.initial_price,
                volatility=VolatilityState(0, 0, 0, 0),
                static_fee=StaticFeeParams(10000, 30, 600, 5000, 40000, 500, 350000),
                bin_liquidity={},
                last_swap_ts=0,
                reward_infos=[],
            ),
            config=RunConfigParams(
                run_id=f"agent_iter_{iteration}",
                config_hash=code_hash,
                window=window,
                tick_secs=300,
                initial_x=initial_x,
                initial_y=initial_y,
                decimals_x=dataset.decimals_x,
                decimals_y=dataset.decimals_y,
                priority_fee_lamports=10_000,
                selection_metric=selection_metric,
            ),
        )
        return ExperimentResult(
            iteration=iteration,
            timestamp=int(time.time() * 1000),
            strategy_code=strategy_code,
            code_hash=code_hash,
            score=result.score,
            score_metric=result.score_metric,
            primitives=dict(result.primitives),
            rebalance_count=len(result.rebalances),
            error=None,
            trajectory=result.trajectory,
        )
    except Exception as exc:
        return ExperimentResult(
            iteration=iteration,
            timestamp=int(time.time() * 1000),
            strategy_code=strategy_code,
            code_hash=code_hash,
            score=float("-inf"),
            score_metric=selection_metric,
            primitives={},
            rebalance_count=0,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}",
        )


def history_summary(history: list[dict[str, Any]], *, top_n: int = 5) -> str:
    """Compact text summary of best + most recent experiments for the prompt."""
    if not history:
        return "(no prior experiments — this is iteration 0)"
    valid = [h for h in history if h.get("error") is None]
    if not valid:
        return "All prior experiments errored. Try a simpler approach."
    by_score = sorted(valid, key=lambda h: h.get("score", float("-inf")), reverse=True)
    top = by_score[:top_n]
    recent = sorted(history, key=lambda h: int(h.get("iteration", 0)), reverse=True)[:top_n]
    lines: list[str] = ["TOP RESULTS BY SCORE:"]
    for h in top:
        prims = h.get("primitives", {})
        lines.append(
            f"  iter {h['iteration']:>3} score={h['score']:.4f} "
            f"net_fee_yield={prims.get('net_fee_yield', 0.0):.4f} "
            f"calmar={prims.get('calmar', 0.0):.4f} "
            f"sharpe={prims.get('sharpe', 0.0):.4f} "
            f"rebalances={h.get('rebalance_count', 0)}"
        )
    lines.append("\nMOST RECENT EXPERIMENTS:")
    for h in recent:
        err = h.get("error")
        if err:
            short = err.split("\n")[0][:100]
            lines.append(f"  iter {h['iteration']:>3} ERROR: {short}")
        else:
            lines.append(f"  iter {h['iteration']:>3} score={h['score']:.4f}")
    return "\n".join(lines)


def read_strategy(name: str) -> str:
    """Read a worked-example strategy file (precision_curve, multiday_cook_up)."""
    path = _STRATEGIES_DIR / f"{name}.py"
    return path.read_text()


def data_summary(dataset: PoolDataset, window: TimeWindow) -> str:
    """One-paragraph human summary for the agent prompt."""
    df = (
        pl.read_parquet(dataset.parquet_path)
        .filter((pl.col("ts") >= window.start_ms) & (pl.col("ts") < window.end_ms))
        .sort("ts")
    )
    if df.is_empty():
        return "(empty window)"
    first_price = float(df["close"][0])
    last_price = float(df["close"][-1])
    high = float(df["high"].max())  # type: ignore[arg-type]
    low = float(df["low"].min())  # type: ignore[arg-type]
    span_hours = (df["ts"][-1] - df["ts"][0]) / (1000 * 60 * 60)
    return (
        f"Pool {dataset.pool_key.address}, bin_step={dataset.bin_step}, "
        f"decimals=({dataset.decimals_x},{dataset.decimals_y}). "
        f"Window: {df.height} bars over {span_hours:.1f}h. "
        f"Price: open={first_price:.4f} close={last_price:.4f} "
        f"range=[{low:.4f}, {high:.4f}] drift={(last_price / first_price - 1) * 100:.2f}%"
    )

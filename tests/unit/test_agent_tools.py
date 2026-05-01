"""Pure-function tests for asteroid_belt.agent.tools."""

from __future__ import annotations

from asteroid_belt.agent.tools import extract_python, history_summary


def test_extract_python_pulls_fenced_block() -> None:
    text = "Sure, here is the strategy:\n\n```python\nclass MyStrategy(Strategy): pass\n```\n"
    assert extract_python(text) == "class MyStrategy(Strategy): pass"


def test_extract_python_handles_bare_python_fence_without_language() -> None:
    text = "```\nclass MyStrategy(Strategy): pass\n```"
    assert extract_python(text) == "class MyStrategy(Strategy): pass"


def test_extract_python_falls_back_to_full_text_when_no_fence() -> None:
    text = "class MyStrategy(Strategy): pass"
    assert extract_python(text) == "class MyStrategy(Strategy): pass"


def test_history_summary_empty() -> None:
    assert "no prior" in history_summary([]).lower()


def test_history_summary_all_errored() -> None:
    history = [
        {"iteration": 0, "score": float("-inf"), "error": "syntax", "primitives": {}},
    ]
    out = history_summary(history)
    assert "errored" in out.lower()


def test_history_summary_ranks_top_by_score() -> None:
    history = [
        {
            "iteration": 0,
            "score": 1.0,
            "error": None,
            "primitives": {"net_fee_yield": 0.5, "calmar": 0.1, "sharpe": 0.0},
            "rebalance_count": 1,
        },
        {
            "iteration": 1,
            "score": 5.0,
            "error": None,
            "primitives": {"net_fee_yield": 2.0, "calmar": 1.0, "sharpe": 0.0},
            "rebalance_count": 3,
        },
        {
            "iteration": 2,
            "score": 2.0,
            "error": None,
            "primitives": {"net_fee_yield": 1.0, "calmar": 0.5, "sharpe": 0.0},
            "rebalance_count": 2,
        },
    ]
    out = history_summary(history, top_n=2)
    # Top section lists iter 1 (best) before iter 2.
    top_idx = out.index("TOP RESULTS")
    recent_idx = out.index("MOST RECENT")
    top_block = out[top_idx:recent_idx]
    assert top_block.index("iter   1") < top_block.index("iter   2")

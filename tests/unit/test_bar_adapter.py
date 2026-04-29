from pathlib import Path

import polars as pl
import pytest

from asteroid_belt.data.adapters.bar import BarSynthesizedAdapter
from asteroid_belt.data.adapters.base import PoolKey, TimeWindow


@pytest.fixture
def tiny_bars_parquet(tmp_path: Path) -> Path:
    """4 minutes of bars: 2 going up, 2 going down."""
    df = pl.DataFrame(
        {
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
        }
    )
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
        parquet_path=tiny_bars_parquet,
        pool=PoolKey(address="test_pool"),
        bin_step=10,
    )
    events = list(adapter.stream(TimeWindow(start_ms=0, end_ms=10**13)))
    # Bar 0: 87.50 -> 87.55 (up). Y->X swap pushes price up.
    assert events[0].swap_for_y is False


def test_dominant_side_when_price_falls(tiny_bars_parquet: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=tiny_bars_parquet,
        pool=PoolKey(address="test_pool"),
        bin_step=10,
    )
    events = list(adapter.stream(TimeWindow(start_ms=0, end_ms=10**13)))
    # Bar 2: 87.60 -> 87.55 (down). X->Y swap pushes price down.
    assert events[2].swap_for_y is True


def test_window_filter_excludes_outside_bars(tiny_bars_parquet: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=tiny_bars_parquet,
        pool=PoolKey(address="test_pool"),
        bin_step=10,
    )
    # Window covers only bars 1 and 2 (ts 60_000 and 120_000)
    win = TimeWindow(start_ms=1_700_000_060_000, end_ms=1_700_000_180_000)
    events = list(adapter.stream(win))
    assert len(events) == 2


def test_window_end_is_exclusive(tiny_bars_parquet: Path) -> None:
    adapter = BarSynthesizedAdapter(
        parquet_path=tiny_bars_parquet,
        pool=PoolKey(address="test_pool"),
        bin_step=10,
    )
    # Window end matches bar 3's ts exactly -> excluded
    win = TimeWindow(start_ms=0, end_ms=1_700_000_180_000)
    events = list(adapter.stream(win))
    assert len(events) == 3

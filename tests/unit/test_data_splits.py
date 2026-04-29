from datetime import UTC, datetime

import pytest

from asteroid_belt.data.adapters.base import TimeWindow
from asteroid_belt.data.splits import (
    HOLDOUT_BOUNDARY_DEFAULT,
    holdout_window,
    train_window,
    validate_window_within_train,
)


def _ms(dt: str) -> int:
    return int(datetime.fromisoformat(dt).replace(tzinfo=UTC).timestamp() * 1000)


def test_train_window_default() -> None:
    w = train_window(start="2024-05-01T00:00:00Z", boundary=HOLDOUT_BOUNDARY_DEFAULT)
    assert w.start_ms == _ms("2024-05-01T00:00:00")
    assert w.end_ms == _ms(HOLDOUT_BOUNDARY_DEFAULT.replace("Z", ""))


def test_holdout_window_default() -> None:
    w = holdout_window(end="2026-04-29T00:00:00Z", boundary=HOLDOUT_BOUNDARY_DEFAULT)
    assert w.start_ms == _ms(HOLDOUT_BOUNDARY_DEFAULT.replace("Z", ""))
    assert w.end_ms == _ms("2026-04-29T00:00:00")


def test_validate_within_train_passes() -> None:
    w = TimeWindow(start_ms=_ms("2024-05-01T00:00:00"), end_ms=_ms("2025-10-01T00:00:00"))
    validate_window_within_train(w, boundary=HOLDOUT_BOUNDARY_DEFAULT)  # no exception


def test_validate_window_crosses_boundary_raises() -> None:
    w = TimeWindow(start_ms=_ms("2024-05-01T00:00:00"), end_ms=_ms("2025-12-01T00:00:00"))
    with pytest.raises(ValueError, match="crosses holdout boundary"):
        validate_window_within_train(w, boundary=HOLDOUT_BOUNDARY_DEFAULT)

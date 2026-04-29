"""Train/holdout window helpers and the sealed-holdout invariant.

The holdout boundary is a single timestamp before which all data is "train"
(visible to agent runs) and after which all data is "holdout" (only the
evaluator process touches it). v1 default is Oct 31 2025 00:00 UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

from asteroid_belt.data.adapters.base import TimeWindow

HOLDOUT_BOUNDARY_DEFAULT = "2025-10-31T00:00:00Z"


def _to_ms(iso: str) -> int:
    """Parse ISO-8601 string (with optional 'Z') to ms-since-epoch."""
    s = iso.replace("Z", "+00:00")
    return int(datetime.fromisoformat(s).astimezone(UTC).timestamp() * 1000)


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

"""Bin id <-> price math and multi-bin swap walks.

Uses Decimal for round-trip stability across the bin_id range we care about
(+/- 50000 covers any real-world DLMM pool active range). Avoids float drift.

Reference: Trader Joe LB whitepaper, Meteora /dlmm-formulas docs.
  price(bin_id) = (1 + bin_step / 10_000) ** bin_id
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal, getcontext

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


def walk_bins_for_swap(*, start_bin: int, end_bin: int, swap_for_y: bool) -> Iterator[int]:
    """Yield each bin a swap traverses, inclusive of start and end.

    For swap_for_y=True (X -> Y), the active bin DECREASES (price drops).
    For swap_for_y=False (Y -> X), the active bin INCREASES (price rises).
    """
    if swap_for_y:
        # X -> Y: active bin descends
        if end_bin > start_bin:
            raise ValueError("swap_for_y=True requires end_bin <= start_bin")
        step = -1
    else:
        if end_bin < start_bin:
            raise ValueError("swap_for_y=False requires end_bin >= start_bin")
        step = 1
    current = start_bin
    while True:
        yield current
        if current == end_bin:
            return
        current += step

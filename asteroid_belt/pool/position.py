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
    del decimals_y  # not used directly here; receiver multiplies by price
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
    """Impermanent loss = position_value - hodl_value (in Y units).

    Negative values mean the LP position is underperforming HODL.
    """
    pos = position_value_in_y(
        composition=composition,
        price=price,
        decimals_x=decimals_x,
        decimals_y=decimals_y,
    )
    hodl = hodl_value_in_y(
        initial_x=initial_x,
        initial_y=initial_y,
        price=price,
        decimals_x=decimals_x,
        decimals_y=decimals_y,
    )
    return pos - hodl

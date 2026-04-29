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
    v = hodl_value_in_y(
        initial_x=1_000_000_000,
        initial_y=100_000_000,
        price=Decimal("87.55"),
        decimals_x=9,
        decimals_y=6,
    )
    assert v == Decimal("187.55")


def test_position_value_in_range() -> None:
    # Position has 0.5 SOL and 50 USDC distributed in bins
    composition = {
        100: BinComposition(amount_x=300_000_000, amount_y=30_000_000, liquidity_share=0.01),
        101: BinComposition(amount_x=200_000_000, amount_y=20_000_000, liquidity_share=0.01),
    }
    v = position_value_in_y(
        composition=composition,
        price=Decimal("87.55"),
        decimals_x=9,
        decimals_y=6,
    )
    # 0.5 SOL * 87.55 + 50 USDC = 43.775 + 50 = 93.775
    assert v == Decimal("93.775")


def test_il_zero_when_position_matches_hodl() -> None:
    composition = {
        0: BinComposition(amount_x=1_000_000_000, amount_y=100_000_000, liquidity_share=0.01),
    }
    il = il_vs_hodl(
        composition=composition,
        initial_x=1_000_000_000,
        initial_y=100_000_000,
        price=Decimal("87.55"),
        decimals_x=9,
        decimals_y=6,
    )
    assert il == Decimal("0")


def test_il_negative_when_underperforming() -> None:
    # Started 1 SOL + 100 USDC; now 0 SOL + 87.55 USDC (price unchanged but lost SOL).
    composition = {
        0: BinComposition(amount_x=0, amount_y=87_550_000, liquidity_share=0.01),
    }
    il = il_vs_hodl(
        composition=composition,
        initial_x=1_000_000_000,
        initial_y=100_000_000,
        price=Decimal("87.55"),
        decimals_x=9,
        decimals_y=6,
    )
    # Position = 87.55, HODL = 187.55, IL = -100
    assert il == Decimal("-100")

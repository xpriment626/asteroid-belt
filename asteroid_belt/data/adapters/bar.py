"""Bar-synthesized adapter.

Loads 1m OHLCV+volume bars from parquet and synthesizes one SwapEvent per bar
at the bar's close price on the dominant side. Documented biases (per spec
§5.3):

- Variable fee understated during high-volatility minutes (single synthetic
  event per bar can't represent intra-minute swap clustering).
- Bin-traversal granularity lost for multi-bin moves within a bar.
- <=1440 events per backtest day -> fast iteration.

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
        df = (
            pl.read_parquet(self._parquet_path)
            .filter((pl.col("ts") >= window.start_ms) & (pl.col("ts") < window.end_ms))
            .sort("ts")
        )

        for i, row in enumerate(df.iter_rows(named=True)):
            open_p = Decimal(str(row["open"]))
            close_p = Decimal(str(row["close"]))
            volume_x = int(row["volume_x"])
            volume_y = int(row["volume_y"])

            # Dominant side: True (X->Y) if price drops, else False (Y->X)
            swap_for_y = close_p < open_p

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
            base_fee_bps_default = self._bin_step  # base_factor=10000 -> bps == bin_step
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
)

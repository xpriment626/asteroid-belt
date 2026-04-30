<script lang="ts">
  import PriceChart from '$lib/components/PriceChart.svelte';
  import type { PageData } from './$types';

  export let data: PageData;

  // v0 sealed holdout: last 7 days (Apr 24 - Apr 30 2026). Train+walk-forward
  // eval covers Dec 1 2025 - Apr 23 2026. Original 18mo/6mo split deferred to
  // v1 once paid data source unlocks pre-Aug 2025 history.
  const HOLDOUT_START_MS = Date.UTC(2026, 3, 24); // month 0-indexed: 3 = Apr
</script>

<header class="mb-4">
  <h2 class="font-mono text-lg">{data.detail.address}</h2>
  <div class="mt-1 flex gap-4 text-xs text-fg-muted">
    <span>{data.detail.name ?? '—'}</span>
    <span>bin_step {data.detail.bin_step ?? '?'} bps</span>
    <span>{data.detail.bars_count.toLocaleString()} bars</span>
  </div>
</header>

<div class="mb-4 flex gap-2 text-xs">
  <span class="rounded bg-bg-muted px-2 py-1">
    Train + walk-forward: Dec 2025 → Apr 23 2026
  </span>
  <span class="rounded border border-fg-dim px-2 py-1 text-fg-muted">
    Holdout: Apr 24 → Apr 30 2026 (sealed, 1wk)
  </span>
</div>

<PriceChart bars={data.bars} holdoutStartMs={HOLDOUT_START_MS} />

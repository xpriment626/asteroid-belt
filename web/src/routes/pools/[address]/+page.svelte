<script lang="ts">
  import PriceChart from '$lib/components/PriceChart.svelte';
  import type { PageData } from './$types';

  export let data: PageData;

  // Holdout boundary: Nov 1 2025 UTC (per spec / data.splits.HOLDOUT_BOUNDARY_DEFAULT).
  // TODO: read from API once /pools/:addr/detail returns the configured boundary.
  const HOLDOUT_START_MS = Date.UTC(2025, 10, 1); // month is 0-indexed: 10 = Nov
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
    Train: May 2024 → Oct 2025
  </span>
  <span class="rounded border border-fg-dim px-2 py-1 text-fg-muted">
    Holdout: Nov 2025 → Apr 2026 (sealed)
  </span>
</div>

<PriceChart bars={data.bars} holdoutStartMs={HOLDOUT_START_MS} />

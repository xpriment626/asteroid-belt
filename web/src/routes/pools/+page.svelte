<script lang="ts">
  import { api, type PoolSummary } from '$lib/api/client';
  import { onMount } from 'svelte';

  let pools: PoolSummary[] = [];
  let loading = true;
  let error: string | null = null;

  onMount(async () => {
    try {
      pools = await api<PoolSummary[]>('/pools');
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });
</script>

<h2 class="mb-4 text-xl font-bold">Pools</h2>
{#if loading}
  <p class="text-fg-muted">Loading...</p>
{:else if error}
  <p class="text-red-400">Error: {error}</p>
{:else if pools.length === 0}
  <p class="text-fg-muted">No pools ingested yet. Run <code>make ingest POOL=... START=... END=...</code>.</p>
{:else}
  <ul class="space-y-2">
    {#each pools as pool}
      <li>
        <a href="/pools/{pool.address}"
           class="block rounded border border-bg-muted bg-bg-surface p-3 hover:border-accent">
          <div class="font-mono text-sm">{pool.address}</div>
          <div class="mt-1 text-xs text-fg-muted">
            {pool.name ?? '—'} · bin_step {pool.bin_step ?? '?'} · {pool.bars_count.toLocaleString()} bars
          </div>
        </a>
      </li>
    {/each}
  </ul>
{/if}

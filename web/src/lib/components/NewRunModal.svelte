<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, apiPost, type PoolSummary, type RunStatus } from '$lib/api/client';
  import { X, Play } from 'lucide-svelte';

  const dispatch = createEventDispatcher();

  let pools: PoolSummary[] = [];
  let pool = '';
  let trial = '';
  let budget = 5;
  let objective = 'vol_capture';
  let status: RunStatus | null = null;
  let err: string | null = null;
  let pollInterval: ReturnType<typeof setInterval> | null = null;

  const objectives = [
    'vol_capture',
    'info_ratio_vs_hodl',
    'net_fee_yield',
    'sharpe',
    'calmar',
  ];

  api<PoolSummary[]>('/pools').then((p) => {
    pools = p;
    if (pools.length > 0 && !pool) pool = pools[0].address;
  }).catch((e) => (err = String(e)));

  function defaultTrialName(): string {
    const d = new Date();
    return `run_${d.toISOString().slice(0, 10).replace(/-/g, '')}_${d.getHours()}${String(d.getMinutes()).padStart(2, '0')}`;
  }

  if (!trial) trial = defaultTrialName();

  async function start() {
    err = null;
    if (!pool || !trial) {
      err = 'pool and trial are required';
      return;
    }
    try {
      status = await apiPost<RunStatus>('/runs/start', { pool, trial, budget, objective });
      pollInterval = setInterval(poll, 2000);
    } catch (e) {
      err = String(e);
    }
  }

  async function poll() {
    if (!status) return;
    try {
      const next = await api<RunStatus>(`/runs/${status.run_id}`);
      status = next;
      if (next.state === 'done' || next.state === 'failed') {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = null;
        if (next.state === 'done') {
          await goto(`/trials/${next.trial}`);
          dispatch('close');
        }
      }
    } catch (e) {
      err = String(e);
    }
  }

  function close() {
    if (pollInterval) clearInterval(pollInterval);
    dispatch('close');
  }

  onDestroy(() => {
    if (pollInterval) clearInterval(pollInterval);
  });
</script>

<div
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
  role="presentation"
  on:click|self={close}
  on:keydown={(e) => e.key === 'Escape' && close()}
>
  <div class="w-full max-w-md rounded-lg border border-bg-muted bg-bg-surface p-5"
       role="dialog" aria-modal="true">
    <header class="mb-4 flex items-center justify-between">
      <h3 class="font-medium">Start new tournament run</h3>
      <button on:click={close} class="text-fg-muted hover:text-fg"><X size={16} /></button>
    </header>

    {#if status === null}
      <div class="space-y-3 text-sm">
        <label class="block">
          <span class="text-xs text-fg-muted">Pool</span>
          <select bind:value={pool} class="mt-1 w-full rounded border border-bg-muted bg-bg px-2 py-1.5 text-sm">
            {#each pools as p}
              <option value={p.address}>{p.name ?? p.address.slice(0, 8)} ({p.bars_count} bars)</option>
            {/each}
          </select>
        </label>

        <label class="block">
          <span class="text-xs text-fg-muted">Trial name</span>
          <input
            type="text"
            bind:value={trial}
            class="mt-1 w-full rounded border border-bg-muted bg-bg px-2 py-1.5 font-mono text-sm"
          />
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-xs text-fg-muted">Budget (iterations)</span>
            <input type="number" min="1" max="100" bind:value={budget}
              class="mt-1 w-full rounded border border-bg-muted bg-bg px-2 py-1.5 text-sm" />
          </label>

          <label class="block">
            <span class="text-xs text-fg-muted">Objective</span>
            <select bind:value={objective}
              class="mt-1 w-full rounded border border-bg-muted bg-bg px-2 py-1.5 text-sm">
              {#each objectives as o}
                <option value={o}>{o}</option>
              {/each}
            </select>
          </label>
        </div>

        {#if err}
          <p class="rounded border border-rose-500/40 bg-rose-500/5 p-2 text-xs text-rose-300">{err}</p>
        {/if}

        <div class="mt-4 flex justify-end gap-2">
          <button on:click={close} class="rounded px-3 py-1.5 text-xs text-fg-muted hover:text-fg">
            Cancel
          </button>
          <button on:click={start}
            class="flex items-center gap-1.5 rounded bg-accent px-3 py-1.5 text-xs font-medium text-bg hover:bg-accent/90">
            <Play size={12} /> Start
          </button>
        </div>

        <p class="mt-2 text-xs text-fg-dim">
          A run with budget {budget} costs roughly ${(0.024 * budget).toFixed(2)} on DeepSeek V4 Pro.
          Each iteration takes ~3–4 minutes.
        </p>
      </div>
    {:else}
      <div class="space-y-3 text-sm">
        <div class="rounded border border-bg-muted p-3">
          <div class="text-xs text-fg-muted">Run id</div>
          <div class="font-mono text-xs">{status.run_id}</div>
          <div class="mt-2 text-xs text-fg-muted">State</div>
          <div class={status.state === 'failed' ? 'text-rose-400' : status.state === 'done' ? 'text-emerald-400' : 'text-amber-400'}>
            {status.state}
          </div>
          <div class="mt-2 text-xs text-fg-muted">Progress</div>
          <div class="font-mono text-xs">{status.iterations_completed} / {status.budget}</div>
          <div class="mt-2 h-1 w-full overflow-hidden rounded bg-bg-muted">
            <div class="h-full bg-accent transition-all" style="width: {Math.min(100, (status.iterations_completed / status.budget) * 100)}%"></div>
          </div>
          {#if status.error}
            <pre class="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-xs text-rose-300">{status.error}</pre>
          {/if}
        </div>
        <p class="text-xs text-fg-dim">
          You can close this dialog — the run will keep going. Visit <code>/trials/{status.trial}</code>
          to watch progress.
        </p>
        <div class="flex justify-end">
          <button on:click={close} class="rounded px-3 py-1.5 text-xs text-fg-muted hover:text-fg">
            Close
          </button>
        </div>
      </div>
    {/if}
  </div>
</div>

<script lang="ts">
  import { api, type IterationDetail, type IterationSummary, type TrajectoryRow } from '$lib/api/client';
  import EquityChart from '$lib/components/EquityChart.svelte';
  import IterationLeaderboard from '$lib/components/IterationLeaderboard.svelte';
  import DeployModal from '$lib/components/DeployModal.svelte';
  import { ArrowLeft, AlertTriangle, Trophy, Rocket } from 'lucide-svelte';
  import type { PageData } from './$types';

  export let data: PageData;

  // Selection: default to best iteration, or iteration 0 if none.
  let selectedIter: number =
    data.trial.best_iteration ?? data.trial.iterations[0]?.iteration ?? 0;

  let detail: IterationDetail | null = null;
  let trajectory: TrajectoryRow[] = [];
  let detailErr: string | null = null;
  let showDeploy = false;

  async function loadIter(n: number) {
    detail = null;
    trajectory = [];
    detailErr = null;
    try {
      detail = await api<IterationDetail>(`/trials/${data.trial.trial}/iterations/${n}`);
      if (detail.has_trajectory) {
        trajectory = await api<TrajectoryRow[]>(
          `/trials/${data.trial.trial}/iterations/${n}/trajectory`,
        );
      }
    } catch (e) {
      detailErr = String(e);
    }
  }

  $: if (selectedIter !== undefined) loadIter(selectedIter);

  function classifyIter(it: IterationSummary): 'error' | 'degenerate' | 'ok' {
    if (it.error) return 'error';
    if ((it.score ?? 0) === 0) return 'degenerate';
    return 'ok';
  }
</script>

<header class="mb-4">
  <a href="/trials" class="mb-3 inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg">
    <ArrowLeft size={12} /> Back to runs
  </a>
  <h2 class="font-mono text-lg">{data.trial.trial}</h2>
  <div class="mt-1 flex flex-wrap gap-3 text-xs text-fg-muted">
    <span>{data.trial.iteration_count} iterations</span>
    <span class="text-emerald-400">
      {data.trial.success_count - data.trial.degenerate_count} ok
    </span>
    {#if data.trial.degenerate_count > 0}
      <span>{data.trial.degenerate_count} degenerate</span>
    {/if}
    {#if data.trial.error_count > 0}
      <span class="text-rose-400">{data.trial.error_count} errors</span>
    {/if}
    {#if data.trial.best_score !== null}
      <span class="flex items-center gap-1 text-amber-400">
        <Trophy size={12} /> best {data.trial.best_score.toFixed(2)}
        ({data.trial.score_metric}) @ iter {data.trial.best_iteration}
      </span>
    {/if}
  </div>
</header>

<div class="mb-4 rounded border border-bg-muted p-3">
  <h3 class="mb-2 text-xs font-medium text-fg-muted">Leaderboard / iteration timeline</h3>
  <IterationLeaderboard
    iterations={data.trial.iterations}
    selected={selectedIter}
    on:select={(e) => (selectedIter = e.detail)}
  />
</div>

{#if detailErr}
  <div class="rounded border border-rose-500/40 bg-rose-500/5 p-3 text-xs text-rose-300">
    Failed to load iteration: {detailErr}
  </div>
{:else if detail === null}
  <p class="text-xs text-fg-muted">Loading iteration {selectedIter}…</p>
{:else}
  <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
    <div class="rounded border border-bg-muted p-3">
      <div class="mb-2 flex items-center justify-between">
        <h3 class="text-xs font-medium text-fg-muted">
          Iteration {detail.iteration}
          {#if classifyIter(detail) === 'error'}
            <span class="ml-2 inline-flex items-center gap-1 rounded bg-rose-500/15 px-1.5 py-0.5 text-rose-300">
              <AlertTriangle size={10} /> errored
            </span>
          {:else if classifyIter(detail) === 'degenerate'}
            <span class="ml-2 inline-flex items-center rounded bg-bg-muted px-1.5 py-0.5">
              degenerate (score = 0)
            </span>
          {:else}
            <span class="ml-2 inline-flex items-center rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-300">
              ok
            </span>
          {/if}
        </h3>
        <div class="text-xs font-mono text-fg-muted">
          score: {detail.score !== null ? detail.score.toFixed(4) : '—'}
        </div>
      </div>

      {#if Object.keys(detail.primitives).length > 0}
        <div class="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {#each Object.entries(detail.primitives).sort() as [k, v]}
            <div class="flex justify-between border-b border-bg-muted/40 py-0.5">
              <span class="text-fg-muted">{k}</span>
              <span class="font-mono">{v.toFixed(4)}</span>
            </div>
          {/each}
        </div>
      {/if}

      {#if detail.error}
        <div class="mb-3 rounded border border-rose-500/30 bg-rose-500/5 p-2">
          <div class="mb-1 text-xs font-medium text-rose-300">Traceback</div>
          <pre class="overflow-x-auto whitespace-pre-wrap break-all text-xs text-rose-200/80">{detail.error}</pre>
        </div>
      {:else}
        <button
          on:click={() => (showDeploy = true)}
          class="mb-3 flex items-center gap-1.5 rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20"
        >
          <Rocket size={12} /> Deploy live (devnet)
        </button>
      {/if}

      <details class="text-xs" open={detail.error === null}>
        <summary class="cursor-pointer text-fg-muted hover:text-fg">
          Strategy code ({detail.strategy_code.split('\n').length} lines)
        </summary>
        <pre class="mt-2 max-h-96 overflow-auto rounded bg-bg p-2 font-mono text-[11px] leading-relaxed">{detail.strategy_code}</pre>
      </details>
    </div>

    <div class="rounded border border-bg-muted p-3">
      <h3 class="mb-2 text-xs font-medium text-fg-muted">
        Trajectory
        {#if !detail.has_trajectory}
          <span class="ml-2 text-fg-dim">(not available — iteration errored or pre-regen)</span>
        {/if}
      </h3>
      {#if trajectory.length > 0}
        <EquityChart rows={trajectory} />
      {:else if detail.has_trajectory}
        <p class="text-xs text-fg-muted">Loading trajectory…</p>
      {:else}
        <p class="text-xs text-fg-dim">
          No trajectory was produced. Errored iterations never reach the engine; pre-regen iterations
          can be repopulated with <code class="font-mono">belt agent-regen</code>.
        </p>
      {/if}
    </div>
  </div>
{/if}

{#if showDeploy && detail !== null}
  <DeployModal
    trial={data.trial.trial}
    iteration={detail.iteration}
    strategySummary={`score ${detail.score?.toFixed(2) ?? '—'} (${detail.score_metric})`}
    on:close={() => (showDeploy = false)}
  />
{/if}

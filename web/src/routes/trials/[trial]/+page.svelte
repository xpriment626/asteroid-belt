<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { invalidateAll } from '$app/navigation';
  import { api, type IterationDetail, type IterationSummary, type TrajectoryRow, type TrialDetail } from '$lib/api/client';
  import EquityChart from '$lib/components/EquityChart.svelte';
  import IterationLeaderboard from '$lib/components/IterationLeaderboard.svelte';
  import DeployModal from '$lib/components/DeployModal.svelte';
  import { ArrowLeft, AlertTriangle, Trophy, Rocket } from 'lucide-svelte';
  import type { PageData } from './$types';

  export let data: PageData;

  // Trial may have zero iterations if the user just clicked Start and the
  // first iter hasn't landed yet. Pick a sentinel and skip auto-load in that
  // case so we don't 404.
  let selectedIter: number | null =
    data.trial.best_iteration ?? data.trial.iterations[0]?.iteration ?? null;

  let detail: IterationDetail | null = null;
  let trajectory: TrajectoryRow[] = [];
  let detailErr: string | null = null;
  let showDeploy = false;

  // Auto-refresh: poll the trial summary; when iteration_count grows,
  // invalidate so the load function re-fetches the leaderboard. Stops
  // once iteration_count >= budget so completed trials don't churn the
  // network forever. If budget is null (migrated trial / no session
  // goal_json), polls for the lifetime of the page — browsers throttle
  // setInterval when the tab is hidden.
  const POLL_MS = 5000;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let lastIterCount = data.trial.iteration_count;

  function trialIsComplete(t: TrialDetail): boolean {
    return t.budget !== null && t.iteration_count >= t.budget;
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function checkForNewIterations() {
    try {
      const fresh = await api<TrialDetail>(`/trials/${data.trial.trial}`);
      if (fresh.iteration_count > lastIterCount) {
        lastIterCount = fresh.iteration_count;
        await invalidateAll();
      }
      if (trialIsComplete(fresh)) stopPolling();
    } catch {
      // Transient network errors shouldn't kill the watcher.
    }
  }

  onMount(() => {
    // Skip polling entirely if the trial is already complete on first load.
    if (!trialIsComplete(data.trial)) {
      pollTimer = setInterval(checkForNewIterations, POLL_MS);
    }
  });

  onDestroy(stopPolling);

  // If the trial transitioned from pending (0 iters) to having iterations,
  // pick a default selection so the detail panel populates without a click.
  $: if (selectedIter === null && data.trial.iterations.length > 0) {
    selectedIter = data.trial.best_iteration ?? data.trial.iterations[0].iteration;
  }
  // Keep the stagnant-counter baseline in sync after invalidateAll re-runs load.
  $: if (data.trial.iteration_count > lastIterCount) {
    lastIterCount = data.trial.iteration_count;
  }

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

  $: if (selectedIter !== null) loadIter(selectedIter);

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
    selected={selectedIter ?? 0}
    on:select={(e) => (selectedIter = e.detail)}
  />
</div>

{#if data.trial.iterations.length === 0}
  <div class="rounded border border-bg-muted bg-bg-muted/20 p-6 text-center">
    <p class="text-sm text-fg-muted">Trial pending — first iteration hasn't landed yet.</p>
    <p class="mt-2 text-xs text-fg-dim">
      Refresh the page in a minute or two; iterations will appear in the leaderboard above as they
      complete. Each iteration takes ~30–60s on DeepSeek V4.
    </p>
  </div>
{:else if detailErr}
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

<script lang="ts">
  import { Plus, Beaker, Trash2 } from 'lucide-svelte';
  import { invalidateAll } from '$app/navigation';
  import NewRunModal from '$lib/components/NewRunModal.svelte';
  import { apiDelete } from '$lib/api/client';
  import type { PageData } from './$types';

  export let data: PageData;
  let showModal = false;
  let deleting: string | null = null;
  let deleteError: string | null = null;

  function fmtTimestamp(ms: number | null): string {
    if (ms === null) return '—';
    return new Date(ms).toLocaleString();
  }

  async function deleteTrial(trial: string, iterationCount: number) {
    const ok = confirm(
      `Delete trial "${trial}" and all ${iterationCount} iterations? `
        + `Strategy code and trajectory files will be removed from disk. `
        + `This cannot be undone.`,
    );
    if (!ok) return;
    deleting = trial;
    deleteError = null;
    try {
      await apiDelete(`/trials/${encodeURIComponent(trial)}`);
      await invalidateAll();
    } catch (e) {
      deleteError = String(e);
    } finally {
      deleting = null;
    }
  }
</script>

<header class="mb-6 flex items-center justify-between">
  <div>
    <h2 class="text-lg font-medium">Tournament runs</h2>
    <p class="mt-1 text-xs text-fg-muted">
      Each trial is a directory of agent iterations. Click a row to inspect strategies, scores, and failure modes.
    </p>
  </div>
  <button
    on:click={() => (showModal = true)}
    class="flex items-center gap-1.5 rounded bg-accent px-3 py-1.5 text-xs font-medium text-bg hover:bg-accent/90"
  >
    <Plus size={14} /> Start new run
  </button>
</header>

{#if data.trials.length === 0}
  <div class="rounded border border-bg-muted p-8 text-center">
    <Beaker class="mx-auto mb-3 text-fg-dim" size={32} />
    <p class="text-sm text-fg-muted">No trials yet.</p>
    <p class="mt-1 text-xs text-fg-dim">
      Run <code class="font-mono">uv run belt agent --pool ... --trial demo --budget 10</code> from the
      project root, or click <span class="font-medium">Start new run</span> above.
    </p>
  </div>
{:else}
  {#if deleteError}
    <p class="mb-3 rounded border border-rose-500/40 bg-rose-500/5 p-2 text-xs text-rose-300">
      {deleteError}
    </p>
  {/if}
  <table class="w-full text-sm">
    <thead class="border-b border-bg-muted text-left text-xs text-fg-muted">
      <tr>
        <th class="py-2 pr-4 font-medium">Trial</th>
        <th class="py-2 pr-4 font-medium">Iterations</th>
        <th class="py-2 pr-4 font-medium">Outcomes</th>
        <th class="py-2 pr-4 font-medium">Best score</th>
        <th class="py-2 pr-4 font-medium">Objective</th>
        <th class="py-2 pr-4 font-medium">Last update</th>
        <th class="py-2 font-medium"></th>
      </tr>
    </thead>
    <tbody>
      {#each data.trials as t}
        <tr class="border-b border-bg-muted/50 hover:bg-bg-muted/30">
          <td class="py-3 pr-4">
            <a href={`/trials/${t.trial}`} class="font-mono font-medium text-accent hover:underline">
              {t.trial}
            </a>
          </td>
          <td class="py-3 pr-4 font-mono">{t.iteration_count}</td>
          <td class="py-3 pr-4 text-xs">
            <span class="text-emerald-400">{t.success_count - t.degenerate_count} ok</span>
            {#if t.degenerate_count > 0}
              <span class="text-fg-muted"> · {t.degenerate_count} degen</span>
            {/if}
            {#if t.error_count > 0}
              <span class="text-rose-400"> · {t.error_count} err</span>
            {/if}
          </td>
          <td class="py-3 pr-4 font-mono">
            {t.best_score !== null ? t.best_score.toFixed(2) : '—'}
            {#if t.best_iteration !== null}
              <span class="text-xs text-fg-muted">@ iter {t.best_iteration}</span>
            {/if}
          </td>
          <td class="py-3 pr-4 text-xs text-fg-muted">{t.score_metric ?? '—'}</td>
          <td class="py-3 pr-4 text-xs text-fg-muted">{fmtTimestamp(t.last_updated)}</td>
          <td class="py-3 text-right">
            <button
              on:click={() => deleteTrial(t.trial, t.iteration_count)}
              disabled={deleting === t.trial}
              title="Delete trial"
              aria-label={`Delete trial ${t.trial}`}
              class="rounded p-1.5 text-fg-muted hover:bg-rose-500/10 hover:text-rose-300 disabled:opacity-40"
            >
              <Trash2 size={14} />
            </button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

{#if showModal}
  <NewRunModal on:close={() => (showModal = false)} />
{/if}

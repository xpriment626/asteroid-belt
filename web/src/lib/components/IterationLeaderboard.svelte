<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import * as echarts from 'echarts';
  import type { IterationSummary } from '$lib/api/client';

  export let iterations: IterationSummary[] = [];
  export let selected: number = 0;

  const dispatch = createEventDispatcher<{ select: number }>();

  let el: HTMLDivElement;
  let chart: echarts.ECharts | null = null;

  function classify(it: IterationSummary): 'error' | 'degenerate' | 'ok' {
    if (it.error) return 'error';
    if ((it.score ?? 0) === 0) return 'degenerate';
    return 'ok';
  }

  function colorFor(kind: 'error' | 'degenerate' | 'ok', isSelected: boolean): string {
    if (isSelected) return '#fbbf24'; // amber-400
    if (kind === 'error') return '#f43f5e'; // rose-500
    if (kind === 'degenerate') return '#6b7280'; // gray-500
    return '#3b82f6'; // blue-500
  }

  function render() {
    if (!chart) return;
    // Clamp negative-/null-scored bars to a small visible height so error bars
    // are still clickable. Real value lives in the tooltip.
    const data = iterations.map((it) => {
      const k = classify(it);
      const value = k === 'error' ? -1 : (it.score ?? 0);
      return {
        value: [it.iteration, value],
        itemStyle: { color: colorFor(k, it.iteration === selected) },
        kind: k,
        score: it.score,
        rebalances: it.rebalance_count,
        error: it.error,
      };
    });

    const maxScore = Math.max(
      0,
      ...iterations.map((it) => (it.error ? 0 : (it.score ?? 0))),
    );

    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 60, right: 24, top: 16, bottom: 32 },
      xAxis: {
        type: 'category',
        data: iterations.map((it) => String(it.iteration)),
        axisLine: { lineStyle: { color: '#374151' } },
        axisLabel: { fontSize: 10 },
        name: 'iteration',
        nameLocation: 'middle',
        nameGap: 24,
        nameTextStyle: { fontSize: 10, color: '#9ca3af' },
      },
      yAxis: {
        type: 'value',
        min: -maxScore * 0.05,
        scale: false,
        axisLine: { lineStyle: { color: '#374151' } },
        axisLabel: { fontSize: 10 },
      },
      tooltip: {
        trigger: 'item',
        formatter: (p: { data: { kind: string; score: number | null; rebalances: number; error: string | null }; name: string }) => {
          const d = p.data;
          if (d.kind === 'error') {
            return `iter ${p.name} — <span style="color:#f43f5e">errored</span><br>${d.error ?? ''}`;
          }
          return `iter ${p.name}<br>score: ${d.score?.toFixed(4) ?? '—'}<br>rebalances: ${d.rebalances}<br>${d.kind === 'degenerate' ? 'degenerate (score = 0)' : 'ok'}`;
        },
      },
      series: [
        {
          type: 'bar',
          data: data.map((d) => ({
            value: d.value[1],
            itemStyle: d.itemStyle,
            kind: d.kind,
            score: d.score,
            rebalances: d.rebalances,
            error: d.error,
          })),
          barCategoryGap: '20%',
        },
      ],
    });
  }

  onMount(() => {
    chart = echarts.init(el, 'dark');
    chart.on('click', (params) => {
      if (typeof params.dataIndex === 'number' && iterations[params.dataIndex]) {
        dispatch('select', iterations[params.dataIndex].iteration);
      }
    });
    render();
    const ro = new ResizeObserver(() => chart?.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart?.dispose();
    };
  });

  $: if (chart) render();
</script>

<div bind:this={el} class="h-44 w-full"></div>

<div class="mt-2 flex flex-wrap gap-3 text-[11px] text-fg-muted">
  <span class="flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-sm bg-blue-500"></span> ok</span>
  <span class="flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-sm bg-gray-500"></span> degenerate (no position / score = 0)</span>
  <span class="flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-sm bg-rose-500"></span> errored</span>
  <span class="flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-sm bg-amber-400"></span> selected</span>
  <span class="ml-auto text-fg-dim">click a bar to inspect</span>
</div>

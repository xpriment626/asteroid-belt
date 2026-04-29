<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';
  import type { Bar } from '$lib/api/client';

  export let bars: Bar[] = [];
  export let holdoutStartMs: number | null = null;

  let el: HTMLDivElement;
  let chart: echarts.ECharts | null = null;

  function render() {
    if (!chart || bars.length === 0) return;
    const data = bars.map((b) => [b.ts, b.close]);
    const markLines: object[] = [];
    if (holdoutStartMs !== null) {
      markLines.push({ xAxis: holdoutStartMs, label: { formatter: 'holdout →' } });
    }
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 60, right: 24, top: 24, bottom: 40 },
      xAxis: { type: 'time', axisLine: { lineStyle: { color: '#374151' } } },
      yAxis: { type: 'value', scale: true, axisLine: { lineStyle: { color: '#374151' } } },
      tooltip: { trigger: 'axis' },
      series: [
        {
          type: 'line',
          data,
          smooth: false,
          symbol: 'none',
          lineStyle: { color: '#3b82f6', width: 1.5 },
          markLine: markLines.length
            ? { data: markLines, lineStyle: { color: '#9ca3af', type: 'dashed' } }
            : undefined,
        },
      ],
    });
  }

  onMount(() => {
    chart = echarts.init(el, 'dark');
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

<div bind:this={el} class="h-96 w-full"></div>

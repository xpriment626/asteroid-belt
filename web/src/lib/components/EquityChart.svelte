<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';
  import type { TrajectoryRow } from '$lib/api/client';

  export let rows: TrajectoryRow[] = [];

  let el: HTMLDivElement;
  let chart: echarts.ECharts | null = null;

  function render() {
    if (!chart || rows.length === 0) return;

    const ts = (r: TrajectoryRow) => r.ts;
    const equity = rows.map((r) => [ts(r), r.position_value_usd + r.fees_value_usd]);
    const hodl = rows.map((r) => [ts(r), r.hodl_value_usd]);
    const fees = rows.map((r) => [ts(r), r.fees_value_usd]);
    const il = rows.map((r) => [ts(r), r.il_cumulative]);

    chart.setOption({
      backgroundColor: 'transparent',
      grid: [
        { left: 60, right: 60, top: 24, height: '50%' },
        { left: 60, right: 60, top: '70%', height: '24%' },
      ],
      xAxis: [
        { type: 'time', gridIndex: 0, axisLine: { lineStyle: { color: '#374151' } } },
        { type: 'time', gridIndex: 1, axisLine: { lineStyle: { color: '#374151' } } },
      ],
      yAxis: [
        {
          type: 'value',
          gridIndex: 0,
          scale: true,
          axisLine: { lineStyle: { color: '#374151' } },
          name: 'value',
          nameTextStyle: { color: '#9ca3af', fontSize: 10 },
        },
        {
          type: 'value',
          gridIndex: 0,
          scale: true,
          axisLine: { lineStyle: { color: '#374151' } },
          name: 'fees',
          nameTextStyle: { color: '#9ca3af', fontSize: 10 },
          position: 'right',
          splitLine: { show: false },
        },
        {
          type: 'value',
          gridIndex: 1,
          scale: true,
          axisLine: { lineStyle: { color: '#374151' } },
          name: 'IL',
          nameTextStyle: { color: '#9ca3af', fontSize: 10 },
        },
      ],
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      legend: {
        data: ['LP equity (pos + fees)', 'HODL', 'Fees (cumulative)', 'IL'],
        textStyle: { color: '#9ca3af', fontSize: 10 },
        top: 0,
      },
      series: [
        {
          name: 'LP equity (pos + fees)',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          showSymbol: false,
          data: equity,
          lineStyle: { color: '#3b82f6', width: 1.5 },
        },
        {
          name: 'HODL',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          showSymbol: false,
          data: hodl,
          lineStyle: { color: '#9ca3af', width: 1, type: 'dashed' },
        },
        {
          name: 'Fees (cumulative)',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 1,
          showSymbol: false,
          data: fees,
          lineStyle: { color: '#10b981', width: 1 },
        },
        {
          name: 'IL',
          type: 'line',
          xAxisIndex: 1,
          yAxisIndex: 2,
          showSymbol: false,
          data: il,
          lineStyle: { color: '#f59e0b', width: 1 },
          areaStyle: { color: 'rgba(245, 158, 11, 0.15)' },
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

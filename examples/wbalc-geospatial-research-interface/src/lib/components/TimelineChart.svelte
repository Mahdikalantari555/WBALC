<script lang="ts">
  /**
   * Acquisition timeline.
   *
   * This is deliberately *not* a water-area chart: RSAL records scene
   * registration but does not compute per-scene water area, so plotting area
   * here would mean inventing numbers. Each point is one registered acquisition
   * (or dataset), positioned by date and coloured by sensor.
   */
  import { useT } from '$lib/t.svelte';

  export interface TimelinePoint {
    id: string;
    date: number;
    label: string;
    sensor: string;
    kind: 'scene' | 'dataset';
  }

  let {
    points,
    selected = null,
    onselect,
  }: {
    points: TimelinePoint[];
    selected?: string | null;
    onselect?: (id: string) => void;
  } = $props();

  const { t, date } = useT();
  let measured = $state(600);

  const width = $derived(Math.max(measured, 260));
  const height = 190;
  const pad = { top: 22, right: 14, bottom: 34, left: 14 };

  const sorted = $derived([...points].sort((a, b) => a.date - b.date));
  const min = $derived(sorted[0]?.date ?? 0);
  const max = $derived(sorted.at(-1)?.date ?? 0);
  const span = $derived(max - min || 1);
  const x = (value: number) =>
    pad.left + ((value - min) / span) * (width - pad.left - pad.right);

  const rows = $derived(
    ['Sentinel-1', 'Sentinel-2'].map((sensor) => ({
      sensor,
      items: sorted.filter((point) => point.sensor === sensor),
    })),
  );

  const ticks = $derived.by(() => {
    if (!sorted.length) return [];
    const count = width > 520 ? 5 : 3;
    return Array.from({ length: count }, (_, index) => min + (span * index) / (count - 1));
  });

  const colors: Record<string, string> = { 'Sentinel-1': '#e9bf73', 'Sentinel-2': '#66bfff' };
</script>

<div class="chart-root" bind:clientWidth={measured}>
  {#if sorted.length}
    <svg height={height} {width} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t('overview.series')}>
      {#each ticks as value}
        <line x1={x(value)} x2={x(value)} y1={pad.top} y2={height - pad.bottom} stroke="#2b3b50" stroke-dasharray="3 4" />
        <text class="axis" x={x(value)} y={height - 12} text-anchor="middle">{date(new Date(value))}</text>
      {/each}
      {#each rows as row, rowIndex}
        {@const y = pad.top + 26 + rowIndex * 54}
        <text class="axis row-label" x={pad.left} y={y - 13}>{row.sensor}</text>
        <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} stroke="#39495d" />
        {#each row.items as point (point.id)}
          {#if onselect}
            <circle
              class="point"
              cx={x(point.date)}
              cy={y}
              r={selected === point.id ? 7 : 4.5}
              fill={colors[point.sensor] ?? '#8fd6d0'}
              stroke={selected === point.id ? '#ffffff' : '#0b1522'}
              stroke-width={selected === point.id ? 2 : 1.5}
              role="button"
              tabindex="0"
              aria-label={`${point.sensor} ${date(new Date(point.date))}`}
              onkeydown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onselect(point.id);
                }
              }}
              onclick={() => onselect(point.id)}
            />
          {:else}
            <circle
              cx={x(point.date)}
              cy={y}
              r={4.5}
              fill={colors[point.sensor] ?? '#8fd6d0'}
              stroke="#0b1522"
              stroke-width={1.5}
            />
          {/if}
        {/each}
        {#if !row.items.length}
          <text class="axis empty" x={width / 2} y={y - 4} text-anchor="middle">{t('chart.noData')}</text>
        {/if}
      {/each}
    </svg>
    <div class="chart-caption">
      <span class="chip-row">
        <span class="chip" style:--chip-color={colors['Sentinel-1']}><i></i>Sentinel-1</span>
        <span class="chip" style:--chip-color={colors['Sentinel-2']}><i></i>Sentinel-2</span>
      </span>
      <span class="mono">{t('overview.seriesHint', { count: sorted.length })}</span>
    </div>
  {:else}
    <div class="empty-state">
      <strong>{t('overview.noSeries')}</strong>
      <span>{t('overview.noSeriesHint')}</span>
    </div>
  {/if}
</div>

<style>
  .chart-root { min-width: 0; }
  .chart-root svg { display: block; max-width: 100%; overflow: visible; }
  .axis { font: 9.5px var(--mono); fill: #93a7bd; }
  .row-label { fill: #b6c5d6; }
  .axis.empty { fill: #5f7387; }
  .point { cursor: pointer; }
  .point:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .chart-caption { display: flex; gap: 6px 14px; flex-wrap: wrap; justify-content: space-between; align-items: center; color: var(--muted); font-size: 10.5px; padding-top: 7px; border-top: 1px solid var(--line); }
</style>

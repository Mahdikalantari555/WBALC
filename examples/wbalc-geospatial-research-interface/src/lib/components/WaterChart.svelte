<script lang="ts">
  import { observations, fmtDate, type Observation, type SensorFilter } from '../data/research';

  const uid = $props.id();
  let { filter, selected, reference, onselect }: {
    filter: SensorFilter; selected: string; reference?: string; onselect: (date: string) => void;
  } = $props();

  let measured = $state(640);
  let hovered = $state<Observation | null>(null);
  const width = $derived(Math.max(measured, 210));
  const height = 228;
  const left = 43;
  const right = 16;
  const top = 13;
  const bottom = 33;
  const start = Date.parse(observations[0].date);
  const span = Date.parse(observations[observations.length - 1].date) - start;
  const min = 5.95;
  const max = 8.15;
  const ticks = [6, 6.5, 7, 7.5, 8];
  const labels = [{ date: '2024-10-16', text: 'Oct' }, { date: '2024-11-16', text: 'Nov' }, { date: '2024-12-16', text: 'Dec' }, { date: '2025-01-16', text: 'Jan' }, { date: '2025-02-16', text: 'Feb' }, { date: '2025-03-16', text: 'Mar' }, { date: '2025-04-14', text: 'Apr' }];

  const x = (date: string) => left + (Date.parse(date) - start) / span * (width - right - left);
  const y = (area: number) => top + (max - area) / (max - min) * (height - bottom - top);
  const items = $derived(observations.filter(item => filter === 'all' || item.sensor === filter));
  const active = $derived(items.find(item => item.date === selected));
  const path = $derived(items.map((item, index) => `${index === 0 ? 'M' : 'L'}${x(item.date)},${y(item.water)}`).join(' '));
  const areaPath = $derived(`${path} L${x(items[items.length - 1].date)},${height - bottom} L${x(items[0].date)},${height - bottom} Z`);

  $effect(() => { if (hovered && filter !== 'all' && filter !== hovered.sensor) hovered = null; });
</script>

<div class="chart-root" bind:clientWidth={measured}>
  <svg height={height} {width} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
    <defs><linearGradient id={`${uid}-area`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#58dccb" stop-opacity=".21" /><stop offset="1" stop-color="#58dccb" stop-opacity=".018" /></linearGradient></defs>
    {#each ticks as value}
      <line x1={left} x2={width - right} y1={y(value)} y2={y(value)} stroke="#2b3b50" stroke-dasharray="3 4" />
      <text class="axis" x={left - 9} y={y(value) + 3.7} text-anchor="end">{value.toFixed(1)}</text>
    {/each}
    <line x1={left} x2={width - right} y1={height - bottom} y2={height - bottom} stroke="#39495d" />
    {#each labels as item, index}
      {#if measured > 430 || index % 2 === 0}
        <text class="axis" x={x(item.date)} y={height - 12} text-anchor="middle">{item.text}</text>
      {/if}
    {/each}
    {#if reference && reference !== selected}
      <line x1={x(reference)} x2={x(reference)} y1={top} y2={height - bottom} stroke="#f3be67" stroke-opacity=".67" stroke-dasharray="4 4" />
    {/if}
    <path d={areaPath} fill={`url(#${uid}-area)`} />
    {#if active}<line x1={x(active.date)} x2={x(active.date)} y1={top} y2={height - bottom} stroke="#68d8ca" stroke-opacity=".44" />{/if}
    <path d={path} fill="none" stroke="#66dfcc" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
    {#each items as item (item.date)}
      {#if item.date === selected || item.date === hovered?.date}<circle cx={x(item.date)} cy={y(item.water)} r="7" fill="#62e2ce25" />{/if}
      <circle cx={x(item.date)} cy={y(item.water)} r={item.date === selected || item.date === hovered?.date ? 3.8 : 2.6} fill={item.sensor === 'Sentinel-1' && item.date !== selected ? '#142635' : '#86edda'} stroke="#79dfcf" stroke-width="1.4" />
    {/each}
  </svg>
  {#each items as item (item.date)}
    <button class="chart-point" style:left={`${x(item.date)}px`} style:top={`${y(item.water)}px`}
      aria-label={`${fmtDate(item.date)}, ${item.water.toFixed(2)} square kilometers, ${item.sensor}`}
      aria-pressed={item.date === selected} onclick={() => onselect(item.date)}
      onpointerenter={() => { hovered = item; }} onpointerleave={() => { hovered = null; }} onfocus={() => { hovered = item; }} onblur={() => { hovered = null; }}></button>
  {/each}
  {#if hovered}
    <div class="chart-tooltip" style:left={`${Math.max(78, Math.min(width - 78, x(hovered.date)))}px`} style:top={`${Math.max(1, y(hovered.water) - 47)}px`}>
      <span>{fmtDate(hovered.date, false)} / {hovered.sensor}</span><strong>{hovered.water.toFixed(2)} km&sup2;</strong>
    </div>
  {/if}
</div>
<div class="chart-caption">
  <span><i class="chart-legend-line"></i>Open water (km&sup2;)</span>
  {#if active}<span class="mono">{fmtDate(active.date)} <b>{active.water.toFixed(2)} km&sup2;</b></span>{/if}
</div>

<style>
  .chart-root { position: relative; min-width: 0; overflow: clip; }
  .chart-root svg { display: block; max-width: 100%; }
  .axis { font: 10px var(--mono); fill: #9daec4; }
  .chart-point { position: absolute; width: 20px; height: 20px; transform: translate(-50%, -50%); border-radius: 50%; }
  .chart-point:focus-visible { outline-offset: -1px; }
  .chart-tooltip { user-select: none; pointer-events: none; position: absolute; transform: translateX(-50%); z-index: 2; background: #192c3a; border: 1px solid #41636f; border-radius: 5px; padding: 5px 7px; min-width: 124px; display: grid; color: var(--muted); font: 9.5px var(--mono); }
  .chart-tooltip strong { color: #a2f2e4; font-weight: 520; font-size: 11px; }
  .chart-caption { display: flex; gap: 6px 16px; flex-wrap: wrap; justify-content: space-between; color: var(--muted); font-size: 11px; line-height: 1.7; padding: 6px 0 0; border-top: 1px solid var(--line); }
  .chart-caption span { display: flex; gap: 7px; align-items: center; }
  .chart-caption b { color: var(--accent); font-weight: 400; }
  .chart-legend-line { display: inline-block; width: 14px; height: 2px; border-radius: 2px; background: var(--accent); }
</style>
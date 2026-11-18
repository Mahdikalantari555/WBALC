<script lang="ts">
  import { ArrowRight, ArrowRightLeft, CalendarDays, ChartNoAxesCombined, Satellite } from '@lucide/svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import SensorFilter from '../components/SensorFilter.svelte';
  import MiniScene from '../components/MiniScene.svelte';
  import WaterChart from '../components/WaterChart.svelte';
  import { fmtDate, getModel, getObservation, observations, sensorDetails } from '../data/research';
  import { filterSensor, getWorkspace, type WorkspaceProps } from '../state.svelte';

  let { go }: WorkspaceProps = $props();
  const workspace = getWorkspace();
  const model = $derived(getModel(workspace.model));
  const current = $derived(getObservation(workspace.observation));
  const reference = $derived(getObservation(workspace.reference));
  const metadata = $derived(sensorDetails[current.sensor]);
  const dates = $derived(observations.filter(item => workspace.sensor === 'all' || item.sensor === workspace.sensor));
  const deltaWater = $derived(current.water - reference.water);
  const deltaVeg = $derived(current.vegetation - reference.vegetation);
  const signed = (value: number) => `${value > .004 ? '+' : ''}${value.toFixed(2)}`;

  function swap() {
    const before = workspace.reference;
    workspace.reference = workspace.observation;
    workspace.observation = before;
    if (workspace.sensor !== 'all' && getObservation(before).sensor !== workspace.sensor) workspace.sensor = 'all';
  }
</script>

<PageHeading title="Temporal Analysis" description="Track how open water and aquatic vegetation change between satellite observations.">
  {#snippet actions()}<button class="button" onclick={() => go('map')}><CalendarDays size={15} /> Open date on map <ArrowRight size={14} /></button>{/snippet}
</PageHeading>

<div class="surface temporal-tools">
  <div class="temporal-sensors"><span class="section-label">OBSERVATION SENSOR</span><SensorFilter value={workspace.sensor} onchange={(sensor) => filterSensor(workspace, sensor)} /></div>
  <div class="date-compare">
    <label class="field">Reference observation<select class="select" aria-label="Reference observation" bind:value={workspace.reference}>{#each observations as item}<option value={item.date}>{fmtDate(item.date)} / {item.sensor}</option>{/each}</select></label>
    <button class="icon-button swap-button" title="Swap the selected and reference dates" aria-label="Swap comparison dates" onclick={swap} disabled={current.date === reference.date}><ArrowRightLeft size={16} /></button>
    <label class="field">Selected observation<select class="select" aria-label="Selected observation" bind:value={workspace.observation}>{#each dates as item}<option value={item.date}>{fmtDate(item.date)} / {item.sensor}</option>{/each}</select></label>
  </div>
</div>

<div class="research-grid temporal-grid">
  <section class="surface section-box">
    <div class="section-heading"><div><h2>Open water area over time</h2><p>{dates.length} simulated observations / Select a point to inspect its date</p></div><ChartNoAxesCombined size={17} class="faint" /></div>
    <WaterChart filter={workspace.sensor} selected={current.date} reference={reference.date} onselect={(date) => { workspace.observation = date; }} />
  </section>
  <section class="surface">
    <div class="panel-heading"><div class="panel-heading-title"><Satellite size={16} /><h2>Observation metadata</h2></div></div>
    <div class="panel-body temporal-meta">
      <div class="observation-id"><span class="status-dot"></span><span>{metadata.product}</span><small class="section-label">SIMULATED</small></div>
      <dl class="kv-list">
        <div><dt>Acquisition</dt><dd>{fmtDate(current.date, false)} / {current.acquisition} UTC</dd></div>
        <div><dt>Mode</dt><dd>{metadata.mode}</dd></div>
        <div><dt>Channels</dt><dd>{metadata.bands}</dd></div>
        <div><dt>Pixel spacing</dt><dd>{metadata.resolution}</dd></div>
        <div><dt>Cloud cover</dt><dd>{current.cloud === null ? 'Not applicable' : `${current.cloud.toFixed(1)}%`}</dd></div>
      </dl>
    </div>
  </section>
</div>

<section class="surface section-box comparison-panel">
  <div class="section-heading"><div><h2>Classification change</h2><p>{model.name} / Schematic open water extent, selected minus reference</p></div></div>
  <div class="comparison-frames">
    <figure><figcaption><strong>Reference</strong><span>{fmtDate(reference.date)}</span></figcaption><div class="comparison-image"><MiniScene observation={reference} {model} label="Reference observation classification" /></div><p>Open water <strong>{reference.water.toFixed(2)} km&sup2;</strong></p></figure>
    <figure><figcaption><strong>Selected</strong><span>{fmtDate(current.date)}</span></figcaption><div class="comparison-image"><MiniScene observation={current} {model} label="Selected observation classification" /></div><p>Open water <strong>{current.water.toFixed(2)} km&sup2;</strong></p></figure>
    <figure><figcaption><strong>Change map</strong><span class="delta" class:negative={deltaWater < 0}>{signed(deltaWater)} km&sup2;</span></figcaption><div class="comparison-image"><MiniScene observation={current} {reference} {model} mode="change" label="Schematic shoreline gain and loss" /></div><p>Aquatic vegetation <strong>{signed(deltaVeg)} km&sup2;</strong></p></figure>
  </div>
  <div class="change-legend">
    <span class="class-label"><i class="class-dot" style:--class-color="#5ff2b3"></i>Water gain</span>
    <span class="class-label"><i class="class-dot" style:--class-color="#ffb465"></i>Water loss</span>
    <span class="class-label"><i class="class-dot" style:--class-color="#4aa9ff"></i>Stable water</span>
    {#if current.date === reference.date}<span class="faint">Same observation selected. Choose two dates to see a change.</span>{/if}
  </div>
</section>

<style>
  .temporal-tools { display: flex; align-items: end; justify-content: space-between; flex-wrap: wrap; gap: 12px 24px; padding: 13px 15px; margin-bottom: 15px; }
  .temporal-sensors { display: grid; gap: 6px; }
  .date-compare { display: flex; gap: 7px; align-items: end; }
  .date-compare .field { min-width: 0; }
  .swap-button { margin-bottom: 1.5px; border: 1px solid var(--border); }
  .temporal-grid { margin-bottom: 15px; }
  .observation-id { display: flex; align-items: center; gap: 8px; color: var(--ink); font-size: 13px; margin-bottom: 5px; }
  .observation-id small { margin-left: auto; }
  .comparison-frames { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; }
  .comparison-frames figure { margin: 0; min-width: 0; }
  .comparison-frames figcaption { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 7px; font-size: 12px; }
  .comparison-frames figcaption strong { font-weight: 590; }
  .comparison-frames figcaption span { font: 10.5px var(--mono); color: var(--muted); white-space: nowrap; }
  .comparison-frames figcaption .delta { color: var(--accent); }
  .comparison-frames figcaption .negative { color: var(--warn); }
  .comparison-image { aspect-ratio: 1.75; border: 1px solid #35495b; border-radius: 5px; overflow: hidden; }
  .comparison-frames p { display: flex; justify-content: space-between; gap: 7px; font-size: 11px; color: var(--faint); margin: 6px 0 0; }
  .comparison-frames p strong { font: 11px var(--mono); color: var(--ink); }
  .change-legend { margin-top: 13px; padding-top: 10px; border-top: 1px solid var(--line); display: flex; gap: 6px 14px; flex-wrap: wrap; color: var(--muted); font-size: 11px; }
  @media (max-width: 650px) { .comparison-frames { grid-template-columns: 1fr; } .comparison-image { aspect-ratio: 1.7; } }
  @media (max-width: 480px) { .date-compare { display: grid; grid-template-columns: minmax(0, 1fr) 30px minmax(0, 1fr); width: 100%; gap: 5px; } .date-compare .select { padding-left: 5px; font-size: 10px; } .swap-button { width: 28px; } }
</style>
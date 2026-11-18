<script lang="ts">
  import { ArrowRight, CalendarDays, ChartNoAxesCombined, Check, CircleCheck, Layers, MapPin, Tags } from '@lucide/svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import SensorFilter from '../components/SensorFilter.svelte';
  import MiniScene from '../components/MiniScene.svelte';
  import WaterChart from '../components/WaterChart.svelte';
  import { classes, evaluateModel, fmtDate, getModel, latest, observations, pct, project, samples } from '../data/research';
  import { filterSensor, getWorkspace, type WorkspaceProps } from '../state.svelte';

  let { go }: WorkspaceProps = $props();
  const workspace = getWorkspace();
  const model = $derived(getModel(workspace.model));
  const metrics = $derived(evaluateModel(model));
  const reviewed = $derived(project.archiveReviewed + Object.keys(workspace.reviews).length);
  const pending = $derived(samples.filter(item => !workspace.reviews[item.id]).length);
  const newestReview = $derived(Object.entries(workspace.reviews).filter(entry => entry[1].date > '2025-04-15').sort((a, b) => b[1].date.localeCompare(a[1].date))[0]);
</script>

<PageHeading title={'Zarivar Lake \u2014 Water Body Monitoring'} description="A local research project tracking open water and shoreline vegetation with Sentinel-1 and Sentinel-2.">
  {#snippet actions()}<button class="button primary" onclick={() => go('map')}><MapPin size={15} /> Open map workspace <ArrowRight size={14} /></button>{/snippet}
</PageHeading>

<div class="overview-grid">
  <div class="stack">
    <section class="surface study-preview">
      <div class="panel-heading"><div class="panel-heading-title"><MapPin size={16} /><h2>Study area</h2></div><span class="section-label">{project.id} / IRAN</span></div>
      <a href="#/map" class="preview-map" aria-label="Zarivar Lake: Open latest observation in the map workspace" onclick={(event) => { event.preventDefault(); workspace.observation = latest.date; workspace.sensor = 'all'; go('map'); }}>
        <MiniScene observation={latest} {model} label="Simulated study area preview near Zarivar Lake" />
        <span class="preview-annotation"><MapPin size={14} /> Zarivar Lake <ArrowRight size={14} /></span>
      </a>
      <div class="study-foot">
        <span class="mono">{project.area.toFixed(2)} km&sup2; study area</span>
        <span class="class-label"><i class="class-dot" style:--class-color={classes.water.color}></i>Open Water</span>
        <span class="class-label"><i class="class-dot" style:--class-color={classes.vegetation.color}></i>Aquatic Vegetation</span>
      </div>
    </section>

    <section class="surface section-box">
      <div class="section-heading"><div><h2>Open water area over time</h2><p>Simulated observations / October 2024 to April 2025</p></div><SensorFilter value={workspace.sensor} onchange={(sensor) => filterSensor(workspace, sensor)} /></div>
      <WaterChart filter={workspace.sensor} selected={workspace.observation} onselect={(date) => { workspace.observation = date; }} />
      <button class="button-link chart-link" onclick={() => go('temporal')}>Explore temporal analysis <ArrowRight size={14} /></button>
    </section>
  </div>

  <div class="stack">
    <section class="surface">
      <div class="panel-heading"><div class="panel-heading-title"><Layers size={16} /><h2>Project status</h2></div><span class="outline-badge">DEMO</span></div>
      <div class="panel-body status-body">
        <dl class="kv-list">
          <div><dt>Latest observation</dt><dd>{fmtDate(latest.date)}</dd></div>
          <div><dt>Available observations</dt><dd>{observations.length}</dd></div>
          <div><dt>Reviewed samples</dt><dd>{reviewed}</dd></div>
          <div><dt>Classification</dt><dd class="ready-state"><Check size={12} /> {pending ? 'Ready for review' : 'Review complete'}</dd></div>
        </dl>
        <button class="button-link status-link" onclick={() => go('learning')}>{pending ? `Review ${pending} pending samples` : 'View completed reviews'} <ArrowRight size={14} /></button>
      </div>
    </section>

    <section class="surface section-box">
      <div class="section-heading"><div><h2>Model performance</h2><p>{model.name} / simulated holdout set</p></div><ChartNoAxesCombined size={16} class="faint" /></div>
      <div class="performance-rows">
        {#each [{ label: 'Overall accuracy', value: metrics.accuracy }, { label: 'Macro F1-score', value: metrics.f1 }, { label: 'Mean IoU', value: metrics.iou }] as metric}
          <div class="performance-row"><div><span>{metric.label}</span><b>{pct(metric.value)}</b></div><div class="metric-track"><i style:width={pct(metric.value)}></i></div></div>
        {/each}
      </div>
      <button class="button-link status-link" onclick={() => go('arena')}>Compare models <ArrowRight size={14} /></button>
    </section>

    <section class="surface section-box">
      <div class="section-heading"><div><h2>Recent activity</h2><p>Local demo project history</p></div></div>
      <div class="activity-list">
        {#if newestReview}
          <button onclick={() => { workspace.selectedSample = newestReview[0]; go('learning'); }}><Tags size={15} /><span><strong>{newestReview[0]} labeled</strong><small>{classes[newestReview[1].label].name} / {fmtDate(newestReview[1].date)}</small></span><ArrowRight size={13} /></button>
        {/if}
        <button onclick={() => go('learning')}><Tags size={15} /><span><strong>Reference reviews imported</strong><small>4 reviewed samples / 15 Apr</small></span><ArrowRight size={13} /></button>
        <button onclick={() => { workspace.observation = latest.date; workspace.sensor = 'all'; go('map'); }}><CircleCheck size={15} /><span><strong>Classification snapshot ready</strong><small>Sentinel Fusion RF / 14 Apr</small></span><ArrowRight size={13} /></button>
        <button onclick={() => go('temporal')}><CalendarDays size={15} /><span><strong>Optical observation added</strong><small>Sentinel-2 L2A / 14 Apr</small></span><ArrowRight size={13} /></button>
      </div>
    </section>
  </div>
</div>

<style>
  .overview-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(275px, .5fr); gap: 15px; align-items: start; }
  .study-preview { overflow: hidden; }
  .preview-map { display: block; position: relative; height: clamp(235px, 28vw, 350px); overflow: hidden; }
  .preview-map:focus-visible { outline-offset: -3px; }
  .preview-annotation { position: absolute; bottom: 12px; left: 12px; display: inline-flex; align-items: center; gap: 8px; padding: 7px 9px; border-radius: 5px; border: 1px solid #59776d; background: #102129ed; color: #e2f4ee; font-size: 11px; }
  .preview-map:hover .preview-annotation { background: #203b42; border-color: var(--accent); }
  .study-foot { padding: 10px 12px; display: flex; gap: 8px 16px; flex-wrap: wrap; color: var(--muted); font-size: 11px; }
  .study-foot .mono { margin-right: auto; }
  .status-body { padding-top: 5px; }
  .ready-state { display: inline-flex; align-items: center; gap: 4px; color: var(--accent); white-space: nowrap; }
  .status-link { margin-top: 11px; }
  .chart-link { margin-top: 10px; }
  .performance-rows { display: grid; gap: 12px; }
  .performance-row > div:first-child { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 4px; color: var(--muted); font-size: 12px; }
  .performance-row b { color: var(--accent); font: 12px var(--mono); }
  .metric-track { height: 4px; border-radius: 4px; background: #293c50; overflow: hidden; }
  .metric-track i { display: block; height: 100%; border-radius: 4px; background: #52b9a8; transition: width 180ms ease; }
  .activity-list { display: grid; }
  .activity-list button { display: flex; align-items: center; text-align: left; gap: 9px; padding: 9px 0; color: #91b5cb; width: 100%; }
  .activity-list button + button { border-top: 1px solid var(--line); }
  .activity-list button:hover { color: var(--accent); }
  .activity-list span { flex: 1; min-width: 0; }
  .activity-list strong { display: block; font-size: 11.5px; font-weight: 560; color: var(--ink); }
  .activity-list small { display: block; font-size: 10.5px; color: var(--faint); margin-top: 3px; }
  @media (max-width: 1040px) { .overview-grid { grid-template-columns: 1fr; } }
</style>
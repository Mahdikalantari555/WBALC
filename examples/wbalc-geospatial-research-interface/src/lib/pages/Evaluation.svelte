<script lang="ts">
  import { ChartNoAxesCombined, Download, MapPin } from '@lucide/svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import ConfusionMatrix from '../components/ConfusionMatrix.svelte';
  import MetricsTable from '../components/MetricsTable.svelte';
  import ModelSelect from '../components/ModelSelect.svelte';
  import ModelTable from '../components/ModelTable.svelte';
  import MiniScene from '../components/MiniScene.svelte';
  import { classKeys, classes, errorSites, fmtDate, getModel, latest, observations, pct, type PredictionClass } from '../data/research';
  import { classificationFeatures, download, errorFeatures, evaluationCsv, geojson, studyAreaFeature } from '../data/exports';
  import { getWorkspace, selectModel, type WorkspaceProps } from '../state.svelte';

  let { notify }: WorkspaceProps = $props();
  const workspace = getWorkspace();
  let filter = $state<PredictionClass | 'all'>('all');
  let highlight = $state<string | null>(null);
  const model = $derived(getModel(workspace.model));
  const sites = $derived(errorSites.filter(site => site.models.includes(model.id) && (filter === 'all' || site.actual === filter)));
  const highlighted = $derived(sites.find(site => site.id === highlight));

  function csv() {
    download(`wbalc-evaluation-${model.id}-${filter}.csv`, 'text/csv;charset=utf-8', evaluationCsv(model, filter, workspace.reviews));
    notify('Simulated evaluation CSV exported.');
  }

  function exportSpatial() {
    const vectors = classificationFeatures(latest, model).filter(item => filter === 'all' || item.properties.class === classes[filter].name);
    download(`wbalc-evaluation-${model.id}-${filter}.geojson`, 'application/geo+json', geojson([
      studyAreaFeature(), ...vectors, ...errorFeatures(sites, model, latest.date),
    ]));
    notify('Simulated evaluation layers exported as GeoJSON.');
  }
</script>

<PageHeading title="Results & Evaluation" description="Inspect validation metrics, shoreline errors, and temporal consistency for the demo classifiers.">
  {#snippet actions()}
    <button class="button" onclick={csv}><Download size={15} /> Export CSV</button>
    <button class="button" onclick={exportSpatial}><Download size={15} /> Export GeoJSON</button>
  {/snippet}
</PageHeading>

<div class="surface evaluation-filters">
  <ModelSelect label="Evaluation model" value={workspace.model} onchange={(id) => { selectModel(workspace, id); highlight = null; }} />
  <label class="field">Reference class<select class="select" aria-label="Reference class" bind:value={filter} onchange={() => { highlight = null; }}>
    <option value="all">All classes</option>{#each classKeys as key}<option value={key}>{classes[key].name}</option>{/each}
  </select></label>
  <p>Evaluation uses a fixed mock holdout set, separate from local review labels.</p>
</div>

<div class="evaluation-grid">
  <div class="stack">
    <MetricsTable {model} focus={filter} />
    <section class="surface error-panel">
      <div class="panel-heading"><div class="panel-heading-title"><MapPin size={16} /><h2>Spatial distribution of errors</h2></div><span class="section-label">{sites.length} PLOTTED</span></div>
      <div class="error-body">
        <div class="error-map"><MiniScene mode="errors" {model} observation={latest} errors={sites} highlight={highlighted?.id} label="Illustrative spatial distribution of classification errors around Zarivar Lake" /></div>
        <div class="site-list">
          <p class="section-label">ILLUSTRATIVE SITES</p>
          {#each sites as site (site.id)}
            <button class:chosen={site.id === highlight} onclick={() => { highlight = highlight === site.id ? null : site.id; }} aria-pressed={site.id === highlight}>
              <i class="class-dot" style:--class-color="var(--warn)"></i><span><strong>{site.id} / {classes[site.actual].short}</strong><small>Predicted: {classes[site.predicted].short}</small></span>
            </button>
          {:else}
            <div class="empty-state">No illustrative errors for this class.</div>
          {/each}
        </div>
      </div>
      <div class="error-foot"><i class="class-dot" style:--class-color="var(--warn)"></i> Illustrative error locations, not the full holdout set. Basemap context: {fmtDate(latest.date)}.</div>
    </section>
  </div>

  <div class="stack">
    <ConfusionMatrix {model} focus={filter} />
    <section class="surface section-box">
      <div class="section-heading"><div><h2>Temporal consistency</h2><p>{model.name} / {observations.length} simulated observation dates</p></div><ChartNoAxesCombined size={16} class="faint" /></div>
      <div class="consistency-rows">
        {#each [{ label: 'Stable open water', value: model.stability, detail: 'Agreement on persistent interior water.' }, { label: 'Shoreline agreement', value: model.agreement, detail: 'Consistency of the modeled shoreline between dates.' }] as item}
          <div class="consistency-item"><div><span>{item.label}</span><b>{pct(item.value)}</b></div><div class="consistency-track"><i style:width={pct(item.value)}></i></div><small>{item.detail}</small></div>
        {/each}
      </div>
      <div class="consistency-foot section-label">MODEL-LEVEL INDICATORS / SIMULATED</div>
    </section>
  </div>
</div>

<ModelTable selected={model.id} focus={filter} onselect={(id) => { selectModel(workspace, id); highlight = null; }} />

<style>
  .evaluation-filters { display: flex; align-items: end; flex-wrap: wrap; gap: 10px 15px; padding: 13px 15px; margin-bottom: 15px; }
  .evaluation-filters :global(.field) { min-width: min(183px, 100%); }
  .evaluation-filters p { color: var(--faint); margin: 0 0 8px auto; font-size: 11px; }
  .evaluation-grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(275px, 1fr); gap: 15px; align-items: start; margin-bottom: 15px; }
  .error-panel { overflow: hidden; }
  .error-body { display: grid; grid-template-columns: minmax(0, 1fr) 158px; }
  .error-map { height: clamp(220px, 24vw, 300px); }
  .site-list { padding: 9px 6px; height: clamp(220px, 24vw, 300px); overflow: auto; border-left: 1px solid var(--line); }
  .site-list > p { margin: 0 0 5px; padding: 2px 5px; }
  .site-list button { display: flex; gap: 6px; align-items: center; text-align: left; width: 100%; border: 1px solid transparent; border-radius: 4px; padding: 6px 5px; }
  .site-list button:hover { background: #1a2b3c; }
  .site-list button.chosen { border-color: #69593e; background: #352b26; }
  .site-list strong, .site-list small { display: block; }
  .site-list strong { color: var(--ink); font-size: 10.5px; font-weight: 540; }
  .site-list small { margin-top: 2px; color: var(--faint); font-size: 10px; }
  .error-foot { display: flex; align-items: center; gap: 7px; padding: 9px 11px; color: var(--muted); font-size: 10.5px; }
  .consistency-rows { display: grid; gap: 13px; }
  .consistency-item > div:first-child { display: flex; justify-content: space-between; gap: 7px; color: var(--ink); font-size: 12px; margin-bottom: 4px; }
  .consistency-item b { color: var(--accent); font: 11.5px var(--mono); }
  .consistency-track { height: 5px; overflow: hidden; border-radius: 4px; background: #293b52; }
  .consistency-track i { display: block; height: 100%; border-radius: 4px; background: #60c4b4; transition: width 180ms ease; }
  .consistency-item small { color: var(--faint); font-size: 10.5px; display: block; margin-top: 5px; }
  .consistency-foot { margin-top: 15px; padding-top: 10px; border-top: 1px solid var(--line); }
  @media (max-width: 1130px) { .evaluation-grid { grid-template-columns: minmax(0, 1fr); } .evaluation-filters p { margin: 0; } }
  @media (max-width: 460px) { .error-body { grid-template-columns: minmax(0, 1fr); } .site-list { height: auto; max-height: 160px; border-left: 0; border-top: 1px solid var(--line); } .evaluation-filters :global(.field) { min-width: 0; flex: 1; } }
</style>
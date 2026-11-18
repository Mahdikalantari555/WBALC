<script lang="ts">
  import { ArrowRight, Download, Droplets, Focus, Layers, Leaf, MapPin, Scan, X } from '@lucide/svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import InteractiveMap from '../components/InteractiveMap.svelte';
  import { classes, fmtDate, getModel, getObservation, pct, project, samples, sensorDetails } from '../data/research';
  import { classificationFeatures, download, geojson, pointFeature, studyAreaFeature, type ExportFeature } from '../data/exports';
  import { getWorkspace, type MapLayer, type Selection, type WorkspaceProps } from '../state.svelte';

  let { go, notify }: WorkspaceProps = $props();
  const workspace = getWorkspace();
  const observation = $derived(getObservation(workspace.observation));
  const model = $derived(getModel(workspace.model));
  const selected = $derived(workspace.map.selected);
  const sample = $derived(selected?.kind === 'sample' ? samples.find(item => item.id === selected.id) : undefined);
  const sampleReview = $derived(sample ? workspace.reviews[sample.id] : undefined);
  const visible = $derived(Object.values(workspace.map.layers).filter(Boolean).length - (workspace.map.basemap === 'terrain' && workspace.map.layers.imagery ? 1 : 0));
  const layerRows = [
    { id: 'imagery', title: 'Satellite imagery', note: 'Local simulated basemap', icon: Scan, tone: '#b4c0cf' },
    { id: 'classification', title: 'Classification', note: 'Open water and vegetation', icon: Layers, tone: '#66bfff' },
    { id: 'boundary', title: 'Study area boundary', note: 'Zarivar Lake AOI', icon: Focus, tone: '#78dccd' },
    { id: 'samples', title: 'Reference samples', note: 'Human review locations', icon: MapPin, tone: '#e9bf73' },
  ] as const;

  function toggle(layer: MapLayer) {
    const enabled = workspace.map.layers[layer] = !workspace.map.layers[layer];
    if (!enabled && selected) {
      if ((layer === 'classification' && (selected.kind === 'water' || selected.kind === 'vegetation')) ||
          (layer === 'boundary' && selected.kind === 'boundary') || (layer === 'samples' && selected.kind === 'sample')) workspace.map.selected = null;
    }
  }

  function selectFeature(feature: Selection) { workspace.map.selected = feature; }

  function reviewSample() {
    workspace.selectedSample = sample?.id ?? samples.find(item => !workspace.reviews[item.id] && item.prediction === selected?.kind)?.id ?? null;
    go('learning');
  }

  function exportView() {
    const features: ExportFeature[] = [];
    if (workspace.map.layers.classification && workspace.map.opacity > 0) features.push(...classificationFeatures(observation, model));
    if (workspace.map.layers.boundary) features.push(studyAreaFeature());
    if (workspace.map.layers.samples) features.push(...samples.map(item => pointFeature(item.point, {
      id: item.id, date: item.observation, prediction: classes[item.prediction].name,
      reviewed: Boolean(workspace.reviews[item.id]), label: workspace.reviews[item.id] ? classes[workspace.reviews[item.id].label].name : '',
    })));
    if (!features.length) { notify('Turn on a vector layer before exporting.'); return; }
    download(`wbalc-map-${observation.date}.geojson`, 'application/geo+json', geojson(features));
    notify('Simulated map layers exported as GeoJSON.');
  }
</script>

<PageHeading title="Geospatial Workspace" description="Explore satellite observations and water-body classifications at Zarivar Lake.">
  {#snippet actions()}<button class="button" onclick={exportView} title="Download the visible vector layers as GeoJSON"><Download size={15} /> Export view</button>{/snippet}
</PageHeading>

<div class="map-workspace">
  <InteractiveMap settings={workspace.map} {observation} {model} reviews={workspace.reviews} onselect={selectFeature}
    onbasemap={(basemap) => { workspace.map.basemap = basemap; }} />

  <aside class="map-sidebar" aria-label="Map layers and feature details">
    <section class="surface layer-panel" aria-labelledby="layer-heading">
      <div class="panel-heading"><div class="panel-heading-title"><Layers size={16} strokeWidth={1.75} /><h2 id="layer-heading">Map layers</h2></div><span class="visible-count mono">{visible} visible</span></div>
      {#each layerRows as layer}
        <div class="layer-row-group" class:is-off={!workspace.map.layers[layer.id]}>
          <div class="layer-row">
            <span class="layer-icon" style:--layer-color={layer.tone}><layer.icon size={15} strokeWidth={1.7} /></span>
            <div class="layer-description"><strong>{layer.title}</strong><small>{layer.id === 'imagery' && workspace.map.basemap === 'terrain' ? 'Satellite basemap not selected' : layer.note}</small></div>
            <button class="layer-switch" role="switch" aria-checked={workspace.map.layers[layer.id] && (layer.id !== 'imagery' || workspace.map.basemap === 'satellite')}
              aria-label={layer.title} disabled={layer.id === 'imagery' && workspace.map.basemap === 'terrain'} onclick={() => toggle(layer.id)}><span></span></button>
          </div>
          {#if layer.id === 'classification'}
            <div class="layer-opacity">
              <label for="classification-opacity"><span>Opacity</span><span class="mono">{workspace.map.opacity}%</span></label>
              <input id="classification-opacity" aria-label="Classification opacity" type="range" min="0" max="100" bind:value={workspace.map.opacity}
                disabled={!workspace.map.layers.classification} style:--fill={`${workspace.map.opacity}%`} />
            </div>
          {/if}
        </div>
      {/each}
    </section>

    <section class="surface feature-panel" aria-labelledby="feature-heading">
      <div class="panel-heading"><div class="panel-heading-title"><Focus size={16} strokeWidth={1.75} /><h2 id="feature-heading">Selected feature</h2></div>
        {#if selected}<button class="icon-button" aria-label="Clear selected feature" title="Clear selection" onclick={() => { workspace.map.selected = null; }}><X size={15} /></button>{/if}
      </div>
      {#if selected}
        <div class="panel-body feature-body">
          {#if sample}
            <div class="feature-name"><div class="feature-icon sample"><MapPin size={18} /></div><div><strong>{sample.id}</strong><small>{sample.location}</small></div></div>
            <dl class="kv-list">
              <div><dt>Prediction</dt><dd>{classes[sample.prediction].name}</dd></div>
              <div><dt>Uncertainty</dt><dd class="feature-warning">{pct(sample.uncertainty)}</dd></div>
              <div><dt>Review label</dt><dd>{sampleReview ? classes[sampleReview.label].name : 'Pending'}</dd></div>
              <div><dt>Observation</dt><dd>{fmtDate(sample.observation)}</dd></div>
            </dl>
          {:else if selected.kind === 'boundary'}
            <div class="feature-name"><div class="feature-icon boundary"><Focus size={18} /></div><div><strong>Zarivar Lake AOI</strong><small>Study boundary</small></div></div>
            <dl class="kv-list">
              <div><dt>Project ID</dt><dd>{project.id}</dd></div>
              <div><dt>Study area</dt><dd>{project.area.toFixed(2)} km&sup2;</dd></div>
              <div><dt>Location</dt><dd>{project.location}</dd></div>
              <div><dt>Geometry</dt><dd>Schematic</dd></div>
            </dl>
          {:else}
            {@const isWater = selected.kind === 'water'}
            {@const classKey = isWater ? 'water' : 'vegetation'}
            <div class="feature-name"><div class="feature-icon" class:vegetation={!isWater}>{#if isWater}<Droplets size={18} strokeWidth={1.65} />{:else}<Leaf size={18} strokeWidth={1.65} />{/if}</div>
              <div><strong>{classes[classKey].name}</strong><small>{model.name} / simulated</small></div>
            </div>
            <dl class="kv-list">
              <div><dt>Feature ID</dt><dd>{isWater ? 'ZL-OW-041' : 'ZL-AV-041'}</dd></div>
              <div><dt>Area</dt><dd>{(isWater ? observation.water : observation.vegetation).toFixed(2)} km&sup2;</dd></div>
              <div><dt>Confidence</dt><dd class="feature-confidence">{pct((isWater ? .968 : .884) - (model.id === 'unet' ? .032 : model.id === 'sar' ? .101 : 0))}</dd></div>
              <div><dt>Source</dt><dd>{sensorDetails[observation.sensor].product}</dd></div>
            </dl>
          {/if}
          <div class="feature-action">
            {#if selected.kind === 'boundary'}<button class="button-link" onclick={() => go('overview')}>View project overview <ArrowRight size={14} /></button>
            {:else}<button class="button-link" onclick={reviewSample}>{sample ? 'Open in Active Learning' : 'Review samples'} <ArrowRight size={14} /></button>{/if}
          </div>
        </div>
      {:else}
        <div class="empty-state"><Focus size={20} /><strong>No feature selected</strong><span>Click a classification, sample, or boundary to inspect it.</span></div>
      {/if}
    </section>
  </aside>
</div>

<style>
  .map-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 285px; align-items: start; gap: 15px; }
  .map-sidebar { display: grid; gap: 14px; min-width: 0; }
  .visible-count { color: #92a9bf; font-size: 10px; }
  .layer-row-group { margin-inline: 13px; }
  .layer-row-group + .layer-row-group { border-top: 1px solid var(--line); }
  .layer-row { display: flex; align-items: center; gap: 10px; min-height: 58px; padding: 6px 0; }
  .layer-icon { display: grid; place-items: center; width: 29px; height: 29px; flex: none; color: var(--layer-color); background: color-mix(in srgb, var(--layer-color) 12%, #102030); border: 1px solid color-mix(in srgb, var(--layer-color) 21%, #1f3140); border-radius: 5px; }
  .layer-description { display: grid; gap: 3px; min-width: 0; }
  .layer-description strong { font-size: 12px; font-weight: 570; line-height: 1.25; }
  .layer-description small { color: var(--faint); font-size: 10.5px; line-height: 1.25; }
  .layer-switch { width: 30px; height: 17px; flex: none; margin-left: auto; display: flex; align-items: center; padding: 2px; background: #263848; border: 1px solid #496174; border-radius: 15px; transition: background 160ms, border-color 160ms; }
  .layer-switch span { width: 11px; height: 11px; border-radius: 50%; background: #a2b2be; transition: transform 160ms, background 160ms; }
  .layer-switch[aria-checked=true] { background: #3c9b91; border-color: #55b9a9; }
  .layer-switch[aria-checked=true] span { transform: translateX(13px); background: #eafff9; }
  .layer-switch:hover:not(:disabled) { border-color: #b2f3e5; }
  .layer-opacity { margin: -1px 0 13px 39px; }
  .layer-opacity label { display: flex; justify-content: space-between; font-size: 10.5px; color: #a3b4c9; margin-bottom: 4px; }
  .layer-opacity .mono { color: #94e8db; }
  .layer-opacity input { display: block; appearance: none; cursor: pointer; width: 100%; height: 14px; margin: 0; background: transparent; }
  .layer-opacity input:disabled { cursor: not-allowed; opacity: .4; }
  .layer-opacity input::-webkit-slider-runnable-track { height: 3px; border-radius: 3px; background: linear-gradient(to right, #63dcca var(--fill), #33485b var(--fill)); }
  .layer-opacity input::-moz-range-track { height: 3px; border-radius: 3px; background: linear-gradient(to right, #63dcca var(--fill), #33485b var(--fill)); }
  .layer-opacity input::-webkit-slider-thumb { appearance: none; width: 11px; height: 11px; margin-top: -4px; border-radius: 50%; background: #87e9d9; border: 1px solid #b6f1e6; }
  .layer-opacity input::-moz-range-thumb { width: 10px; height: 10px; border-radius: 50%; background: #87e9d9; border: 1px solid #b6f1e6; }
  .is-off .layer-icon { opacity: .56; }
  .feature-name { display: flex; gap: 10px; align-items: center; margin: 0 0 9px; }
  .feature-icon { display: grid; place-items: center; width: 36px; height: 36px; flex: none; border-radius: 6px; background: #173b5a; border: 1px solid #28567b; color: #79caff; }
  .feature-icon.vegetation { background: #1d3e35; border-color: #365d4b; color: #9fe7ac; }
  .feature-icon.boundary { background: #193d43; border-color: #37565d; color: var(--accent); }
  .feature-icon.sample { background: #453724; border-color: #69563a; color: var(--warn); }
  .feature-name strong { display: block; font-size: 14px; font-weight: 640; }
  .feature-name small { display: block; font-size: 10.5px; color: var(--faint); margin-top: 1px; }
  .feature-body .kv-list > div { padding-block: 7px; }
  .feature-body .kv-list dd { font-size: 11px; }
  .feature-body .kv-list dd.feature-confidence { color: var(--accent); }
  .feature-body .kv-list dd.feature-warning { color: var(--warn); }
  .feature-action { border-top: 1px solid var(--line); margin-top: 5px; padding-top: 10px; }
  @media (max-width: 1150px) { .map-workspace { grid-template-columns: minmax(0, 1fr) 252px; gap: 12px; } .layer-row { gap: 8px; } }
  @media (max-width: 920px) { .map-workspace { grid-template-columns: minmax(0, 1fr); } .map-sidebar { grid-template-columns: 1fr 1fr; align-items: start; gap: 12px; } }
  @media (max-width: 590px) { .map-sidebar { grid-template-columns: minmax(0, 1fr); } }
</style>
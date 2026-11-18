<script lang="ts">
  import { Download, Focus, Layers, MapPin, RotateCw, Scan, X } from '@lucide/svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import InteractiveMap from '../components/InteractiveMap.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import { api } from '../client/api';
  import { classColor } from '../palette';
  import { getWorkspace, type MapLayer, type Selection } from '../state.svelte';
  import { useT } from '../t.svelte';
  import type { MapFieldView } from '../types';

  const workspace = getWorkspace();
  const { t, integer, percent, number, date } = useT();

  const dataset = $derived(workspace.dataset);
  const hard = $derived(workspace.field.hard as MapFieldView | null);
  const uncertainty = $derived(workspace.field.uncertainty as MapFieldView | null);
  const selected = $derived(workspace.map.selected);

  const layers = $derived([
    { id: 'imagery' as const, title: t('map.layer.imagery'), note: t('map.layer.imageryNote'), icon: Scan },
    { id: 'classification' as const, title: t('map.layer.classification'), note: t('map.layer.classificationNote'), icon: Layers },
    { id: 'uncertainty' as const, title: t('map.layer.uncertainty'), note: t('map.layer.uncertaintyNote'), icon: Focus },
    { id: 'samples' as const, title: t('map.layer.samples'), note: t('map.layer.samplesNote'), icon: MapPin },
  ]);

  const visible = $derived(Object.values(workspace.map.layers).filter(Boolean).length);

  /** Adapter reason codes are stable identifiers, not English prose. */
  function georefKey(reason: 'not-georeferenced' | 'unsupported-crs' | 'non-axis-aligned' | null) {
    if (reason === 'unsupported-crs') return 'map.georef.unsupportedCrs' as const;
    if (reason === 'non-axis-aligned') return 'map.georef.nonAxisAligned' as const;
    return 'map.georef.notGeoreferenced' as const;
  }

  const sample = $derived(
    selected?.kind === 'sample'
      ? workspace.labels.find((label) => label.sampleId === selected.sampleId) ?? null
      : null,
  );

  const cell = $derived.by(() => {
    if (selected?.kind !== 'cell' || !hard) return null;
    const row = hard.values[selected.row]?.[selected.col];
    const valid = hard.valid[selected.row]?.[selected.col];
    return {
      row: selected.row,
      col: selected.col,
      valid: Boolean(valid),
      className: row !== null && row !== undefined ? hard.classes[row] ?? null : null,
      uncertainty: uncertainty?.values[selected.row]?.[selected.col] ?? null,
      confidence: null as number | null,
    };
  });

  function toggle(layer: MapLayer) {
    const next = !workspace.map.layers[layer];
    workspace.map.layers[layer] = next;
    if ((layer === 'classification' || layer === 'uncertainty') && workspace.latestRun) {
      void workspace.loadMapField();
    }
    if (!next && layer === 'samples' && selected?.kind === 'sample') workspace.map.selected = null;
  }

  function select(feature: Selection) {
    workspace.map.selected = feature;
  }

  function exportView() {
    if (!dataset) return;
    const url = api.exportUrl(workspace.project!.id, {
      type: workspace.map.layers.uncertainty ? 'uncertainty' : 'hard',
      datasetId: dataset.id,
      method: workspace.map.method,
    });
    window.location.assign(url);
    workspace.notify(t('map.exportView'));
  }

  function retryField() {
    void workspace.loadMapField();
  }
</script>

<PageHeading
  title={t('map.title')}
  description={t('map.description')}
  eyebrow={workspace.project ? `#${workspace.project.id} · ${workspace.project.name}` : 'WBALC'}
>
  {#snippet actions()}
    <button class="button" onclick={exportView} disabled={!dataset || !workspace.latestRun}>
      <Download size={15} /> {t('map.exportView')}
    </button>
  {/snippet}
</PageHeading>

{#if !dataset}
  <div class="surface">
    <EmptyState title={t('map.noDataset')} hint={t('map.noDatasetHint')} />
  </div>
{:else}
  <div class="map-workspace">
    <div class="stack">
      <InteractiveMap {dataset} {hard} {uncertainty} labels={workspace.labels} onselect={select} />

      {#if workspace.fieldError}
        <div class="inline-error" role="alert">
          <X size={16} />
          <div>
            <strong>{t('map.noModel')}</strong>
            <span>{workspace.fieldError}</span>
          </div>
          <button class="button small" onclick={retryField}><RotateCw size={13} /> {t('common.retry')}</button>
        </div>
      {:else if !workspace.latestRun}
        <div class="surface section-box hint-box">
          <strong>{t('map.noModel')}</strong>
          <p>{t('map.noModelHint')}</p>
        </div>
      {/if}
    </div>

    <aside class="map-sidebar" aria-label={t('map.layers')}>
      <section class="surface layer-panel" aria-labelledby="layer-heading">
        <div class="panel-heading">
          <div class="panel-heading-title"><Layers size={16} strokeWidth={1.75} /><h2 id="layer-heading">{t('map.layers')}</h2></div>
          <span class="visible-count mono">{t('map.visible', { count: visible })}</span>
        </div>
        {#each layers as layer (layer.id)}
          <div class="layer-row-group" class:is-off={!workspace.map.layers[layer.id]}>
            <div class="layer-row">
              <span class="layer-icon"><layer.icon size={15} strokeWidth={1.7} /></span>
              <div class="layer-description"><strong>{layer.title}</strong><small>{layer.note}</small></div>
              <button
                class="layer-switch"
                role="switch"
                aria-checked={workspace.map.layers[layer.id]}
                aria-label={layer.title}
                onclick={() => toggle(layer.id)}
                ><span></span></button
              >
            </div>
            {#if layer.id === 'classification' || layer.id === 'uncertainty'}
              <div class="layer-opacity">
                <label for={`${layer.id}-opacity`}>
                  <span>{t('map.opacity')}</span><span class="mono ltr-numeric">{workspace.map.opacity}%</span>
                </label>
                <input
                  id={`${layer.id}-opacity`}
                  aria-label={t('map.opacity')}
                  type="range"
                  min="0"
                  max="100"
                  bind:value={workspace.map.opacity}
                  disabled={!workspace.map.layers[layer.id]}
                  style:--fill={`${workspace.map.opacity}%`}
                />
              </div>
            {/if}
            {#if layer.id === 'uncertainty'}
              <div class="layer-opacity">
                <label for="uncertainty-method"><span>{t('map.uncertaintyMethod')}</span></label>
                <select
                  id="uncertainty-method"
                  class="select"
                  value={workspace.map.method}
                  onchange={(event) => {
                    workspace.map.method = event.currentTarget.value as typeof workspace.map.method;
                    void workspace.loadMapField();
                  }}
                >
                  <option value="entropy">{t('map.method.entropy')}</option>
                  <option value="margin">{t('map.method.margin')}</option>
                  <option value="least_confidence">{t('map.method.leastConfidence')}</option>
                </select>
              </div>
            {/if}
          </div>
        {/each}
      </section>

      <section class="surface feature-panel" aria-labelledby="feature-heading">
        <div class="panel-heading">
          <div class="panel-heading-title"><Focus size={16} strokeWidth={1.75} /><h2 id="feature-heading">{t('map.selection')}</h2></div>
          {#if selected}
            <button class="icon-button" aria-label={t('map.clearSelection')} title={t('map.clearSelection')} onclick={() => (workspace.map.selected = null)}><X size={15} /></button>
          {/if}
        </div>

        {#if sample}
          <div class="panel-body feature-body">
            <div class="feature-name">
              <div class="feature-icon sample"><MapPin size={18} /></div>
              <div><strong>{sample.sampleId}</strong><small>{sample.className}</small></div>
            </div>
            <dl class="kv-list">
              <div><dt>{t('common.class')}</dt><dd style:color={classColor(sample.className, 0)}>{sample.className}</dd></div>
              <div><dt>{t('map.sampleReview')}</dt><dd>{sample.className}</dd></div>
              <div><dt>{t('common.dataset')}</dt><dd>{workspace.datasets.find((item) => item.id === sample.datasetId)?.name ?? '—'}</dd></div>
              <div><dt>{t('common.date')}</dt><dd>{date(sample.createdAt)}</dd></div>
              <div><dt>v</dt><dd>{integer(sample.version)}</dd></div>
              <div><dt>{t('arena.resolution')}</dt><dd>{sample.sampleType}</dd></div>
            </dl>
            <div class="feature-action">
              <button
                class="button-link"
                onclick={() => {
                  workspace.selectedSample = sample.sampleId;
                  workspace.go('learning');
                }}>{t('map.openInLearning')}</button
              >
            </div>
          </div>
        {:else if cell}
          <div class="panel-body feature-body">
            <div class="feature-name">
              <div class="feature-icon"><Layers size={18} /></div>
              <div>
                <strong>{cell.className ?? t('common.notAvailable')}</strong>
                <small>r{cell.row} · c{cell.col}</small>
              </div>
            </div>
            <dl class="kv-list">
              <div><dt>{t('map.cell')}</dt><dd class="ltr-numeric">{cell.row}, {cell.col}</dd></div>
              <div><dt>{t('map.predictedClass')}</dt><dd>{cell.className ?? '—'}</dd></div>
              <div><dt>{t('common.validity')}</dt><dd>{cell.valid ? '✓' : '—'}</dd></div>
              <div><dt>{t('map.uncertainty')}</dt><dd>{percent(cell.uncertainty)}</dd></div>
              <div>
                <dt>{t('map.grid')}</dt>
                <dd>{hard?.resolution === 'pixel' ? t('map.grid.pixel') : t('map.grid.patch', { size: hard?.grid.patchSize ?? 0 })}</dd>
              </div>
              <div><dt>{t('common.model')}</dt><dd>#{hard?.iteration ?? '—'}</dd></div>
            </dl>
          </div>
        {:else}
          <EmptyState title={t('map.noSelection')} hint={t('map.noSelectionHint')} />
        {/if}
      </section>

      <section class="surface section-box">
        <div class="section-heading"><div><h2>{t('map.dataset')}</h2><p>{dataset.name}</p></div></div>
        <dl class="kv-list">
          <div><dt>{t('temporal.grid')}</dt><dd class="ltr-numeric">{integer(dataset.width)} × {integer(dataset.height)}</dd></div>
          <div><dt>{t('temporal.channels')}</dt><dd>{integer(dataset.bands)} · {dataset.dtype}</dd></div>
          <div><dt>{t('temporal.crs')}</dt><dd>{dataset.crs ?? t('map.pixelSpace')}</dd></div>
          <div><dt>{t('map.grid')}</dt><dd>{dataset.patchGrid ? `${dataset.patchGrid.patchSize}px / ${dataset.patchGrid.stride}px` : '—'}</dd></div>
          <div><dt>{t('project.created')}</dt><dd>{date(dataset.createdAt)}</dd></div>
          <div><dt>{t('common.source')}</dt><dd>{number(dataset.sizeBytes / 1_048_576, 1)} MB</dd></div>
          <div>
            <dt>{t('project.studyArea')}</dt>
            <dd>
              {#if workspace.project?.studyAreaGeometry}
                {t('map.studyAreaRecorded')}
              {:else}
                {t('project.noGeometry')}
              {/if}
            </dd>
          </div>
        </dl>
        {#if workspace.project?.studyAreaGeometry}
          <p class="mask-note">{t('map.studyAreaNotMasked')}</p>
        {/if}
        {#if dataset.georeferenced === false && dataset.georefReason}
          <p class="mask-note">{t('map.pixelSpaceReason', { reason: t(georefKey(dataset.georefReason)) })}</p>
        {/if}
      </section>
    </aside>
  </div>
{/if}

<style>
  .map-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 292px; align-items: start; gap: 15px; }
  .map-sidebar { display: grid; gap: 14px; min-width: 0; }
  .visible-count { color: #92a9bf; font-size: 10px; }
  .layer-row-group { margin-inline: 13px; }
  .layer-row-group + .layer-row-group { border-top: 1px solid var(--line); }
  .mask-note { margin: 9px 13px 11px; color: var(--faint); font-size: 10.5px; line-height: 1.5; }
  .layer-row { display: flex; align-items: center; gap: 10px; min-height: 56px; padding: 6px 0; }
  .layer-icon { display: grid; place-items: center; width: 29px; height: 29px; flex: none; color: #8fd6d0; background: #14283a; border: 1px solid #24404f; border-radius: 5px; }
  .layer-description { display: grid; gap: 3px; min-width: 0; }
  .layer-description strong { font-size: 12px; font-weight: 570; line-height: 1.25; }
  .layer-description small { color: var(--faint); font-size: 10.5px; line-height: 1.25; }
  .layer-switch { width: 30px; height: 17px; flex: none; margin-inline-start: auto; display: flex; align-items: center; padding: 2px; background: #263848; border: 1px solid #496174; border-radius: 15px; transition: background 160ms, border-color 160ms; }
  .layer-switch span { width: 11px; height: 11px; border-radius: 50%; background: #a2b2be; transition: transform 160ms, background 160ms; }
  .layer-switch[aria-checked='true'] { background: #3c9b91; border-color: #55b9a9; }
  .layer-switch[aria-checked='true'] span { transform: translateX(13px); background: #eafff9; }
  .layer-opacity { margin: -1px 0 12px 39px; }
  .layer-opacity label { display: flex; justify-content: space-between; font-size: 10.5px; color: #a3b4c9; margin-bottom: 4px; }
  .layer-opacity .mono { color: #94e8db; }
  .layer-opacity input[type='range'] { display: block; appearance: none; cursor: pointer; width: 100%; height: 14px; margin: 0; background: transparent; }
  .layer-opacity input[type='range']:disabled { cursor: not-allowed; opacity: 0.4; }
  .layer-opacity input[type='range']::-webkit-slider-runnable-track { height: 3px; border-radius: 3px; background: linear-gradient(to right, #63dcca var(--fill), #33485b var(--fill)); }
  .layer-opacity input[type='range']::-moz-range-track { height: 3px; border-radius: 3px; background: linear-gradient(to right, #63dcca var(--fill), #33485b var(--fill)); }
  .layer-opacity input[type='range']::-webkit-slider-thumb { appearance: none; width: 11px; height: 11px; margin-top: -4px; border-radius: 50%; background: #87e9d9; border: 1px solid #b6f1e6; }
  .layer-opacity input[type='range']::-moz-range-thumb { width: 10px; height: 10px; border-radius: 50%; background: #87e9d9; border: 1px solid #b6f1e6; }
  .layer-opacity .select { width: 100%; min-height: 30px; font-size: 11px; }
  .is-off .layer-icon { opacity: 0.56; }
  .feature-name { display: flex; gap: 10px; align-items: center; margin: 0 0 9px; }
  .feature-icon { display: grid; place-items: center; width: 36px; height: 36px; flex: none; border-radius: 6px; background: #173b5a; border: 1px solid #28567b; color: #79caff; }
  .feature-icon.sample { background: #453724; border-color: #69563a; color: var(--warn); }
  .feature-name strong { display: block; font-size: 14px; font-weight: 640; }
  .feature-name small { display: block; font-size: 10.5px; color: var(--faint); margin-top: 1px; }
  .feature-body .kv-list > div { padding-block: 7px; }
  .feature-body .kv-list dd { font-size: 11px; }
  .feature-action { border-top: 1px solid var(--line); margin-top: 5px; padding-top: 10px; }
  .hint-box { display: grid; gap: 4px; }
  .hint-box strong { font-size: 12.5px; }
  .hint-box p { margin: 0; color: var(--faint); font-size: 11.5px; }
  @media (max-width: 1150px) {
    .map-workspace { grid-template-columns: minmax(0, 1fr) 252px; gap: 12px; }
  }
  @media (max-width: 920px) {
    .map-workspace { grid-template-columns: minmax(0, 1fr); }
    .map-sidebar { grid-template-columns: 1fr 1fr; align-items: start; gap: 12px; }
  }
  @media (max-width: 590px) {
    .map-sidebar { grid-template-columns: minmax(0, 1fr); }
  }
</style>

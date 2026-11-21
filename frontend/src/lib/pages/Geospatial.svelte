<script lang="ts">
  import { Download, Droplets, Focus, Layers, MapPin, RotateCw, Scan, X } from '@lucide/svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import InteractiveMap from '../components/InteractiveMap.svelte';
  import RasterLayers from '../components/RasterLayers.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import { api } from '../client/api';
  import { classColor } from '../palette';
  import { getWorkspace, type MapLayer, type Selection } from '../state.svelte';
  import { useT } from '../t.svelte';
  import type { DatasetView, MapFieldView, SceneView, WaterThresholdView } from '../types';
  import { sameNativeGrid } from '../map-inspection';
  import { assessGeoreferencing } from '../geo';
  import { NEAR_DAYS, epochLabel, groupEpochs, primaryScene } from '../epochs';

  const workspace = getWorkspace();
  const { t, integer, percent, number, date } = useT();

  const scene = $derived(workspace.scenes.find(candidate => workspace.mapScene?.projectId === workspace.project?.id && candidate.id === workspace.mapScene?.id) ??
    (!workspace.dataset ? workspace.scenes[0] : undefined));

  /* ------------------------------------------------ near-date epoch grouping */

  const epochs = $derived(groupEpochs(workspace.scenes));
  const activeEpoch = $derived(epochs.findIndex(group => scene && group.some(candidate => candidate.id === scene.id)));

  function gotoEpoch(index: number) {
    const group = epochs[index];
    if (!group || !workspace.project) return;
    const primary = primaryScene(group, scene?.id);
    const sibling = group.find(candidate => candidate.id !== primary.id && sameNativeGrid(primary, candidate));
    compareId = sibling?.id ?? '';
    workspace.mapScene = { projectId: workspace.project.id, id: primary.id };
    workspace.map.bandMode = 'true-color';
    workspace.map.layers.imagery = true;
    workspace.map.selected = null;
    workspace.notify(t('map.epoch.selected', { label: epochLabel(group) }));
  }

  function epochSummary(group: SceneView[]): string {
    const sensors = [...new Set(group.map(candidate => candidate.sensor))].join(', ');
    return `${epochLabel(group)} · ${t('map.epoch.nScenes', { count: group.length })} · ${sensors}`;
  }

  /* ------------------------------------------------- threshold water layer */

  let thresholdField = $state<WaterThresholdView | null>(null);
  let thresholdSceneId = $state<string | null>(null);
  let thresholdLoading = $state(false);
  let thresholdError = $state<string | null>(null);

  async function loadThreshold() {
    const target = scene?.id;
    if (!target || !workspace.project || thresholdLoading) return;
    if (thresholdSceneId === target && thresholdField) return;
    thresholdLoading = true;
    thresholdError = null;
    try {
      thresholdField = await api.sceneWaterThreshold(workspace.project.id, target);
      thresholdSceneId = target;
    } catch (error) {
      thresholdField = null;
      thresholdSceneId = null;
      thresholdError = error instanceof Error ? error.message : String(error);
    } finally {
      thresholdLoading = false;
    }
  }
  // A different scene invalidates the cached threshold product.
  $effect(() => {
    const id = scene?.id ?? null;
    if (thresholdSceneId !== id) {
      thresholdField = null;
      thresholdSceneId = null;
      thresholdError = null;
      if (id && workspace.map.layers.threshold) void loadThreshold();
    }
  });
  const thresholdShown = $derived(workspace.map.layers.threshold && scene ? thresholdField : null);

  function sceneRaster(acquisition: SceneView): DatasetView {
    // Prefer the real derived dataset row: it carries the identity (bands,
    // schema, content hash) the model layers need. Legacy scenes without a
    // link fall back to a synthetic view over the scene file endpoint.
    const derived = acquisition.datasetId
      ? workspace.datasets.find((item) => item.id === acquisition.datasetId)
      : null;
    if (derived) return derived;
    const geo = assessGeoreferencing({ crsCode: acquisition.crs, transform: acquisition.transform, width: acquisition.width, height: acquisition.height });
    return {
      id: `scene:${acquisition.id}`, projectId: acquisition.projectId, name: acquisition.sourceFilename,
      origin: 'scene',
      url: `/api/projects/${encodeURIComponent(acquisition.projectId)}/scenes/${encodeURIComponent(acquisition.id)}/file`,
      crs: acquisition.crs, transform: acquisition.transform, width: acquisition.width, height: acquisition.height, bands: acquisition.bandCount,
      dtype: acquisition.bandDtypes?.join(', ') ?? '—', nodata: null, bounds: acquisition.bounds, sizeBytes: acquisition.sizeBytes,
      contentSha256: null, createdAt: acquisition.registeredAt, georeferenced: geo.mode === 'map', georefReason: geo.reason,
      bandNames: acquisition.bandNames?.map(name => name ?? '') ?? null, bandSchemaDeclared: Boolean(acquisition.bandNames?.every(Boolean)),
      sensor: acquisition.sensor, patchGrid: null,
    };
  }
  const dataset = $derived(scene ? sceneRaster(scene) : workspace.dataset);
  let compareId = $state('');
  const compareCandidates = $derived(scene ? workspace.scenes.filter(other => other.id !== scene.id && other.acquisitionDateTime && scene.acquisitionDateTime &&
    other.acquisitionDateTime.slice(0, 10) !== scene.acquisitionDateTime.slice(0, 10) && sameNativeGrid(scene, other)) : []);
  const compareScene = $derived(compareCandidates.find(other => other.id === compareId));
  const comparison = $derived(compareScene ? { raster: sceneRaster(compareScene), left: scene?.acquisitionDateTime?.slice(0, 10) ?? '', right: compareScene.acquisitionDateTime?.slice(0, 10) ?? '' } : null);
  /**
   * Model layers are only painted from a field computed for the raster on
   * screen — the workspace clears its field when the target changes, so this
   * identity check keeps a stale cross-date product from ever showing.
   */
  const fieldIsCurrent = $derived(
    Boolean(dataset) && workspace.fieldDatasetId === String(dataset!.id),
  );
  const hard = $derived(fieldIsCurrent ? workspace.field.hard as MapFieldView | null : null);
  const uncertainty = $derived(fieldIsCurrent ? workspace.field.uncertainty as MapFieldView | null : null);
  const binaryField = $derived(fieldIsCurrent ? workspace.field.binary as MapFieldView | null : null);
  /** A field exists for the active raster + latest run, or one is arriving. */
  const fieldReady = $derived(
    Boolean(workspace.latestRun) && fieldIsCurrent && Boolean(hard) && !workspace.fieldError,
  );
  /** Derived water product is only meaningful when the run recorded one. */
  const binary = $derived(hard?.binary ?? uncertainty?.binary ?? null);
  const selected = $derived(workspace.map.selected);
  /** Provenance of the field currently painted, or null before a first load. */
  const provenance = $derived(hard ?? uncertainty);
  const schemaConflict = $derived(workspace.fieldErrorStatus === 409);

  // One loader for every entry path: date switches (scene → dataset), raster
  // source changes, hash navigation and fresh runs all converge here.
  $effect(() => {
    const target = scene ? scene.datasetId : workspace.dataset?.id ?? null;
    const run = workspace.latestRun?.id ?? null;
    if (target && run) void workspace.loadMapField();
  });

  const layers = $derived([
    { id: 'imagery' as const, title: t('map.layer.imagery'), note: t('map.layer.imageryNote'), icon: Scan },
    // Model-free water detection is meaningful before any training exists, so
    // it is offered exactly where models are not: on scene views.
    ...(scene
      ? [{ id: 'threshold' as const, title: t('map.layer.threshold'), note: t('map.layer.thresholdNote'), icon: Droplets }]
      : []),
    { id: 'classification' as const, title: t('map.layer.classification'), note: t('map.layer.classificationNote'), icon: Layers },
    // Only offered when the run actually recorded a water interpretation: a toggle
    // that always fails is worse than no toggle.
    ...(binary
      ? [{ id: 'binary' as const, title: t('map.layer.binary'), note: t('map.layer.binaryNote'), icon: Droplets }]
      : []),
    { id: 'uncertainty' as const, title: t('map.layer.uncertainty'), note: t('map.layer.uncertaintyNote'), icon: Focus },
    { id: 'samples' as const, title: t('map.layer.samples'), note: t('map.layer.samplesNote'), icon: MapPin },
  ]);

  const visible = $derived(Object.values(workspace.map.layers).filter(Boolean).length);

  /**
   * Labels painted on the map belong to the raster on screen: dataset-scoped
   * labels are filtered by the active dataset, and dataset-agnostic imports
   * only appear on the training raster view.
   */
  const activeLabels = $derived(
    workspace.labels.filter((item) =>
      item.datasetId ? item.datasetId === String(dataset?.id ?? '') : !scene,
    ),
  );

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
    // A model layer cannot be switched on for a raster the latest run has not
    // classified (or cannot classify): the switch stays off until a field exists.
    if (
      (layer === 'classification' || layer === 'uncertainty' || layer === 'binary') &&
      next &&
      workspace.latestRun &&
      !fieldReady
    ) {
      return;
    }
    workspace.map.layers[layer] = next;
    if (
      (layer === 'classification' || layer === 'uncertainty' || layer === 'binary') &&
      workspace.latestRun
    ) {
      void workspace.loadMapField();
    }
    if (layer === 'threshold' && next && scene) void loadThreshold();
    if (!next && layer === 'samples' && selected?.kind === 'sample') workspace.map.selected = null;
  }

  function select(feature: Selection) {
    workspace.map.selected = feature;
  }

  const exportReason = $derived(!dataset ? 'ux.exportData' : scene ? 'ux.exportScene' : !workspace.latestRun ? 'ux.exportTrain' :
    !(workspace.map.layers.classification || workspace.map.layers.uncertainty || workspace.map.layers.binary) ? 'ux.exportLayer' : null);

  function exportView() {
    if (!dataset || scene) return;
    // Export what the operator is looking at: the derived binary product is its
    // own file, never a reinterpretation of the three-class one.
    const type = workspace.map.layers.uncertainty
      ? 'uncertainty'
      : workspace.map.layers.binary && binary?.available
        ? 'binary'
        : 'hard';
    const url = api.exportUrl(workspace.project!.id, {
      type,
      datasetId: dataset.id,
      method: workspace.map.method,
      acceptUnverifiedSchema: workspace.schemaOverride,
    });
    window.location.assign(url);
    workspace.notify(t('map.exportView'));
  }

  function retryField() {
    void workspace.loadMapField();
  }

  /**
   * The engine refused because the raster's ordered bands cannot be proven to
   * match the model's. Predicting anyway is a decision the operator has to make
   * explicitly — and it gets recorded with the product, not hidden.
   */
  async function overrideSchema() {
    await workspace.acceptSchemaOverride();
    if (workspace.field && !workspace.fieldError) workspace.notify(t('map.schema.overrideRecorded'));
  }
</script>

<PageHeading
  title={t('map.title')}
  description={t('map.description')}
  eyebrow={workspace.project ? `#${workspace.project.id} · ${workspace.project.name}` : 'WBALC'}
>
  {#snippet actions()}
    <div class="export-action">
      <button class="button" onclick={exportView} disabled={Boolean(exportReason)} aria-describedby={exportReason ? 'export-reason' : undefined}>
        <Download size={15} /> {t('map.exportView')}
      </button>
      {#if exportReason}<small id="export-reason">{t(exportReason)}
        {#if exportReason === 'ux.exportTrain'}<a href="#/learning" onclick={() => workspace.go('learning')}>{t('nav.learning')}</a>
        {:else if exportReason === 'ux.exportData'}<a href="#/intake" onclick={() => workspace.go('intake')}>{t('nav.intake')}</a>{/if}
      </small>{/if}
    </div>
  {/snippet}
</PageHeading>

{#if workspace.scenes.length}
  <label class="field raster-source">{t('layer.source')}    <select class="select" value={scene?.id ?? ''} onchange={(event) => {
      compareId = '';
      workspace.mapScene = event.currentTarget.value && workspace.project ? { projectId: workspace.project.id, id: event.currentTarget.value } : null;
      workspace.map.bandMode = 'true-color';
      workspace.map.layers.imagery = true;
      workspace.map.selected = null;
      // The field effect re-loads the model layers for the newly active raster.
    }}>
      {#if workspace.dataset}<option value="">{t('intake.dataset')} · {workspace.dataset.name}</option>{/if}
      {#each workspace.scenes as acquisition (acquisition.id)}
        <option value={acquisition.id}>{acquisition.acquisitionDateTime?.slice(0, 10) ?? '—'} · {acquisition.sensor} · {acquisition.sourceFilename}</option>
      {/each}
    </select>
  </label>
{/if}

{#if epochs.length > 1}
  <div class="surface epoch-panel">
    <div class="epoch-head">
      <label for="epoch-range">{t('map.dateSlider')}</label>
      <small>{t('map.epoch.count', { count: epochs.length, days: NEAR_DAYS })}</small>
    </div>
    <input
      id="epoch-range"
      class="epoch-range"
      type="range"
      min="0"
      max={epochs.length - 1}
      value={activeEpoch < 0 ? 0 : activeEpoch}
      aria-label={t('map.dateSlider')}
      oninput={(event) => gotoEpoch(Number(event.currentTarget.value))}
    />
    <div class="epoch-scale" dir="ltr">
      <span class="mono">{epochSummary(epochs[0])}</span>
      <span class="mono">{epochSummary(epochs[epochs.length - 1])}</span>
    </div>
  </div>
{/if}

{#if scene}
  <label class="field raster-source">{t('inspection.compare')}
    <select class="select" bind:value={compareId} disabled={!compareCandidates.length}>
      <option value="">{t('inspection.noCompare')}</option>
      {#each compareCandidates as other (other.id)}
        <option value={other.id}>{other.acquisitionDateTime?.slice(0, 10)} · {other.sensor} · {other.sourceFilename}</option>
      {/each}
    </select>
    {#if !compareCandidates.length}<small>{t('inspection.noMatch')}</small>{/if}
  </label>
{/if}

{#if !dataset}
  <div class="surface">
    <EmptyState title={t('map.noDataset')} hint={t('map.noDatasetHint')} />
  </div>
{:else}
  <div class="map-workspace">
    <div class="stack">
      {#key dataset.id}
        <InteractiveMap {dataset} {comparison} {hard} {uncertainty} {binaryField} threshold={thresholdShown} labels={activeLabels} onselect={select} />
        <RasterLayers {dataset} imageryOnly={Boolean(scene)} />
      {/key}

      {#if workspace.fieldError}
        <div class="alert alert-destructive" role="alert">
          <X size={15} class="alert-icon" />
          <div>
            <strong>{schemaConflict ? t('map.schema.unverified') : t('map.noModel')}</strong>
            <span>{workspace.fieldError}</span>
          </div>
          {#if schemaConflict && !workspace.schemaOverride}
            <button class="button small" onclick={overrideSchema}>
              {t('map.schema.accept')}
            </button>
          {:else}
            <button class="button small" onclick={retryField}><RotateCw size={13} /> {t('common.retry')}</button>
          {/if}
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
          {@const needsField = layer.id === 'classification' || layer.id === 'uncertainty' || layer.id === 'binary'}
          <div class="layer-row-group" class:is-off={!workspace.map.layers[layer.id]}>
            <div class="layer-row">
              <span class="layer-icon"><layer.icon size={15} strokeWidth={1.7} /></span>
              <div class="layer-description"><strong>{layer.title}</strong><small>{layer.note}</small></div>
              <button
                class="layer-switch"
                role="switch"
                aria-checked={workspace.map.layers[layer.id]}
                aria-label={layer.title}
                disabled={needsField && Boolean(workspace.latestRun) && !fieldReady}
                onclick={() => toggle(layer.id)}
                ><span></span></button
              >
            </div>
            {#if needsField && workspace.latestRun && !fieldReady}
              <div class="layer-field-state">
                {#if workspace.fieldLoading}
                  <small role="status"><span class="spinner"></span> {t('common.loading')}</small>
                {:else}
                  <small>{t('map.notClassifiedDate')}</small>
                  <button class="button small" disabled={workspace.fieldLoading} onclick={retryField}>
                    <RotateCw size={12} /> {t('map.classifyDate')}
                  </button>
                {/if}
              </div>
            {/if}
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
            {#if layer.id === 'threshold'}
              <div class="layer-opacity">
                {#if thresholdLoading}
                  <small role="status">{t('common.loading')}</small>
                {:else if thresholdError}
                  <small class="threshold-error" role="alert">{thresholdError}</small>
                {:else if thresholdShown}
                  <small class="mono ltr-numeric">
                    {t('map.threshold.method', { index: thresholdShown.index.toUpperCase(), method: thresholdShown.method, threshold: number(thresholdShown.threshold, 4) })}
                  </small>
                {/if}
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
              <div><dt>{t('common.class')}</dt><dd style:color={classColor(sample.className, workspace.project?.classes.indexOf(sample.className) ?? -1)}>{sample.className}</dd></div>
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

      {#if workspace.project}
        <section class="surface section-box" aria-labelledby="taxonomy-heading">
          <div class="section-heading">
            <div>
              <h2 id="taxonomy-heading">{t('map.taxonomy.title')}</h2>
              <p>
                {workspace.project.taxonomy?.version
                  ? `${t('map.taxonomy.internal')} · ${workspace.project.taxonomy.version}`
                  : t('map.taxonomy.generic')}
              </p>
            </div>
          </div>
          <dl class="kv-list">
            <div>
              <dt>{t('map.taxonomy.internal')}</dt>
              <dd>{(workspace.project.taxonomy?.classes ?? workspace.project.classes).join(', ')}</dd>
            </div>
            {#if binary}
              <div>
                <dt>{t('map.layer.binary')}</dt>
                <dd>
                  {binary.interpretation === 'open_water_vs_other'
                    ? t('map.binary.interpretation.openWaterVsOther')
                    : t('map.binary.interpretation.waterVsNonWater')}
                </dd>
              </div>
              <div>
                <dt>{t('map.binary.mapping')}</dt>
                <dd>
                  {#if binary.available}
                    {Object.entries(binary.mapping)
                      .map(([name, role]) => `${name} → ${role === 'water' ? t('map.binary.water') : t('map.binary.nonWater')}`)
                      .join(' · ')}
                  {:else}
                    {t('map.binary.unavailable')}
                  {/if}
                </dd>
              </div>
            {/if}
          </dl>
          {#if binary && !binary.available}
            <p class="mask-note">{binary.reason}</p>
          {:else if binary}
            <p class="mask-note">{t('map.binary.note')}</p>
          {/if}
        </section>
      {/if}

      {#if provenance}
        <section class="surface section-box" aria-labelledby="provenance-heading">
          <div class="section-heading">
            <div>
              <h2 id="provenance-heading">{t('map.schema.title')}</h2>
              <p>
                {#if provenance.bandSchemaVerified}
                  {t('map.schema.verified')}
                {:else}
                  {t('map.schema.unverified')}
                {/if}
              </p>
            </div>
          </div>
          <dl class="kv-list">
            <div><dt>{t('common.model')}</dt><dd class="ltr-numeric">#{provenance.iteration}</dd></div>
            <div>
              <dt>{t('map.grid')}</dt>
              <dd>{provenance.resolution === 'pixel' ? t('map.grid.pixel') : t('map.grid.patch', { size: provenance.grid.patchSize })}</dd>
            </div>
            <div>
              <dt>{t('map.studyAreaApplied')}</dt>
              <dd>{provenance.studyAreaApplied ? t('map.studyAreaApplied') : t('map.studyAreaNotApplied')}</dd>
            </div>
            {#if provenance.bandSchemaReason}
              <div><dt>{t('map.schema.reason')}</dt><dd>{provenance.bandSchemaReason}</dd></div>
            {/if}
          </dl>
          {#if !provenance.bandSchemaVerified}
            <p class="mask-note">{t('map.schema.overrideHint')}</p>
          {/if}
          {#if provenance.stale}
            <p class="mask-note">{t('map.stale')}</p>
          {/if}
        </section>
      {/if}

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
            <dt>{t('map.contentHash')}</dt>
            <dd class="mono ltr-numeric small">
              {dataset.contentSha256
                ? `${dataset.contentSha256.slice(0, 16)}…`
                : t('map.contentHashMissing')}
            </dd>
          </div>
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
          <div>
            <dt>{t('map.studyAreaApplied')}</dt>
            <dd>
              {#if provenance}
                {provenance.studyAreaApplied ? t('map.studyAreaApplied') : t('map.studyAreaNotApplied')}
              {:else}
                —
              {/if}
            </dd>
          </div>
          <div>
            <dt>{t('map.schema.title')}</dt>
            <dd>
              {#if dataset.bandSchemaDeclared && dataset.bandNames}
                {dataset.bandNames.join(', ')}
              {:else}
                {t('map.schema.undeclared')}
              {/if}
            </dd>
          </div>
        </dl>
        {#if workspace.project?.studyAreaGeometry}
          <p class="mask-note">{t('map.studyAreaMaskHint')}</p>
        {/if}
        {#if dataset.georeferenced === false && dataset.georefReason}
          <p class="mask-note">{t('map.pixelSpaceReason', { reason: t(georefKey(dataset.georefReason)) })}</p>
        {/if}
      </section>
    </aside>
  </div>
{/if}

<style>
  .export-action { display: grid; justify-items: end; gap: 5px; }
  .export-action small { color: var(--muted); }
  .export-action a { text-decoration: underline; }
  .raster-source { max-width: 420px; margin-block-end: 14px; }
  .raster-source select { min-width: 0; width: 100%; }
  .map-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 292px; align-items: start; gap: 15px; }
  .map-sidebar { display: grid; gap: 14px; min-width: 0; }
  .visible-count { color: var(--faint); font-size: 10px; }
  .layer-row-group { margin-inline: 13px; }
  .layer-row-group + .layer-row-group { border-top: 1px solid var(--line); }
  .mask-note { margin: 9px 13px 11px; color: var(--faint); font-size: 10.5px; line-height: 1.5; }
  .layer-row { display: flex; align-items: center; gap: 10px; min-height: 56px; padding: 6px 0; }
  .layer-icon { display: grid; place-items: center; width: 29px; height: 29px; flex: none; color: var(--accent); background: var(--control-bg); border: 1px solid var(--control-border); border-radius: 5px; }
  .layer-description { display: grid; gap: 3px; min-width: 0; }
  .layer-description strong { font-size: 12px; font-weight: 570; line-height: 1.25; }
  .layer-description small { color: var(--faint); font-size: 10.5px; line-height: 1.25; }
  .layer-switch { width: 30px; height: 17px; flex: none; margin-inline-start: auto; display: flex; align-items: center; padding: 2px; background: var(--control-border); border: 1px solid var(--control-border); border-radius: 15px; transition: background 160ms, border-color 160ms; }
  .layer-switch span { width: 11px; height: 11px; border-radius: 50%; background: var(--faint); transition: transform 160ms, background 160ms; }
  .layer-switch[aria-checked='true'] { background: var(--control-border); border-color: var(--success); }
  .layer-switch[aria-checked='true'] span { transform: translateX(13px); background: var(--ink); }
  .layer-opacity { margin: -1px 0 12px 39px; }
  .layer-opacity label { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--faint); margin-bottom: 4px; }
  .layer-opacity .mono { color: var(--accent); }
  .layer-opacity input[type='range'] { display: block; appearance: none; cursor: pointer; width: 100%; height: 14px; margin: 0; background: transparent; }
  .layer-opacity input[type='range']:disabled { cursor: not-allowed; opacity: 0.4; }
  .layer-opacity input[type='range']::-webkit-slider-runnable-track { height: 3px; border-radius: 3px; background: linear-gradient(to right, var(--accent) var(--fill), var(--control-border) var(--fill)); }
  .layer-opacity input[type='range']::-moz-range-track { height: 3px; border-radius: 3px; background: linear-gradient(to right, var(--accent) var(--fill), var(--control-border) var(--fill)); }
  .layer-opacity input[type='range']::-webkit-slider-thumb { appearance: none; width: 11px; height: 11px; margin-top: -4px; border-radius: 50%; background: var(--accent); border: 1px solid var(--accent-foreground); }
  .layer-opacity input[type='range']::-moz-range-thumb { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); border: 1px solid var(--accent-foreground); }
  .layer-opacity .select { width: 100%; min-height: 30px; font-size: 11px; }
  .is-off .layer-icon { opacity: 0.56; }
  .layer-field-state { margin: -1px 0 12px 39px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .layer-field-state small { color: var(--warn); font-size: 10.5px; }
  .layer-field-state .button { flex: none; }
  .layer-field-state .spinner { display: inline-block; width: 10px; height: 10px; border-radius: 50%; border: 2px solid var(--control-border); border-top-color: var(--accent); animation: geospin 700ms linear infinite; vertical-align: -1px; margin-inline-end: 4px; }
  @keyframes geospin { to { transform: rotate(360deg); } }
  .feature-name { display: flex; gap: 10px; align-items: center; margin: 0 0 9px; }
  .feature-icon { display: grid; place-items: center; width: 36px; height: 36px; flex: none; border-radius: 6px; background: var(--control-bg); border: 1px solid var(--control-border); color: var(--info); }
  .feature-icon.sample { background: var(--control-bg); border-color: var(--control-border); color: var(--warn); }
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

  /* Near-date epoch slider */
  .epoch-panel { padding: 12px 14px; display: grid; gap: 8px; }
  .epoch-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .epoch-head label { font-size: 13px; font-weight: 650; }
  .epoch-head small { color: var(--muted); }
  .epoch-range { width: 100%; accent-color: var(--accent); }
  .epoch-scale { display: flex; justify-content: space-between; gap: 12px; font-size: 11px; color: var(--muted); }
  .epoch-scale span { overflow-wrap: anywhere; }
  .threshold-error { color: var(--danger, #e5484d); overflow-wrap: anywhere; }
</style>

<script lang="ts">
  import {
    ArrowRight,
    ArrowRightLeft,
    ChartNoAxesCombined,
    Download,
    Layers,
    Satellite,
    ScanLine,
    Sigma,
  } from '@lucide/svelte';
  import { api, ClientError } from '../client/api';
  import EmptyState from '../components/EmptyState.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import TimelineChart, { type TimelinePoint } from '../components/TimelineChart.svelte';
  import { classColor } from '../palette';
  import { getWorkspace } from '../state.svelte';
  import { useT } from '../t.svelte';
  import type {
    FusionView,
    SceneAnalysisView,
    SceneView,
    TemporalComparisonView,
    TemporalSeriesView,
  } from '../types';

  const workspace = getWorkspace();
  const { t, date, integer, number, percent } = useT();

  let selectedId = $state<string | null>(null);
  let referenceId = $state<string | null>(null);
  let sensor = $state<'all' | 'Sentinel-1' | 'Sentinel-2'>('all');

  // ---- Phase 4: classification results, change analysis, late fusion
  let analyses = $state<SceneAnalysisView[]>([]);
  let series = $state<TemporalSeriesView | null>(null);
  let seriesError = $state<string | null>(null);
  let comparison = $state<TemporalComparisonView | null>(null);
  let mismatch = $state<string | null>(null);
  let alignOnto = $state<string | null>(null);
  let fusions = $state<FusionView[]>([]);
  let fusionError = $state<string | null>(null);
  let fusionRule = $state<'weighted_probability' | 'weighted_vote' | 'priority'>(
    'weighted_probability',
  );
  let fusionMissing = $state<'require_all' | 'renormalise'>('require_all');
  let fusionTarget = $state<string | null>(null);
  let busy = $state<'classify' | 'compare' | 'fusion' | null>(null);
  let feedback = $state<string | null>(null);

  const sorted = $derived(
    [...workspace.scenes].sort((a, b) => {
      const aDate = a.acquisitionDateTime ? Date.parse(a.acquisitionDateTime) : 0;
      const bDate = b.acquisitionDateTime ? Date.parse(b.acquisitionDateTime) : 0;
      return bDate - aDate;
    }),
  );

  const filtered = $derived(
    sensor === 'all' ? sorted : sorted.filter((scene) => scene.sensor === sensor),
  );

  // Default to the two newest acquisitions once scenes arrive.
  $effect(() => {
    if (!sorted.length) return;
    if (!selectedId || !sorted.some((scene) => scene.id === selectedId)) {
      selectedId = sorted[0].id;
    }
    if (!referenceId || !sorted.some((scene) => scene.id === referenceId)) {
      referenceId = sorted[1]?.id ?? sorted[0].id;
    }
  });

  const selected = $derived(sorted.find((scene) => scene.id === selectedId) ?? null);
  const reference = $derived(sorted.find((scene) => scene.id === referenceId) ?? null);

  /** Native-grid equality: compared, never enforced. RSAL never aligns scenes. */
  const gridMatch = $derived.by(() => {
    if (!selected || !reference) return 'unknown' as const;
    const complete = (scene: SceneView) =>
      Boolean(scene.crs) &&
      scene.width > 0 &&
      scene.height > 0 &&
      scene.pixelSizeX !== null &&
      scene.pixelSizeY !== null;
    if (!complete(selected) || !complete(reference)) return 'unknown' as const;
    const same =
      selected.crs === reference.crs &&
      selected.width === reference.width &&
      selected.height === reference.height &&
      Math.abs((selected.pixelSizeX ?? 0) - (reference.pixelSizeX ?? 0)) < 1e-9 &&
      Math.abs((selected.pixelSizeY ?? 0) - (reference.pixelSizeY ?? 0)) < 1e-9;
    return same ? ('same' as const) : ('different' as const);
  });

  const timeline = $derived<TimelinePoint[]>(
    sorted
      .filter((scene) => scene.acquisitionDateTime)
      .map((scene) => ({
        id: scene.id,
        date: Date.parse(scene.acquisitionDateTime!),
        label: scene.sourceFilename,
        sensor: scene.sensor,
        kind: 'scene' as const,
      })),
  );

  function swap() {
    const before = referenceId;
    referenceId = selectedId;
    selectedId = before;
  }

  // ---- Phase 4 helpers -------------------------------------------------------
  const project = $derived(workspace.project);

  /** Latest analysis per scene id, so the timeline and panels agree. */
  const latestAnalyses = $derived.by(() => {
    const map = new Map<string, SceneAnalysisView>();
    for (const analysis of analyses) map.set(analysis.sceneId, analysis);
    return map;
  });

  const classifiedCount = $derived(latestAnalyses.size);

  const selectedAnalysis = $derived(selectedId ? latestAnalyses.get(selectedId) ?? null : null);
  const referenceAnalysis = $derived(referenceId ? latestAnalyses.get(referenceId) ?? null : null);

  /** Two classified scenes on identical grids → the engine will compare directly. */
  const comparisonReady = $derived(
    Boolean(selectedAnalysis && referenceAnalysis) &&
      selectedAnalysis!.id !== referenceAnalysis!.id &&
      selectedAnalysis!.crs === referenceAnalysis!.crs &&
      selectedAnalysis!.width === referenceAnalysis!.width &&
      selectedAnalysis!.height === referenceAnalysis!.height,
  );

  const fusedScenes = $derived(
    [...latestAnalyses.values()].filter((analysis) => analysis.areas.available),
  );

  async function loadAnalyses() {
    if (!project || !workspace.scenes.length) {
      analyses = [];
      return;
    }
    try {
      const lists = await Promise.all(
        workspace.scenes.map((scene) => api.sceneAnalyses(project.id, scene.id)),
      );
      analyses = lists.flat();
    } catch {
      analyses = [];
    }
  }

  async function loadSeries() {
    if (!project) return;
    seriesError = null;
    try {
      series = await api.temporalSeries(project.id);
    } catch (error) {
      series = null;
      // 409 means "nothing classified yet", which is an empty state, not a fault.
      if (!(error instanceof ClientError && error.status === 409)) {
        seriesError = error instanceof ClientError ? error.message : String(error);
      }
    }
  }

  async function loadFusions() {
    if (!project) return;
    fusionError = null;
    try {
      fusions = await api.fusions(project.id);
      if (!fusionTarget && fusedScenes.length) fusionTarget = fusedScenes[0].sceneId;
    } catch (error) {
      fusions = [];
      fusionError = error instanceof ClientError ? error.message : String(error);
    }
  }

  $effect(() => {
    // Re-fetch whenever the scene set changes; the engine is the source of truth.
    if (!project) return;
    void workspace.scenes.length;
    void loadAnalyses().then(() => Promise.all([loadSeries(), loadFusions()]));
  });

  async function classifyScene(sceneId: string) {
    if (!project) return;
    busy = 'classify';
    feedback = null;
    try {
      const analysis = await api.classifyScene(project.id, sceneId);
      feedback = t('temporal.analysis') + ' #' + analysis.id;
      await loadAnalyses();
      await loadSeries();
      await loadFusions();
    } catch (error) {
      feedback = error instanceof ClientError ? error.message : String(error);
    } finally {
      busy = null;
    }
  }

  async function compareDates(referenceSceneId: string | null = null) {
    if (!project || !selectedId || !referenceId) return;
    busy = 'compare';
    mismatch = null;
    try {
      comparison = await api.compareDates(project.id, {
        // The engine compares `before` → `after`, so the reference date leads.
        beforeSceneId: referenceId,
        afterSceneId: selectedId,
        referenceSceneId,
      });
    } catch (error) {
      comparison = null;
      mismatch = error instanceof ClientError ? error.message : String(error);
    } finally {
      busy = null;
    }
  }

  async function runFusion() {
    if (!project || !fusionTarget) return;
    const sources = fusedScenes.filter((analysis) => analysis.sceneId !== fusionTarget);
    if (fusedScenes.length < 2) return;
    const target = fusedScenes.find((analysis) => analysis.sceneId === fusionTarget);
    const inputs = target ? [target, ...sources.slice(0, 1)] : [];
    if (inputs.length < 2) return;
    busy = 'fusion';
    fusionError = null;
    try {
      const fusion = await api.createFusion(project.id, {
        rule: fusionRule,
        targetSceneId: fusionTarget,
        analysisIds: inputs.map((analysis) => analysis.id),
        missingPolicy: fusionMissing,
        weights: { 'Sentinel-1': 0.5, 'Sentinel-2': 0.5 },
      });
      fusions = [...fusions, fusion];
    } catch (error) {
      fusionError = error instanceof ClientError ? error.message : String(error);
    } finally {
      busy = null;
    }
  }

  function areaMethodLabel(analysis: SceneAnalysisView | null): string {
    if (!analysis) return t('common.notAvailable');
    const method = analysis.areas.method;
    if (!analysis.areas.available || !method) {
      return t('temporal.areaMethodUnavailable', {
        reason: analysis.areas.reason ?? t('common.unknown'),
      });
    }
    if (method.kind === 'projected') {
      return t('temporal.areaMethodProjected', { unit: method.unit ?? 'm' });
    }
    if (method.kind === 'geographic') {
      return t('temporal.areaMethodGeographic', { ellipsoid: method.ellipsoid ?? 'WGS84' });
    }
    return method.reason ?? t('common.notAvailable');
  }

  function hectares(squareMetres: number): string {
    return `${number(squareMetres / 10_000, 2)} ha`;
  }

  function pixelSpacing(scene: SceneView): string {
    if (scene.pixelSizeX === null || scene.pixelSizeY === null) return t('common.notAvailable');
    return `${number(Math.abs(scene.pixelSizeX), 6)} × ${number(Math.abs(scene.pixelSizeY), 6)}`;
  }
</script>

<PageHeading
  title={t('temporal.title')}
  description={t('temporal.description')}
  eyebrow={workspace.project ? `#${workspace.project.id} · ${t('temporal.timeline')}` : 'WBALC'}
/>

{#if !sorted.length}
  <div class="surface">
    <EmptyState title={t('temporal.noScenes')} hint={t('temporal.noScenesHint')} />
  </div>
{:else}
  <div class="surface temporal-tools">
    <div class="temporal-sensors">
      <span class="section-label">{t('temporal.sensor')}</span>
      <div class="segments" role="group" aria-label={t('temporal.sensor')}>
        {#each [['all', t('common.all')], ['Sentinel-1', 'Sentinel-1'], ['Sentinel-2', 'Sentinel-2']] as [value, label]}
          <button
            aria-pressed={sensor === value}
            class:chosen={sensor === value}
            onclick={() => (sensor = value as typeof sensor)}>{label}</button
          >
        {/each}
      </div>
    </div>

    <div class="date-compare">
      <label class="field">
        {t('temporal.reference')}
        <select class="select" bind:value={referenceId}>
          {#each filtered as scene (scene.id)}
            <option value={scene.id}>{date(scene.acquisitionDateTime)} · {scene.sensor}</option>
          {/each}
        </select>
      </label>
      <button
        class="icon-button swap-button"
        title={t('temporal.swap')}
        aria-label={t('temporal.swap')}
        onclick={swap}
        disabled={selectedId === referenceId}
        ><ArrowRightLeft size={16} /></button
      >
      <label class="field">
        {t('temporal.selected')}
        <select class="select" bind:value={selectedId}>
          {#each filtered as scene (scene.id)}
            <option value={scene.id}>{date(scene.acquisitionDateTime)} · {scene.sensor}</option>
          {/each}
        </select>
      </label>
    </div>
  </div>

  <div class="research-grid temporal-grid">
    <section class="surface section-box">
      <div class="section-heading">
        <div>
          <h2>{t('temporal.timeline')}</h2>
          <p>{t('temporal.timelineHint', { count: timeline.length })}</p>
        </div>
        <ChartNoAxesCombined size={17} class="faint" />
      </div>
      <TimelineChart points={timeline} selected={selectedId} onselect={(id) => (selectedId = id)} />
    </section>

    <section class="surface">
      <div class="panel-heading">
        <div class="panel-heading-title"><Satellite size={16} /><h2>{t('temporal.metadata')}</h2></div>
        {#if selected}<span class="badge-live">{selected.sensor}</span>{/if}
      </div>
      {#if selected}
        <div class="panel-body temporal-meta">
          <div class="observation-id">
            <span class="status-dot"></span>
            <span>{selected.sourceFilename}</span>
            <small class="section-label">#{selected.id}</small>
          </div>
          <dl class="kv-list">
            <div><dt>{t('common.date')}</dt><dd>{date(selected.acquisitionDateTime)}</dd></div>
            <div><dt>{t('temporal.platform')}</dt><dd>{selected.platform ?? '—'}</dd></div>
            <div><dt>{t('temporal.product')}</dt><dd>{selected.productType ?? '—'} / {selected.productLevel ?? '—'}</dd></div>
            <div><dt>{t('temporal.mode')}</dt><dd>{selected.acquisitionMode ?? '—'}</dd></div>
            <div><dt>{t('temporal.channels')}</dt><dd>{selected.polarization?.join(' / ') ?? integer(selected.bandCount)}</dd></div>
            <div><dt>{t('temporal.pixelSpacing')}</dt><dd class="ltr-numeric">{pixelSpacing(selected)}</dd></div>
            <div><dt>{t('temporal.grid')}</dt><dd class="ltr-numeric">{selected.width} × {selected.height}</dd></div>
            <div><dt>{t('temporal.crs')}</dt><dd>{selected.crs ?? t('map.pixelSpace')}</dd></div>
            <div><dt>{t('temporal.orbit')}</dt><dd>{selected.orbitDirection ?? '—'}</dd></div>
            <div><dt>{t('temporal.relativeOrbit')}</dt><dd>{selected.relativeOrbit ?? '—'}</dd></div>
            <div><dt>{t('temporal.source')}</dt><dd>{number(selected.sizeBytes / 1_048_576, 1)} MB</dd></div>
          </dl>
        </div>
      {/if}
    </section>
  </div>

  <section class="surface section-box comparison-panel">
    <div class="section-heading">
      <div>
        <h2>{t('temporal.compare')}</h2>
        <p>{date(reference?.acquisitionDateTime)} → {date(selected?.acquisitionDateTime)}</p>
      </div>
      <ScanLine size={17} class="faint" />
    </div>

    <div class="compare-body">
      <div class="compare-state" class:ok={gridMatch === 'same'} class:warn={gridMatch === 'different'}>
        {#if gridMatch === 'same'}
          ✓ {t('temporal.compareSame')}
        {:else if gridMatch === 'different'}
          ⚠ {t('temporal.compareDifferent')}
        {:else}
          ? {t('temporal.compareUnknown')}
        {/if}
      </div>

      <div class="compare-grid">
        {#each [reference, selected] as scene, index (index)}
          {#if scene}
            <figure>
              <figcaption>
                <strong>{index === 0 ? t('temporal.reference') : t('temporal.selected')}</strong>
                <span class="mono">{date(scene.acquisitionDateTime)}</span>
              </figcaption>
              <dl class="kv-list compact">
                <div><dt>{t('common.sensor')}</dt><dd>{scene.sensor}</dd></div>
                <div><dt>{t('temporal.grid')}</dt><dd class="ltr-numeric">{scene.width} × {scene.height}</dd></div>
                <div><dt>{t('temporal.crs')}</dt><dd>{scene.crs ?? '—'}</dd></div>
                <div><dt>{t('temporal.pixelSpacing')}</dt><dd class="ltr-numeric">{pixelSpacing(scene)}</dd></div>
                <div><dt>{t('temporal.bounds')}</dt><dd class="ltr-numeric">{scene.bounds ? scene.bounds.map((v) => number(v, 4)).join(', ') : '—'}</dd></div>
              </dl>
            </figure>
          {/if}
        {/each}
      </div>

      <p class="area-note">{t('temporal.areaNote2')}</p>
      <button class="button-link" onclick={() => workspace.go('map')}
        >{t('temporal.openOnMap')} <ArrowRight size={14} /></button
      >
    </div>
  </section>

  <!-- Phase 4: classification records, per-date areas, change, fusion -->
  <section class="surface section-box">
    <div class="section-heading">
      <div>
        <h2>{t('temporal.results')}</h2>
        <p>{t('temporal.resultsHint')}</p>
      </div>
      <Sigma size={17} class="faint" />
    </div>

    {#if feedback}<p class="notice-line">{feedback}</p>{/if}
    {#if seriesError}<p class="notice-line warn">{seriesError}</p>{/if}

    <div class="results-grid">
      <div class="results-list">
        {#each filtered.filter((scene) => scene.id === selectedId || scene.id === referenceId) as scene (scene.id)}
          {@const analysis = latestAnalyses.get(scene.id) ?? null}
          <article class="result-card">
            <header>
              <div>
                <strong>{date(scene.acquisitionDateTime)}</strong>
                <small class="mono">{scene.sensor} · #{scene.id}</small>
              </div>
              <div class="badge-row">
                {#if analysis}
                  <span class="badge-live">{t('temporal.nativeBadge')}</span>
                {:else}
                  <span class="badge-muted">{t('common.notAvailable')}</span>
                {/if}
              </div>
            </header>

            {#if analysis}
              <dl class="kv-list compact">
                <div><dt>{t('temporal.analysisRun')}</dt><dd class="ltr-numeric">#{analysis.runId} · {analysis.resolution}</dd></div>
                <div><dt>{t('temporal.coverage')}</dt><dd class="ltr-numeric">{percent(analysis.areas.coverage)}</dd></div>
                <div><dt>{t('temporal.validArea')}</dt><dd class="ltr-numeric">{hectares(analysis.areas.validAreaM2)}</dd></div>
                {#if analysis.areas.water}
                  <div><dt>{t('temporal.waterArea')}</dt><dd class="ltr-numeric">{hectares(analysis.areas.water.areaM2)}</dd></div>
                {/if}
                <div><dt>{t('temporal.analysisDigest')}</dt><dd class="mono truncate">{analysis.analysisDigest?.slice(0, 16) ?? '—'}…</dd></div>
              </dl>

              <p class="method-line" class:warn={!analysis.areas.available}>
                <strong>{t('temporal.areaMethod')}:</strong> {areaMethodLabel(analysis)}
              </p>
              {#if analysis.areas.method?.variesByRow}
                <p class="method-line">
                  {t('temporal.areaVariesByRow', {
                    min: number(analysis.areas.method.rowAreaMinM2 ?? 0, 2),
                    max: number(analysis.areas.method.rowAreaMaxM2 ?? 0, 2),
                  })}
                </p>
              {/if}

              <ul class="class-areas">
                {#each analysis.areas.perClass as entry, index (entry.className)}
                  <li>
                    <span class="swatch" style={`background:${classColor(entry.className, index)}`}></span>
                    <span class="class-name">{entry.className}</span>
                    <span class="ltr-numeric">{hectares(entry.areaM2)}</span>
                    <span class="ltr-numeric faint">{percent(entry.shareOfValid)}</span>
                  </li>
                {/each}
              </ul>

              <div class="card-actions">
                {#each ['hard', 'probability', 'uncertainty'] as kind (kind)}
                  {#if project && analysis.artifacts[kind]}
                    <a class="button-link" href={api.sceneExportUrl(project.id, analysis.id, kind as 'hard')}
                      ><Download size={13} /> {kind}</a
                    >
                  {/if}
                {/each}
              </div>
            {:else}
              <p class="method-line">{t('temporal.notClassified')}</p>
              <p class="method-line faint">{t('temporal.notClassifiedHint')}</p>
              <button
                class="button-primary"
                disabled={busy !== null || !workspace.runs.length}
                onclick={() => classifyScene(scene.id)}
              >
                {busy === 'classify' ? t('temporal.classifying') : t('temporal.classify')}
              </button>
            {/if}
          </article>
        {/each}
      </div>

      <div class="series-panel">
        <div class="section-heading compact-heading">
          <div>
            <h3>{t('temporal.results')}</h3>
            <p>{t('temporal.resultsHint')}</p>
          </div>
        </div>
        {#if series && series.dates.length}
          <table class="series-table">
            <thead>
              <tr>
                <th>{t('common.date')}</th>
                <th>{t('temporal.validArea')}</th>
                <th>{t('temporal.waterArea')}</th>
                <th>{t('temporal.coverage')}</th>
              </tr>
            </thead>
            <tbody>
              {#each series.dates as point (point.analysisId)}
                <tr class:chosen={point.sceneId === selectedId}>
                  <td>
                    <button class="link-button" onclick={() => (selectedId = point.sceneId)}>
                      {date(point.acquisitionDateTime)}
                    </button>
                    <small class="mono">{point.sensor ?? '—'}</small>
                  </td>
                  <td class="ltr-numeric">{hectares(point.validAreaM2)}</td>
                  <td class="ltr-numeric">{point.water ? hectares(point.water.areaM2) : '—'}</td>
                  <td class="ltr-numeric">{percent(point.coverage)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if series.caveats.length}
            <ul class="caveat-list">
              {#each series.caveats as caveat (caveat)}<li>{caveat}</li>{/each}
            </ul>
          {/if}
        {:else}
          <p class="method-line faint">{t('temporal.notClassifiedHint')}</p>
        {/if}
      </div>
    </div>
  </section>

  <section class="surface section-box">
    <div class="section-heading">
      <div>
        <h2>{t('temporal.change')}</h2>
        <p>{t('temporal.changeHint')}</p>
      </div>
      <Layers size={17} class="faint" />
    </div>

    {#if classifiedCount < 2}
      <p class="method-line faint">{t('temporal.needTwoScenes')}</p>
    {:else}
      <div class="change-actions">
        <button
          class="button-primary"
          disabled={busy !== null || !comparisonReady}
          onclick={() => compareDates()}
        >
          {busy === 'compare' ? t('common.loading') : t('temporal.compareDates')}
        </button>
        {#if !comparisonReady}
          <span class="method-line faint">{t('temporal.mismatchHint')}</span>
        {/if}
      </div>

      {#if mismatch}
        <div class="mismatch-box">
          <strong>⚠ {t('temporal.mismatch')}</strong>
          <p>{mismatch}</p>
          <div class="align-row">
            <label class="field">
              {t('temporal.alignOnto')}
              <select class="select" bind:value={alignOnto}>
                <option value={referenceId}>{t('temporal.reference')} · {date(reference?.acquisitionDateTime)}</option>
                <option value={selectedId}>{t('temporal.selected')} · {date(selected?.acquisitionDateTime)}</option>
              </select>
            </label>
            <button
              class="button-primary"
              disabled={busy !== null || !alignOnto}
              onclick={() => compareDates(alignOnto)}
              >{t('temporal.alignAndCompare')}</button
            >
          </div>
        </div>
      {/if}

      {#if comparison}
        <div class="change-body">
          <div class="compare-state" class:ok={!comparison.aligned} class:warn={comparison.aligned}>
            {#if comparison.aligned}
              ⚠ {t('temporal.alignedBadge', { id: comparison.referenceSceneId ?? '' })} — {t('temporal.derivedBadge')}
            {:else}
              ✓ {t('temporal.noResampling')}
            {/if}
          </div>

          <dl class="kv-list compact change-kpis">
            <div><dt>{t('temporal.changedArea')}</dt><dd class="ltr-numeric">{hectares(comparison.changedAreaM2)}</dd></div>
            <div><dt>{t('temporal.jointValid')}</dt><dd class="ltr-numeric">{hectares(comparison.jointValidAreaM2)}</dd></div>
            <div><dt>{t('temporal.denominator')}</dt><dd>{comparison.denominator}</dd></div>
          </dl>

          <table class="series-table">
            <thead>
              <tr>
                <th>{t('temporal.transitionFrom')}</th>
                <th>{t('temporal.transitionTo')}</th>
                <th>{t('temporal.pixels')}</th>
                <th>{t('temporal.validArea')}</th>
              </tr>
            </thead>
            <tbody>
              {#each comparison.transitions as row (row.from + '→' + row.to)}
                <tr>
                  <td>{row.from}</td>
                  <td>{row.to}</td>
                  <td class="ltr-numeric">{integer(row.pixels)}</td>
                  <td class="ltr-numeric">{hectares(row.areaM2)}</td>
                </tr>
              {:else}
                <tr><td colspan="4" class="faint">—</td></tr>
              {/each}
            </tbody>
          </table>

          {#if comparison.caveats.length}
            <div>
              <span class="section-label">{t('temporal.caveats')}</span>
              <ul class="caveat-list">
                {#each comparison.caveats as caveat (caveat)}<li>{caveat}</li>{/each}
              </ul>
            </div>
          {/if}
        </div>
      {/if}
    {/if}
  </section>

  <section class="surface section-box">
    <div class="section-heading">
      <div>
        <h2>{t('temporal.fusion')}</h2>
        <p>{t('temporal.fusionHint')}</p>
      </div>
      <Layers size={17} class="faint" />
    </div>

    {#if fusedScenes.length < 2}
      <p class="method-line faint">{t('temporal.fusionNeedTwo')}</p>
    {:else}
      <div class="fusion-controls">
        <label class="field">
          {t('temporal.fusionRule')}
          <select class="select" bind:value={fusionRule}>
            <option value="weighted_probability">{t('temporal.fusionRuleWeightedProbability')}</option>
            <option value="weighted_vote">{t('temporal.fusionRuleWeightedVote')}</option>
            <option value="priority">{t('temporal.fusionRulePriority')}</option>
          </select>
        </label>
        <label class="field">
          {t('temporal.fusionTarget')}
          <select class="select" bind:value={fusionTarget}>
            {#each fusedScenes as analysis (analysis.id)}
              <option value={analysis.sceneId}>{t('common.date')} · #{analysis.sceneId}</option>
            {/each}
          </select>
        </label>
        <label class="field">
          {t('temporal.fusionMissing')}
          <select class="select" bind:value={fusionMissing}>
            <option value="require_all">{t('temporal.fusionMissingRequireAll')}</option>
            <option value="renormalise">{t('temporal.fusionMissingRenormalise')}</option>
          </select>
        </label>
        <button class="button-primary" disabled={busy !== null} onclick={runFusion}>
          {busy === 'fusion' ? t('common.loading') : t('temporal.fusionRun')}
        </button>
      </div>
      <p class="method-line faint">{t('temporal.earlyFusionNote')}</p>
    {/if}

    {#if fusionError}<p class="notice-line warn">{fusionError}</p>{/if}

    {#if fusions.length}
      <div class="fusion-list">
        {#each fusions as fusion (fusion.id)}
          <article class="result-card">
            <header>
              <div>
                <strong>{fusion.name || `#${fusion.id}`}</strong>
                <small class="mono">{fusion.rule} · {fusion.missingPolicy}</small>
              </div>
              <span class:badge-live={!fusion.aligned} class:badge-muted={fusion.aligned}>
                {fusion.aligned ? t('temporal.derivedBadge') : t('temporal.nativeBadge')}
              </span>
            </header>
            <ul class="source-list">
              {#each fusion.sources as source (source.analysisId)}
                <li>
                  <span>{source.sensor}</span>
                  <small class="mono">#{source.sceneId} · w {number(source.weight, 2)}</small>
                  <span class:badge-live={!source.gridAligned} class:badge-muted={source.gridAligned}>
                    {source.gridAligned ? t('temporal.fusionAligned') : t('temporal.fusionNative')}
                  </span>
                </li>
              {/each}
            </ul>
            {#if fusion.unanimousShare !== null}
              <p class="method-line">
                <strong>{t('temporal.fusionAgreement')}:</strong>
                {t('temporal.fusionAgreementValue', { share: percent(fusion.unanimousShare) })}
              </p>
            {/if}
            {#if fusion.areas?.water}
              <p class="method-line">
                <strong>{t('temporal.waterArea')}:</strong> {hectares(fusion.areas.water.areaM2)}
              </p>
            {/if}
            <p class="method-line faint mono">{t('temporal.fusionDigest')}: {fusion.fusionDigest?.slice(0, 16) ?? '—'}…</p>
          </article>
        {/each}
      </div>
    {:else if !fusionError}
      <p class="method-line faint">{t('temporal.fusionNone')}</p>
    {/if}
  </section>
{/if}

<style>
  .temporal-tools { display: flex; align-items: end; justify-content: space-between; flex-wrap: wrap; gap: 12px 24px; padding: 13px 15px; margin-bottom: 15px; }
  .temporal-sensors { display: grid; gap: 6px; }
  .date-compare { display: flex; gap: 7px; align-items: end; }
  .date-compare .field { min-width: min(210px, 100%); }
  .swap-button { margin-bottom: 1.5px; border: 1px solid var(--border); }
  .temporal-grid { margin-bottom: 15px; display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(260px, 1fr); gap: 15px; align-items: start; }
  .observation-id { display: flex; align-items: center; gap: 8px; color: var(--ink); font-size: 12px; margin-bottom: 5px; }
  .observation-id span:first-of-type { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .compare-body { display: grid; gap: 12px; }
  .compare-state { padding: 9px 11px; border-radius: 6px; font-size: 11.5px; border: 1px solid var(--border); background: #14202f; color: var(--muted); }
  .compare-state.ok { border-color: #2e5b58; background: #16302f; color: #a6ecdf; }
  .compare-state.warn { border-color: #6b5432; background: #302818; color: #f3d59a; }
  .compare-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; }
  .compare-grid figure { margin: 0; min-width: 0; }
  .compare-grid figcaption { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 6px; font-size: 12px; }
  .compare-grid figcaption strong { font-weight: 590; }
  .compare-grid figcaption span { font: 10.5px var(--mono); color: var(--muted); }
  .compact > div { padding-block: 5px; }
  .area-note { margin: 0; color: var(--faint); font-size: 10.5px; line-height: 1.6; padding-top: 9px; border-top: 1px solid var(--line); }
  /* ---- Phase 4 panels ---- */
  .results-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr); gap: 15px; }
  .results-list { display: grid; gap: 12px; align-content: start; }
  .result-card { border: 1px solid var(--line); border-radius: 6px; padding: 11px 12px; display: grid; gap: 8px; }
  .result-card header { display: flex; justify-content: space-between; align-items: start; gap: 8px; }
  .result-card header div { display: grid; gap: 2px; min-width: 0; }
  .result-card header strong { font-weight: 590; font-size: 12px; }
  .result-card header small { color: var(--muted); font-size: 10.5px; }
  .badge-row { display: flex; gap: 5px; }
  .badge-muted { font: 10px var(--mono); color: var(--faint); border: 1px solid var(--line); border-radius: 4px; padding: 2px 6px; }
  .method-line { margin: 0; color: var(--muted); font-size: 10.5px; line-height: 1.6; }
  .method-line.warn { color: #f3d59a; }
  .notice-line { margin: 0 0 9px; font-size: 11px; color: var(--muted); }
  .notice-line.warn { color: #f3d59a; }
  .class-areas { list-style: none; margin: 0; padding: 0; display: grid; gap: 3px; }
  .class-areas li { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto auto; gap: 7px; align-items: center; font-size: 11px; }
  .swatch { width: 8px; height: 8px; border-radius: 2px; }
  .class-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .card-actions { display: flex; gap: 10px; flex-wrap: wrap; }
  .series-panel { min-width: 0; }
  .compact-heading { margin-bottom: 6px; }
  .compact-heading h3 { font-size: 12px; margin: 0; }
  .compact-heading p { margin: 2px 0 0; color: var(--muted); font-size: 10.5px; }
  .series-table { width: 100%; border-collapse: collapse; font-size: 11px; }
  .series-table th { text-align: left; color: var(--muted); font-weight: 500; font-size: 10px; padding: 5px 6px; border-bottom: 1px solid var(--line); }
  .series-table td { padding: 5px 6px; border-bottom: 1px solid var(--line); }
  .series-table tr.chosen td { background: #16222f; }
  .series-table td small { display: block; color: var(--faint); font-size: 9.5px; }
  .link-button { background: none; border: 0; padding: 0; color: var(--ink); font: inherit; cursor: pointer; text-decoration: underline dotted; }
  .caveat-list { margin: 6px 0 0; padding-left: 16px; color: var(--faint); font-size: 10.5px; line-height: 1.7; }
  .change-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
  .change-body { display: grid; gap: 10px; }
  .change-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
  .mismatch-box { border: 1px solid #6b5432; background: #302818; border-radius: 6px; padding: 11px 12px; display: grid; gap: 8px; }
  .mismatch-box strong { color: #f3d59a; font-size: 11.5px; }
  .mismatch-box p { margin: 0; color: var(--muted); font-size: 10.5px; line-height: 1.6; }
  .align-row { display: flex; gap: 9px; align-items: end; flex-wrap: wrap; }
  .fusion-controls { display: flex; gap: 10px; align-items: end; flex-wrap: wrap; margin-bottom: 8px; }
  .fusion-list { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); margin-top: 11px; }
  .source-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  .source-list li { display: flex; gap: 7px; align-items: center; font-size: 11px; flex-wrap: wrap; }
  .source-list small { color: var(--faint); font-size: 10px; }
  .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
  @media (max-width: 980px) {
    .results-grid { grid-template-columns: minmax(0, 1fr); }
    .temporal-grid { grid-template-columns: minmax(0, 1fr); }
  }
  @media (max-width: 650px) {
    .compare-grid { grid-template-columns: minmax(0, 1fr); }
    .date-compare { display: grid; grid-template-columns: minmax(0, 1fr) 32px minmax(0, 1fr); width: 100%; gap: 5px; }
  }
</style>

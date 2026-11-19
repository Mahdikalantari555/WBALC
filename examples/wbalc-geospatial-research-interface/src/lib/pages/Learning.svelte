<script lang="ts">
  import { onMount } from 'svelte';
  import {
    Check, ChevronLeft, ChevronRight, CircleCheck, Download, History, LocateFixed, MapPin,
    SkipForward, Tags, Trash2, Upload, X,
  } from '@lucide/svelte';
  import Alert from '../components/Alert.svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import { api, ClientError } from '../client/api';
  import { classColor } from '../palette';
  import { renderWindow } from '../raster';
  import { getWorkspace } from '../state.svelte';
  import { useT } from '../t.svelte';
  import type { QueryHistoryEntry, QuerySampleView } from '../types';

  const workspace = getWorkspace();
  const { t, date, integer, percent } = useT();

  let strategy = $state<'uncertainty' | 'diversity' | 'hybrid' | 'random'>('diversity');
  let batchSize = $state(20);
  /** Only used by the random baseline; the engine records whatever it used. */
  let seed = $state<number | null>(null);
  let history = $state<QueryHistoryEntry[]>([]);
  let historyError = $state<string | null>(null);
  let loadingHistory = $state(false);
  let resumeId = $state<string | null>(null);
  let method = $state<'least_confidence' | 'margin' | 'entropy'>('least_confidence');
  let requesting = $state(false);
  let requestError = $state<string | null>(null);
  let mode = $state<'pending' | 'reviewed' | 'all'>('pending');
  let threshold = $state(0);
  let predictedClass = $state<'all' | string>('all');
  let focused = $state<string | null>(null);
  let preview = $state<'prediction' | 'imagery'>('imagery');
  let thumbnail = $state<string | null>(null);
  let thumbnailError = $state<string | null>(null);
  let submitting = $state(false);
  let importMessage = $state<string | null>(null);
  let importCrs = $state<'EPSG:4326' | 'dataset'>('EPSG:4326');
  let trainResolution = $state<'patch' | 'pixel'>('patch');
  let trainProtocol = $state<'random' | 'spatial'>('random');
  let trainModel = $state<'rf' | 'lightgbm'>('rf');
  /** Set when the engine refused training because the band schemas conflict. */
  let schemaRefused = $state(false);
  let acceptUnverified = $state(false);

  const classes = $derived(workspace.project?.classes ?? []);
  const batch = $derived(workspace.review.batch);
  const decisions = $derived(workspace.review.decisions);

  /**
   * Reviewable samples. When a batch came from the server, the item's recorded
   * decision wins over the cached copy: a suggestion rejected or deferred in an
   * earlier session must not look pending here.
   */
  const queue = $derived<QuerySampleView[]>(
    (batch?.samples ?? []).filter((sample) => {
      const decided = Boolean(decisions[sample.sampleId]);
      if (mode === 'pending' && decided) return false;
      if (mode === 'reviewed' && !decided) return false;
      if (threshold > 0 && (sample.uncertainty ?? 0) < threshold) return false;
      if (predictedClass !== 'all' && sample.prediction !== predictedClass) return false;
      return true;
    }),
  );

  const position = $derived(Math.max(queue.findIndex((item) => item.sampleId === focused), 0));
  const sample = $derived<QuerySampleView | undefined>(queue[position]);
  const decision = $derived(sample ? decisions[sample.sampleId] : undefined);
  let draft = $state<string | null>(null);
  const choice = $derived(draft ?? decision?.className ?? null);

  const reviewedHere = $derived(
    (batch?.samples ?? []).filter((item) => decisions[item.sampleId]).length,
  );
  const total = $derived(batch?.samples.length ?? 0);
  const pending = $derived(total - reviewedHere);
  const flagged = $derived(
    Object.values(decisions).filter((item) => item.className === 'uncertain').length,
  );

  const dataset = $derived(
    sample ? workspace.datasets.find((item) => item.id === sample.datasetId) ?? workspace.dataset : workspace.dataset,
  );

  /** Exact-window thumbnail of the sampled patch, straight from the source. */
  $effect(() => {
    const current = sample;
    const source = dataset;
    const modeValue = preview;
    if (!current || !source) {
      thumbnail = null;
      return;
    }
    let active = true;
    thumbnailError = null;
    renderWindow(source.url, source.id, current.window, 'true-color', 190)
      .then((url) => {
        if (active) thumbnail = url;
      })
      .catch((error) => {
        if (active) thumbnailError = error instanceof Error ? error.message : String(error);
      });
    return () => {
      active = false;
    };
    void modeValue;
  });

  async function loadHistory() {
    if (!workspace.project) return;
    loadingHistory = true;
    historyError = null;
    try {
      history = await api.queryHistory(workspace.project.id, 20);
    } catch (error) {
      historyError = error instanceof ClientError ? error.message : String(error);
    } finally {
      loadingHistory = false;
    }
  }

  /** Reopen a durable batch: items, order and recorded decisions come from the server. */
  async function resume(entry: QueryHistoryEntry) {
    if (!workspace.project) return;
    requesting = true;
    requestError = null;
    resumeId = entry.batchId;
    try {
      const full = await api.queryBatch(workspace.project.id, entry.batchId);
      const submitted: Record<string, string> = {};
      for (const item of full.items) {
        if (item.status === 'labeled' && item.decidedClass) {
          submitted[item.sampleId] = item.decidedClass;
        }
      }
      workspace.loadBatch(
        {
          batchId: full.batchId,
          strategy: full.strategy,
          method: full.method,
          strategyVersion: full.strategyVersion,
          seed: full.seed,
          requestedSize: full.requested,
          modelIteration: full.modelIteration,
          trainingRunId: full.trainingRunId,
          notes: full.notes,
          requestedAt: full.createdAt,
          pool: null,
          samples: full.items.map((item) => ({
            sampleId: item.sampleId,
            datasetId: item.datasetId,
            row: item.row,
            col: item.col,
            center: item.center,
            window: item.window,
            geo: item.geo,
            bbox: item.bbox,
            prediction: item.prediction,
            confidence: item.confidence,
            uncertainty: item.uncertainty,
          })),
        },
        full.batchId,
        submitted,
      );
      focus(full.items.find((item) => item.status === 'pending')?.sampleId ?? null);
      workspace.notify(t('learning.history.resumed', { id: full.batchId }));
    } catch (error) {
      requestError = error instanceof ClientError ? error.message : String(error);
    } finally {
      requesting = false;
    }
  }

  onMount(() => {
    void loadHistory();
    // Arriving from the map with a specific sample selected.
    if (workspace.selectedSample) {
      focused = workspace.selectedSample;
      draft = null;
      workspace.selectedSample = null;
    }
  });

  function focus(sampleId: string | null) {
    focused = sampleId;
    draft = null;
  }

  function nextSample(from: QuerySampleView | undefined): string | null {
    const index = from ? queue.findIndex((item) => item.sampleId === from.sampleId) : -1;
    return queue[index + 1]?.sampleId ?? queue[index - 1]?.sampleId ?? null;
  }

  async function requestBatch() {
    if (!workspace.project) return;
    requesting = true;
    requestError = null;
    try {
      const response = await api.query(workspace.project.id, {
        strategy,
        method,
        batchSize,
        datasetId: workspace.dataset?.id ?? '',
        ...(strategy === 'random' && seed != null ? { seed } : {}),
      });
      workspace.setBatch(response);
      focus(response.samples[0]?.sampleId ?? null);
      void loadHistory();
    } catch (error) {
      requestError = error instanceof ClientError ? error.message : String(error);
    } finally {
      requesting = false;
    }
  }

  async function submit() {
    if (!sample || !choice || !workspace.project) return;
    // The durable item id for this sample, when the batch came from the engine.
    const currentItem = await resolveItem(sample.sampleId);
    submitting = true;
    try {
      await api.submitLabel(workspace.project.id, {
        sampleId: sample.sampleId,
        datasetId: sample.datasetId,
        className: choice,
        col: sample.center[0],
        row: sample.center[1],
        iteration: batch?.modelIteration ?? workspace.latestRun?.iteration ?? 0,
        revise: Boolean(decision),
        ...(batch?.batchId ? { queryBatchId: batch.batchId } : {}),
        ...(batch?.batchId && currentItem ? { queryItemId: currentItem.id } : {}),
      });
      workspace.markDecision(sample, choice);
      const next = nextSample(sample);
      focus(next);
      workspace.notify(t('learning.submitted', { id: sample.sampleId }));
      // Labels feed training, so refresh the derived counts in the background.
      void workspace.reload();
    } catch (error) {
      requestError = error instanceof ClientError ? error.message : String(error);
    } finally {
      submitting = false;
    }
  }

  /**
   * Train with the resolution and validation protocol the operator picked.
   *
   * Both are explicit because they change what the resulting score means: patch
   * cells are not independent pixels, and a random holdout on neighbouring
   * patches is optimistic compared with a spatial block holdout.
   */
  async function train() {
    if (!workspace.project) return;
    schemaRefused = false;
    const run = await workspace.train({
      resolution: trainResolution,
      evaluationStrategy: trainProtocol,
      modelType: trainModel,
      acceptUnverifiedSchema: acceptUnverified,
    });
    if (run) {
      workspace.notify(
        acceptUnverified
          ? t('learning.train.schemaOverridden')
          : t('learning.train.trained', { iteration: run.iteration }),
      );
      void workspace.reload();
    } else if (workspace.engineError) {
      // 422 = the contributing rasters do not share one declared band schema.
      // Say so, and offer the same explicit override the API requires.
      schemaRefused = true;
    }
  }

  function skip() {
    void decide(sample, 'deferred');
  }

  /**
   * Record a decision that is not a label — rejected (suggestion wrong) or
   * deferred (skipped for now) — on the server, so it survives a reload.
   */
  async function decide(target: QuerySampleView | undefined, status: 'rejected' | 'deferred') {
    if (!target) return;
    const item = await resolveItem(target.sampleId);
    if (!item || !batch?.batchId || !workspace.project) {
      // No durable item (a cached batch from before this phase): the local skip
      // list is all that exists, and it is reported as such.
      workspace.markSkipped(target.sampleId);
      focus(nextSample(target));
      return;
    }
    try {
      await api.decideQueryItem(workspace.project.id, batch.batchId, item.id, { status });
      workspace.markSkipped(target.sampleId);
      focus(nextSample(target));
      workspace.notify(
        status === 'rejected'
          ? t('learning.decision.rejected', { id: target.sampleId })
          : t('learning.skipped', { id: target.sampleId }),
      );
      void loadHistory();
    } catch (error) {
      requestError = error instanceof ClientError ? error.message : String(error);
    }
  }

  /** Look up the durable item for a sample in the current batch (cached). */
  const itemCache = new Map<string, { id: string } | null>();
  async function resolveItem(sampleIdValue: string) {
    if (!batch?.batchId || !workspace.project) return null;
    const key = `${batch.batchId}:${sampleIdValue}`;
    if (itemCache.has(key)) return itemCache.get(key) ?? null;
    try {
      const full = await api.queryBatch(workspace.project.id, batch.batchId);
      for (const item of full.items) itemCache.set(`${full.batchId}:${item.sampleId}`, { id: item.id });
      return itemCache.get(key) ?? null;
    } catch {
      return null;
    }
  }

  async function removeLabel() {
    if (!sample || !workspace.project) return;
    if (!confirm(t('learning.deleteConfirm', { id: sample.sampleId }))) return;
    try {
      await api.deleteLabel(workspace.project.id, sample.sampleId);
      workspace.unmarkDecision(sample.sampleId);
      // Keep the durable decision honest: deleting the label means the item is
      // no longer answered, so it goes back to pending.
      const item = await resolveItem(sample.sampleId);
      if (item && batch?.batchId) {
        await api.decideQueryItem(workspace.project.id, batch.batchId, item.id, { status: 'pending' });
      }
      workspace.notify(t('learning.deleted', { id: sample.sampleId }));
      void workspace.reload();
      void loadHistory();
    } catch (error) {
      requestError = error instanceof ClientError ? error.message : String(error);
    }
  }

  async function importFile(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !workspace.project) return;
    importMessage = null;
    try {
      const geojson = JSON.parse(await file.text());
      const result = await api.importLabels(workspace.project.id, {
        geojson,
        datasetId: workspace.dataset?.id ?? null,
        coordinateCrs: importCrs,
      });
      importMessage =
        result.imported || result.skipped
          ? t('learning.imported', { imported: result.imported, skipped: result.skipped })
          : t('learning.importNoFeatures');
      if (result.errors.length) importMessage += ` — ${result.errors[0]}`;
      void workspace.reload();
    } catch (error) {
      importMessage = error instanceof ClientError ? error.message : String(error);
    } finally {
      input.value = '';
    }
  }

  function showOnMap(item: QuerySampleView) {
    workspace.map.layers.samples = true;
    workspace.map.selected = { kind: 'cell', row: item.row, col: item.col };
    workspace.go('map');
  }

  // Keyboard review loop: class keys, Enter to submit, S to skip, arrows to move.
  function onKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    if (target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const index = Number(event.key) - 1;
    if (Number.isInteger(index) && index >= 0 && index < classes.length) {
      event.preventDefault();
      draft = classes[index];
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      void submit();
    } else if (event.key.toLowerCase() === 's') {
      event.preventDefault();
      skip();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
      event.preventDefault();
      const next = nextSample(sample);
      if (next) focus(next);
    } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
      event.preventDefault();
      const previous = queue[position - 1];
      if (previous) focus(previous.sampleId);
    }
  }

  const hasModel = $derived(workspace.runs.length > 0);
  const training = $derived(workspace.training);
</script>

<svelte:window onkeydown={onKeydown} />

<PageHeading
  title={t('learning.title')}
  description={t('learning.description')}
  eyebrow={workspace.project ? `#${workspace.project.id} · ${t('learning.keyboard')}` : 'WBALC'}
>
  {#snippet actions()}
    <label class="button file-button">
      <Upload size={15} /> {t('learning.import')}
      <input type="file" accept=".geojson,.json,application/geo+json,application/json" onchange={importFile} />
    </label>
  {/snippet}
</PageHeading>

<div class="surface import-bar">
  <span class="section-label">{t('learning.import')}</span>
  <label class="field inline-field">
    {t('learning.importCrs')}
    <select class="select" bind:value={importCrs}>
      <option value="EPSG:4326">WGS84 (EPSG:4326)</option>
      <option value="dataset">{t('learning.importCrsDataset')} ({dataset?.crs ?? '—'})</option>
    </select>
  </label>
  <span class="import-hint">{t('learning.importHint')}</span>
</div>
{#if importMessage}<div class="inline-info">{importMessage}</div>{/if}

<div class="surface import-bar train-bar">
  <span class="section-label">{t('learning.train.title')}</span>
  <label class="field inline-field">
    {t('learning.train.resolution')}
    <select class="select" bind:value={trainResolution}>
      <option value="patch">{t('learning.train.patch')}</option>
      <option value="pixel">{t('learning.train.pixel')}</option>
    </select>
  </label>
  <label class="field inline-field">
    {t('learning.train.protocol')}
    <select class="select" bind:value={trainProtocol}>
      <option value="random">{t('evaluation.protocol.random')}</option>
      <option value="spatial">{t('evaluation.protocol.spatial')}</option>
    </select>
  </label>
  <label class="field inline-field compact">
    {t('learning.train.model')}
    <select class="select" bind:value={trainModel}>
      <option value="rf">Random Forest</option>
      <option value="lightgbm">LightGBM</option>
    </select>
  </label>
  <label class="field inline-field checkbox-field" title={t('learning.train.schemaHint')}>
    <input type="checkbox" bind:checked={acceptUnverified} />
    {t('learning.train.acceptUnverified')}
  </label>
  <button class="button primary" onclick={train} disabled={training || !workspace.labels.length}>
    {training ? t('learning.train.running') : t('learning.train.run')}
  </button>
  <span class="import-hint">
    {trainResolution === 'pixel' ? t('learning.train.pixelHint') : t('learning.train.patchHint')}
    {trainProtocol === 'spatial' ? t('learning.train.spatialHint') : t('learning.train.randomHint')}
  </span>
</div>
{#if workspace.engineError}
  <Alert title={schemaRefused ? t('learning.train.schemaRefused') : t('learning.train.failed')}>
    <span>{workspace.engineError}</span>
    {#if schemaRefused}<span>{t('learning.train.schemaHint')}</span>{/if}
  </Alert>
{/if}
{#if requestError}
  <Alert title={t('error.generic')}><span>{requestError}</span></Alert>
{/if}
{#if batch?.notes.length}
  <div class="inline-info">
    {#each batch.notes as note}<span>{note}</span>{/each}
  </div>
{/if}

{#if batch}
  <section class="surface provenance-bar" aria-label={t('learning.provenance')}>
    <span class="section-label">{t('learning.provenance')}</span>
    <dl class="prov-list">
      <div>
        <dt>{t('learning.batch')}</dt>
        <dd class="mono">#{batch.batchId ?? t('learning.batchUnrecorded')}</dd>
      </div>
      <div>
        <dt>{t('learning.strategy')}</dt>
        <dd>{batch.strategy}{batch.method ? ` · ${batch.method}` : ''}</dd>
      </div>
      <div>
        <dt>{t('learning.seed')}</dt>
        <dd class="mono ltr-numeric">{batch.seed ?? t('learning.seedNone')}</dd>
      </div>
      <div>
        <dt>{t('learning.model')}</dt>
        <dd>{batch.modelIteration != null ? t('learning.iterationShort', { iteration: batch.modelIteration }) : t('learning.noModel')}</dd>
      </div>
      {#if batch.pool}
        <div>
          <dt>{t('learning.pool')}</dt>
          <dd class="mono ltr-numeric">{batch.pool.size} / {batch.pool.gridCells} · {batch.pool.hash.slice(0, 10)}</dd>
        </div>
      {/if}
    </dl>
  </section>
{/if}

<section class="surface history-panel" aria-labelledby="history-heading">
  <div class="panel-heading">
    <div class="panel-heading-title"><History size={16} /><h2 id="history-heading">{t('learning.history')}</h2></div>
    <span class="section-label">{t('learning.historyCount', { count: history.length })}</span>
  </div>
  <p class="queue-caption">{t('learning.historyHint')}</p>
  {#if historyError}
    <p class="queue-hint warn">{historyError}</p>
  {/if}
  <div class="history-list">
    {#each history as entry (entry.batchId)}
      <div class="history-row" class:current={entry.batchId === (batch?.batchId ?? resumeId)}>
        <div class="history-meta">
          <strong class="mono">#{entry.batchId}</strong>
          <span>{entry.strategy}{entry.method ? ` · ${entry.method}` : ''}</span>
          <span class="faint">{date(entry.createdAt)}</span>
        </div>
        <div class="history-facts">
          <span class="mono ltr-numeric">{t('learning.history.decisions', {
            labeled: entry.decisions.labeled,
            rejected: entry.decisions.rejected,
            deferred: entry.decisions.deferred,
            pending: entry.decisions.pending,
          })}</span>
          {#if entry.poolSize != null}
            <span class="faint mono ltr-numeric">{t('learning.history.pool', { size: entry.poolSize })}</span>
          {/if}
        </div>
        <button class="button quiet" onclick={() => resume(entry)} disabled={requesting}>
          {entry.batchId === batch?.batchId ? t('learning.history.current') : t('learning.history.resume')}
        </button>
      </div>
    {:else}
      <p class="queue-hint">{loadingHistory ? t('common.loading') : t('learning.historyEmpty')}</p>
    {/each}
  </div>
</section>

<div class="learning-layout">
  <section class="surface queue-panel">
    <div class="panel-heading">
      <div class="panel-heading-title"><Tags size={16} /><h2>{t('learning.queue')}</h2></div>
      <span class="section-label">{t('learning.queueCount', { count: total })}</span>
    </div>

    <div class="queue-settings">
      <div class="queue-stats">
        <div><strong class="mono">{integer(pending)}</strong><span>{t('common.pending')}</span></div>
        <div><strong class="mono">{integer(reviewedHere)}</strong><span>{t('common.reviewed')}</span></div>
      </div>
      <div class="queue-progress"><i style:width={`${total ? (reviewedHere / total) * 100 : 0}%`}></i></div>
      <p class="queue-caption">
        <span>{t('learning.progress', { done: reviewedHere, total })}</span>
        {#if flagged}<span class="flag-count">{t('learning.flagged', { count: flagged })}</span>{/if}
      </p>

      <div class="field">
        <span>{t('learning.strategy')}</span>
        <select class="select" bind:value={strategy}>
          <option value="diversity">{t('learning.strategy.diversity')}</option>
          <option value="uncertainty" disabled={!hasModel}>{t('learning.strategy.uncertainty')}</option>
          <option value="hybrid" disabled={!hasModel}>{t('learning.strategy.hybrid')}</option>
          <option value="random">{t('learning.strategy.random')}</option>
        </select>
      </div>
      {#if strategy === 'random'}
        <label class="field">
          <span>{t('learning.seed')}</span>
          <input
            class="text-input ltr-numeric"
            type="number"
            min="0"
            placeholder={t('learning.seedDefault')}
            value={seed ?? ''}
            oninput={(event) => {
              const value = (event.currentTarget as HTMLInputElement).value;
              seed = value === '' ? null : Math.max(0, Math.trunc(Number(value)));
            }}
          />
        </label>
        <p class="queue-hint">{t('learning.strategy.randomHint')}</p>
      {/if}
      {#if strategy === 'uncertainty' || strategy === 'hybrid'}
        <div class="field">
          <span>{t('map.uncertaintyMethod')}</span>
          <select class="select" bind:value={method}>
            <option value="least_confidence">{t('map.method.leastConfidence')}</option>
            <option value="margin">{t('map.method.margin')}</option>
            <option value="entropy">{t('map.method.entropy')}</option>
          </select>
        </div>
      {/if}
      <div class="field">
        <label for="batch-size">{t('learning.batchSize')}</label>
        <input id="batch-size" class="text-input" type="number" min="1" max="200" bind:value={batchSize} />
      </div>
      <button class="button primary" onclick={requestBatch} disabled={requesting || !workspace.dataset}>
        {requesting ? t('learning.requesting') : t('learning.request')}
      </button>
      {#if !hasModel}<p class="queue-hint">{t('learning.noLabelsColdStart')}</p>{/if}

      <div class="queue-tabs segments" role="group" aria-label={t('learning.filter.mode')}>
        {#each [['pending', t('learning.filter.mode.pending')], ['reviewed', t('learning.filter.mode.reviewed')], ['all', t('learning.filter.mode.all')]] as [value, label]}
          <button aria-pressed={mode === value} class:chosen={mode === value} onclick={() => { mode = value as typeof mode; focus(null); }}>{label}</button>
        {/each}
      </div>
      <div class="queue-filters">
        <label class="field">
          <span>{t('learning.filter.uncertainty')}</span>
          <input class="text-input" type="range" min="0" max="1" step="0.05" bind:value={threshold} />
        </label>
        <label class="field">
          <span>{t('learning.filter.class')}</span>
          <select class="select" bind:value={predictedClass}>
            <option value="all">{t('common.all')}</option>
            {#each classes as name}<option value={name}>{name}</option>{/each}
          </select>
        </label>
      </div>
    </div>

    <div class="sample-list">
      {#each queue as item (item.sampleId)}
        <button class="sample-row" class:current={item.sampleId === sample?.sampleId} onclick={() => focus(item.sampleId)}>
          <span class="sample-row-icon" style:--class-color={classColor(item.prediction ?? '', 0)}>
            <MapPin size={12} />
          </span>
          <span class="sample-row-id">
            <strong>{item.sampleId}</strong>
            <small>{item.prediction ?? '—'} · {percent(item.uncertainty)}</small>
          </span>
          {#if decisions[item.sampleId]}<CircleCheck size={14} class="accent" />{:else}<span class="sample-score mono">{percent(item.uncertainty)}</span>{/if}
          <ChevronRight size={13} class="faint" />
        </button>
      {:else}
        <EmptyState
          title={batch ? (pending ? t('learning.empty') : t('learning.queueComplete')) : t('learning.noBatch')}
          hint={batch ? (pending ? t('learning.emptyHint') : t('learning.queueCompleteHint')) : t('learning.noBatchHint')}
        />
      {/each}
    </div>
  </section>

  {#if sample}
    <div class="stack">
      <section class="surface sample-panel">
        <div class="panel-heading sample-heading">
          <div class="panel-heading-title">
            <LocateFixed size={17} />
            <h2>{sample.sampleId}</h2>
            <span class="sample-location">r{sample.row} · c{sample.col}</span>
          </div>
          <div class="sample-navigation" aria-label={t('learning.navigation')}>
            <button class="icon-button" aria-label={t('learning.previous')} title={t('learning.previous')} disabled={position === 0} onclick={() => focus(queue[position - 1]?.sampleId ?? null)}><ChevronLeft size={17} /></button>
            <span class="mono ltr-numeric">{position + 1} / {queue.length}</span>
            <button class="icon-button" aria-label={t('learning.next')} title={t('learning.next')} disabled={position + 1 >= queue.length} onclick={() => focus(queue[position + 1]?.sampleId ?? null)}><ChevronRight size={17} /></button>
          </div>
        </div>

        <div class="sample-image">
          {#if preview === 'imagery'}
            {#if thumbnail}
              <img src={thumbnail} alt={t('learning.sample', { id: sample.sampleId })} />
            {:else if thumbnailError}
              <div class="empty-state"><span>{thumbnailError}</span></div>
            {:else}
              <div class="empty-state"><span class="spinner"></span></div>
            {/if}
          {:else}
            <div class="prediction-view" aria-label={t('learning.prediction')}>
              <div class="prediction-swatch" style:background={classColor(sample.prediction ?? '', 0)}></div>
              <strong>{sample.prediction ?? t('common.notAvailable')}</strong>
              <span class="mono">{percent(sample.confidence)}</span>
            </div>
          {/if}
          <div class="segments preview-controls" role="group" aria-label={t('learning.prediction')}>
            <button class:chosen={preview === 'imagery'} aria-pressed={preview === 'imagery'} onclick={() => (preview = 'imagery')}>{t('map.layer.imagery')}</button>
            <button class:chosen={preview === 'prediction'} aria-pressed={preview === 'prediction'} onclick={() => (preview = 'prediction')}>{t('learning.prediction')}</button>
          </div>
        </div>

        <div class="sample-meta">
          <div>
            <small>{t('learning.prediction').toUpperCase()}</small>
            <strong class="class-label"><i class="class-dot" style:--class-color={classColor(sample.prediction ?? '', 0)}></i>{sample.prediction ?? '—'}</strong>
            <span>{t('map.confidence')}: {percent(sample.confidence)}</span>
          </div>
          <div>
            <small>{t('learning.uncertaintyScore').toUpperCase()}</small>
            <strong class="uncertainty mono">{percent(sample.uncertainty)}</strong>
            <span>{t('map.grid.patch', { size: Math.round(sample.window.x1 - sample.window.x0) })}</span>
          </div>
          <div>
            <small>{t('common.dataset').toUpperCase()}</small>
            <strong class="mono">{dataset?.name ?? '—'}</strong>
            <button class="button-link" onclick={() => showOnMap(sample)}><MapPin size={12} /> {t('learning.showOnMap')}</button>
          </div>
        </div>
      </section>

      <section class="surface section-box label-panel">
        <div class="section-heading">
          <div>
            <h2>{decision ? t('learning.resubmit') : t('learning.submit')}</h2>
            <p>{decision ? t('learning.reviewedOn', { date: date(decision.at) }) : t('learning.choose')}</p>
          </div>
          {#if decision}<span class="badge-live"><Check size={12} /> {t('common.reviewed')}</span>{/if}
        </div>

        <fieldset class="label-options">
          <legend class="sr-only">{t('common.classes')}</legend>
          {#each classes as name, index (name)}
            <label class="label-option" class:chosen={choice === name} style:--class-color={classColor(name, index)}>
              <input type="radio" name="review-label" value={name} checked={choice === name} onchange={() => (draft = name)} />
              <i class="class-dot"></i><span>{name}</span>
              <kbd>{index + 1}</kbd>
              {#if choice === name}<Check size={14} />{/if}
            </label>
          {/each}
        </fieldset>

        <div class="label-actions">
          <span class="label-hint">{t('learning.localDraftServer')}</span>
          <div class="label-buttons">
            {#if decision}
              <button class="button quiet" onclick={removeLabel} title={t('learning.delete')}><Trash2 size={14} /> {t('learning.delete')}</button>
            {/if}
            <button class="button" onclick={() => decide(sample, 'rejected')} title={t('learning.reject')}><X size={14} /> {t('learning.reject')}</button>
            <button class="button" onclick={skip} title={t('learning.skip')}><SkipForward size={14} /> {t('learning.skip')}</button>
            <button class="button primary" disabled={!choice || submitting || choice === decision?.className} onclick={submit}>
              {submitting ? t('learning.submitting') : decision ? t('learning.resubmit') : t('learning.submit')}
            </button>
          </div>
        </div>
      </section>
    </div>
  {:else}
    <div class="surface empty-state sample-empty">
      <LocateFixed size={26} />
      <strong>{batch ? t('learning.empty') : t('learning.noBatch')}</strong>
      <span>{batch ? t('learning.emptyHint') : t('learning.noBatchHint')}</span>
      {#if !batch}
        <button class="button primary" onclick={requestBatch} disabled={requesting || !workspace.dataset}>
          <Download size={14} /> {t('learning.request')}
        </button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .provenance-bar { padding: 12px 14px; display: grid; gap: 8px; }
  .prov-list { display: flex; flex-wrap: wrap; gap: 18px; margin: 0; }
  .prov-list > div { display: grid; gap: 1px; }
  .prov-list dt { color: var(--faint); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em; }
  .prov-list dd { margin: 0; color: var(--ink); font-size: 12.5px; }
  .history-panel { padding: 12px 14px; display: grid; gap: 8px; }
  .history-list { display: grid; gap: 6px; max-height: 230px; overflow: auto; }
  .history-row { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 7px 9px; border: 1px solid var(--line); border-radius: 6px; }
  .history-row.current { border-color: var(--control-border); background: rgba(74, 169, 255, 0.07); }
  .history-meta { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; font-size: 11.5px; }
  .history-facts { display: flex; gap: 8px; flex-wrap: wrap; font-size: 11px; color: var(--muted); }
  .queue-hint.warn { color: var(--warn); }
  .learning-layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 15px; align-items: start; }
  .queue-settings { padding: 12px; border-bottom: 1px solid var(--line); display: grid; gap: 9px; }
  .queue-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .queue-stats > div { display: grid; gap: 1px; }
  .queue-stats > div + div { border-inline-start: 1px solid var(--line); padding-inline-start: 12px; }
  .queue-stats strong { color: var(--ink); font-size: 22px; font-weight: 400; line-height: 1.2; }
  .queue-stats span { color: var(--muted); font-size: 11px; }
  .queue-progress { height: 4px; overflow: hidden; background: var(--control-border); border-radius: 5px; }
  .queue-progress i { display: block; height: 100%; background: var(--accent); border-radius: 5px; transition: width 200ms ease; }
  .queue-caption { color: var(--faint); font-size: 10.5px; display: flex; justify-content: space-between; gap: 6px; margin: 0; }
  .flag-count { color: var(--warn); }
  .queue-hint { margin: 0; color: var(--faint); font-size: 10.5px; line-height: 1.55; }
  .queue-tabs { display: flex; }
  .queue-tabs button { flex: 1; }
  .queue-filters { display: grid; gap: 8px; grid-template-columns: 0.95fr 1.05fr; }
  .text-input { min-height: 32px; padding: 0 8px; border-radius: 5px; border: 1px solid var(--control-border); background: var(--control-bg); color: var(--ink); font-size: 12px; }
  input[type='range'].text-input { padding: 0; border: 0; background: transparent; min-height: 20px; accent-color: var(--accent); }
  .sample-list { max-height: 396px; overflow: auto; padding: 5px; display: grid; align-content: start; }
  .sample-row { display: flex; align-items: center; text-align: start; gap: 7px; width: 100%; min-height: 47px; padding: 6px; border: 1px solid transparent; border-bottom-color: var(--line); }
  .sample-row.current { border: 1px solid var(--control-border); border-radius: 5px; background: var(--control-bg); }
  .sample-row:not(.current):hover { background: var(--control-border); border-radius: 5px; }
  .sample-row-icon { display: grid; place-items: center; flex: none; width: 22px; height: 22px; border-radius: 5px; color: var(--class-color, var(--accent)); background: color-mix(in srgb, var(--class-color, var(--info)) 16%, var(--control-bg)); }
  .sample-row-id { display: grid; flex: 1; min-width: 0; gap: 2px; }
  .sample-row-id strong { color: var(--ink); font: 10.5px var(--mono); overflow: hidden; text-overflow: ellipsis; }
  .sample-row-id small { color: var(--faint); font-size: 10px; }
  .sample-score { color: var(--warn); font-size: 10px; }
  .sample-heading { padding-block: 9px; }
  .sample-location { color: var(--faint); border-inline-start: 1px solid var(--border); padding-inline-start: 8px; font-size: 11px; }
  .sample-navigation { display: flex; gap: 5px; align-items: center; color: var(--muted); white-space: nowrap; font-size: 10.5px; }
  .sample-navigation .icon-button { border: 1px solid var(--border); }
  .sample-panel { overflow: hidden; }
  .sample-image { height: clamp(222px, 29vw, 345px); position: relative; display: grid; place-items: center; background: var(--plot-bg); }
  .sample-image img { max-width: 100%; max-height: 100%; image-rendering: pixelated; }
  .preview-controls { position: absolute; inset-block-start: 11px; inset-inline-start: 11px; background: #0e1a29ed; border-color: var(--faint); }
  .prediction-view { display: grid; place-items: center; gap: 6px; color: var(--muted); font-size: 12px; }
  .prediction-swatch { width: 84px; height: 84px; border-radius: 8px; opacity: 0.85; }
  .sample-meta { display: grid; grid-template-columns: 1.15fr 1fr 1.1fr; }
  .sample-meta > div { display: grid; align-content: start; min-width: 0; padding: 11px 13px; gap: 3px; }
  .sample-meta > div + div { border-inline-start: 1px solid var(--line); }
  .sample-meta small { font: 10px var(--mono); letter-spacing: 0.045em; color: var(--faint); }
  .sample-meta strong { color: var(--ink); font-size: 12px; font-weight: 560; overflow: hidden; text-overflow: ellipsis; }
  .sample-meta .uncertainty { color: var(--warn); }
  .sample-meta span, .sample-meta button { font-size: 10.5px; }
  .sample-meta span { color: var(--faint); }
  .label-options { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; padding: 0; border: 0; margin: 0; }
  .label-option { display: flex; align-items: center; gap: 7px; padding: 7px 9px; min-height: 36px; border: 1px solid var(--border); border-radius: 5px; color: var(--muted); background: var(--control-bg); cursor: pointer; font-size: 11.5px; }
  .label-option:hover, .label-option.chosen { color: var(--ink); border-color: color-mix(in srgb, var(--class-color) 66%, var(--control-border)); background: color-mix(in srgb, var(--class-color) 13%, var(--control-bg)); }
  .label-option input { width: 12px; height: 12px; accent-color: var(--class-color); }
  .label-option kbd { margin-inline-start: auto; font: 10px var(--mono); color: var(--faint); border: 1px solid var(--border); border-radius: 3px; padding: 1px 4px; }
  .label-option :global(svg) { margin-inline-start: auto; color: var(--class-color); flex: none; }
  .label-actions { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .label-buttons { display: flex; gap: 7px; flex-wrap: wrap; }
  .label-hint { color: var(--faint); font-size: 10.5px; max-width: 46ch; }
  .sample-empty { min-height: 282px; }
  .import-bar { display: flex; align-items: end; flex-wrap: wrap; gap: 8px 14px; padding: 10px 13px; margin-bottom: 13px; }
  .inline-field { min-width: min(240px, 100%); }
  .inline-field.compact { min-width: min(150px, 100%); }
  .train-bar { border-color: var(--control-border); }
  .train-bar .button { margin-bottom: 0; }
  .checkbox-field { flex-direction: row; align-items: center; gap: 6px; font-size: 11px; }
  .import-hint { color: var(--faint); font-size: 10.5px; margin-bottom: 9px; }
  .file-button { position: relative; overflow: hidden; }
  .file-button input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  .inline-info { display: grid; gap: 3px; padding: 9px 12px; margin-bottom: 13px; border: 1px solid var(--control-border); border-radius: 6px; background: var(--control-bg); color: var(--info); font-size: 11.5px; }
  .spinner { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--control-border); border-top-color: var(--accent); animation: spin 700ms linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 1100px) { .learning-layout { grid-template-columns: 258px minmax(0, 1fr); gap: 11px; } }
  @media (max-width: 900px) { .learning-layout { grid-template-columns: minmax(0, 1fr); } .sample-list { max-height: 210px; } }
  @media (max-width: 460px) { .sample-meta { grid-template-columns: 1fr; } .label-options { grid-template-columns: 1fr; } .sample-location { display: none; } }
</style>

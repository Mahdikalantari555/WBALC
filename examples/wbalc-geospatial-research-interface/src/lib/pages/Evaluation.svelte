<script lang="ts">
  import { ChartNoAxesCombined, Download, FileJson, FlaskConical, GitCompare, Layers, ShieldCheck, TriangleAlert } from '@lucide/svelte';
  import { api, ClientError } from '../client/api';
  import type {
    ComparisonView,
    ExperimentView,
    FusionView,
    RunLineageView,
    TemporalSeriesView,
  } from '../types';
  import ConfusionMatrix from '../components/ConfusionMatrix.svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import MetricBar from '../components/MetricBar.svelte';
  import MetricsTable from '../components/MetricsTable.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import { classColor } from '../palette';
  import { getWorkspace } from '../state.svelte';
  import { useT } from '../t.svelte';

  const workspace = getWorkspace();
  const { t, date, integer, percent, number } = useT();

  let runId = $state<string | null>(null);
  let focus = $state<'all' | string>('all');
  // ---- lineage (Phase 3)
  let lineage = $state<RunLineageView | null>(null);
  let lineageError = $state<string | null>(null);
  let experiments = $state<ExperimentView[]>([]);
  let experimentId = $state<string | null>(null);
  let comparison = $state<ComparisonView | null>(null);
  let comparisonError = $state<string | null>(null);
  let newExperiment = $state('');
  let busy = $state(false);
  // ---- scene products & late fusion (Phase 4)
  let fusions = $state<FusionView[]>([]);
  let fusionSeries = $state<TemporalSeriesView | null>(null);
  let fusionError = $state<string | null>(null);

  const runs = $derived(workspace.runs);

  $effect(() => {
    if (!runs.length) return;
    if (!runId || !runs.some((run) => run.id === runId)) runId = runs[0].id;
  });

  const run = $derived(runs.find((item) => item.id === runId) ?? runs[0] ?? null);
  const metrics = $derived(run?.metrics ?? null);

  /**
   * Current label distribution, counted once per sample.
   *
   * The adapter returns the latest version of each sample, but a project may
   * still hold labels for several datasets; counting rows instead of distinct
   * samples would inflate a class whenever a label was corrected.
   */
  const labelledSamples = $derived.by(() => {
    const byId = new Map<string, string>();
    for (const label of workspace.labels) {
      if (!byId.has(label.sampleId)) byId.set(label.sampleId, label.className);
    }
    return [...byId.values()];
  });

  const distribution = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const className of labelledSamples) {
      counts.set(className, (counts.get(className) ?? 0) + 1);
    }
    const total = labelledSamples.length || 1;
    return (workspace.project?.classes ?? []).map((name, index) => ({
      name,
      index,
      count: counts.get(name) ?? 0,
      share: (counts.get(name) ?? 0) / total,
    }));
  });

  /** Load the run's reproducibility record; "legacy" is shown, not filled in. */
  async function loadLineage(id: string | null) {
    if (!id || !workspace.project) {
      lineage = null;
      return;
    }
    lineageError = null;
    try {
      lineage = await api.runLineage(workspace.project.id, id);
    } catch (error) {
      lineage = null;
      lineageError = error instanceof ClientError ? error.message : String(error);
    }
  }

  async function loadExperiments() {
    if (!workspace.project) return;
    try {
      experiments = await api.experiments(workspace.project.id);
    } catch {
      experiments = [];
    }
  }

  async function loadComparison(id: string | null = experimentId) {
    if (!workspace.project) return;
    comparisonError = null;
    try {
      if (id) {
        const experiment = experiments.find((entry) => entry.id === id);
        comparison = experiment?.runIds.length
          ? await api.compareRuns(workspace.project.id, experiment.runIds)
          : null;
      } else {
        comparison = await api.compareRuns(workspace.project.id, []);
      }
    } catch (error) {
      comparison = null;
      comparisonError = error instanceof ClientError ? error.message : String(error);
    }
  }

  async function createExperiment() {
    if (!workspace.project || !newExperiment.trim()) return;
    busy = true;
    try {
      const created = await api.createExperiment(workspace.project.id, {
        name: newExperiment.trim(),
        runIds: runId ? [runId] : [],
      });
      newExperiment = '';
      experimentId = created.id;
      await loadExperiments();
      await loadComparison(created.id);
      workspace.notify(t('evaluation.experiment.created', { name: created.name }));
    } catch (error) {
      comparisonError = error instanceof ClientError ? error.message : String(error);
    } finally {
      busy = false;
    }
  }

  async function addCurrentRun() {
    if (!workspace.project || !experimentId || !runId) return;
    try {
      await api.addRunsToExperiment(workspace.project.id, experimentId, [runId]);
      await loadExperiments();
      await loadComparison(experimentId);
    } catch (error) {
      comparisonError = error instanceof ClientError ? error.message : String(error);
    }
  }

  $effect(() => {
    const current = run?.id ?? null;
    void loadLineage(current);
  });

  $effect(() => {
    if (workspace.project) void loadExperiments();
  });

  /** Per-date single-sensor areas and recorded fused products, for one table. */
  async function loadFusionComparison() {
    if (!workspace.project) return;
    fusionError = null;
    try {
      const [recorded, series] = await Promise.all([
        api.fusions(workspace.project.id),
        api.temporalSeries(workspace.project.id).catch((error: unknown) => {
          // 409 = nothing classified yet, which is an empty state, not a fault.
          if (error instanceof ClientError && error.status === 409) return null;
          throw error;
        }),
      ]);
      fusions = recorded;
      fusionSeries = series;
    } catch (error) {
      fusions = [];
      fusionSeries = null;
      fusionError = error instanceof ClientError ? error.message : String(error);
    }
  }

  $effect(() => {
    if (workspace.project) void loadFusionComparison();
  });

  function hectares(squareMetres: number): string {
    return `${number(squareMetres / 10_000, 2)} ha`;
  }

  function downloadCsv() {
    if (!metrics) return;
    const escape = (value: string | number | boolean | null) =>
      `"${String(value ?? '').replace(/"/g, '""')}"`;
    const rows = [
      [
        'project',
        'iteration',
        'model_type',
        'resolution',
        'evaluation',
        'evaluation_strategy',
        'class',
        'support',
        'precision',
        'recall',
        'f1',
        'iou',
        'accuracy',
        'f1_macro',
        'f1_weighted',
        'n_train',
        'n_test',
        'insufficient',
      ],
      ...metrics.perClass
        .filter((row) => focus === 'all' || row.className === focus)
        .map((row) => [
          workspace.project?.name ?? '',
          metrics.iteration,
          metrics.modelType,
          metrics.resolution,
          metrics.evaluation,
          metrics.evaluationStrategy ?? '',
          row.className,
          row.support,
          row.precision,
          row.recall,
          row.f1,
          row.iou,
          metrics.accuracy,
          metrics.f1Macro,
          metrics.f1Weighted,
          metrics.nTrain,
          metrics.nTest,
          metrics.insufficient,
        ]),
    ];
    save(
      `wbalc-evaluation-${metrics.iteration}-${metrics.modelType}.csv`,
      'text/csv;charset=utf-8',
      rows.map((row) => row.map(escape).join(',')).join('\r\n'),
    );
    workspace.notify(t('evaluation.exported'));
  }

  function downloadJson() {
    if (!run || !metrics) return;
    save(
      `wbalc-evaluation-${metrics.iteration}-${metrics.modelType}.json`,
      'application/json',
      JSON.stringify(
        {
          project: { id: workspace.project?.id, name: workspace.project?.name },
          run: { id: run.id, iteration: run.iteration, modelType: run.modelType, resolution: run.resolution },
          evaluation: {
            protocol: metrics.evaluation,
            // Recorded so a reader cannot mistake an in-sample fit for a
            // validated score, or a spatial holdout for a random one.
            protocolCaveat: metrics.insufficient
              ? 'insufficient held-out data: metrics are in-sample'
              : metrics.evaluationStrategy === 'random'
                ? 'random holdout over neighbouring patches: optimistic'
                : null,
            strategy: metrics.evaluationStrategy,
            details: metrics.evaluationDetails,
            nSamples: metrics.nSamples,
            nTrain: metrics.nTrain,
            nTest: metrics.nTest,
            heldOutGroups: metrics.heldOutGroups,
          },
          classes: metrics.classes,
          confusionMatrix: metrics.confusionMatrix,
          perClass: metrics.perClass,
          accuracy: metrics.accuracy,
          f1Macro: metrics.f1Macro,
          f1Weighted: metrics.f1Weighted,
        },
        null,
        2,
      ),
    );
    workspace.notify(t('evaluation.exported'));
  }

  function save(filename: string, mime: string, content: string) {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
</script>

<PageHeading
  title={t('evaluation.title')}
  description={t('evaluation.description')}
  eyebrow={workspace.project ? `#${workspace.project.id} · ${t('evaluation.hint')}` : 'WBALC'}
>
  {#snippet actions()}
    <button class="button" onclick={downloadCsv} disabled={!metrics}><Download size={15} /> {t('evaluation.exportCsv')}</button>
    <button class="button" onclick={downloadJson} disabled={!metrics}><FileJson size={15} /> {t('evaluation.exportJson')}</button>
  {/snippet}
</PageHeading>

{#if !runs.length}
  <div class="surface">
    <EmptyState title={t('evaluation.noMetrics')} hint={t('evaluation.noMetricsHint')} />
  </div>
{:else}
  <div class="surface evaluation-filters">
    <label class="field">
      {t('evaluation.model')}
      <select class="select" bind:value={runId}>
        {#each runs as item (item.id)}
          <option value={item.id}>#{item.iteration} · {item.modelType} · {item.resolution}</option>
        {/each}
      </select>
    </label>
    <label class="field">
      {t('evaluation.class')}
      <select class="select" bind:value={focus}>
        <option value="all">{t('common.all')}</option>
        {#each metrics?.classes ?? [] as name}<option value={name}>{name}</option>{/each}
      </select>
    </label>
    {#if metrics}
      <p class="filter-meta">
        {metrics.evaluationStrategy ?? metrics.evaluation} · {t('evaluation.evaluated')} {date(metrics.createdAt)}
      </p>
    {/if}
  </div>

  <section class="surface section-box" aria-labelledby="fusion-heading">
    <div class="section-heading">
      <div>
        <h2 id="fusion-heading"><Layers size={15} /> {t('evaluation.fusion.title')}</h2>
        <p>{t('evaluation.fusion.description')}</p>
      </div>
      <Layers size={16} class="faint" />
    </div>

    {#if fusionError}
      <p class="note-block warn">{fusionError}</p>
    {:else if !fusions.length}
      <p class="note-block">{t('evaluation.fusion.empty')}</p>
    {:else}
      <div class="table-scroll">
        <table class="compare-table">
          <thead>
            <tr>
              <th>{t('evaluation.fusion.product')}</th>
              <th>{t('evaluation.fusion.rule')}</th>
              <th>{t('evaluation.fusion.sources')}</th>
              <th>{t('temporal.waterArea')}</th>
              <th>{t('temporal.fusionAgreement')}</th>
              <th>{t('evaluation.fusion.digest')}</th>
            </tr>
          </thead>
          <tbody>
            {#each fusions as fusion (fusion.id)}
              <tr>
                <td>
                  {fusion.name || `#${fusion.id}`}
                  <small class="mono small">
                    {fusion.aligned ? t('temporal.derivedBadge') : t('temporal.nativeBadge')}
                  </small>
                </td>
                <td>{fusion.rule} · {fusion.missingPolicy}</td>
                <td class="mono small">
                  {#each fusion.sources as source (source.analysisId)}
                    <span class="source-chip" class:aligned={source.gridAligned}>
                      {source.sensor} · #{source.sceneId} · w {number(source.weight, 2)}
                    </span>
                  {/each}
                </td>
                <td class="mono ltr-numeric">
                  {fusion.areas?.water ? hectares(fusion.areas.water.areaM2) : '—'}
                </td>
                <td class="mono ltr-numeric">
                  {fusion.unanimousShare === null ? '—' : percent(fusion.unanimousShare)}
                </td>
                <td class="mono small">{fusion.fusionDigest ? fusion.fusionDigest.slice(0, 10) : '—'}…</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      {#if fusionSeries && fusionSeries.dates.length}
        <span class="section-label">{t('temporal.singleSensorHeading')}</span>
        <div class="table-scroll">
          <table class="compare-table">
            <thead>
              <tr>
                <th>{t('common.date')}</th>
                <th>{t('common.sensor')}</th>
                <th>{t('temporal.validArea')}</th>
                <th>{t('temporal.waterArea')}</th>
                <th>{t('temporal.coverage')}</th>
              </tr>
            </thead>
            <tbody>
              {#each fusionSeries.dates as point (point.analysisId)}
                <tr>
                  <td class="mono">{date(point.acquisitionDateTime)}</td>
                  <td>{point.sensor ?? '—'}</td>
                  <td class="mono ltr-numeric">{hectares(point.validAreaM2)}</td>
                  <td class="mono ltr-numeric">{point.water ? hectares(point.water.areaM2) : '—'}</td>
                  <td class="mono ltr-numeric">{percent(point.coverage)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#each fusionSeries.caveats as caveat}
          <p class="note-block">{caveat}</p>
        {/each}
      {:else}
        <p class="note-block">{t('temporal.fusionNeedTwo')}</p>
      {/if}
      <p class="note-block faint">{t('temporal.earlyFusionNote')}</p>
    {/if}
  </section>

  <section class="surface section-box experiment-panel" aria-labelledby="experiment-heading">
    <div class="section-heading">
      <div>
        <h2 id="experiment-heading"><FlaskConical size={15} /> {t('evaluation.experiment.title')}</h2>
        <p>{t('evaluation.experiment.description')}</p>
      </div>
      <GitCompare size={16} class="faint" />
    </div>
    <div class="experiment-controls">
      <input
        class="text-input"
        placeholder={t('evaluation.experiment.namePlaceholder')}
        bind:value={newExperiment}
      />
      <button class="button" onclick={createExperiment} disabled={busy || !newExperiment.trim()}>
        {t('evaluation.experiment.create')}
      </button>
      <select
        class="select"
        value={experimentId ?? ''}
        onchange={(event) => {
          experimentId = (event.currentTarget as HTMLSelectElement).value || null;
          void loadComparison(experimentId);
        }}
      >
        <option value="">{t('evaluation.experiment.allRuns')}</option>
        {#each experiments as entry (entry.id)}
          <option value={entry.id}>{entry.name} ({entry.runIds.length})</option>
        {/each}
      </select>
      {#if experimentId}
        <button class="button quiet" onclick={addCurrentRun} disabled={!runId}>
          {t('evaluation.experiment.addCurrent')}
        </button>
      {/if}
    </div>

    {#if comparisonError}
      <p class="note-block warn">{comparisonError}</p>
    {:else if comparison}
      <p class="comparison-verdict" class:ok={comparison.comparable}>
        {comparison.comparable
          ? t('evaluation.compare.comparable')
          : t('evaluation.compare.notComparable')}
      </p>
      <div class="table-scroll">
        <table class="compare-table">
          <thead>
            <tr>
              <th>{t('evaluation.experiment.run')}</th>
              <th>{t('evaluation.experiment.model')}</th>
              <th>{t('evaluation.experiment.protocol')}</th>
              <th>{t('arena.accuracy')}</th>
              <th>{t('arena.f1')}</th>
              <th>{t('evaluation.experiment.labels')}</th>
              <th>{t('evaluation.experiment.lineage')}</th>
            </tr>
          </thead>
          <tbody>
            {#each comparison.runs as row (row.runId)}
              <tr>
                <td class="mono">#{row.iteration}</td>
                <td>{row.modelType} · {String(row.config.resolution ?? '—')}</td>
                <td>{row.config.evaluation_strategy ?? row.evaluation ?? '—'}</td>
                <td class="mono ltr-numeric">{row.accuracy === null ? '—' : percent(row.accuracy)}</td>
                <td class="mono ltr-numeric">{row.f1Macro === null ? '—' : percent(row.f1Macro)}</td>
                <td class="mono ltr-numeric small">{row.labelSnapshotHash ? row.labelSnapshotHash.slice(0, 8) : '—'}</td>
                <td>
                  <span class={`lineage-status ${row.status}`}>{t(`evaluation.lineage.status.${row.status}`)}</span>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if Object.keys(comparison.differences).length}
        <div class="differences">
          <span class="section-label">{t('evaluation.compare.differences')}</span>
          <ul>
            {#each Object.keys(comparison.differences) as key (key)}
              <li class="mono small">{key}</li>
            {/each}
          </ul>
        </div>
      {/if}
      {#each comparison.caveats as caveat}
        <p class="note-block">{caveat}</p>
      {/each}
    {:else}
      <p class="note-block">{t('evaluation.compare.empty')}</p>
    {/if}
  </section>

  {#if metrics}
    <div class="evaluation-grid">
      <div class="stack">
        <section class="surface section-box" aria-labelledby="lineage-heading">
          <div class="section-heading">
            <div>
              <h2 id="lineage-heading">{t('evaluation.lineage.title')}</h2>
              <p>{t('evaluation.lineage.description')}</p>
            </div>
            {#if lineage?.status === 'complete'}
              <ShieldCheck size={16} class="accent" />
            {:else}
              <TriangleAlert size={16} class="warn-icon" />
            {/if}
          </div>
          {#if lineageError}
            <p class="note-block warn">{lineageError}</p>
          {:else if lineage}
            <dl class="kv-list">
              <div>
                <dt>{t('evaluation.lineage.status')}</dt>
                <dd class={`lineage-status ${lineage.status}`}>{t(`evaluation.lineage.status.${lineage.status}`)}</dd>
              </div>
              <div>
                <dt>{t('evaluation.lineage.manifest')}</dt>
                <dd class="mono ltr-numeric small">{lineage.manifestHash ? `${lineage.manifestHash.slice(0, 16)}…` : t('evaluation.lineage.unavailable')}</dd>
              </div>
              <div>
                <dt>{t('evaluation.lineage.labels')}</dt>
                <dd class="mono ltr-numeric small">{lineage.labelSnapshotHash ? `${lineage.labelSnapshotHash.slice(0, 16)}…` : t('evaluation.lineage.unavailable')}</dd>
              </div>
              {#each lineage.inputs as input (input.datasetId)}
                <div>
                  <dt>{t('evaluation.lineage.input', { id: input.datasetId })}</dt>
                  <dd class="mono ltr-numeric small">{input.sha256 ? `${input.sha256.slice(0, 16)}…` : t('evaluation.lineage.noContentHash')}</dd>
                </div>
              {/each}
              <div>
                <dt>{t('evaluation.lineage.checkpoint')}</dt>
                <dd>
                  {#if lineage.artifact?.verified}
                    <span class="lineage-status complete">{t('evaluation.lineage.artifactVerified')}</span>
                  {:else if lineage.artifact?.reason}
                    <span class="lineage-status legacy">{lineage.artifact.reason}</span>
                  {:else}
                    {t('evaluation.lineage.unavailable')}
                  {/if}
                </dd>
              </div>
              {#if lineage.environment?.revision}
                <div>
                  <dt>{t('evaluation.lineage.revision')}</dt>
                  <dd class="mono ltr-numeric small">{lineage.environment.revision.slice(0, 12)}</dd>
                </div>
              {/if}
            </dl>
            {#if lineage.missing.length}
              <p class="note-block warn">
                <strong>{t('evaluation.lineage.missing')}</strong>{lineage.missing.join(', ')}
              </p>
            {/if}
            {#each lineage.notes as note}
              <p class="note-block">{note}</p>
            {/each}
          {/if}
        </section>

        <MetricsTable {metrics} focus={focus} />
        <ConfusionMatrix {metrics} focus={focus} />
      </div>

      <div class="stack">
        <section class="surface section-box">
          <div class="section-heading">
            <div>
              <h2>{t('evaluation.protocol')}</h2>
              <p>{metrics.evaluation}</p>
            </div>
            <ChartNoAxesCombined size={16} class="faint" />
          </div>
          <dl class="kv-list">
            <div><dt>{t('evaluation.protocol')}</dt><dd>{metrics.evaluationStrategy === 'spatial' ? t('evaluation.protocol.spatial') : t('evaluation.protocol.random')}</dd></div>
            <div><dt>{t('evaluation.groups')}</dt><dd>{metrics.heldOutGroups === null ? '—' : integer(metrics.heldOutGroups)}</dd></div>
            <div><dt>{t('evaluation.nTrain')}</dt><dd>{metrics.nTrain === null ? '—' : integer(metrics.nTrain)}</dd></div>
            <div><dt>{t('evaluation.nTest')}</dt><dd>{metrics.nTest === null ? '—' : integer(metrics.nTest)}</dd></div>
            <div><dt>{t('arena.accuracy')}</dt><dd>{percent(metrics.accuracy)}</dd></div>
            <div><dt>{t('arena.f1')} (macro)</dt><dd>{percent(metrics.f1Macro)}</dd></div>
            <div><dt>{t('arena.f1')} (weighted)</dt><dd>{percent(metrics.f1Weighted)}</dd></div>
            <div><dt>{t('arena.resolution')}</dt><dd>{metrics.resolution}</dd></div>
          </dl>
          {#if metrics.insufficient}
            <p class="note-block warn"><strong>{t('arena.insufficient')}</strong>{t('overview.insufficient')}</p>
          {:else if metrics.evaluationStrategy === 'random'}
            <p class="note-block"><strong>{t('evaluation.protocolCaveat')}</strong>{t('overview.randomCaveat')}</p>
          {/if}
          {#if metrics.evaluationDetails}
            <p class="note-block"><strong>{t('evaluation.notes')}</strong>{metrics.evaluationDetails}</p>
          {/if}
        </section>

        <section class="surface section-box">
          <div class="section-heading">
            <div>
              <h2>{t('evaluation.perClassIoU')}</h2>
              <p>{t('arena.perClass')}</p>
            </div>
          </div>
          <div class="iou-rows">
            {#each metrics.perClass as row (row.className)}
              <MetricBar
                label={row.className}
                value={row.iou}
                display={percent(row.iou)}
                hint={`${t('arena.support')}: ${integer(row.support)}`}
              />
            {/each}
          </div>
        </section>

        <section class="surface section-box">
          <div class="section-heading">
            <div>
              <h2>{t('evaluation.classDistribution')}</h2>
              <p>{t('evaluation.classDistributionHint', { count: labelledSamples.length })}</p>
            </div>
          </div>
          {#if labelledSamples.length}
            <div class="distribution">
              {#each distribution as item (item.name)}
                <div class="distribution-row">
                  <span class="class-label"><i class="class-dot" style:--class-color={classColor(item.name, item.index)}></i>{item.name}</span>
                  <span class="mono ltr-numeric">{integer(item.count)}</span>
                  <div class="distribution-track"><i style:width={`${item.share * 100}%`}></i></div>
                </div>
              {/each}
            </div>
          {:else}
            <EmptyState title={t('evaluation.noLabels')} hint={t('evaluation.noLabelsHint')} />
          {/if}
        </section>
      </div>
    </div>
  {/if}
{/if}

<style>
  .source-chip { display: inline-block; margin-inline-end: 5px; padding: 1px 5px; border: 1px solid var(--line); border-radius: 4px; font-size: 9.5px; }
  .source-chip.aligned { color: #e5a25a; border-color: #7a5528; }
  .lineage-status { font-size: 11px; padding: 1px 6px; border-radius: 4px; border: 1px solid var(--line); }
  .lineage-status.complete { color: #7fd6b4; border-color: #2f6b57; }
  .lineage-status.incomplete { color: #e5a25a; border-color: #7a5528; }
  .lineage-status.legacy { color: #9fb2c4; }
  .accent { color: #66dcbe; }
  .warn-icon { color: #e5a25a; }
  .small { font-size: 11px; }
  .experiment-panel { display: grid; gap: 10px; }
  .experiment-controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .experiment-controls .text-input, .experiment-controls .select { max-width: 240px; }
  .comparison-verdict { margin: 0; font-size: 12px; color: #e5a25a; }
  .comparison-verdict.ok { color: #7fd6b4; }
  .table-scroll { overflow-x: auto; }
  .compare-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .compare-table th, .compare-table td { text-align: start; padding: 5px 8px; border-bottom: 1px solid var(--line); }
  .compare-table th { color: var(--faint); font-weight: 400; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em; }
  .differences ul { margin: 4px 0 0; padding-inline-start: 16px; color: var(--muted); }
  .evaluation-filters { display: flex; align-items: end; flex-wrap: wrap; gap: 10px 15px; padding: 13px 15px; margin-bottom: 15px; }
  .evaluation-filters .field { min-width: min(190px, 100%); }
  .filter-meta { color: var(--faint); margin: 0 0 8px auto; font-size: 11px; }
  .evaluation-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(280px, 1fr); gap: 15px; align-items: start; }
  .iou-rows { display: grid; gap: 12px; }
  .note-block { margin: 10px 0 0; padding-top: 9px; border-top: 1px solid var(--line); color: var(--muted); font-size: 11px; line-height: 1.6; }
  .note-block.warn { color: var(--warn); }
  .note-block strong { display: block; color: var(--ink); font-size: 10.5px; margin-bottom: 3px; font-family: var(--mono); letter-spacing: 0.04em; }
  .distribution { display: grid; gap: 9px; }
  .distribution-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 8px; align-items: center; font-size: 11.5px; }
  .distribution-row .mono { color: var(--ink); font-size: 11px; }
  .distribution-track { grid-column: 1 / -1; height: 4px; border-radius: 4px; background: #293c50; overflow: hidden; }
  .distribution-track i { display: block; height: 100%; background: #52b9a8; border-radius: 4px; }
  @media (max-width: 1130px) {
    .evaluation-grid { grid-template-columns: minmax(0, 1fr); }
    .filter-meta { margin: 0; }
  }
</style>

<script lang="ts">
  import { ChartNoAxesCombined, Download, FileJson } from '@lucide/svelte';
  import ConfusionMatrix from '../components/ConfusionMatrix.svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import MetricBar from '../components/MetricBar.svelte';
  import MetricsTable from '../components/MetricsTable.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import { classColor } from '../palette';
  import { getWorkspace } from '../state.svelte';
  import { useT } from '../t.svelte';

  const workspace = getWorkspace();
  const { t, date, integer, percent } = useT();

  let runId = $state<string | null>(null);
  let focus = $state<'all' | string>('all');

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

  {#if metrics}
    <div class="evaluation-grid">
      <div class="stack">
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

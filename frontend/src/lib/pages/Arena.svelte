<script lang="ts">
  import { ArrowRight, FlaskConical } from '@lucide/svelte';
  import ConfusionMatrix from '../components/ConfusionMatrix.svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import MetricsTable from '../components/MetricsTable.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import { getWorkspace } from '../state.svelte';
  import { useT } from '../t.svelte';

  const workspace = getWorkspace();
  const { t, date, integer, percent } = useT();

  let inspect = $state<'A' | 'B'>('A');

  const runs = $derived(workspace.runs);
  const primary = $derived(runs.find((run) => run.id === workspace.arena.primary) ?? runs[0] ?? null);
  const challenger = $derived(
    runs.find((run) => run.id === workspace.arena.challenger) ?? runs[1] ?? runs[0] ?? null,
  );
  const inspected = $derived(inspect === 'A' ? primary : challenger);

  const rows = $derived(
    [primary, challenger]
      .filter((run, index, list): run is NonNullable<typeof run> => Boolean(run) && list.findIndex((item) => item?.id === run?.id) === index)
      .map((run) => ({
        run,
        iou: run.metrics.perClass.length
          ? run.metrics.perClass.reduce((sum, row) => sum + (row.iou ?? 0), 0) / run.metrics.perClass.length
          : null,
      })),
  );

  /**
   * Why two runs may not be directly comparable.
   *
   * The engine records resolution, protocol and sample counts per run, but not
   * a content manifest; rather than implying identical inputs, the arena states
   * every recorded difference it knows about.
   */
  const differences = $derived.by(() => {
    if (!primary || !challenger || primary.id === challenger.id) return [];
    const found: string[] = [];
    if (primary.metrics.resolution !== challenger.metrics.resolution) found.push('resolution');
    if (primary.metrics.evaluationStrategy !== challenger.metrics.evaluationStrategy) found.push('protocol');
    if (primary.metrics.nSamples !== challenger.metrics.nSamples) found.push('samples');
    if (primary.metrics.modelType !== challenger.metrics.modelType) found.push('modelType');
    if (
      primary.metrics.classes.join('|') !== challenger.metrics.classes.join('|')
    )
      found.push('taxonomy');
    if (primary.metrics.insufficient !== challenger.metrics.insufficient) found.push('scoring');
    return found;
  });

  function label(run: (typeof runs)[number] | null) {
    return run ? `#${run.iteration} · ${run.modelType} · ${run.resolution}` : '—';
  }
</script>

<PageHeading
  title={t('arena.title')}
  description={t('arena.description')}
  eyebrow={workspace.project ? `#${workspace.project.id} · ${t('arena.comparisonHint')}` : 'WBALC'}
>
  {#snippet actions()}
    <button class="button" onclick={() => workspace.go('evaluation')} disabled={!inspected}
      >{t('arena.openEvaluation')} <ArrowRight size={15} /></button
    >
  {/snippet}
</PageHeading>

{#if !runs.length}
  <div class="surface">
    <EmptyState title={t('arena.noRuns')} hint={t('arena.noRunsHint')} />
  </div>
{:else}
  <div class="surface model-picker-bar">
    <div class="picker">
      <span class="arena-letter">A</span>
      <label class="field">
        {t('arena.primary')}
        <select class="select" value={workspace.arena.primary ?? ''} onchange={(event) => (workspace.arena.primary = event.currentTarget.value)}>
          {#each runs as run (run.id)}<option value={run.id}>{label(run)}</option>{/each}
        </select>
      </label>
    </div>
    <div class="picker">
      <span class="arena-letter second">B</span>
      <label class="field">
        {t('arena.challenger')}
        <select class="select" value={workspace.arena.challenger ?? ''} onchange={(event) => (workspace.arena.challenger = event.currentTarget.value)}>
          {#each runs as run (run.id)}<option value={run.id}>{label(run)}</option>{/each}
        </select>
      </label>
    </div>
    <div class="inspect-control">
      <span class="section-label">{t('arena.inspect')}</span>
      <div class="segments" role="group" aria-label={t('arena.inspect')}>
        <button class:chosen={inspect === 'A'} aria-pressed={inspect === 'A'} onclick={() => (inspect = 'A')}>A</button>
        <button class:chosen={inspect === 'B'} aria-pressed={inspect === 'B'} onclick={() => (inspect = 'B')}>B</button>
      </div>
    </div>
  </div>

  {#if runs.length === 1}<p class="single-note">{t('arena.onlyOne')}</p>{/if}
  {#if differences.length}
    <p class="single-note" role="status">
      {t('arena.notComparable', { fields: differences.join(', ') })}
    </p>
  {/if}

  <section class="surface section-box">
    <div class="section-heading">
      <div>
        <h2>{t('arena.comparison')}</h2>
        <p>{t('arena.comparisonHint')}</p>
      </div>
      <FlaskConical size={16} class="faint" />
    </div>
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th scope="col">{t('arena.config')}</th>
            <th class="number" scope="col">{t('arena.accuracy')}</th>
            <th class="number" scope="col">{t('arena.f1')}</th>
            <th class="number" scope="col">{t('arena.iou')}</th>
            <th class="number" scope="col">{t('arena.samples')}</th>
            <th class="number" scope="col">{t('evaluation.nTest')}</th>
            <th class="number" scope="col">{t('arena.trained')}</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as { run, iou }, index (run.id)}
            <tr class:selected={inspected?.id === run.id}>
              <td>
                <button class="model-name" onclick={() => (inspect = index === 0 ? 'A' : 'B')}>
                  <span class="model-letter" class:second={index === 1}>{index === 0 ? 'A' : 'B'}</span>
                  {label(run)}
                </button>
              </td>
              <td class="number">{percent(run.metrics.accuracy)}</td>
              <td class="number">{percent(run.metrics.f1Macro)}</td>
              <td class="number">{percent(iou)}</td>
              <td class="number">{integer(run.metrics.nSamples)}</td>
              <td class="number">{run.metrics.nTest === null ? '—' : integer(run.metrics.nTest)}</td>
              <td class="number">{date(run.metrics.createdAt)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <div class="arena-top">
    {#if inspected}
      <section class="surface">
        <div class="panel-heading">
          <div class="panel-heading-title"><FlaskConical size={16} /><h2>{t('arena.config')}</h2></div>
          <span class="badge-muted">{inspected.metrics.resolution}</span>
        </div>
        <div class="panel-body">
          <dl class="kv-list">
            <div><dt>{t('arena.iteration')}</dt><dd>{integer(inspected.metrics.iteration)}</dd></div>
            <div><dt>{t('arena.modelType')}</dt><dd>{inspected.metrics.modelType}</dd></div>
            <div><dt>{t('arena.resolution')}</dt><dd>{inspected.metrics.resolution}</dd></div>
            <div><dt>{t('evaluation.protocol')}</dt><dd>{inspected.metrics.evaluationStrategy ?? inspected.metrics.evaluation}</dd></div>
            <div><dt>{t('arena.samples')}</dt><dd>{integer(inspected.metrics.nSamples)}</dd></div>
            <div><dt>{t('arena.trainTest')}</dt><dd>{inspected.metrics.nTrain === null ? '—' : integer(inspected.metrics.nTrain)} / {inspected.metrics.nTest === null ? '—' : integer(inspected.metrics.nTest)}</dd></div>
            <div><dt>{t('evaluation.groups')}</dt><dd>{inspected.metrics.heldOutGroups === null ? '—' : integer(inspected.metrics.heldOutGroups)}</dd></div>
            <div><dt>{t('arena.trained')}</dt><dd>{date(inspected.metrics.createdAt)}</dd></div>
            <div><dt>{t('arena.f1')} (weighted)</dt><dd>{percent(inspected.metrics.f1Weighted)}</dd></div>
            <div><dt>{t('common.classes')}</dt><dd>{inspected.metrics.classes.join(', ')}</dd></div>
          </dl>
          {#if inspected.metrics.insufficient}
            <p class="insufficient">{t('arena.insufficient')}</p>
            <p class="insufficient">{t('overview.insufficient')}</p>
          {:else if inspected.metrics.evaluationStrategy === 'random'}
            <p class="insufficient">{t('overview.randomCaveat')}</p>
          {/if}
        </div>
      </section>
    {:else}
      <div class="surface"><EmptyState title={t('arena.noMetrics')} /></div>
    {/if}

    {#if inspected}
      <ConfusionMatrix metrics={inspected.metrics} />
    {/if}
  </div>

  {#if inspected}
    <MetricsTable metrics={inspected.metrics} />
  {/if}
{/if}

<style>
  .model-picker-bar { display: flex; gap: 12px 19px; align-items: end; flex-wrap: wrap; padding: 13px 15px; margin-bottom: 15px; }
  .picker { display: flex; align-items: end; gap: 8px; min-width: min(240px, 100%); }
  .picker :global(.field) { flex: 1; }
  .arena-letter { display: inline-grid; place-items: center; flex: none; width: 22px; height: 22px; margin-bottom: 6px; border-radius: 4px; border: 1px solid var(--control-border); background: var(--control-bg); color: var(--accent); font: 11px var(--mono); }
  .arena-letter.second { background: var(--control-border); border-color: var(--control-border); color: var(--info); }
  .inspect-control { display: grid; gap: 6px; margin-inline-start: auto; }
  .single-note { margin: -6px 0 13px; color: var(--warn); font-size: 11px; }
  .arena-top { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr); gap: 15px; align-items: start; margin-top: 15px; margin-bottom: 15px; }
  .model-name { display: inline-flex; font-weight: 560; align-items: center; gap: 7px; padding: 2px 0; white-space: nowrap; }
  .model-name:hover { text-decoration: underline; color: var(--accent); }
  .model-letter { display: grid; place-items: center; width: 16px; height: 16px; font: 10px var(--mono); border: 1px solid var(--control-border); color: var(--accent); background: var(--control-bg); border-radius: 4px; }
  .model-letter.second { background: var(--control-border); border-color: var(--control-border); color: var(--info); }
  .insufficient { margin: 8px 0 0; color: var(--warn); font-size: 11px; }
  @media (max-width: 1150px) {
    .arena-top { grid-template-columns: minmax(0, 1fr); }
    .inspect-control { margin-inline-start: 0; }
  }
  @media (max-width: 700px) { .picker { width: 100%; } }
</style>

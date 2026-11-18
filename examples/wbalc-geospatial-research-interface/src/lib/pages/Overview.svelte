<script lang="ts">
  import { ArrowRight, CalendarDays, Check, CircleDashed, Layers, MapPin, Tags } from '@lucide/svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import MetricBar from '../components/MetricBar.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import TimelineChart, { type TimelinePoint } from '../components/TimelineChart.svelte';
  import { classColor } from '../palette';
  import { getWorkspace, type ViewId } from '../state.svelte';
  import { useT } from '../t.svelte';

  const workspace = getWorkspace();
  const { t, date, integer, percent } = useT();

  const project = $derived(workspace.project);
  const metrics = $derived(workspace.latestRun?.metrics ?? null);
  const colors = $derived(
    (project?.classes ?? []).map((name, index) => ({ name, color: classColor(name, index) })),
  );

  const timeline = $derived<TimelinePoint[]>([
    ...workspace.scenes
      .filter((scene) => scene.acquisitionDateTime)
      .map((scene) => ({
        id: `scene-${scene.id}`,
        date: Date.parse(scene.acquisitionDateTime!),
        label: scene.sourceFilename,
        sensor: scene.sensor,
        kind: 'scene' as const,
      })),
    ...workspace.datasets.map((dataset) => ({
      id: `dataset-${dataset.id}`,
      date: Date.parse(dataset.createdAt),
      label: dataset.name,
      sensor: 'Dataset',
      kind: 'dataset' as const,
    })),
  ]);

  const checks = $derived([
    { key: 'overview.check.dataset' as const, done: workspace.datasets.length > 0 },
    { key: 'overview.check.labels' as const, done: workspace.labels.length > 0 },
    { key: 'overview.check.model' as const, done: workspace.runs.length > 0 },
    { key: 'overview.check.scenes' as const, done: workspace.scenes.length > 0 },
  ]);

  const go = (view: ViewId) => workspace.go(view);
</script>

<PageHeading
  title={t('overview.title')}
  description={t('overview.description', { project: project?.name ?? '—' })}
  eyebrow={project ? `#${project.id} · ${project.status.toUpperCase()}` : 'WBALC'}
>
  {#snippet actions()}
    <button class="button primary" onclick={() => go('map')}
      ><MapPin size={15} /> {t('overview.openMap')} <ArrowRight size={14} /></button
    >
  {/snippet}
</PageHeading>

<div class="overview-grid">
  <div class="stack">
    <section class="surface section-box">
      <div class="section-heading">
        <div>
          <h2>{t('overview.series')}</h2>
          <p>{t('overview.seriesHint', { count: timeline.length })}</p>
        </div>
        <CalendarDays size={16} class="faint" />
      </div>
      <TimelineChart points={timeline} />
      <p class="engine-note">{t('overview.waterAreaMissing')} — {t('overview.noSeriesHint')}</p>
    </section>

    <section class="surface">
      <div class="panel-heading">
        <div class="panel-heading-title"><Layers size={16} /><h2>{t('overview.studyArea')}</h2></div>
        <span class="badge-muted">{t('project.id')} #{project?.id}</span>
      </div>
      <div class="panel-body">
        <dl class="kv-list">
          <div><dt>{t('project.status')}</dt><dd>{project?.status ?? '—'}</dd></div>
          <div>
            <dt>{t('project.taxonomy')}</dt>
            <dd>
              <span class="chip-row">
                {#each colors as item}
                  <span class="chip" style:--chip-color={item.color}><i></i>{item.name}</span>
                {/each}
              </span>
            </dd>
          </div>
          <div>
            <dt>{t('project.binary')}</dt>
            <dd>
              {project?.classificationConfig.binaryOutputInterpretation ?? '—'}
              <small class="dd-note">{t('project.binaryNotApplied')}</small>
            </dd>
          </div>
          <div>
            <dt>{t('project.studyArea')}</dt>
            <dd>
              {#if project?.studyAreaGeometry}
                {project.studyAreaCrs ?? t('common.unknown')}
              {:else}
                {t('project.noGeometry')}
              {/if}
            </dd>
          </div>
          <div><dt>{t('project.updated')}</dt><dd>{date(project?.updatedAt)}</dd></div>
        </dl>
      </div>
    </section>
  </div>

  <div class="stack">
    <section class="surface">
      <div class="panel-heading">
        <div class="panel-heading-title"><CircleDashed size={16} /><h2>{t('overview.status')}</h2></div>
        <span class="badge-live">RSAL</span>
      </div>
      <div class="panel-body status-body">
        <dl class="kv-list">
          <div><dt>{t('overview.datasets')}</dt><dd>{integer(workspace.datasets.length)}</dd></div>
          <div><dt>{t('overview.scenes')}</dt><dd>{integer(workspace.scenes.length)}</dd></div>
          <div><dt>{t('overview.labels')}</dt><dd>{integer(workspace.labels.length)}</dd></div>
          <div><dt>{t('overview.runs')}</dt><dd>{integer(workspace.runs.length)}</dd></div>
        </dl>
        <button class="button-link status-link" onclick={() => go('learning')}
          >{t('overview.reviewAction')} <ArrowRight size={14} /></button
        >
      </div>
    </section>

    <section class="surface section-box">
      <div class="section-heading">
        <div><h2>{t('overview.checklist')}</h2></div>
      </div>
      <ul class="checklist">
        {#each checks as check (check.key)}
          <li class:done={check.done}>
            {#if check.done}<Check size={13} class="accent" />{:else}<CircleDashed size={13} />{/if}
            <span>{t(check.key)}</span>
            <em>{check.done ? t('overview.check.done') : t('overview.check.missing')}</em>
          </li>
        {/each}
      </ul>
    </section>

    <section class="surface section-box">
      <div class="section-heading">
        <div>
          <h2>{t('overview.modelPerformance')}</h2>
          <p>{metrics ? `#${metrics.iteration} · ${metrics.modelType} · ${metrics.resolution}` : ''}</p>
        </div>
        <Tags size={16} class="faint" />
      </div>
      {#if metrics}
        <div class="performance-rows">
          <MetricBar label={t('overview.accuracy')} value={metrics.accuracy} display={percent(metrics.accuracy)} />
          <MetricBar label={t('overview.f1')} value={metrics.f1Macro} display={percent(metrics.f1Macro)} />
          <MetricBar
            label={t('arena.iou')}
            value={metrics.perClass.length
              ? metrics.perClass.reduce((sum, row) => sum + (row.iou ?? 0), 0) / metrics.perClass.length
              : null}
            display={percent(
              metrics.perClass.length
                ? metrics.perClass.reduce((sum, row) => sum + (row.iou ?? 0), 0) / metrics.perClass.length
                : null,
            )}
          />
        </div>
        {#if metrics.insufficient}
          <p class="engine-note warn">{t('overview.insufficient')}</p>
        {:else if metrics.evaluationStrategy === 'random'}
          <p class="engine-note">{t('overview.randomCaveat')}</p>
        {/if}
        <button class="button-link status-link" onclick={() => go('arena')}
          >{t('overview.compareModels')} <ArrowRight size={14} /></button
        >
      {:else}
        <EmptyState title={t('overview.noModel')} hint={t('overview.noModelHint')} />
      {/if}
    </section>
  </div>
</div>

<style>
  .overview-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 0.52fr); gap: 15px; align-items: start; }
  .engine-note { margin: 10px 0 0; padding-top: 9px; border-top: 1px solid var(--line); color: var(--faint); font-size: 10.5px; line-height: 1.6; }
  .engine-note.warn { color: var(--warn); }
  .dd-note { display: block; margin-top: 2px; color: var(--faint); font-size: 10px; line-height: 1.45; }
  .status-body { padding-top: 6px; }
  .status-link { margin-top: 11px; }
  .checklist { list-style: none; margin: 0; padding: 0; display: grid; gap: 7px; }
  .checklist li { display: flex; align-items: center; gap: 8px; color: var(--faint); font-size: 11.5px; }
  .checklist li.done { color: var(--ink); }
  .checklist em { margin-inline-start: auto; font: 9.5px var(--mono); font-style: normal; color: var(--faint); }
  .checklist li.done em { color: var(--accent); }
  .performance-rows { display: grid; gap: 12px; }
  @media (max-width: 1040px) {
    .overview-grid { grid-template-columns: minmax(0, 1fr); }
  }
</style>

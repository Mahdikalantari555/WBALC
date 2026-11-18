<script lang="ts">
  import { ArrowRight, ArrowRightLeft, ChartNoAxesCombined, Satellite, ScanLine } from '@lucide/svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import TimelineChart, { type TimelinePoint } from '../components/TimelineChart.svelte';
  import { getWorkspace } from '../state.svelte';
  import { useT } from '../t.svelte';
  import type { SceneView } from '../types';

  const workspace = getWorkspace();
  const { t, date, integer, number } = useT();

  let selectedId = $state<string | null>(null);
  let referenceId = $state<string | null>(null);
  let sensor = $state<'all' | 'Sentinel-1' | 'Sentinel-2'>('all');

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
  const comparison = $derived.by(() => {
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
      <div class="compare-state" class:ok={comparison === 'same'} class:warn={comparison === 'different'}>
        {#if comparison === 'same'}
          ✓ {t('temporal.compareSame')}
        {:else if comparison === 'different'}
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

      <p class="area-note">{t('temporal.areaNote')}</p>
      <button class="button-link" onclick={() => workspace.go('map')}
        >{t('temporal.openOnMap')} <ArrowRight size={14} /></button
      >
    </div>
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
  @media (max-width: 980px) {
    .temporal-grid { grid-template-columns: minmax(0, 1fr); }
  }
  @media (max-width: 650px) {
    .compare-grid { grid-template-columns: minmax(0, 1fr); }
    .date-compare { display: grid; grid-template-columns: minmax(0, 1fr) 32px minmax(0, 1fr); width: 100%; gap: 5px; }
  }
</style>

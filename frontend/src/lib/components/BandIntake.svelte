<script lang="ts">
  import { FolderOpen, Layers, Upload } from '@lucide/svelte';
  import { tick } from 'svelte';
  import { mappingKey, readDraft, writeDraft } from '$lib/drafts';
  import { api } from '$lib/client/api';
  import { planFolder, planManual, inferBand, validNames, type Job } from '$lib/intake';
  import { getWorkspace } from '$lib/state.svelte';
  import { useT } from '$lib/t.svelte';
  let { projectId }: { projectId: string } = $props();
  const workspace = getWorkspace();
  const { t } = useT();
  let jobs = $state<Job[]>([]);
  let states = $state<Record<string, { id?: number; error?: string }>>({});
  let mode = $state<'folder' | 'manual'>('folder');
  let target = $state<'scene' | 'dataset'>('scene');
  let staging = $state(false);
  let busy = $state(false);
  let stopRequested = $state(false);
  let processing = $state('');
  let error = $state('');
  let modal: HTMLDialogElement;
  let pending = $derived(jobs.filter(job => !states[job.key]?.id && !job.error && validNames(job.names) && (target === 'dataset' || job.date)));
  let needsOnly = $state(false);
  let reviewed = $state<Record<string, boolean>>({});
  let drafts = $state<Record<string, string[] | null>>({});
  const draftKey = (job: Job) => mappingKey(projectId, mode, job.files);
  function save(job: Job) {
    reviewed[job.key] = false;
    drafts[job.key] = null;
    writeDraft(draftKey(job), [...job.names]);
  }
  function needsReview(job: Job) { return !states[job.key]?.id && (!reviewed[job.key] || !!job.error || !!states[job.key]?.error || !validNames(job.names) || (target === 'scene' && !job.date)); }
  const problems = {
    dateInvalid: 'batch.dateInvalid', dateConflict: 'batch.dateConflict', metadataInvalid: 'batch.metadataInvalid',
    metadataTooLarge: 'batch.metadataTooLarge', metadataConflict: 'batch.metadataConflict', mixedSensor: 'batch.mixedSensor',
  } as const;
  async function stage(event: Event, kind: 'folder' | 'manual') {
    const input = event.currentTarget as HTMLInputElement;
    const selected = [...(input.files ?? [])];
    input.value = '';
    if (!selected.length || busy || staging) return;
    error = ''; states = {}; reviewed = {}; drafts = {}; needsOnly = false; jobs = []; staging = true; mode = kind;
    try {
      if (kind === 'folder') {
        target = 'scene';
        jobs = await planFolder(selected);
      } else {
        target = 'dataset';
        jobs = await planManual(selected);
      }
      if (!jobs.length) error = t('batch.empty');
      else {
        for (const job of jobs) drafts[job.key] = readDraft(draftKey(job), job.names.length);
        modal.showModal();
      }
    } finally { staging = false; }
  }
  async function upload() {
    if (busy || !pending.length) return;
    const queue = [...pending];
    const destination = target;
    busy = true; stopRequested = false;
    try {
      let last: number | undefined;
      for (const job of queue) {
        if (stopRequested || workspace.project?.id !== projectId) break;
        processing = job.date || job.key;
        const fields = new FormData();
        for (const file of job.files) fields.append('files', file);
        fields.set('band_names', JSON.stringify(job.names));
        fields.set('sensor', job.sensor);
        fields.set('kind', destination);
        if (job.date) fields.set('acquisition_datetime', job.date.length === 10 ? `${job.date}T00:00:00Z` : job.date);
        if (job.platform) fields.set('platform', job.platform);
        if (destination === 'scene' && job.metadata) {
          const metadata = job.metadata;
          const set = (key: string, value: string | number | null | undefined) => {
            if (value !== null && value !== undefined && value !== '') fields.set(key, String(value));
          };
          set('product_type', metadata.productType);
          set('product_level', metadata.productLevel);
          set('processing_baseline', metadata.processingBaseline);
          set('orbit_direction', metadata.orbitDirection);
          set('relative_orbit', metadata.relativeOrbit);
          if (job.sensor === 'Sentinel-1') {
            set('polarization', metadata.polarization.length ? metadata.polarization.join(',') : null);
            set('acquisition_mode', metadata.acquisitionMode);
          }
          if (job.sensor === 'Sentinel-2' && metadata.nativeBandResolutions) {
            fields.set('native_band_resolutions', JSON.stringify(metadata.nativeBandResolutions));
          }
          if (metadata.acquisitionMetadata) fields.set('acquisition_metadata', JSON.stringify(metadata.acquisitionMetadata));
          if (metadata.productMetadata) fields.set('product_metadata', JSON.stringify(metadata.productMetadata));
        }
        try { const result = await api.uploadStack(projectId, fields); states[job.key] = { id: result.id }; last = result.id; writeDraft(draftKey(job), null); drafts[job.key] = null; }
        catch (failure) { states[job.key] = { error: failure instanceof Error ? failure.message : String(failure) }; }
      }
      if (last && workspace.project?.id === projectId) {
        await workspace.reload();
        if (destination === 'dataset' && workspace.project?.id === projectId) workspace.selectDataset(String(last));
      }
    } finally { busy = false; processing = ''; }
  }
</script>

<section class="surface batch-panel" aria-labelledby="batch-heading">
  <div><h2 id="batch-heading"><Layers size={18} />{t('batch.title')}</h2><p>{t('batch.hint')}</p></div>
  <div class="batch-actions">
    <label class="button chooser"><FolderOpen size={15} />{t('batch.folder')}<input type="file" aria-label={t('batch.folder')} webkitdirectory multiple onchange={(e) => stage(e, 'folder')} disabled={staging || busy} /></label>
    <label class="button chooser"><Upload size={15} />{t('batch.single')}<input type="file" aria-label={t('batch.single')} accept=".tif,.tiff,.json,application/json,image/tiff" multiple onchange={(e) => stage(e, 'manual')} disabled={staging || busy} /></label>
    {#if jobs.length}<button class="button quiet" onclick={() => modal.showModal()}>{t('batch.review')}</button>{/if}
  </div>
  {#if staging}<p role="status">{t('batch.scanning')}</p>{/if}
  {#if error}<p role="alert">{error}</p>{/if}
</section>

<dialog bind:this={modal} aria-labelledby="batch-review" oncancel={(e) => { if (busy) e.preventDefault(); }}>
  <header><h2 id="batch-review">{t('batch.review')}</h2><p>{t('batch.reviewHint')}</p></header>
  <label class="field">{t('intake.kind')}
    <select class="select" bind:value={target} onchange={() => { reviewed = {}; }} disabled={busy || Object.values(states).some(state => state.id)}>
      <option value="scene">{t('intake.scene')}</option><option value="dataset">{t('intake.dataset')}</option>
    </select>
  </label>
  <label class="review-check"><input type="checkbox" bind:checked={needsOnly} /> {t('ux.needsOnly')}</label>
  <div class="jobs">
    {#each jobs.filter(job => !needsOnly || needsReview(job)) as job (job.key)}
      <details open={mode === 'manual' || jobs.length === 1}>
        <summary><bdi>{job.date.slice(0, 10) || (mode === 'manual' ? t('batch.single') : job.key || t('batch.unknown'))}</bdi> · {job.sensor} · {job.files.length} GeoTIFF {states[job.key]?.id ? `· ${t('batch.done')}` : reviewed[job.key] ? `· ${t('ux.reviewed')}` : `· ${t('ux.unreviewed')}`}</summary>
        <fieldset disabled={busy || Boolean(states[job.key]?.id)}>
          <label class="field">{t('intake.sensor')}
            <select class="select" bind:value={job.sensor} onchange={() => { reviewed[job.key] = false; }}><option value="Sentinel-2">Sentinel-2</option><option value="Sentinel-1">Sentinel-1</option></select>
          </label>
          {#if target === 'scene'}
            <label class="field">{t('intake.date')}<input class="input" type="date" value={job.date.slice(0, 10)} onchange={(event) => {
              const day = event.currentTarget.value;
              const time = job.date.length > 10 ? job.date.slice(10) : 'T00:00:00Z';
              job.date = day ? `${day}${time}` : '';
              if (job.error === 'dateInvalid' || job.error === 'dateConflict') delete job.error;
              reviewed[job.key] = false;
            }} /></label>
          {/if}
          {#if target === 'scene'}
            <label class="field">{t('intake.platform')}<input class="input" maxlength="100" bind:value={job.platform} oninput={() => { reviewed[job.key] = false; }} /></label>
          {/if}
          {#if job.metadata?.metadataFileCount}
            <p class="metadata-read">{t('batch.metadataRead', { count: job.metadata.metadataFileCount })}</p>
          {/if}
          {#if job.ignoredMerged}<p class="metadata-read">{t('batch.mergedSkipped', { count: job.ignoredMerged })}</p>{/if}
          {#if drafts[job.key]}<button class="button" onclick={() => { job.names = [...(drafts[job.key] ?? job.names)]; save(job); }}>{t('ux.restore')}</button>{/if}
          {#each job.files as file, index}
            <label class="band-row"><span><bdi>{file.name}</bdi>{#if inferBand(file.name)}<small class="suggestion">{t('ux.suggested', { name: inferBand(file.name) })}</small>{/if}</span><input class="input" aria-label={t('batch.bandName', { index: index + 1 })} dir="ltr" bind:value={job.names[index]} oninput={() => { void tick().then(() => save(job)); }} /></label>
          {/each}
          <label class="review-check"><input type="checkbox" bind:checked={reviewed[job.key]} disabled={!validNames(job.names) || Boolean(job.error) || (target === 'scene' && !job.date)} /> {t('ux.confirmMapping')}</label>
        </fieldset>
        {#if states[job.key]?.id}<button class="button small" disabled={busy} onclick={() => { modal.close(); workspace.openRaster(projectId, target, String(states[job.key].id)); }}>{t('ux.openMap')}</button>{/if}
      </details>
      {#if job.error || states[job.key]?.error}<p class="problem" role="alert">{job.key}: {job.error ? t(problems[job.error as keyof typeof problems]) : states[job.key].error}</p>
      {:else if !validNames(job.names)}<p class="problem">{t('batch.namesInvalid')}</p>{/if}
    {/each}
  </div>
  {#if needsOnly && !jobs.some(needsReview)}<p role="status">{t('ux.noneToReview')}</p>{/if}
  <footer><span role="status">{busy ? t('batch.processing', { item: processing }) : t('batch.ready', { count: pending.length, total: jobs.length })}</span>
    {#if busy}<button class="button quiet" onclick={() => stopRequested = true} disabled={stopRequested}>{t('batch.stop')}</button>{/if}
    <button class="button" onclick={() => modal.close()} disabled={busy}>{t('batch.close')}</button>
    {#if !busy && !pending.length && jobs.some(job => !states[job.key]?.id)}<small>{t('ux.importBlocked')}</small>{/if}
    <button class="button primary" onclick={upload} disabled={busy || !pending.length}>{busy ? t('intake.uploading') : t('batch.import')}</button>
  </footer>
</dialog>

<style>
  .review-check { display: flex; gap: 8px; align-items: center; min-block-size: 32px; padding-block: 4px; }
  .review-check input { accent-color: var(--accent); flex: none; }
  .suggestion { display: block; color: var(--muted); }
  details > button { margin-block: 8px; }
  .batch-panel { margin-block-start: 16px; max-width: 1100px; padding: 20px 24px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; }
  h2 { display: flex; align-items: center; gap: 8px; font-size: 17px; font-weight: 650; }
  p, footer span { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
  header p { margin-block: 4px 12px; }
  .batch-panel p { margin-block-start: 4px; }
  .batch-actions, footer { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .chooser { position: relative; overflow: hidden; }
  .chooser:focus-within { outline: 2px solid var(--ring); }
  .chooser input { position: absolute; inset: 0; opacity: 0; width: 100%; cursor: pointer; }
  dialog { margin: auto; width: min(660px, calc(100% - 24px)); max-height: calc(100dvh - 24px); overflow: auto; padding: 20px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); color: var(--ink); }
  dialog::backdrop { background: color-mix(in srgb, var(--surface) 35%, black 65%); }
  .jobs { margin-block: 12px; display: grid; gap: 8px; }
  details { border: 1px solid var(--line); border-radius: 6px; padding: 10px; }
  summary { cursor: pointer; font-size: 13px; overflow-wrap: anywhere; }
  fieldset { min-width: 0; display: grid; gap: 8px; margin-block-start: 10px; }
  .band-row { display: grid; grid-template-columns: 1fr minmax(0, 1fr); align-items: center; gap: 8px; font-size: 12px; overflow-wrap: anywhere; }
  .band-row input { min-width: 0; width: 100%; }
  footer span { flex: 1 1 auto; }
  .problem { color: var(--danger-fg); }
  .metadata-read { color: var(--muted); font-size: 11px; margin-block: 4px; }
</style>

<script lang="ts">
  import { Database, FolderPlus, Plus, Upload, X } from '@lucide/svelte';
  import { onMount, tick } from 'svelte';
  import { mappingKey, readDraft, writeDraft } from '$lib/drafts';
  import { validNames } from '$lib/intake';
  import { normalizeStudyArea } from '$lib/study-area';
  import { api } from '$lib/client/api';
  import BandIntake from '$lib/components/BandIntake.svelte';
  import ProjectClasses from '$lib/components/ProjectClasses.svelte';
  import { getWorkspace } from '$lib/state.svelte';
  import { useT } from '$lib/t.svelte';

  const workspace = getWorkspace();
  const { t } = useT();
  let classRows = $state(['water', 'non_water']);
  let classDraft = $state<string[] | null>(null);
  let bandDraft = $state<string[] | null>(null);
  let bandKey = $state('');
  onMount(() => { classDraft = readDraft('classes'); });
  const saveClasses = () => { classDraft = null; writeDraft('classes', [...classRows]); };
  const saveBands = () => { bandDraft = null; if (bandKey) writeDraft(bandKey, [...inspectedNames]); };
  let inspectedNames = $state<string[]>([]);
  let bandNamesConfirmed = $state(false);
  let inspecting = $state(false);
  let inspection = 0;
  let kind = $state<'dataset' | 'scene'>('dataset');
  let creating = $state(false);
  let uploading = $state(false);
  let projectError = $state('');
  let uploadError = $state('');
  let uploaded = $state<{ id: string; rasterId: string; name: string; kind: 'dataset' | 'scene' } | null>(null);
  let intakeHeading: HTMLHeadingElement;

  async function create(event: SubmitEvent) {
    event.preventDefault();
    if (creating || uploading) return;
    const form = event.currentTarget as HTMLFormElement;
    const fields = new FormData(form);
    const name = String(fields.get('name')).trim();
    const classes = classRows.map(value => value.trim());
    projectError = '';
    if (!name) { projectError = t('intake.nameRequired'); return; }
    if (classes.some(value => !value || value.length > 255) || new Set(classes.map(value => value.toLowerCase())).size !== classes.length) {
      projectError = t('intake.classesRequired'); return;
    }
    creating = true;
    try {
      const source = fields.get('study_area');
      let studyArea: ReturnType<typeof normalizeStudyArea> | null = null;
      if (source instanceof File && source.name) {
        try { studyArea = normalizeStudyArea(JSON.parse(await source.text())); }
        catch { throw new Error(t('intake.areaInvalid')); }
      }
      const created = await api.createProject({
        name, description: String(fields.get('description')).trim(),
        classes, generic_classes: true,
        ...(studyArea ? { study_area_geometry: studyArea.geometry, study_area_crs: studyArea.crs } : {}),
      });
      form.reset();
      await tick();
      classRows = ['water', 'non_water'];
      classDraft = null; writeDraft('classes', null);
      workspace.go('intake');
      workspace.projects = [...workspace.projects, created];
      await workspace.selectProject(created.id);
      workspace.notify(t('intake.created', { name: created.name }));
      intakeHeading?.focus();
    } catch (error) {
      projectError = error instanceof Error ? error.message : String(error);
    } finally {
      creating = false;
    }
  }

  async function inspect(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    const token = ++inspection;
    const projectId = workspace.project?.id;
    inspectedNames = [];
    bandNamesConfirmed = false;
    bandDraft = null;
    bandKey = file && workspace.project ? mappingKey(workspace.project.id, 'tiff', [file]) : '';
    uploadError = '';
    inspecting = Boolean(file);
    if (!file) return;
    try {
      const { fromBlob } = await import('geotiff');
      const image = await (await fromBlob(file)).getImage();
      if (token !== inspection || projectId !== workspace.project?.id) return;
      inspectedNames = Array.from({ length: image.getSamplesPerPixel() }, (_, index) => {
        const metadata = image.getGDALMetadata(index) as Record<string, unknown> | null;
        return typeof metadata?.DESCRIPTION === 'string' ? metadata.DESCRIPTION : '';
      });
      bandDraft = bandKey ? readDraft(bandKey, inspectedNames.length) : null;
    } catch {
      if (token === inspection) uploadError = t('intake.inspectFailed');
    } finally {
      if (token === inspection) inspecting = false;
    }
  }

  async function upload(event: SubmitEvent) {
    event.preventDefault();
    const id = workspace.project?.id;
    if (!id || uploading || creating || inspecting) return;
    const form = event.currentTarget as HTMLFormElement;
    const fields = new FormData(form);
    const file = fields.get('file');
    const mode = kind;
    uploadError = '';
    uploaded = null;
    if (!(file instanceof File) || !/\.tiff?$/i.test(file.name) || !file.size) {
      uploadError = t('intake.fileError'); return;
    }
    if (mode === 'scene') fields.set('acquisition_datetime', `${fields.get('date')}T00:00:00Z`);
    fields.delete('date');
    if (!validNames(inspectedNames)) { uploadError = t('batch.namesInvalid'); return; }
    if (!bandNamesConfirmed) { uploadError = t('intake.confirmBandsRequired'); return; }
    fields.set('band_names', inspectedNames.map(name => name.trim().toLowerCase()).join(','));
    const submittedBandKey = bandKey;
    uploading = true;
    try {
      const uploadedInput = mode === 'scene' ? await api.registerScene(id, fields) : await api.uploadDataset(id, fields);
      if (workspace.project?.id === id) {
        form.reset();
        await tick();
        inspectedNames = [];
        bandNamesConfirmed = false;
        uploaded = { id, rasterId: String(uploadedInput.id), name: file.name, kind: mode };
        await workspace.reload();
        if (workspace.project?.id === id) {
          const queryDataset = mode === 'dataset'
            ? uploadedInput.id
            : workspace.datasets.at(-1)?.id;
          if (queryDataset) workspace.selectDataset(queryDataset);
        }
      }
      if (submittedBandKey) writeDraft(submittedBandKey, null);
      bandDraft = null;
      workspace.notify(t('intake.uploaded', { name: file.name }));
    } catch (error) {
      uploadError = error instanceof Error ? error.message : String(error);
    } finally {
      uploading = false;
    }
  }
</script>

<div class="page-heading">
  <div><h1>{t('nav.intake')}</h1><p>{t('intake.description')}</p></div>
</div>
<div class="intake-layout">
  <section class="surface intake-panel" aria-labelledby="new-project-heading">
    <div class="intro">
      <FolderPlus size={20} class="accent" />
      <div><h2 id="new-project-heading">{t('intake.create')}</h2><p>{t('intake.projectHint')}</p></div>
    </div>
    <form onsubmit={create}>
      <fieldset disabled={creating || uploading}>
        <label class="field">{t('intake.name')}<input class="input" name="name" maxlength="255" required /></label>
        <label class="field">{t('intake.notes')}<textarea class="input" name="description" rows="3"></textarea></label>
        <div class="classes">
          <p class="help">{t('intake.classesHelp')}</p>
          {#if classDraft}<button type="button" class="button" onclick={() => { if (classDraft) classRows = classDraft; saveClasses(); }}>{t('ux.restore')}</button>{/if}
          {#each classRows as _, index}
            <div class="class-row">
              <label class="field">{t('intake.className', { index: index + 1 })}<input class="input" maxlength="255" required bind:value={classRows[index]} oninput={() => { void tick().then(saveClasses); }} /></label>
              <button type="button" class="icon-button" aria-label={t('intake.removeClass', { index: index + 1 })} disabled={classRows.length <= 2} onclick={() => { classRows.splice(index, 1); saveClasses(); }}><X size={16} /></button>
            </div>
          {/each}
          <button type="button" class="button quiet" onclick={() => { classRows.push(''); saveClasses(); }}><Plus size={14} />{t('intake.addClass')}</button>
        </div>
        <details class="study-area">
          <summary>{t('intake.area')}</summary>
          <label class="field">{t('intake.areaFile')}
            <input class="input file" name="study_area" type="file" accept=".geojson,.json,application/geo+json,application/json" />
          </label>
          <p class="help">{t('intake.areaHelp')}</p>
        </details>
        <div class="form-actions"><button class="button primary" type="submit">{creating ? t('intake.creating') : t('intake.create')}</button></div>
      </fieldset>
      {#if projectError}<p class="form-error" role="alert">{projectError}</p>{/if}
    </form>
  </section>

  <section class="surface intake-panel" aria-labelledby="intake-heading">
    <div class="intro">
      <Database size={20} class="accent" />
      <div>
        <h2 id="intake-heading" tabindex="-1" bind:this={intakeHeading}>{t('intake.add')}</h2>
        <p>{workspace.project ? t('intake.destination', { name: workspace.project.name }) : t('intake.noProject')}</p>
      </div>
    </div>
    {#if workspace.project}
      {#key workspace.project.id}
        <form onsubmit={upload}>
          <fieldset disabled={uploading || creating || workspace.detailLoading}>
            <label class="field">{t('intake.kind')}
              <select class="select" bind:value={kind}>
                <option value="dataset">{t('intake.dataset')}</option>
                <option value="scene">{t('intake.scene')}</option>
              </select>
            </label>
            <p class="help">{t(kind === 'dataset' ? 'intake.datasetHelp' : 'intake.sceneHelp')}</p>
            <label class="field">{t('intake.file')}<input class="input file" name="file" type="file" accept=".tif,.tiff,image/tiff" onchange={inspect} required /></label>
            {#if kind === 'scene'}
              <div class="paired">
                <label class="field">{t('intake.sensor')}
                  <select class="select" name="sensor"><option>Sentinel-2</option><option>Sentinel-1</option></select>
                </label>
                <label class="field">{t('intake.date')}<input class="input" name="date" type="date" required /></label>
              </div>
            {:else}
              <label class="field">{t('intake.sensorOptional')}<input class="input" name="sensor" /></label>
            {/if}
            {#if inspecting}<p role="status" class="help">{t('batch.scanning')}</p>{/if}
            {#if inspectedNames.length}
              <div class="band-grid">
                {#each inspectedNames as _, index}
                  <label class="field">{t('batch.bandName', { index: index + 1 })}<input class="input" dir="ltr" required bind:value={inspectedNames[index]} oninput={() => { bandNamesConfirmed = false; void tick().then(saveBands); }} /></label>
                {/each}
              </div>
              <label class="review-check"><input type="checkbox" bind:checked={bandNamesConfirmed} disabled={!validNames(inspectedNames) || inspecting} /> {t('intake.confirmBands')}</label>
            {/if}
            <div class="form-actions">
              <button class="button primary" type="submit" disabled={inspecting || !validNames(inspectedNames) || !bandNamesConfirmed}><Upload size={14} />{uploading ? t('intake.uploading') : t('intake.upload')}</button>
            </div>
          </fieldset>
          {#if !inspecting && !inspectedNames.length && !uploadError}<p class="help">{t('ux.chooseRaster')}</p>{/if}
          {#if bandDraft}<button type="button" class="button" onclick={() => { if (bandDraft) inspectedNames = bandDraft; bandNamesConfirmed = false; saveBands(); }}>{t('ux.restore')}</button>{/if}
          {#if uploadError}<p class="form-error" role="alert">{uploadError}</p>{/if}
        </form>
      {/key}
      {#if uploaded?.id === workspace.project.id}
        <div class="next">
          <span role="status">{t('intake.uploaded', { name: uploaded.name })}</span>
          <button class="button" onclick={() => uploaded && workspace.openRaster(uploaded.id, uploaded.kind, uploaded.rasterId)}>{t('ux.openMap')}</button>
          {#if uploaded.kind === 'scene'}
            <button class="button" onclick={() => workspace.go('temporal')}>{t('nav.temporal')}</button>
          {:else}
            <button class="button" onclick={() => workspace.go('learning')}>{t('nav.learning')}</button>
          {/if}
        </div>
      {/if}
    {:else}
      <div class="waiting">{t('intake.waiting')}</div>
    {/if}
  </section>
</div>

{#if workspace.project}
  {#key workspace.project.id}<BandIntake projectId={workspace.project.id} />{/key}
  {#key workspace.project.id}<ProjectClasses project={workspace.project} />{/key}
{/if}

<style>
  .intake-layout { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; max-width: 1100px; }
  .intake-panel { min-width: 0; padding: clamp(16px, 2vw, 24px); }
  .intro { display: flex; align-items: flex-start; gap: 12px; margin-block-end: 20px; }
  .intro :global(svg) { flex: none; margin-block-start: 2px; }
  h2 { font-size: 17px; font-weight: 650; }
  .intro p, .help, .waiting { font-size: 12px; line-height: 1.55; color: var(--muted); }
  .intro p { margin-block-start: 4px; overflow-wrap: anywhere; }
  fieldset { display: grid; min-inline-size: 0; gap: 14px; }
  .field { font-size: 12px; min-width: 0; }
  .review-check { display: flex; gap: 8px; align-items: center; min-block-size: 32px; font-size: 12px; }
  .review-check input { accent-color: var(--accent); flex: none; }
  .input, .select { width: 100%; min-width: 0; }
  .file { height: auto; padding-block: 7px; }
  .file::file-selector-button { padding: 4px 8px; margin-inline-end: 8px; color: var(--ink); background: var(--control); border: 1px solid var(--line); border-radius: 4px; }
  .classes { display: grid; gap: 9px; justify-items: start; }
  .class-row { display: grid; width: 100%; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: end; }
  .band-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .paired { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  textarea.input { height: auto; resize: vertical; padding-block: 8px; }
  .form-actions { display: flex; flex-wrap: wrap; }
  .study-area { border-block-start: 1px solid var(--line); padding-block-start: 10px; }
  .study-area summary { cursor: pointer; font-size: 12px; color: var(--muted); }
  .study-area > .field, .study-area > .help { margin-block-start: 8px; }
  .waiting { padding-block: 12px; border-block-start: 1px solid var(--line); }
  .next { border-block-start: 1px solid var(--line); margin-block-start: 16px; padding-block-start: 14px; display: flex; gap: 8px; flex-wrap: wrap; }
  .next span { flex-basis: 100%; color: var(--accent); overflow-wrap: anywhere; font-size: 12px; }
  .form-error { margin-block-start: 12px; color: var(--danger-fg); font-size: 12px; overflow-wrap: anywhere; }
  @media (max-width: 900px) { .intake-layout { grid-template-columns: minmax(0, 1fr); } }
</style>

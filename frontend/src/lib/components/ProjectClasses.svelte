<script lang="ts">
  import { api } from '$lib/client/api';
  import { getWorkspace } from '$lib/state.svelte';
  import { useT } from '$lib/t.svelte';
  import type { ProjectView } from '$lib/types';
  let { project }: { project: ProjectView } = $props();
  const workspace = getWorkspace();
  const { t } = useT();
  let name = $state('');
  let busy = $state(false);
  let error = $state('');
  async function append(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !name.trim()) return;
    busy = true; error = '';
    const id = project.id;
    try {
      const updated = await api.appendClass(id, name.trim());
      workspace.projects = workspace.projects.map(item => item.id === id ? updated : item);
      if (workspace.project?.id === id) workspace.project = updated;
      name = '';
    } catch (failure) { error = failure instanceof Error ? failure.message : String(failure); }
    finally { busy = false; }
  }
</script>
<details class="surface class-manager">
  <summary>{t('intake.manageClasses')} · {project.classes.length}</summary>
  <ul aria-label={t('common.classes')}>{#each project.classes as item (item)}<li>{item}</li>{/each}</ul>
  <p>{t('intake.appendHint')}</p>
  {#if project.taxonomy}<p>{t('intake.legacyWarning')}</p>{/if}
  <form onsubmit={append}>
    <label class="field">{t('intake.newClass')}<input class="input" bind:value={name} maxlength="255" required disabled={busy} /></label>
    <button class="button" type="submit" disabled={busy || !name.trim()}>{t('intake.addClass')}</button>
  </form>
  {#if error}<p role="alert">{error}</p>{/if}
</details>
<style>
  .class-manager { max-width: 1100px; margin-block-start: 16px; padding: 14px 24px; }
  summary { cursor: pointer; font-size: 14px; font-weight: 650; }
  ul { display: flex; flex-wrap: wrap; gap: 6px; padding: 0; margin-block: 12px; list-style: none; }
  li { font-size: 12px; border: 1px solid var(--line); border-radius: 5px; padding: 4px 8px; overflow-wrap: anywhere; }
  p { color: var(--muted); font-size: 12px; margin-block: 8px; }
  form { display: flex; gap: 8px; align-items: end; flex-wrap: wrap; }
  label, input { min-width: 0; }
</style>

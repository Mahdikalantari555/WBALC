<script lang="ts">
  import { Layers, Plus, X } from '@lucide/svelte';
  import { getWorkspace } from '$lib/state.svelte';
  import { useT } from '$lib/t.svelte';
  import type { DatasetView } from '$lib/types';
  import { onMount } from 'svelte';
  let { dataset, imageryOnly = false }: { dataset: DatasetView; imageryOnly?: boolean } = $props();
  const workspace = getWorkspace();
  const { t } = useT();
  type Recipe = { name: string; a: number; b: number };
  let recipes = $state<Recipe[]>([]);
  let name = $state('');
  let a = $state(0);
  let b = $state(1);
  let editing = $state(false);
  const bands = $derived(Array.from({ length: dataset.bands }, (_, i) => dataset.bandNames?.[i] || `#${i + 1}`));
  const key = () => `wbalc:layers:${workspace.project?.id}:${dataset.id}:${dataset.contentSha256 ?? dataset.createdAt}`;
  onMount(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(key()) ?? '[]');
      if (Array.isArray(saved)) recipes = saved.filter(r => r && typeof r.name === 'string' && Number.isInteger(r.a) && Number.isInteger(r.b) && r.a >= 0 && r.b >= 0 && r.a < bands.length && r.b < bands.length && r.a !== r.b);
    } catch { /* browser storage is optional */ }
  });
  function persist() { try { localStorage.setItem(key(), JSON.stringify(recipes)); } catch { /* optional */ } }
  function show(mode: `band:${number}` | `nd:${number}:${number}`) {
    workspace.activeRecipe = null;
    workspace.map.bandMode = mode;
    workspace.map.layers.imagery = true;
    if (!imageryOnly) {
      workspace.map.layers.classification = false;
      workspace.map.layers.binary = false;
      workspace.map.layers.uncertainty = false;
    }
  }
  function showRecipe(recipe: Recipe) {
    const mode = `nd:${recipe.a}:${recipe.b}` as const;
    show(mode);
    workspace.activeRecipe = { raster: key(), name: recipe.name, mode };
  }
  function add(event: SubmitEvent) {
    event.preventDefault();
    if (!name.trim() || a === b || recipes.some(r => r.name === name.trim())) return;
    recipes = [...recipes, { name: name.trim(), a, b }];
    showRecipe({ name: name.trim(), a, b });
    persist(); name = ''; editing = false;
  }
  function remove(recipe: Recipe) {
    recipes = recipes.filter(item => item.name !== recipe.name);
    if (workspace.activeRecipe?.name === recipe.name) { workspace.activeRecipe = null; workspace.map.bandMode = 'true-color'; }
    persist();
  }
</script>
<section class="surface layer-panel" aria-labelledby="raster-layers-title">
  <header><h2 id="raster-layers-title"><Layers size={17} />{t('layer.raw')}</h2>
    <button class="button small" disabled={bands.length < 2} aria-expanded={editing} onclick={() => editing = !editing}><Plus size={14} />{t('layer.add')}</button>
  </header>
  <p>{t(bands.length < 2 ? 'ux.twoBands' : 'layer.hint')}</p>
  <div class="chips">
    {#each bands as band, index}
      <button class="button small quiet" aria-pressed={workspace.map.bandMode === `band:${index}`} onclick={() => show(`band:${index}`)}>{band}</button>
    {/each}
  </div>
  {#if recipes.length}
    <h3>{t('layer.custom')}</h3>
    {#each recipes as recipe (recipe.name)}
      <div class="recipe">
        <button class="button small quiet" aria-pressed={workspace.activeRecipe?.raster === key() && workspace.activeRecipe?.name === recipe.name && workspace.map.bandMode === workspace.activeRecipe.mode} onclick={() => showRecipe(recipe)}>{recipe.name}</button>
        <small dir="ltr">({bands[recipe.a]} − {bands[recipe.b]}) ÷ ({bands[recipe.a]} + {bands[recipe.b]})</small>
        <button class="icon-button" aria-label={t('layer.remove', { name: recipe.name })} onclick={() => remove(recipe)}><X size={14} /></button>
      </div>
    {/each}
  {/if}
  {#if editing}
    <form onsubmit={add}>
      <p>{t('layer.diff')}</p>
      <label class="field">{t('layer.name')}<input class="input" maxlength="64" required bind:value={name} /></label>
      <div class="pair">
        <label class="field">{t('layer.first')}<select class="select" bind:value={a}>{#each bands as band, i}<option value={i}>{band}</option>{/each}</select></label>
        <label class="field">{t('layer.second')}<select class="select" bind:value={b}>{#each bands as band, i}<option value={i}>{band}</option>{/each}</select></label>
      </div>
      <button class="button primary" type="submit" disabled={!name.trim() || a === b || recipes.some(r => r.name === name.trim())}>{t('layer.add')}</button>
    </form>
  {/if}
</section>
<style>
  .layer-panel { padding: 14px; display: grid; gap: 10px; min-width: 0; }
  header, .chips, .recipe { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; }
  header { justify-content: space-between; }
  h2 { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 650; }
  h3, p, small { font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
  form { border-block-start: 1px solid var(--line); padding-block-start: 12px; display: grid; gap: 10px; justify-items: start; }
  form > label, .pair { width: 100%; min-width: 0; }
  .pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .recipe button { max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
  button[aria-pressed='true'] { color: var(--accent); border-color: var(--accent); }
</style>

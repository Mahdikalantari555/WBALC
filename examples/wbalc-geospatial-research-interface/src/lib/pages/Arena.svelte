<script lang="ts">
  import { ArrowRight } from '@lucide/svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import ModelSelect from '../components/ModelSelect.svelte';
  import ModelTable from '../components/ModelTable.svelte';
  import ConfusionMatrix from '../components/ConfusionMatrix.svelte';
  import MetricsTable from '../components/MetricsTable.svelte';
  import MiniScene from '../components/MiniScene.svelte';
  import { classes, evaluateModel, fmtDate, getModel, getObservation, pct } from '../data/research';
  import { getWorkspace, selectModel, type WorkspaceProps } from '../state.svelte';

  let { go }: WorkspaceProps = $props();
  const workspace = getWorkspace();
  const primary = $derived(getModel(workspace.model));
  const challenger = $derived(getModel(workspace.challenger));
  const observation = $derived(getObservation(workspace.observation));
  const comparisons = $derived([primary, challenger]);
  let inspect = $state<'A' | 'B'>('A');
  const inspected = $derived(inspect === 'A' ? primary : challenger);
</script>

<PageHeading title="Model Arena" description="Benchmark three simulated classifiers and compare how they delineate water and reeds.">
  {#snippet actions()}<button class="button" onclick={() => { selectModel(workspace, inspected.id); go('evaluation'); }}>Open evaluation <ArrowRight size={15} /></button>{/snippet}
</PageHeading>

<div class="surface model-picker-bar">
  <div class="picker"><span class="arena-letter">A</span><ModelSelect label="Primary model" value={workspace.model} onchange={(id) => selectModel(workspace, id)} /></div>
  <div class="picker"><span class="arena-letter second">B</span><ModelSelect label="Comparison model" value={workspace.challenger} onchange={(id) => selectModel(workspace, id, 'challenger')} /></div>
  <div class="inspect-control">
    <span class="field">Detailed metrics</span>
    <div class="segments" role="group" aria-label="Model for detailed metrics">
      <button class:chosen={inspect === 'A'} aria-pressed={inspect === 'A'} onclick={() => { inspect = 'A'; }}>A / {primary.name}</button>
      <button class:chosen={inspect === 'B'} aria-pressed={inspect === 'B'} onclick={() => { inspect = 'B'; }}>B / {challenger.name}</button>
    </div>
  </div>
</div>

<div class="arena-top">
  <ModelTable selected={workspace.model} challenger={workspace.challenger} onselect={(id) => { selectModel(workspace, id); inspect = 'A'; }} />
  <ConfusionMatrix model={inspected} />
</div>

<section class="surface section-box arena-visual">
  <div class="section-heading"><div><h2>Classification output</h2><p>Side-by-side simulated footprints / {fmtDate(observation.date)}</p></div>
    <div class="output-legend">
      <span class="class-label"><i class="class-dot" style:--class-color={classes.water.color}></i>Open Water</span>
      <span class="class-label"><i class="class-dot" style:--class-color={classes.vegetation.color}></i>Aquatic Vegetation</span>
    </div>
  </div>
  <div class="model-frames">
    {#each comparisons as model, index}
      <figure class="model-frame">
        <figcaption><span class="arena-letter" class:second={index === 1}>{index === 0 ? 'A' : 'B'}</span><strong>{model.name}</strong><span class="frame-accuracy">{pct(evaluateModel(model).accuracy)} accuracy</span></figcaption>
        <div class="model-image"><MiniScene {model} {observation} label={`Simulated classification output for ${model.name}`} /></div>
        <dl class="kv-list model-config">
          <div><dt>Model</dt><dd>{model.version} / {model.type}</dd></div>
          <div><dt>Inputs</dt><dd>{model.inputs}</dd></div>
          <div><dt>Configuration</dt><dd>{model.config}</dd></div>
          <div><dt>Inference</dt><dd>{model.inference.toFixed(2)} s / scene (simulated)</dd></div>
        </dl>
      </figure>
    {/each}
  </div>
</section>

<MetricsTable model={inspected} />

<style>
  .model-picker-bar { display: flex; gap: 12px 19px; align-items: end; flex-wrap: wrap; padding: 13px 15px; margin-bottom: 15px; }
  .picker { display: flex; align-items: end; gap: 8px; min-width: min(230px, 100%); }
  .picker :global(.field) { flex: 1; }
  .arena-letter { display: inline-grid; place-items: center; flex: none; width: 22px; height: 22px; border-radius: 4px; border: 1px solid #426967; background: #1c3c42; color: #a3eee0; font: 11px var(--mono); }
  .picker .arena-letter { margin-bottom: 6px; }
  .arena-letter.second { background: #273152; border-color: #566088; color: #c5d6ff; }
  .inspect-control { display: grid; gap: 6px; margin-left: auto; }
  .arena-top { display: grid; grid-template-columns: minmax(0, 1.46fr) minmax(0, 1fr); align-items: start; gap: 15px; margin-bottom: 15px; }
  .arena-visual { margin-bottom: 15px; }
  .output-legend { display: flex; flex-wrap: wrap; gap: 5px 13px; color: var(--muted); font-size: 11px; }
  .model-frames { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; }
  .model-frame { min-width: 0; margin: 0; }
  .model-frame figcaption { display: flex; align-items: center; gap: 7px; margin-bottom: 7px; font-size: 12px; }
  .model-frame figcaption strong { font-weight: 590; }
  .frame-accuracy { margin-left: auto; color: var(--accent); font: 10.5px var(--mono); white-space: nowrap; }
  .model-image { aspect-ratio: 1.75; max-height: 350px; border: 1px solid #384e61; border-radius: 5px; overflow: hidden; }
  .model-config { margin-top: 5px; }
  .model-config div { padding-block: 6px; }
  .inspect-control .segments { flex-wrap: wrap; }
  @media (max-width: 1150px) { .arena-top { grid-template-columns: minmax(0, 1fr); } .inspect-control { margin-left: 0; } }
  @media (max-width: 700px) { .model-frames { grid-template-columns: minmax(0, 1fr); } .picker { width: 100%; } }
</style>
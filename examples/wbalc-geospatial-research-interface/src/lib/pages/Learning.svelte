<script lang="ts">
  import { onMount } from 'svelte';
  import { ArrowLeft, ArrowRight, Check, ChevronLeft, ChevronRight, CircleCheck, LocateFixed, MapPin, Tags, TriangleAlert } from '@lucide/svelte';
  import PageHeading from '../components/PageHeading.svelte';
  import MiniScene from '../components/MiniScene.svelte';
  import { classKeys, classes, fmtDate, getObservation, labelKeys, pct, project, samples, type LabelClass, type PredictionClass, type Sample } from '../data/research';
  import { getWorkspace, type WorkspaceProps } from '../state.svelte';

  let { go, notify }: WorkspaceProps = $props();
  const workspace = getWorkspace();
  let mode = $state<'pending' | 'reviewed' | 'all'>('pending');
  let threshold = $state(0);
  let predicted = $state<'all' | PredictionClass>('all');
  let focused = $state<string | null>(null);
  let draft = $state<{ sample: string; label: LabelClass } | null>(null);
  let preview = $state<'raw' | 'prediction'>('prediction');
  const modes = [{ value: 'pending', label: 'Pending' }, { value: 'reviewed', label: 'Reviewed' }, { value: 'all', label: 'All' }] as const;

  const reviewedHere = $derived(samples.filter(item => workspace.reviews[item.id]).length);
  const pending = $derived(samples.length - reviewedHere);
  const needsReview = $derived(Object.values(workspace.reviews).filter(review => review.label === 'uncertain').length);
  const queue = $derived(samples.filter(item => item.uncertainty >= threshold && (predicted === 'all' || item.prediction === predicted)
    && (mode === 'all' || (mode === 'reviewed' ? Boolean(workspace.reviews[item.id]) : !workspace.reviews[item.id]))));
  const position = $derived(Math.max(queue.findIndex(item => item.id === focused), 0));
  const sample = $derived(queue[position]);
  const review = $derived(sample ? workspace.reviews[sample.id] : undefined);
  const choice = $derived(draft && draft.sample === sample?.id ? draft.label : review?.label ?? null);

  onMount(() => {
    const fromMap = workspace.selectedSample;
    if (!fromMap) return;
    mode = workspace.reviews[fromMap] ? 'reviewed' : 'pending';
    focused = fromMap;
    workspace.selectedSample = null;
  });

  function focus(id: string | null) { focused = id; draft = null; }

  function submit() {
    if (!sample || !choice) return;
    const id = sample.id;
    const next = queue[position + 1] ?? queue[position - 1];
    workspace.reviews[id] = { label: choice, date: new Date().toISOString().slice(0, 10) };
    focus(mode === 'pending' ? next?.id ?? null : id);
    notify(choice === 'uncertain' ? `${id} saved and flagged for follow-up.` : `Label saved for ${id}.`);
  }

  function showMap(item: Sample) {
    workspace.observation = item.observation;
    workspace.sensor = 'all';
    workspace.map.layers.samples = true;
    workspace.map.selected = { kind: 'sample', id: item.id };
    go('map');
  }
</script>

<PageHeading title="Active Learning" description="Review shoreline samples and record human labels for uncertain model predictions." />

<div class="learning-layout">
  <section class="surface queue-panel">
    <div class="panel-heading"><div class="panel-heading-title"><Tags size={16} /><h2>Review queue</h2></div><span class="section-label">{samples.length} SAMPLES</span></div>
    <div class="queue-settings">
      <div class="queue-stats">
        <div><strong class="mono">{pending}</strong><span>Pending</span></div>
        <div><strong class="mono">{project.archiveReviewed + reviewedHere}</strong><span>Project reviewed</span></div>
      </div>
      <div class="queue-progress" title={`${reviewedHere} of ${samples.length} local samples reviewed`}><i style:width={`${reviewedHere / samples.length * 100}%`}></i></div>
      <div class="queue-caption"><span>{reviewedHere} of {samples.length} in this queue reviewed</span>{#if needsReview}<span class="flag-count">{needsReview} flagged</span>{/if}</div>
      <div class="segments queue-tabs" role="group" aria-label="Queue status">
        {#each modes as tab}
          <button class:chosen={mode === tab.value} aria-pressed={mode === tab.value} onclick={() => { mode = tab.value; focus(null); }}>{tab.label}</button>
        {/each}
      </div>
      <div class="queue-filters">
        <label class="field">Uncertainty<select class="select" aria-label="Uncertainty" bind:value={threshold} onchange={() => focus(null)}><option value={0}>Any score</option><option value={.6}>60% and up</option><option value={.75}>75% and up</option><option value={.8}>80% and up</option></select></label>
        <label class="field">Predicted class<select class="select" aria-label="Predicted class" bind:value={predicted} onchange={() => focus(null)}><option value="all">All classes</option>{#each classKeys as key}<option value={key}>{classes[key].name}</option>{/each}</select></label>
      </div>
    </div>

    <div class="sample-list" aria-label="Candidate samples">
      {#each queue as item (item.id)}
        <button class="sample-row" class:current={sample?.id === item.id} aria-current={sample?.id === item.id ? 'true' : undefined} onclick={() => focus(item.id)}>
          <span class="sample-row-icon" style:--class-color={classes[item.prediction].color}><i class="class-dot"></i></span>
          <span class="sample-row-id"><strong>{item.id}</strong><small>{item.location}</small></span>
          <span class="sample-score">{#if workspace.reviews[item.id]}<CircleCheck size={15} class="accent" aria-label="Reviewed" />{:else}{pct(item.uncertainty)}{/if}</span>
          <ChevronRight size={13} class="faint" />
        </button>
      {:else}
        <div class="empty-state"><CircleCheck size={20} /><strong>{!pending && mode === 'pending' ? 'Queue complete' : 'No matching samples'}</strong><span>{!pending && mode === 'pending' ? 'All candidate samples have been reviewed.' : 'Adjust the uncertainty or class filter.'}</span>
          {#if threshold || predicted !== 'all'}<button class="button-link" onclick={() => { threshold = 0; predicted = 'all'; focus(null); }}>Clear filters</button>
          {:else if mode === 'pending'}<button class="button-link" onclick={() => { mode = 'reviewed'; focus(null); }}>View reviewed samples</button>{/if}
        </div>
      {/each}
    </div>
  </section>

  {#if sample}
    <div class="stack">
      <section class="surface sample-panel">
        <div class="panel-heading sample-heading">
          <div class="panel-heading-title"><LocateFixed size={17} /><h2>{sample.id}</h2><span class="sample-location">{sample.location}</span></div>
          <div class="sample-navigation">
            <button class="icon-button" aria-label="Previous sample" title="Previous sample" disabled={position === 0} onclick={() => focus(queue[position - 1].id)}><ChevronLeft size={17} /></button>
            <span class="mono">{position + 1} / {queue.length}</span>
            <button class="icon-button" aria-label="Next sample" title="Next sample" disabled={position + 1 >= queue.length} onclick={() => focus(queue[position + 1].id)}><ChevronRight size={17} /></button>
          </div>
        </div>
        <div class="sample-image">
          <MiniScene {sample} observation={getObservation(sample.observation)} mode={preview} label={`${sample.location}, sample ${sample.id}, simulated imagery`} />
          <div class="segments preview-controls" role="group" aria-label="Sample overlay">
            <button class:chosen={preview === 'prediction'} aria-pressed={preview === 'prediction'} onclick={() => { preview = 'prediction'; }}>Prediction</button>
            <button class:chosen={preview === 'raw'} aria-pressed={preview === 'raw'} onclick={() => { preview = 'raw'; }}>Imagery</button>
          </div>
        </div>
        <div class="sample-meta">
          <div><small>MODEL PREDICTION</small><strong class="class-label"><i class="class-dot" style:--class-color={classes[sample.prediction].color}></i>{classes[sample.prediction].name}</strong><span>Sentinel Fusion RF / simulated</span></div>
          <div><small>UNCERTAINTY SCORE</small><strong class="uncertainty mono">{pct(sample.uncertainty)}</strong><span>Higher values indicate less certainty</span></div>
          <div><small>OBSERVATION</small><strong class="mono">{fmtDate(sample.observation)}</strong><button class="button-link" onclick={() => showMap(sample)}><MapPin size={12} /> Locate on map</button></div>
        </div>
      </section>

      <section class="surface section-box label-panel">
        <div class="section-heading"><div><h2>{review ? 'Human-reviewed label' : 'Assign a review label'}</h2><p>{review ? `Reviewed ${fmtDate(review.date)} / You can revise this local label.` : 'Choose the class that best describes the marked sample.'}</p></div>
          {#if review}<span class="outline-badge"><Check size={12} /> REVIEWED</span>{/if}
        </div>
        <fieldset class="label-options">
          <legend class="sr-only">Available water-body class labels</legend>
          {#each labelKeys as key}
            <label class="label-option" class:chosen={choice === key} style:--class-color={classes[key].color}>
              <input type="radio" name="review-label" value={key} checked={choice === key} onchange={() => { draft = { sample: sample.id, label: key }; }} />
              <i class="class-dot"></i><span>{classes[key].name}</span>{#if choice === key}<Check size={14} />{/if}
            </label>
          {/each}
        </fieldset>
        <div class="label-actions">
          {#if choice === 'uncertain'}<span class="label-hint"><TriangleAlert size={13} /> Flag this sample for follow-up.</span>{:else}<span class="label-hint">Labels are saved to this browser.</span>{/if}
          <button class="button primary" disabled={!choice || choice === review?.label} onclick={submit}>{review ? 'Save revised label' : mode === 'pending' ? 'Submit label & next' : 'Submit label'} <ArrowRight size={15} /></button>
        </div>
      </section>
    </div>
  {:else}
    <div class="surface empty-state sample-empty"><LocateFixed size={27} /><strong>No sample to inspect</strong><span>Choose a different queue or adjust your filters.</span><button class="button-link" onclick={() => { mode = 'all'; predicted = 'all'; threshold = 0; focus(null); }}><ArrowLeft size={14} /> Show all candidate samples</button></div>
  {/if}
</div>

<style>
  .learning-layout { display: grid; grid-template-columns: 295px minmax(0, 1fr); gap: 15px; align-items: start; }
  .queue-settings { padding: 12px; border-bottom: 1px solid var(--line); }
  .queue-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 9px; }
  .queue-stats > div { display: grid; gap: 1px; }
  .queue-stats > div + div { border-left: 1px solid var(--line); padding-left: 12px; }
  .queue-stats strong { color: #e1f1f9; font-size: 23px; font-weight: 400; line-height: 1.2; }
  .queue-stats span { color: var(--muted); font-size: 11px; }
  .queue-progress { height: 4px; overflow: hidden; background: #2b3d52; border-radius: 5px; }
  .queue-progress i { display: block; height: 100%; background: #66dcbe; border-radius: 5px; transition: width 200ms ease; }
  .queue-caption { color: var(--faint); font-size: 10.5px; display: flex; justify-content: space-between; gap: 6px; margin: 6px 0 10px; }
  .flag-count { color: var(--warn); }
  .queue-tabs { display: flex; }
  .queue-tabs button { flex: 1; }
  .queue-filters { margin-top: 10px; display: grid; gap: 8px; grid-template-columns: .95fr 1.05fr; }
  .queue-filters .field { min-width: 0; }
  .queue-filters .select { font-size: 11px; padding-left: 7px; min-height: 32px; }
  .sample-list { max-height: 421px; overflow: auto; padding: 5px; }
  .sample-row { display: flex; align-items: center; text-align: left; gap: 7px; width: 100%; min-height: 48px; padding: 6px; border: 1px solid transparent; border-bottom-color: var(--line); }
  .sample-row.current { border: 1px solid #2e595d; border-radius: 5px; background: #18343e; }
  .sample-row:not(.current):hover { background: #192a3e; border-radius: 5px; }
  .sample-row-icon { display: grid; place-items: center; flex: none; width: 22px; height: 22px; border-radius: 5px; background: color-mix(in srgb, var(--class-color) 16%, #142334); }
  .sample-row-id { display: grid; flex: 1; min-width: 0; gap: 2px; }
  .sample-row-id strong { color: var(--ink); font: 11px var(--mono); }
  .sample-row-id small { color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10.5px; }
  .sample-row.current .sample-row-id small { color: var(--muted); }
  .sample-score { color: var(--warn); font: 10.5px var(--mono); }
  .sample-heading { padding-block: 9px; }
  .sample-location { color: var(--faint); border-left: 1px solid var(--border); padding-left: 8px; font-size: 11px; }
  .sample-navigation { display: flex; gap: 5px; align-items: center; color: var(--muted); white-space: nowrap; font-size: 10.5px; }
  .sample-navigation .icon-button { border: 1px solid var(--border); }
  .sample-panel { overflow: hidden; }
  .sample-image { height: clamp(222px, 29vw, 345px); position: relative; }
  .preview-controls { position: absolute; top: 11px; left: 11px; background: #0e1a29ed; border-color: #546779; }
  .sample-meta { display: grid; grid-template-columns: 1.15fr 1fr .95fr; }
  .sample-meta > div { display: grid; align-content: start; min-width: 0; padding: 11px 13px; gap: 3px; }
  .sample-meta > div + div { border-left: 1px solid var(--line); }
  .sample-meta small { font: 9.5px var(--mono); letter-spacing: .045em; color: var(--faint); }
  .sample-meta strong { color: var(--ink); font-size: 12px; font-weight: 560; }
  .sample-meta .uncertainty { color: var(--warn); }
  .sample-meta span, .sample-meta button { font-size: 10.5px; }
  .sample-meta span { color: var(--faint); }
  .label-options { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; padding: 0; border: 0; margin: 0; }
  .label-option { display: flex; align-items: center; gap: 7px; padding: 7px 9px; min-height: 36px; border: 1px solid var(--border); border-radius: 5px; color: var(--muted); background: #122133; cursor: pointer; font-size: 11.5px; }
  .label-option:hover, .label-option.chosen { color: var(--ink); border-color: color-mix(in srgb, var(--class-color) 66%, #315063); background: color-mix(in srgb, var(--class-color) 13%, #172635); }
  .label-option input { width: 12px; height: 12px; accent-color: var(--class-color); }
  .label-option :global(svg) { margin-left: auto; color: var(--class-color); flex: none; }
  .label-actions { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .label-hint { display: flex; align-items: center; gap: 6px; color: var(--faint); font-size: 11px; }
  .label-hint :global(svg) { color: var(--warn); }
  .sample-empty { min-height: 282px; }
  @media (max-width: 1100px) { .learning-layout { grid-template-columns: 252px minmax(0, 1fr); gap: 11px; } }
  @media (max-width: 900px) { .learning-layout { grid-template-columns: minmax(0, 1fr); } .sample-list { max-height: 190px; } }
  @media (max-width: 440px) { .sample-location { display: none; } .sample-meta > div { padding-inline: 7px; } .sample-meta small { font-size: 8px; } .sample-meta span, .sample-meta button { font-size: 9.5px; } .sample-meta strong { font-size: 11px; } }
</style>
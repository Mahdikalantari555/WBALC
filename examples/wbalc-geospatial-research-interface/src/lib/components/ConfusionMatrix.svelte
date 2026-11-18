<script lang="ts">
  import { classKeys, classes, evaluateModel, type Model, type PredictionClass } from '../data/research';

  let { model, focus = 'all' }: { model: Model; focus?: PredictionClass | 'all' } = $props();
  let normalized = $state(false);
  const metrics = $derived(evaluateModel(model));
</script>

<section class="surface section-box matrix-panel">
  <div class="section-heading"><div><h2>Confusion matrix</h2><p>{model.name} / {metrics.total} simulated references</p></div>
    <div class="segments" role="group" aria-label="Confusion matrix display">
      <button class:chosen={!normalized} aria-pressed={!normalized} onclick={() => { normalized = false; }}>Count</button>
      <button class:chosen={normalized} aria-pressed={normalized} onclick={() => { normalized = true; }}>Row %</button>
    </div>
  </div>
  <div class="matrix-axis">PREDICTED CLASS</div>
  <table class="matrix-table">
    <caption class="sr-only">Simulated confusion matrix, rows are reference labels and columns are predictions.</caption>
    <thead><tr><th scope="col">Reference</th>{#each classKeys as key}<th scope="col" aria-label={classes[key].name}>{classes[key].short}</th>{/each}</tr></thead>
    <tbody>
      {#each model.matrix as row, i}
        <tr class:deemphasized={focus !== 'all' && focus !== classKeys[i]}>
          <th scope="row"><span class="class-label"><i class="class-dot" style:--class-color={classes[classKeys[i]].color}></i>{classes[classKeys[i]].short}</span></th>
          {#each row as value, j}
            <td class:diagonal={i === j} style:--heat={i === j ? `${(value / metrics.rows[i].support) * 45}%` : `${Math.min(49, value * 2.9)}%`}
              title={`${classes[classKeys[i]].name} reference, ${classes[classKeys[j]].name} predicted`}>
              {normalized ? `${(value / metrics.rows[i].support * 100).toFixed(1)}%` : value}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
  <p class="matrix-note">Rows are reference labels. Columns are model predictions.</p>
</section>

<style>
  .matrix-table { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 4px; margin-inline: -4px; width: calc(100% + 8px); }
  .matrix-axis { color: var(--faint); text-align: right; padding-right: 13%; font: 9px var(--mono); letter-spacing: .05em; }
  .matrix-table th { color: var(--muted); text-align: left; font-size: 10px; font-weight: 550; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .matrix-table th:first-child { width: 28%; }
  .matrix-table thead th:not(:first-child) { text-align: center; }
  .matrix-table td { font: 11.5px/1 var(--mono); color: #f3d8b2; text-align: center; border: 1px solid #354359; height: 39px; border-radius: 4px; background: color-mix(in srgb, #9b572e var(--heat), #172336); }
  .matrix-table td.diagonal { color: #e1faf2; border-color: #365d60; background: color-mix(in srgb, #30887f var(--heat), #152336); }
  .matrix-table .class-dot { width: 6px; height: 6px; }
  .matrix-table .deemphasized td { color: #acb8c8; background: #162235; border-color: #2b394c; }
  .matrix-note { color: var(--faint); font-size: 10.5px; margin: 8px 0 0; }
</style>
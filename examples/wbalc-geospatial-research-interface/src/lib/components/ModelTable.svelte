<script lang="ts">
  import { classes, evaluateModel, metricKeys, metricLabels, models, pct, type ModelId, type PredictionClass } from '../data/research';

  let { selected, challenger, onselect, focus = 'all' }: {
    selected: ModelId; challenger?: ModelId; focus?: PredictionClass | 'all'; onselect: (model: ModelId) => void;
  } = $props();
  const records = models.map(model => ({ model, score: evaluateModel(model) }));
</script>

<section class="surface section-box">
  <div class="section-heading"><div><h2>Model performance comparison</h2><p>{focus === 'all' ? 'Macro-averaged metrics across three classes / 300 simulated references' : `${classes[focus].name} metrics / Accuracy remains overall`}</p></div><span class="outline-badge">SIMULATED</span></div>
  <div class="table-scroll">
    <table class="data-table" aria-label="Simulated model performance comparison">
      <thead><tr><th scope="col">Classification model</th><th class="number" scope="col">Accuracy</th>{#each metricKeys as key}<th class="number" scope="col">{metricLabels[key]}</th>{/each}<th class="number" scope="col">Inference</th></tr></thead>
      <tbody>
        {#each records as { model, score }}
          {@const row = focus === 'all' ? score : score.rows.find(item => item.key === focus) ?? score}
          <tr class:selected={model.id === selected}>
            <td><button class="model-name" aria-pressed={model.id === selected} onclick={() => onselect(model.id)}>
              {#if challenger && (model.id === selected || model.id === challenger)}<span class="model-letter" class:second={model.id === challenger}>{model.id === selected ? 'A' : 'B'}</span>{/if}
              {model.name}
            </button></td>
            <td class="number">{pct(score.accuracy)}</td>{#each metricKeys as key}<td class="number">{pct(row[key])}</td>{/each}<td class="number">{model.inference.toFixed(2)} s</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>

<style>
  .model-name { display: inline-flex; font-weight: 560; align-items: center; gap: 7px; padding: 2px 0; white-space: nowrap; }
  .model-name:hover { text-decoration: underline; color: var(--accent); }
  .model-letter { display: grid; align-items: center; text-align: center; width: 16px; height: 16px; font: 10px var(--mono); border: 1px solid #456f6d; color: #a2eedf; background: #19383c; border-radius: 4px; }
  .model-letter.second { background: #283152; border-color: #505b86; color: #cbd6ff; }
</style>
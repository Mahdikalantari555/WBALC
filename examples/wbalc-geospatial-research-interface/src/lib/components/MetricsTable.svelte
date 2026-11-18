<script lang="ts">
  import { classes, evaluateModel, metricKeys, metricLabels, pct, type Model, type PredictionClass } from '../data/research';

  let { model, focus = 'all' }: { model: Model; focus?: PredictionClass | 'all' } = $props();
  const rows = $derived(evaluateModel(model).rows.filter(row => focus === 'all' || focus === row.key));
</script>

<section class="surface section-box">
  <div class="section-heading"><div><h2>Per-class performance</h2><p>{model.name} / simulated holdout results</p></div></div>
  <div class="table-scroll">
    <table class="data-table" aria-label="Simulated per-class performance">
      <thead><tr><th scope="col">Reference class</th><th class="number" scope="col">Support</th>{#each metricKeys as key}<th class="number" scope="col">{metricLabels[key]}</th>{/each}</tr></thead>
      <tbody>
        {#each rows as row (row.key)}
          <tr><td><span class="class-label nowrap"><i class="class-dot" style:--class-color={classes[row.key].color}></i>{classes[row.key].name}</span></td><td class="number">{row.support}</td>
            {#each metricKeys as key}<td class="number">{pct(row[key])}</td>{/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>
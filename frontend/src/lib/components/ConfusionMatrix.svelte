<script lang="ts">
  import { useT } from '$lib/t.svelte';
  import type { MetricsView } from '$lib/types';
  import { classColor } from '$lib/palette';

  let { metrics, focus = 'all' }: { metrics: MetricsView; focus?: string } = $props();

  const { t, integer, percent } = useT();
  let normalized = $state(false);

  const total = $derived(
    metrics.confusionMatrix.reduce((sum, row) => sum + row.reduce((a, b) => a + b, 0), 0),
  );
</script>

<section class="surface section-box matrix-panel">
  <div class="section-heading">
    <div>
      <h2>{t('arena.confusion')}</h2>
      <p>{t('arena.confusionHint', { total: integer(total) })} · {metrics.modelType} / {metrics.resolution}</p>
    </div>
    <div class="segments" role="group" aria-label={t('arena.confusion')}>
      <button class:chosen={!normalized} aria-pressed={!normalized} onclick={() => (normalized = false)}>{t('arena.count')}</button>
      <button class:chosen={normalized} aria-pressed={normalized} onclick={() => (normalized = true)}>{t('arena.rowPercent')}</button>
    </div>
  </div>

  {#if metrics.confusionMatrix.length}
    <div class="matrix-axis">{t('arena.predicted')}</div>
    <div class="table-scroll">
      <table class="matrix-table">
        <caption class="sr-only">{t('arena.confusion')}</caption>
        <thead>
          <tr>
            <th scope="col">{t('arena.reference')}</th>
            {#each metrics.classes as name}
              <th scope="col">{name}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each metrics.confusionMatrix as row, i}
            {@const rowTotal = row.reduce((a, b) => a + b, 0)}
            <tr class:deemphasized={focus !== 'all' && focus !== metrics.classes[i]}>
              <th scope="row">
                <span class="class-label"><i class="class-dot" style:--class-color={classColor(metrics.classes[i], i)}></i>{metrics.classes[i]}</span>
              </th>
              {#each row as value, j}
                <td
                  class:diagonal={i === j}
                  style:--heat={i === j
                    ? `${rowTotal ? (value / rowTotal) * 45 : 0}%`
                    : `${Math.min(49, (rowTotal ? value / rowTotal : 0) * 60)}%`}
                >
                  <span class="ltr-numeric">
                    {normalized ? percent(rowTotal ? value / rowTotal : 0) : integer(value)}
                  </span>
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="matrix-note">{t('arena.reference')} → {t('arena.predicted')}</p>
  {:else}
    <div class="empty-state"><strong>{t('arena.noMetrics')}</strong></div>
  {/if}
</section>

<style>
  .matrix-axis { color: var(--faint); text-align: right; padding-inline-end: 13%; font: 10px var(--mono); letter-spacing: .05em; text-transform: uppercase; }
  .matrix-table { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 4px; margin-inline: -4px; width: calc(100% + 8px); }
  .matrix-table th { color: var(--muted); text-align: start; font-size: 10px; font-weight: 550; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .matrix-table th:first-child { width: 30%; }
  .matrix-table thead th:not(:first-child) { text-align: center; }
  .matrix-table td { font: 11.5px/1 var(--mono); color: var(--warn); text-align: center; border: 1px solid var(--control-border); height: 39px; border-radius: 4px; background: color-mix(in srgb, var(--danger) var(--heat), var(--control-bg)); }
  .matrix-table td.diagonal { color: var(--ink); border-color: var(--control-border); background: color-mix(in srgb, var(--control-border) var(--heat), var(--control-bg)); }
  .matrix-table .class-dot { width: 6px; height: 6px; }
  .matrix-table .deemphasized td { color: var(--muted); background: var(--control-bg); border-color: var(--control-border); }
  .matrix-note { color: var(--faint); font-size: 10.5px; margin: 8px 0 0; }
</style>

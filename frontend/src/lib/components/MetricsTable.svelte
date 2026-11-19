<script lang="ts">
  import { classColor } from '$lib/palette';
  import { useT } from '$lib/t.svelte';
  import type { MetricsView } from '$lib/types';

  let { metrics, focus = 'all' }: { metrics: MetricsView; focus?: string } = $props();

  const { t, integer, percent } = useT();
  const rows = $derived(
    metrics.perClass.filter((row) => focus === 'all' || row.className === focus),
  );
</script>

<section class="surface section-box">
  <div class="section-heading">
    <div>
      <h2>{t('arena.perClass')}</h2>
      <p>{metrics.modelType} / {metrics.evaluationStrategy ?? 'random'} · {metrics.resolution}</p>
    </div>
    {#if metrics.insufficient}<span class="badge-muted">{t('arena.insufficient')}</span>{/if}
  </div>
  {#if rows.length}
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th scope="col">{t('arena.reference')}</th>
            <th class="number" scope="col">{t('arena.support')}</th>
            <th class="number" scope="col">{t('arena.precision')}</th>
            <th class="number" scope="col">{t('arena.recall')}</th>
            <th class="number" scope="col">{t('arena.f1')}</th>
            <th class="number" scope="col">{t('arena.iou')}</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as row, index (row.className)}
            <tr>
              <td>
                <span class="class-label">
                  <i class="class-dot" style:--class-color={classColor(row.className, index)}></i>{row.className}
                </span>
              </td>
              <td class="number">{integer(row.support)}</td>
              <td class="number">{percent(row.precision)}</td>
              <td class="number">{percent(row.recall)}</td>
              <td class="number">{percent(row.f1)}</td>
              <td class="number">{percent(row.iou)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div class="empty-state"><strong>{t('arena.noMetrics')}</strong></div>
  {/if}
</section>

<script lang="ts">
  let {
    label,
    value,
    display,
    hint = '',
  }: { label: string; value: number | null; display: string; hint?: string } = $props();

  const width = $derived(value === null ? '0%' : `${Math.max(0, Math.min(1, value)) * 100}%`);
</script>

<div class="metric-bar">
  <div class="metric-head">
    <span>{label}</span>
    <b class="mono ltr-numeric">{display}</b>
  </div>
  <div class="metric-track"><i style:width></i></div>
  {#if hint}<small>{hint}</small>{/if}
</div>

<style>
  .metric-bar > .metric-head { display: flex; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 12px; margin-bottom: 4px; }
  .metric-head b { color: var(--accent); font-size: 12px; font-weight: 500; }
  .metric-track { height: 4px; border-radius: 4px; background: #293c50; overflow: hidden; }
  .metric-track i { display: block; height: 100%; border-radius: 4px; background: #52b9a8; transition: width 180ms ease; }
  small { display: block; margin-top: 4px; color: var(--faint); font-size: 10.5px; }
</style>

<script lang="ts">
  import type { SensorFilter } from '../data/research';
  let { value, onchange }: { value: SensorFilter; onchange: (value: SensorFilter) => void } = $props();
  const options = [{ value: 'all', label: 'All sensors' }, { value: 'Sentinel-1', label: 'Sentinel-1' }, { value: 'Sentinel-2', label: 'Sentinel-2' }] as const;
</script>

<div class="segments" role="group" aria-label="Filter observations by satellite sensor">
  {#each options as option}
    <button aria-pressed={value === option.value} class:chosen={value === option.value} onclick={() => onchange(option.value)}>{option.label}</button>
  {/each}
</div>
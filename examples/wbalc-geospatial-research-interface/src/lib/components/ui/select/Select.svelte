<script lang="ts">
  /**
   * Select — a native `<select>`, deliberately.
   *
   * A custom listbox would need focus management this workspace does not have,
   * and native selects keep keyboard behaviour and RTL text direction correct
   * for free. Options are passed as data so callers cannot forget a `value`.
   */
  import { cn } from '$lib/utils';
  import type { HTMLSelectAttributes } from 'svelte/elements';

  let {
    options,
    value = $bindable(''),
    class: className = '',
    ...rest
  }: HTMLSelectAttributes & {
    options: { value: string; label: string }[];
    value?: string;
    class?: string;
  } = $props();
</script>

<select class={cn('select', className)} bind:value {...rest}>
  {#each options as option (option.value)}
    <option value={option.value}>{option.label}</option>
  {/each}
</select>

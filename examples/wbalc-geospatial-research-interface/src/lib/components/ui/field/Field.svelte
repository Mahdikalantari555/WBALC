<script lang="ts">
  /**
   * Field — label + control + optional hint, wired for screen readers.
   *
   * `for` is required in spirit: an unlabelled control in a research UI is a
   * reproducibility hazard (the user cannot say which knob they turned).
   */
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    id,
    label,
    hint = '',
    inline = false,
    class: className = '',
    children,
  }: {
    id?: string;
    label: string;
    hint?: string;
    inline?: boolean;
    class?: string;
    children?: Snippet;
  } = $props();
</script>

<div class={cn(inline ? 'field-inline' : 'field', className)}>
  <label for={id}>{label}</label>
  {@render children?.()}
  {#if hint}<small class="field-hint">{hint}</small>{/if}
</div>

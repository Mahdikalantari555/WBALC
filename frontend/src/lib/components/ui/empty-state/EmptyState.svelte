<script lang="ts">
  /**
   * EmptyState — what the panel shows when the engine has nothing to report.
   *
   * A missing record is a *result* in this workspace ("no reference area, so
   * areas are estimates"), so the hint is part of the component, not optional
   * decoration.
   */
  import type { Snippet } from 'svelte';
  import { CircleSlash } from '@lucide/svelte';
  import { cn } from '$lib/utils';

  let {
    title,
    hint = '',
    action,
    class: className = '',
  }: { title: string; hint?: string; action?: Snippet; class?: string } = $props();
</script>

<div class={cn('empty-state', className)}>
  <CircleSlash size={18} />
  <strong>{title}</strong>
  {#if hint}<span>{hint}</span>{/if}
  {#if action}{@render action()}{/if}
</div>

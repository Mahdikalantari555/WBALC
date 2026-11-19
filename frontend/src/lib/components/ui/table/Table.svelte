<script lang="ts">
  /**
   * Table — a scrollable, semantically correct table shell.
   *
   * `caption` is required: every table in this app must say what it counts
   * (samples? classes? scenes?) because the unit is the claim.
   */
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    caption,
    head,
    class: className = '',
    children,
  }: { caption: string; head: Snippet; class?: string; children?: Snippet } = $props();
</script>

<div class="table-wrap">
  <table class={cn('table', className)}>
    <caption class="table-caption">{caption}</caption>
    <thead>{@render head()}</thead>
    <tbody>{@render children?.()}</tbody>
  </table>
</div>

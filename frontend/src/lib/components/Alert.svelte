<script lang="ts">
  /**
   * Alert — one place for "the engine refused this" / "this number is limited".
   *
   * Each page used to hand-roll `<div class="inline-error">` with its own icon
   * and its own phrasing of the same three states. The wording still comes from
   * the caller (it is evidence-specific); the shape, the role and the icon no
   * longer drift between views.
   */
  import type { Snippet } from 'svelte';
  import { TriangleAlert } from '@lucide/svelte';

  let {
    title,
    tone = 'danger',
    actions,
    children,
  }: {
    title: string;
    tone?: 'danger' | 'warning';
    actions?: Snippet;
    children?: Snippet;
  } = $props();
</script>

<div class="alert {tone === 'warning' ? 'alert-warning' : 'alert-destructive'}" role="alert">
  <TriangleAlert size={15} class="alert-icon" />
  <div>
    <strong>{title}</strong>
    {@render children?.()}
  </div>
  {#if actions}{@render actions()}{/if}
</div>

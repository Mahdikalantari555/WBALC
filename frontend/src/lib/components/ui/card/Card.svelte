<script lang="ts">
  /**
   * Card — the standard panel: header (title, meta, actions) + body.
   * Replaces the repeated `surface section-box` + `section-heading` markup.
   */
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    title,
    description = '',
    id = '',
    actions,
    class: className = '',
    children,
  }: {
    title: string;
    description?: string;
    id?: string;
    actions?: Snippet;
    class?: string;
    children?: Snippet;
  } = $props();
</script>

<section class={cn('card', className)} aria-labelledby={id || undefined}>
  <header class="card-header">
    <div>
      <h2 id={id || undefined}>{title}</h2>
      {#if description}<p>{description}</p>{/if}
    </div>
    {#if actions}{@render actions()}{/if}
  </header>
  <div class="card-body">{@render children?.()}</div>
</section>

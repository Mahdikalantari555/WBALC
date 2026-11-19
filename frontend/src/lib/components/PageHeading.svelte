<script lang="ts">
  import { Crosshair } from '@lucide/svelte';
  import type { Snippet } from 'svelte';

  let {
    title,
    description,
    eyebrow = '',
    actions,
  }: {
    title: string;
    description: string;
    eyebrow?: string;
    actions?: Snippet;
  } = $props();
</script>

<div class="page-heading">
  <div>
    <div class="eyebrow">
      <Crosshair size={13} strokeWidth={1.8} />{eyebrow}
    </div>
    <h1>{title}</h1>
    <p>{description}</p>
  </div>
  {#if actions}<div class="heading-actions">{@render actions()}</div>{/if}
</div>

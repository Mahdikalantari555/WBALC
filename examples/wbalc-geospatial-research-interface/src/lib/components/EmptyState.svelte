<script lang="ts">
  import type { Snippet } from 'svelte';
  import { CircleSlash } from '@lucide/svelte';

  let {
    title,
    hint = '',
    action,
  }: { title: string; hint?: string; action?: Snippet } = $props();
</script>

<div class="empty-state">
  <CircleSlash size={20} />
  <strong>{title}</strong>
  {#if hint}<span>{hint}</span>{/if}
  {#if action}{@render action()}{/if}
</div>

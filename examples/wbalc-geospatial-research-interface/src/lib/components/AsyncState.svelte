<script lang="ts">
  import type { Snippet } from 'svelte';
  import { TriangleAlert } from '@lucide/svelte';

  let {
    loading = false,
    error = null,
    children,
    empty = false,
    emptyTitle = '',
    emptyHint = '',
    emptyAction,
  }: {
    loading?: boolean;
    error?: string | null;
    empty?: boolean;
    emptyTitle?: string;
    emptyHint?: string;
    emptyAction?: Snippet;
    children: Snippet;
  } = $props();
</script>

{#if error}
  <div class="inline-error" role="alert">
    <TriangleAlert size={16} />
    <div><strong>{emptyTitle || 'Request failed'}</strong><span>{error}</span></div>
  </div>
{:else if loading}
  <div class="surface-empty"><span class="spinner"></span></div>
{:else if empty}
  <div class="empty-state">
    <strong>{emptyTitle}</strong>
    {#if emptyHint}<span>{emptyHint}</span>{/if}
    {#if emptyAction}{@render emptyAction()}{/if}
  </div>
{:else}
  {@render children()}
{/if}

<style>
  .surface-empty { display: grid; place-items: center; min-height: 120px; }
  .spinner { width: 15px; height: 15px; border-radius: 50%; border: 2px solid #35485a; border-top-color: var(--accent); animation: spin 700ms linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>

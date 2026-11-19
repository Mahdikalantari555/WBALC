<script lang="ts">
  import type { Snippet } from 'svelte';
  import { cn, variantOf } from '$lib/utils';
  import { badgeVariants, type BadgeVariant } from './badge-variants';

  let {
    variant = 'default',
    mono = false,
    title = '',
    class: className = '',
    children,
  }: {
    variant?: BadgeVariant;
    /** Tabular/monospaced: hashes, counts, ids. */
    mono?: boolean;
    title?: string;
    class?: string;
    children?: Snippet;
  } = $props();
</script>

<span class={cn(variantOf(badgeVariants, variant, 'default'), mono && 'badge-mono', className)} {title}>
  {@render children?.()}
</span>

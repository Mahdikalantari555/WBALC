<script lang="ts">
  /**
   * Button — the one button in this workspace.
   *
   * Collapses the ad-hoc `.button` / `.button.primary` / `.button.quiet` /
   * `.button.small` combinations that every page repeated into a
   * variant/size pair. `primary` is reserved for the action that moves the
   * workflow forward.
   */
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import { cn } from '$lib/utils';
  import { buttonSizes, buttonVariants, type ButtonSize, type ButtonVariant } from './button-variants';

  let {
    variant = 'default',
    size = 'default',
    class: className = '',
    href = '',
    children,
    ...rest
  }: HTMLButtonAttributes & {
    variant?: ButtonVariant;
    size?: ButtonSize;
    /** Render an anchor instead of a button (downloads, links). */
    href?: string;
    class?: string;
    children?: Snippet;
  } = $props();

  const classes = $derived(cn(buttonVariants[variant], buttonSizes[size], className));
</script>

{#if href}
  <a {href} class={classes}>
    {@render children?.()}
  </a>
{:else}
  <button class={classes} {...rest}>
    {@render children?.()}
  </button>
{/if}

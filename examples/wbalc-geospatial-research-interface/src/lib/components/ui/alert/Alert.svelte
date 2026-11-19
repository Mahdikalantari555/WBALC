<script lang="ts">
  import type { Snippet } from 'svelte';
  import { AlertTriangle, CheckCircle2, Info, OctagonAlert } from '@lucide/svelte';
  import { cn, variantOf } from '$lib/utils';
  import { alertVariants, type AlertVariant } from './alert-variants';

  let {
    variant = 'default',
    title = '',
    class: className = '',
    children,
  }: { variant?: AlertVariant; title?: string; class?: string; children?: Snippet } = $props();

  const Icon = $derived(
    variant === 'warning'
      ? AlertTriangle
      : variant === 'destructive'
        ? OctagonAlert
        : variant === 'success'
          ? CheckCircle2
          : Info,
  );
</script>

<div class={cn(variantOf(alertVariants, variant, 'default'), className)} role={variant === 'destructive' ? 'alert' : 'status'}>
  <Icon size={15} class="alert-icon" />
  <div>
    {#if title}<strong>{title}</strong>{/if}
    {@render children?.()}
  </div>
</div>

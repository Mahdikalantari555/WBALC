<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements';
  import { cn } from '$lib/utils';
  import { inputVariants, type InputVariant } from './input-variants';

  let {
    variant = 'default',
    class: className = '',
    ...rest
  }: HTMLInputAttributes & { variant?: InputVariant; class?: string } = $props();
</script>

<input class={cn(inputVariants[variant], className)} {...rest} />

<script lang="ts">
  /** Test-only harness: mounts one component inside the workspace context. */
  import { untrack } from 'svelte';
  import type { Component } from 'svelte';
  import { provideWorkspace, type Workspace } from '$lib/state.svelte';

  let {
    workspace,
    component,
    props = {},
  }: { workspace: Workspace; component: Component<Record<string, unknown>>; props?: Record<string, unknown> } =
    $props();

  // Both values are fixed for the lifetime of a test mount by design.
  const View = untrack(() => component);
  provideWorkspace(untrack(() => workspace));
</script>

<View {...props} />

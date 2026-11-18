<script lang="ts">
  import Workspace from '$lib/Workspace.svelte';
  import '$lib/../index.css';
  import type { Locale } from '$lib/i18n/locales';

  let { data }: { data: { locale: Locale } } = $props();
</script>

<svelte:head>
  <title>WBALC | Geospatial Research Workspace</title>
</svelte:head>

<Workspace locale={data.locale} />

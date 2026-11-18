<script lang="ts">
  import { LOCALE_LABELS, LOCALES } from '$lib/i18n/locales';
  import { getWorkspace } from '$lib/state.svelte';
  import { useT } from '$lib/t.svelte';

  const workspace = getWorkspace();
  const { t } = useT();
</script>

<div class="locale-switch" role="group" aria-label={t('locale.switch')}>
  {#each LOCALES as locale}
    <button
      type="button"
      lang={locale}
      aria-pressed={workspace.locale.current === locale}
      onclick={() => workspace.locale.set(locale)}
    >
      {LOCALE_LABELS[locale]}
    </button>
  {/each}
</div>

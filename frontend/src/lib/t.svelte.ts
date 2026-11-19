/**
 * Reactive translation helpers.
 *
 * `t(key, params)` reads `locale.current`, so any template that calls it
 * re-renders when the language changes — no reload, no re-subscription. The
 * formatters take the active locale the same way.
 */
import { formatDate, formatDateTime, formatInteger, formatNumber, formatPercent } from './i18n/format';
import type { TranslationKey } from './i18n/en';
import { getWorkspace } from './state.svelte';

export function useT() {
  const workspace = getWorkspace();

  const t = (key: TranslationKey, params?: Record<string, string | number>): string => {
    // Touch the reactive primitive so callers in markup re-run on switch.
    const locale = workspace.locale.current;
    return translateFor(locale, key, params);
  };

  return {
    t,
    date: (value: string | Date | null | undefined) => formatDate(workspace.locale.current, value),
    dateTime: (value: string | Date | null | undefined) =>
      formatDateTime(workspace.locale.current, value),
    number: (value: number | null | undefined, digits = 2) =>
      formatNumber(workspace.locale.current, value, digits),
    integer: (value: number | null | undefined) => formatInteger(workspace.locale.current, value),
    percent: (value: number | null | undefined, digits = 1) =>
      formatPercent(workspace.locale.current, value, digits),
  };
}

// Imported lazily to keep the store module free of a cycle at module scope.
import { translate } from './i18n/format';
import type { Locale } from './i18n/locales';

function translateFor(
  locale: Locale,
  key: TranslationKey,
  params?: Record<string, string | number>,
): string {
  return translate(locale, key, params);
}

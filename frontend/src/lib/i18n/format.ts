import {
  DEFAULT_LOCALE,
  dictionaries,
  intlLocale,
  type Locale,
  type TranslationKey,
} from './locales';

export type TranslationParams = Record<string, string | number>;

/**
 * Look a key up in the active locale and interpolate `{name}` placeholders.
 *
 * Falls back to the English dictionary (then to the key itself) so a missing
 * string degrades visibly but never breaks a screen. `check:i18n` keeps both
 * dictionaries complete, so this path should stay unused in practice.
 */
export function translate(
  locale: Locale,
  key: TranslationKey,
  params?: TranslationParams,
): string {
  const template =
    dictionaries[locale]?.[key] ?? dictionaries[DEFAULT_LOCALE][key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

/** Locale-aware date, defaulting to a medium date with a UTC-safe parse. */
export function formatDate(
  locale: Locale,
  value: string | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' },
): string {
  if (value === null || value === undefined || value === '') return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(intlLocale(locale), { timeZone: 'UTC', ...options }).format(
    date,
  );
}

export function formatDateTime(locale: Locale, value: string | Date | null | undefined): string {
  return formatDate(locale, value, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Grouped number with a fixed fraction-digit count (locale digits included). */
export function formatNumber(
  locale: Locale,
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat(intlLocale(locale), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatInteger(locale: Locale, value: number | null | undefined): string {
  return formatNumber(locale, value, 0);
}

/**
 * Percent from a 0..1 fraction. `digits` defaults to one decimal so metric
 * tables keep a stable column width.
 */
export function formatPercent(
  locale: Locale,
  value: number | null | undefined,
  digits = 1,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat(intlLocale(locale), {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

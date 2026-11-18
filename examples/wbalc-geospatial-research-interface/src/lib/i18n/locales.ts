/** Locale plumbing shared by the server hooks, the runtime store and the UI. */
import { en, type TranslationKey } from './en';
import { fa } from './fa';

export type Locale = 'en' | 'fa';
export const LOCALES: Locale[] = ['en', 'fa'];
export const DEFAULT_LOCALE: Locale = 'en';
export const LOCALE_COOKIE = 'wbalc.locale';
export const LOCALE_STORAGE_KEY = 'wbalc:locale';

export const dictionaries: Record<Locale, Record<TranslationKey, string>> = { en, fa };

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'English',
  fa: 'فارسی',
};

export function isLocale(value: unknown): value is Locale {
  return value === 'en' || value === 'fa';
}

/** Coerce anything (cookie, storage, query param) to a supported locale. */
export function normalizeLocale(value: unknown): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}

export function localeDir(locale: Locale): 'ltr' | 'rtl' {
  return locale === 'fa' ? 'rtl' : 'ltr';
}

/** BCP-47 tags used for `Intl` formatting. */
export function intlLocale(locale: Locale): string {
  return locale === 'fa' ? 'fa-IR' : 'en-GB';
}

export type { TranslationKey };

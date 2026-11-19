import { LOCALE_COOKIE, LOCALE_STORAGE_KEY, normalizeLocale, type Locale } from './locales';

/**
 * Active-locale state shared by every component.
 *
 * The initial value is seeded during SSR from the `wbalc.locale` cookie (see
 * `src/hooks.server.ts`), so the very first HTML already has the right strings
 * and `dir`. `applyDocumentLocale` mirrors the choice onto `<html>` at runtime
 * for the no-reload language switch.
 */
class LocaleStore {
  current = $state<Locale>('en');

  constructor(initial: Locale) {
    this.current = initial;
  }

  set(locale: Locale) {
    this.current = normalizeLocale(locale);
    persist(this.current);
    applyDocumentLocale(this.current);
  }

  /** Seed from the server payload without writing client storage. */
  hydrate(locale: Locale) {
    this.current = normalizeLocale(locale);
  }
}

function persist(locale: Locale) {
  if (typeof document === 'undefined') return;
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    /* Storage can be disabled; the cookie still carries the preference. */
  }
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
}

export function applyDocumentLocale(locale: Locale) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.lang = locale;
  root.dir = locale === 'fa' ? 'rtl' : 'ltr';
  root.dataset.locale = locale;
}

export function createLocaleStore(initial: Locale = 'en') {
  return new LocaleStore(initial);
}

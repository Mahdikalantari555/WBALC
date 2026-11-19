import type { PageServerLoad } from './$types';
import { LOCALE_COOKIE, normalizeLocale } from '$lib/i18n/locales';

/**
 * Seed the runtime locale from the cookie during SSR, so the first paint is
 * already in the right language and direction (no LTR flash for Persian).
 */
export const load: PageServerLoad = async ({ cookies }) => {
  return { locale: normalizeLocale(cookies.get(LOCALE_COOKIE)) };
};

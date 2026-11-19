import type { RequestEvent } from '@sveltejs/kit';
import { LOCALE_COOKIE, normalizeLocale, type Locale } from '$lib/i18n/locales';

/**
 * Server hook: resolve the locale from the cookie and emit the document
 * `<html lang dir>` attributes on the very first byte, so there is no
 * left-to-right flash before hydration.
 */
export async function handle({ event, resolve }: { event: RequestEvent; resolve: (event: RequestEvent, options?: { transformPageChunk?: (input: { html: string }) => string }) => Promise<Response> }) {
  const locale: Locale = normalizeLocale(event.cookies.get(LOCALE_COOKIE));
  event.locals.locale = locale;

  return resolve(event, {
    transformPageChunk: ({ html }) =>
      html.replace('%wbalc.lang%', locale).replace('%wbalc.dir%', locale === 'fa' ? 'rtl' : 'ltr'),
  });
}

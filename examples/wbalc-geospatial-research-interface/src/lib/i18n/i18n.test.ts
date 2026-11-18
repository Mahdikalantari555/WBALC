import { describe, expect, it } from 'vitest';
import { dictionaries, intlLocale, isLocale, normalizeLocale } from './locales';
import { formatDate, formatNumber, formatPercent, translate } from './format';
import { en, type TranslationKey } from './en';

describe('dictionary completeness', () => {
  it('has the same keys in both locales', () => {
    const english = Object.keys(dictionaries.en).sort();
    const persian = Object.keys(dictionaries.fa).sort();
    expect(persian).toEqual(english);
  });

  it('keeps the same {placeholders} per key', () => {
    const placeholders = (value: string) => (value.match(/\{(\w+)\}/g) ?? []).sort();
    for (const key of Object.keys(en) as TranslationKey[]) {
      expect({ key, fa: placeholders(dictionaries.fa[key]) }).toEqual({
        key,
        fa: placeholders(dictionaries.en[key]),
      });
    }
  });

  it('translates every key to a non-empty string', () => {
    for (const key of Object.keys(en) as TranslationKey[]) {
      expect(dictionaries.en[key].length).toBeGreaterThan(0);
      expect(dictionaries.fa[key].length).toBeGreaterThan(0);
    }
  });

  it('does not leave English chrome untranslated in fa', () => {
    // A handful of values are legitimately identical across locales.
    // Names, endonyms and scientific acronyms are intentionally not translated.
    const allowed = new Set([
      'app.name',
      'locale.english',
      'locale.persian',
      'map.band.ndvi',
      'arena.iou',
    ]);
    const untranslated = (Object.keys(en) as TranslationKey[]).filter(
      (key) =>
        !allowed.has(key) &&
        dictionaries.fa[key] === dictionaries.en[key] &&
        !/\d/.test(dictionaries.en[key]),
    );
    expect(untranslated).toEqual([]);
  });
});

describe('translate', () => {
  it('returns the active locale string', () => {
    expect(translate('en', 'nav.overview')).toBe('Overview');
    expect(translate('fa', 'nav.overview')).toBe('نگاه کلی');
  });

  it('interpolates named parameters', () => {
    expect(translate('en', 'learning.progress', { done: 3, total: 8 })).toBe('3 of 8 reviewed');
    expect(translate('fa', 'overview.seriesHint', { count: 4 })).toContain('4');
  });

  it('leaves unknown placeholders visible rather than printing "undefined"', () => {
    expect(translate('en', 'learning.queueCount', {})).toBe('{count} samples');
  });

  it('falls back to English for a key missing in the active dictionary', () => {
    const dictionary = dictionaries.fa as Record<string, string>;
    const had = 'nav.overview' in dictionary;
    delete dictionary['nav.overview'];
    expect(translate('fa', 'nav.overview')).toBe('Overview');
    if (had) dictionary['nav.overview'] = 'نگاه کلی';
  });
});

describe('locale helpers', () => {
  it('normalises anything to a supported locale', () => {
    expect(isLocale('fa')).toBe(true);
    expect(isLocale('de')).toBe(false);
    expect(normalizeLocale('de')).toBe('en');
    expect(normalizeLocale(null)).toBe('en');
    expect(intlLocale('fa')).toBe('fa-IR');
  });
});

describe('locale-aware formatting', () => {
  const date = '2025-04-14T07:41:00Z';

  it('formats dates per locale in UTC', () => {
    expect(formatDate('en', date)).toContain('Apr');
    expect(formatDate('en', date)).toContain('2025');
    const persian = formatDate('fa', date);
    expect(persian).toMatch(/[\u06F0-\u06F9]/);
  });

  it('uses locale digits for numbers', () => {
    expect(formatNumber('en', 1234.5, 1)).toBe('1,234.5');
    expect(formatNumber('fa', 1234.5, 1)).toMatch(/[\u06F0-\u06F9]/);
    expect(formatNumber('en', null)).toBe('—');
  });

  it('formats percentages from 0..1 fractions', () => {
    expect(formatPercent('en', 0.91234)).toBe('91.2%');
    expect(formatPercent('fa', 0.5)).toMatch(/[\u06F0-\u06F9]/);
    expect(formatPercent('en', Number.NaN)).toBe('—');
  });
});

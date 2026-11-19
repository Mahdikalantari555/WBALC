#!/usr/bin/env node
/**
 * Translation completeness gate.
 *
 * Reads the two dictionaries as text (no bundler needed) and fails when:
 *  - a key exists in one locale but not the other, or
 *  - the two locales disagree on the `{placeholder}` set for a key, or
 *  - a key is defined twice in one file.
 */
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const en = read('../src/lib/i18n/en.ts');
const fa = read('../src/lib/i18n/fa.ts');

const KEY = /^\s*'([a-zA-Z0-9_.-]+)':/gm;

function collect(source, name) {
  const keys = new Map();
  const duplicates = [];
  for (const match of source.matchAll(KEY)) {
    const key = match[1];
    if (keys.has(key)) duplicates.push(key);
    keys.set(key, match.index);
  }
  if (duplicates.length) {
    console.error(`✖ ${name}: duplicate keys -> ${[...new Set(duplicates)].join(', ')}`);
    process.exitCode = 1;
  }
  return keys;
}

function placeholders(source, key) {
  const start = source.indexOf(`'${key}':`);
  if (start < 0) return new Set();
  const next = source.slice(start + 1).search(/^\s*'[a-zA-Z0-9_.-]+':/m);
  const chunk = next < 0 ? source.slice(start) : source.slice(start, start + 1 + next);
  return new Set([...chunk.matchAll(/\{(\w+)\}/g)].map((m) => m[1]));
}

const enKeys = collect(en, 'en.ts');
const faKeys = collect(fa, 'fa.ts');

const missingInFa = [...enKeys.keys()].filter((key) => !faKeys.has(key));
const missingInEn = [...faKeys.keys()].filter((key) => !enKeys.has(key));
if (missingInFa.length) {
  console.error(`✖ ${missingInFa.length} key(s) missing in fa.ts: ${missingInFa.join(', ')}`);
  process.exitCode = 1;
}
if (missingInEn.length) {
  console.error(`✖ ${missingInEn.length} key(s) missing in en.ts: ${missingInEn.join(', ')}`);
  process.exitCode = 1;
}

const placeholderDrift = [];
for (const key of enKeys.keys()) {
  if (!faKeys.has(key)) continue;
  const a = [...placeholders(en, key)].sort().join(',');
  const b = [...placeholders(fa, key)].sort().join(',');
  if (a !== b) placeholderDrift.push(`${key} (en: {${a}} fa: {${b}})`);
}
if (placeholderDrift.length) {
  console.error(`✖ placeholder mismatch: ${placeholderDrift.join('; ')}`);
  process.exitCode = 1;
}

if (!process.exitCode) {
  console.log(`✔ i18n complete: ${enKeys.size} keys in en.ts and fa.ts`);
}

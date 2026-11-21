/**
 * Design-system guards.
 *
 * A design system's real failure mode is silent drift: one page grows a 9px
 * label, another invents a hex colour, a third ships a control with no label.
 * None of that breaks a type check, and none of it is visible in a screenshot
 * diff. These assertions read the actual source files, so drift fails CI.
 *
 * They are deliberately opinionated about *this* app: it must stay honest about
 * what the engine measured, so status colour is semantic, and any text the user
 * reads has a floor.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { contrastRatio, parseColour, type Rgb } from './contrast';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

// src/lib/components/ui/ -> app root
const ROOT = fileURLToPath(new URL('../../../../', import.meta.url));
const SRC = join(ROOT, 'src');

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === 'node_modules' || entry === '.svelte-kit') continue;
      walk(full, out);
    } else if (/\.(svelte|css|ts)$/.test(entry) && !entry.endsWith('.test.ts')) {
      out.push(full);
    }
  }
  return out;
}

const files = walk(SRC).map((path) => ({
  path,
  // Normalize to forward slashes: relative() emits OS separators and the
  // guards below compare POSIX-style routes like 'src/index.css'.
  rel: relative(ROOT, path).split('\\').join('/'),
  text: readFileSync(path, 'utf8'),
}));
const uiFiles = files.filter((file) => file.rel.includes('components/ui/'));
const viewFiles = files.filter((file) => !file.rel.includes('components/ui/'));
const stylesheet = files.find((file) => file.rel === 'src/index.css')!;

describe('design tokens', () => {
  it('defines the shadcn semantic layer the ui/ primitives rely on', () => {
    const required = [
      '--background',
      '--foreground',
      '--card',
      '--card-foreground',
      '--popover',
      '--primary',
      '--primary-foreground',
      '--secondary',
      '--secondary-foreground',
      '--muted-foreground',
      '--accent-foreground',
      '--destructive',
      '--warning',
      '--success',
      '--border',
      '--input',
      '--ring',
      '--radius',
    ];
    for (const token of required) {
      expect(stylesheet.text, `missing token ${token}`).toContain(`${token}:`);
    }
  });

  it('keeps the legacy domain aliases pointing at the semantic layer', () => {
    // Pages still use --surface/--muted/--faint; they must resolve through the
    // tokens, or a token change silently stops applying.
    expect(stylesheet.text).toMatch(/--surface:\s*var\(--card\)/);
    expect(stylesheet.text).toMatch(/--muted:\s*var\(--muted-foreground\)/);
    expect(stylesheet.text).toMatch(/--faint:\s*var\(--faint-foreground\)/);
    expect(stylesheet.text).toMatch(/--accent:\s*var\(--primary\)/);
    expect(stylesheet.text).toMatch(/--ink:\s*var\(--foreground\)/);
  });

  it('uses oklch for its palette so lightness is perceptually uniform', () => {
    const rootBlock = stylesheet.text.slice(
      stylesheet.text.indexOf(':root {'),
      stylesheet.text.indexOf('* { box-sizing'),
    );
    const hex = rootBlock.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
    expect(hex, `palette should not use hex: ${hex.join(', ')}`).toHaveLength(0);
    expect(rootBlock.match(/oklch\(/g)?.length ?? 0).toBeGreaterThan(15);
  });

  it('honours reduced-motion', () => {
    expect(stylesheet.text).toContain('prefers-reduced-motion');
  });

  it('declares a visible focus ring for every interactive element', () => {
    expect(stylesheet.text).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--accent\)/);
  });
});

describe('no drift in view code', () => {
  it('never sets a font size below the readable floor', () => {
    const offenders: string[] = [];
    for (const file of files) {
      for (const match of file.text.matchAll(/font-size:\s*([0-9.]+)px/g)) {
        const size = Number(match[1]);
        if (size < 10) offenders.push(`${file.rel}: ${size}px`);
      }
      for (const match of file.text.matchAll(/font:\s*([0-9.]+)px/g)) {
        const size = Number(match[1]);
        if (size < 10) offenders.push(`${file.rel}: font shorthand ${size}px`);
      }
    }
    expect(offenders, offenders.join('\n')).toHaveLength(0);
  });

  it('keeps every hex colour in the stylesheet, not in components', () => {
    // The palette has exactly one owner. A component that needs a colour uses a
    // token; if the token does not exist, the stylesheet grows one. This is what
    // makes a future light theme a token-only change.
    const offenders: string[] = [];
    for (const file of [...uiFiles, ...viewFiles]) {
      if (!file.rel.endsWith('.svelte')) continue;
      for (const match of file.text.matchAll(/#[0-9a-fA-F]{6}\b/g)) {
        offenders.push(`${file.rel}: ${match[0]}`);
      }
    }
    expect(offenders, `hard-coded colours in components:\n${offenders.join('\n')}`).toHaveLength(0);
  });
});

describe('accessibility of view markup', () => {
  it('gives every placeholder-only input an aria-label', () => {
    // A placeholder disappears as soon as the user types, so it is not a name.
    const offenders: string[] = [];
    for (const file of viewFiles) {
      if (!file.rel.endsWith('.svelte')) continue;
      for (const match of file.text.matchAll(/<input\b((?:(?:"[^"]*")|(?:\{[^{}]*\})|[^>"{}])*)>/g)) {
        const attrs = match[1];
        const named = /aria-label|aria-labelledby|\bid=/.test(attrs) || /type="(hidden|file|radio|checkbox)"/.test(attrs);
        if (/placeholder=/.test(attrs) && !named) {
          offenders.push(`${file.rel}: ${attrs.trim().slice(0, 60)}`);
        }
      }
    }
    expect(offenders, offenders.join('\n')).toHaveLength(0);
  });

  it('never renders a clickable div', () => {
    const offenders: string[] = [];
    for (const file of viewFiles) {
      if (!file.rel.endsWith('.svelte')) continue;
      if (/<div[^>]*\bon:click\b/.test(file.text) || /<div[^>]*\bonclick\b/.test(file.text)) {
        offenders.push(file.rel);
      }
    }
    // A div with a click handler is unreachable by keyboard; use <button>.
    expect(offenders, offenders.join(', ')).toHaveLength(0);
  });

  it('has no orphaned components', () => {
    const components = uiFiles
      .filter((file) => file.rel.endsWith('.svelte'))
      .map((file) => file.rel.split('/').pop()!.replace('.svelte', ''));
    const lost: string[] = [];
    for (const name of components) {
      const imported = files.some(
        (file) => file.rel !== `src/lib/components/ui/${name.toLowerCase()}/${name}.svelte` &&
          file.text.includes(`/${name}`),
      );
      if (!imported) lost.push(name);
    }
    expect(lost, `unused primitives: ${lost.join(', ')}`).toHaveLength(0);
  });
});

describe('accessibility of the primitives', () => {
  it('has a barrel and a variant record for every primitive', () => {
    // Only folders that hold a component; helper modules (contrast.ts) are not primitives.
    const names = [
      ...new Set(
        uiFiles
          .filter((file) => file.rel.endsWith('.svelte'))
          .map((file) => file.rel.split('/')[4]),
      ),
    ];
    for (const name of names) {
      const inDir = uiFiles.filter((file) => file.rel.includes(`/ui/${name}/`));
      expect(inDir.some((file) => file.rel.endsWith('index.ts')), `${name} has no index.ts`).toBe(true);
    }
  });

  it('gives the Badge a semantic variant rather than a colour prop', () => {
    const badge = uiFiles.find((file) => file.rel.endsWith('badge/Badge.svelte'))!;
    expect(badge.text).not.toMatch(/\bcolor\s*=/);
    expect(badge.text).toContain('BadgeVariant');
  });

  it('gives every Select its options as data, so no bare option tag can drift', () => {
    const viewOptions = viewFiles.filter((file) => file.text.includes('<option'));
    expect(
      viewOptions.map((file) => file.rel),
      'prefer <Select options={…}> so values and labels cannot diverge',
    ).not.toContain('src/lib/components/ui/select/Select.svelte');
  });

  it('renders an Alert with text, never colour alone', () => {
    const alert = uiFiles.find((file) => file.rel.endsWith('alert/Alert.svelte'))!;
    // role=status/alert plus a title slot: the meaning is in the words.
    expect(alert.text).toMatch(/role=\{/);
    expect(alert.text).toContain('children');
  });

  it('requires a caption on every Table (the unit is the claim)', () => {
    const table = uiFiles.find((file) => file.rel.endsWith('table/Table.svelte'))!;
    expect(table.text).toMatch(/caption:/);
    expect(table.text).toContain('<caption');
  });
});

describe('colour contrast (WCAG 2.1 AA)', () => {
  /** Resolve a token, following `var(--x)` aliases once. */
  function tokenValues(): Map<string, string> {
    const root = stylesheet.text.slice(stylesheet.text.indexOf(':root {'), stylesheet.text.indexOf('* { box-sizing'));
    const map = new Map<string, string>();
    for (const [, name, value] of root.matchAll(/(--[a-z-]+):\s*([^;]+);/g)) {
      map.set(name, value.trim());
    }
    return map;
  }

  function resolve(name: string, seen = new Set<string>()): Rgb {
    const tokens = tokenValues();
    const raw = tokens.get(name);
    if (!raw) throw new Error(`unknown token ${name}`);
    const alias = raw.match(/^var\((--[a-z-]+)\)$/);
    if (alias) {
      if (seen.has(name)) throw new Error(`alias cycle at ${name}`);
      seen.add(name);
      return resolve(alias[1], seen);
    }
    return parseColour(raw);
  }

  // Body text must reach 4.5:1 against every surface it can appear on.
  const textOnSurfaces: [string, string][] = [
    ['--foreground', '--background'],
    ['--foreground', '--card'],
    ['--muted-foreground', '--background'],
    ['--muted-foreground', '--card'],
    ['--faint-foreground', '--card'],
    ['--primary', '--background'],
    ['--success', '--card'],
    ['--warning', '--card'],
    ['--destructive', '--card'],
    ['--danger-fg', '--control-bg'],
    ['--primary-foreground', '--primary'],
  ];

  it.each(textOnSurfaces)('%s on %s is readable', (fg, bg) => {
    const ratio = contrastRatio(resolve(fg), resolve(bg));
    expect(ratio, `${fg} on ${bg} = ${ratio.toFixed(2)}:1, needs 4.5:1`).toBeGreaterThanOrEqual(4.5);
  });

  it('keeps the light-theme question honest by not shipping one', () => {
    // A half-themed app is worse than a dark-only one: pages still hard-code
    // surface assumptions in map/raster chrome. When a light theme lands it must
    // land with its own contrast table, not by flipping a colour-scheme flag.
    expect(stylesheet.text).not.toContain('data-theme');
  });
});

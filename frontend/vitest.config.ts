import path from 'node:path';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

/**
 * Vitest runs the adapter and geo/i18n modules outside SvelteKit's dev server, so
 * it needs the same `$lib` alias and a stub for `$env/dynamic/private`.
 */
export default defineConfig({
  resolve: {
    // jsdom component tests must use Svelte's client build, not the SSR one.
    conditions: ['browser'],
    alias: {
      $lib: path.resolve(import.meta.dirname, 'src/lib'),
      '$env/dynamic/private': path.resolve(import.meta.dirname, 'src/lib/test/env-stub.ts'),
    },
  },
  // Component tests need Svelte compilation; plain modules do not care.
  plugins: [svelte({ hot: false })],
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
    environmentMatchGlobs: [['src/**/*.dom.test.ts', 'jsdom']],
    // jsdom under vitest can miss localStorage; install a fallback before tests.
    setupFiles: ['src/lib/test/local-storage.ts'],
    globals: false,
  },
});

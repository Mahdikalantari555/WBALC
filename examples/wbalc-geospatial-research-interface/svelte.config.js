import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/**
 * The example runs against a live backend, so it is built as a Node server:
 * the adapter route handlers in `src/routes/api/**` need a runtime that can
 * reach RSAL_API_URL (a static export cannot).
 */
/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({ out: 'build' }),
    files: { assets: 'public' },
    alias: {
      $lib: 'src/lib',
    },
    // The app is same-origin: it posts only to its own /api routes.
    csrf: { trustedOrigins: [] },
  },
};

export default config;

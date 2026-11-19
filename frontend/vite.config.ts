import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    // Bind all interfaces so the sandboxed preview proxy can reach the dev server.
    host: '0.0.0.0',
    port: Number(process.env.PORT ?? 5173),
    strictPort: false,
    // The preview host is served through a proxy; allow it explicitly.
    allowedHosts: true,
    fs: { allow: ['.'] },
  },
  preview: { host: '0.0.0.0', allowedHosts: true },
});

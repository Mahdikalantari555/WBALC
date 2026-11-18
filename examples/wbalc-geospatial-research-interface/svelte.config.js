import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
export default {
  kit: {
    adapter: adapter(),
    files: { assets: 'public' },
    prerender: {
      handleMissingId: ({ id, message }) => {
        // The workspace uses hash navigation so deep links work on a static host.
        if (!/^\/(map|overview|temporal|learning|arena|evaluation)$/.test(id)) throw new Error(message);
      },
    },
  },
};
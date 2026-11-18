// The workspace is a live client application: it fetches from the adapter after
// mount, so server-side prerendering of its data would only add a second request.
export const ssr = true;
export const csr = true;

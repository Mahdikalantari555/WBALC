/**
 * Storage guard for test environments.
 *
 * Under vitest the jsdom environment does not always expose `localStorage`
 * (sessionStorage arrives, localStorage does not), and the drafts module
 * degrades silently when storage throws — every read returns null and the
 * tests would fail forever without touching a real bug. Install a Map-backed
 * implementation whenever the environment lacks one.
 */
if (typeof globalThis.localStorage === 'undefined') {
  const store = new Map<string, string>();
  const storage = {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.has(key) ? (store.get(key) as string) : null;
    },
    key(index: number) {
      return [...store.keys()][index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, String(value));
    },
  } as unknown as Storage;
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true });
}

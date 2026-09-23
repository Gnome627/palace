/* Per-browser settings in localStorage, under "palace.*". Private mode or blocked storage: the defaults, silently. */
export const store = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem("palace." + key);
      return v === null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem("palace." + key, JSON.stringify(value));
    } catch { /* private mode */ }
  },
};

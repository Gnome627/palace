/* Every word the page shows comes from locales/<id>.json; nothing user-facing is written in the code.
 *
 *   t("card.hide")                          → "Hide"
 *   t("failure.title", { verb, name })      → "Couldn't turn off “Night light”"   ({placeholders} are filled in)
 *   has("class.co2")                        → whether the current locale (or the fallback) knows the key
 *
 * Markup is translated by attributes: data-i18n (text), data-i18n-title (title), data-i18n-label (aria-label).
 * A key missing from the chosen locale falls back to FALLBACK, then to the key itself — visible, never blank.
 */
import { store } from "./store.js";

export const LOCALES = ["ru", "en-US"];
const FALLBACK = "en-US";

const dicts = {};                    // locale id → the parsed JSON
let current = FALLBACK;
const listeners = [];

function lookup(dict, key) {
  let node = dict;
  for (const part of key.split(".")) {
    if (node === null || typeof node !== "object" || !(part in node)) return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

export function has(key) {
  return lookup(dicts[current] || {}, key) !== undefined || lookup(dicts[FALLBACK] || {}, key) !== undefined;
}

export function t(key, params = {}) {
  const text = lookup(dicts[current] || {}, key) ?? lookup(dicts[FALLBACK] || {}, key) ?? key;
  return text.replace(/\{(\w+)\}/g, (whole, name) => (name in params ? String(params[name]) : whole));
}

/** A word from a given locale, not the current one — the language switcher names each language in itself. */
export const tIn = (id, key) => lookup(dicts[id] || {}, key) ?? key;

/** `t(key)` when the locale has it, else `fallback` — for words keyed by what HA sends (device classes, states). */
export const tOr = (key, fallback) => (has(key) ? t(key) : fallback);

export const locale = () => current;

/** The stored choice, else the first of the browser's languages we have, else the fallback. */
function preferred() {
  const stored = store.get("locale", null);
  if (LOCALES.includes(stored)) return stored;
  for (const lang of navigator.languages || [navigator.language]) {
    const hit = LOCALES.find((id) => id.toLowerCase() === lang.toLowerCase())
             || LOCALES.find((id) => id.split("-")[0] === lang.toLowerCase().split("-")[0]);
    if (hit) return hit;
  }
  return FALLBACK;
}

/** Load every locale (they are small; the switcher shows each one's own name) and pick the preferred one. */
export async function initI18n() {
  await Promise.all(LOCALES.map(async (id) => {
    try {
      dicts[id] = await (await fetch(`locales/${id}.json`)).json();
    } catch (err) {
      console.warn("locale", id, err.message);
    }
  }));
  apply(preferred());
}

export function setLocale(id) {
  if (!LOCALES.includes(id) || id === current) return;
  store.set("locale", id);
  apply(id);
  for (const fn of listeners) fn(id);
}

export function onLocaleChange(fn) { listeners.push(fn); }

function apply(id) {
  current = dicts[id] ? id : FALLBACK;
  document.documentElement.lang = current;
  translate(document);
}

export function translate(root) {
  for (const el of root.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of root.querySelectorAll("[data-i18n-title]")) el.title = t(el.dataset.i18nTitle);
  for (const el of root.querySelectorAll("[data-i18n-label]")) el.setAttribute("aria-label", t(el.dataset.i18nLabel));
}

/* What the page holds, and the questions asked of it.
 *
 * `house` — what the server last said (areas, cards, counters). `layout` — what the user arranged (map positions,
 * order, icons, hidden flags); edited in memory, `dirty` until saved as palace.yaml.
 */
import { hasIcon } from "./dom.js";
import { store } from "./store.js";

export const NONE = "__none__";      // the pseudo-area for cards without one, always last

export const state = {
  house: { areas: [], cards: [], version: 0, readings: 0 },
  layout: { areas: [], cards: {}, devices: {} },
  flags: { names: store.get("names", true), hidden: store.get("hidden", false) },
  dirty: false,
  confirmTimeout: 10,                // s, the server's CONFIRM_TIMEOUT (from /api/events)
};

export const busy = new Set();       // card ids with an action under way
export const failed = new Map();     // card id → "failed" | "unconfirmed", for a few seconds after a failure

const dirtyListeners = [];
export function onDirtyChange(fn) { dirtyListeners.push(fn); }
export function setDirty(value) {
  state.dirty = value;
  for (const fn of dirtyListeners) fn(value);
}

// ---- cards

export const cardById = (id) => state.house.cards.find((c) => c.id === id);
export const cardOfEntity = (entityId) => state.house.cards.find((c) => c.entities.some((e) => e.entity_id === entityId));

const hasArea = (c) => Boolean(c.area_id) && state.house.areas.some((a) => a.id === c.area_id);

// ---- the layout

/** The layout entry of a card, created on first touch. */
export const placed = (id) => (state.layout.devices[id] ||= {});
export const isHidden = (id) => Boolean(state.layout.devices[id]?.hidden);

/** By hand → what HA shows (if we have the glyph) → by domain and class. */
export function iconOf(card) {
  return [state.layout.devices[card.id]?.icon, card.ha_icon, card.icon].find(hasIcon) || "cog";
}

/** Areas in the user's order; new ones after; the NONE pseudo-area (no name: the view words it) last, if any card needs it. */
export function orderedAreas() {
  const known = new Map(state.house.areas.map((a) => [a.id, a]));
  const out = [];
  for (const id of state.layout.areas) {
    if (known.has(id)) { out.push(known.get(id)); known.delete(id); }
  }
  out.push(...known.values());
  if (state.house.cards.some((c) => !hasArea(c))) out.push({ id: NONE, name: null });
  return out;
}

/** The cards of an area in the user's order; new ones after. */
export function cardsOf(areaId) {
  const inArea = (c) => (areaId === NONE ? !hasArea(c) : c.area_id === areaId);
  const pool = new Map(state.house.cards.filter(inArea).map((c) => [c.id, c]));
  const out = [];
  for (const id of state.layout.cards[areaId] || []) {
    if (pool.has(id)) { out.push(pool.get(id)); pool.delete(id); }
  }
  return [...out, ...pool.values()];
}

/** Cards the file has never placed get a spot in a grid across the map; more cards than the grid holds —
 *  more columns, so nothing lands outside the map or on top of another. */
export function placeNew(width, height) {
  const fresh = state.house.cards.filter((c) => state.layout.devices[c.id]?.x === undefined);
  if (!fresh.length) return;
  const rows = Math.max(3, Math.floor((height - 40) / 96));
  const cols = Math.max(3, Math.floor((width - 40) / 110), Math.ceil(state.house.cards.length / rows));
  const cellOf = (x, y) => Math.round(x * cols - 0.5) + ":" + Math.round(y * rows - 0.5);
  const taken = new Set(Object.values(state.layout.devices).filter((d) => d.x !== undefined).map((d) => cellOf(d.x, d.y)));
  let i = 0;
  for (const c of fresh) {
    while (taken.has((i % cols) + ":" + Math.floor(i / cols)) && i < cols * rows) i++;
    const col = i % cols, row = Math.floor(i / cols);
    taken.add(col + ":" + row);
    Object.assign(placed(c.id), { x: round4((col + 0.5) / cols), y: round4((row + 0.5) / rows) });
    i++;
  }
}

export const round4 = (v) => +v.toFixed(4);

/** What gets written: the full current order and every position, so the file describes the whole picture. */
export function layoutToSave() {
  const areas = orderedAreas().map((a) => a.id).filter((id) => id !== NONE);
  const cards = Object.fromEntries(orderedAreas().map((a) => [a.id, cardsOf(a.id).map((c) => c.id)]));
  const devices = {};
  for (const c of state.house.cards) {
    const d = state.layout.devices[c.id];
    if (d && (d.x !== undefined || d.icon || d.hidden)) devices[c.id] = d;
  }
  return { areas, cards, devices };
}

/* Reordering cards inside an area and areas among themselves: drag by the header.
 *
 * Pointer events, not HTML5 drag-and-drop — that one does not exist for a finger. A mouse lifts the item after a few
 * pixels of travel; a finger holds it for a moment first, so a swipe over a header still scrolls. While lifted, a
 * ghost copy follows the pointer, the original fades, the drop target gets a brass bar; near the edge of the list
 * it scrolls by itself. A drop rewrites the order in the layout and calls `onDrop`.
 */
import { cardsOf, NONE, orderedAreas, setDirty, state } from "./state.js";

const HOLD_MS = 320;                 // a finger lifts after holding this long
const LIFT_PX = 4;                   // a mouse lifts after this much travel
const EDGE_PX = 48;                  // this close to the list's edge, it scrolls
const SCROLL_STEP = 8;               // px per frame

let dnd = null;

export const reordering = () => Boolean(dnd?.lifted);

export function initReorder(rooms, { onDrop }) {
  rooms.addEventListener("pointerdown", (e) => {
    const head = e.target.closest(".card-head, .area-head");
    if (!head || e.button !== 0 || e.target.closest("button")) return;
    const item = head.parentElement;
    const kind = item.classList.contains("card") ? "card" : "area";
    if (kind === "area" && item.dataset.area === NONE) return;
    dnd = {
      kind, item, head, area: item.closest(".area")?.dataset.area, pointer: e.pointerId,
      sx: e.clientX, sy: e.clientY, lifted: false, timer: null, target: null, scroll: 0,
    };
    if (e.pointerType !== "mouse") {
      dnd.timer = setTimeout(() => { if (dnd && !dnd.lifted) lift(rooms, e.clientX, e.clientY); }, HOLD_MS);
    }
  });

  document.addEventListener("pointermove", (e) => {
    if (!dnd || e.pointerId !== dnd.pointer) return;
    if (!dnd.lifted) {
      if (Math.hypot(e.clientX - dnd.sx, e.clientY - dnd.sy) < LIFT_PX) return;
      if (e.pointerType !== "mouse") { cancel(); return; }   // a swipe before the hold: let it scroll
      lift(rooms, e.clientX, e.clientY);
    }
    dnd.ghost.style.left = e.clientX - dnd.dx + "px";
    dnd.ghost.style.top = e.clientY - dnd.dy + "px";
    const box = rooms.getBoundingClientRect();
    dnd.scroll = e.clientY < box.top + EDGE_PX ? -SCROLL_STEP : e.clientY > box.bottom - EDGE_PX ? SCROLL_STEP : 0;
    clearMarks(rooms);
    dnd.target = dropTarget(e.clientX, e.clientY);
    if (dnd.target) dnd.target.el.classList.add(dnd.target.before ? "drop-before" : "drop-after");
  });

  const end = (e) => {
    if (!dnd || e.pointerId !== dnd.pointer) return;
    const d = dnd;
    cancel();
    if (!d.lifted) return;
    d.ghost.remove();
    d.item.classList.remove("dragging");
    clearMarks(rooms);
    if (e.type === "pointerup" && d.target) {
      drop(d);
      setDirty(true);
      onDrop();
    }
  };
  document.addEventListener("pointerup", end);
  document.addEventListener("pointercancel", end);
  // once lifted, the finger moves the card, not the page
  document.addEventListener("touchmove", (e) => { if (dnd?.lifted) e.preventDefault(); }, { passive: false });
  // a long press must not open the context menu
  rooms.addEventListener("contextmenu", (e) => { if (dnd) e.preventDefault(); });
}

function cancel() {
  if (dnd) clearTimeout(dnd.timer);
  dnd = null;
}

function lift(rooms, x, y) {
  const d = dnd;
  d.lifted = true;
  try { d.head.setPointerCapture(d.pointer); } catch { /* the pointer may already be gone */ }
  const r = d.item.getBoundingClientRect();
  d.dx = x - r.left;
  d.dy = y - r.top;
  d.ghost = d.item.cloneNode(true);
  d.ghost.className = d.item.className + " ghost-drag";
  Object.assign(d.ghost.style, { width: r.width + "px", left: r.left + "px", top: r.top + "px" });
  document.body.appendChild(d.ghost);
  d.item.classList.add("dragging");
  const tick = () => {
    if (dnd !== d) return;
    if (d.scroll) rooms.scrollBy(0, d.scroll);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function dropTarget(x, y) {
  const under = document.elementFromPoint(x, y);
  if (!under) return null;
  if (dnd.kind === "card") {
    const target = under.closest(".card");
    if (!target || target === dnd.item || target.closest(".area").dataset.area !== dnd.area) return null;
    const r = target.getBoundingClientRect(), grid = target.parentElement.getBoundingClientRect();
    // one card per row (a phone): before/after by height; a grid: by width
    const column = r.width > grid.width * 0.7;
    return { el: target, before: column ? y < r.top + r.height / 2 : x < r.left + r.width / 2 };
  }
  const target = under.closest(".area");
  if (!target || target === dnd.item || target.dataset.area === NONE) return null;
  const r = target.getBoundingClientRect();
  return { el: target, before: y < r.top + r.height / 2 };
}

function drop(d) {
  const at = (ids, id) => ids.indexOf(id) + (d.target.before ? 0 : 1);
  if (d.kind === "card") {
    const moved = d.item.dataset.id;
    const ids = cardsOf(d.area).map((c) => c.id).filter((id) => id !== moved);
    ids.splice(at(ids, d.target.el.dataset.id), 0, moved);
    state.layout.cards[d.area] = ids;
  } else {
    const moved = d.item.dataset.area;
    const ids = orderedAreas().map((a) => a.id).filter((id) => id !== NONE && id !== moved);
    ids.splice(at(ids, d.target.el.dataset.area), 0, moved);
    state.layout.areas = ids;
  }
}

function clearMarks(rooms) {
  for (const x of rooms.querySelectorAll(".drop-before, .drop-after")) x.classList.remove("drop-before", "drop-after");
}

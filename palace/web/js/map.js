/* The map: a node per card at its layout position. Dragging a node moves it (the layout gets dirty);
 * a press that does not travel is a click — `onToggle(id)`. */
import { el, icon } from "./dom.js";
import { t } from "./i18n.js";
import { busy, failed, iconOf, isHidden, placed, round4, setDirty, state } from "./state.js";

const CLICK_PX = 4;                  // travel below this is a click, not a drag

let drag = null;

export const dragging = () => drag !== null;

export function renderMap(map) {
  map.replaceChildren();
  map.classList.toggle("names", state.flags.names);
  const shown = state.house.cards.filter((c) => state.flags.hidden || !isHidden(c.id));
  for (const c of shown) map.appendChild(node(c));
  if (!shown.length) map.appendChild(el("div", "empty", t(state.house.cards.length ? "map.all_hidden" : "map.empty")));
}

function node(c) {
  const d = state.layout.devices[c.id];
  const n = el("div", "node");
  n.dataset.id = c.id;
  n.style.left = d.x * 100 + "%";
  n.style.top = d.y * 100 + "%";
  if (!c.available) {
    n.classList.add("unavailable");
    n.title = t("card.unavailable");
  } else if (c.on === null) {
    n.classList.add("inert");
  } else if (c.on) {
    n.classList.add("on");
  }
  if (isHidden(c.id)) n.classList.add("ghost");
  if (busy.has(c.id)) n.classList.add("busy");
  if (failed.has(c.id)) n.classList.add(failed.get(c.id));
  const name = el("span", "name", c.name);
  name.title = c.name;
  n.append(icon(iconOf(c)), name);
  return n;
}

export function initMap(map, { onToggle }) {
  map.addEventListener("pointerdown", (e) => {
    const n = e.target.closest(".node");
    if (!n || e.button !== 0) return;
    const at = placed(n.dataset.id);
    drag = { n, id: n.dataset.id, sx: e.clientX, sy: e.clientY, x0: at.x, y0: at.y, moved: false, to: null };
    n.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  map.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (!drag.moved && Math.hypot(dx, dy) < CLICK_PX) return;
    drag.moved = true;
    drag.n.classList.add("dragging");
    const r = map.getBoundingClientRect();
    const x = clamp01(drag.x0 + dx / r.width), y = clamp01(drag.y0 + dy / r.height);
    drag.n.style.left = x * 100 + "%";
    drag.n.style.top = y * 100 + "%";
    drag.to = { x, y };
  });

  const end = (e) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    d.n.classList.remove("dragging");
    if (d.moved && d.to) {
      Object.assign(placed(d.id), { x: round4(d.to.x), y: round4(d.to.y) });
      setDirty(true);
    } else if (!d.moved && e.type === "pointerup") {
      onToggle(d.id);
    }
  };
  map.addEventListener("pointerup", end);
  map.addEventListener("pointercancel", end);
}

const clamp01 = (v) => Math.min(1, Math.max(0, v));

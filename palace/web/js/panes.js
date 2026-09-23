/* The two panes. Wide screens: map and list side by side, the splitter between them sets the map's share.
 * Phones: one pane at a time, picked from the tab bar at the bottom (CSS ignores the tabs on wide screens). */
import { $, icon } from "./dom.js";
import { store } from "./store.js";

const MIN_PANE = 260;                // px: a card still fits, a map still has room

let panes = null;

export function initPanes() {
  panes = document.querySelector(".panes");
  initTabs();
  initSplitter();
}

function initTabs() {
  for (const b of document.querySelectorAll(".tab[data-icon]")) b.prepend(icon(b.dataset.icon));
  $("tabs").addEventListener("click", (e) => {
    const b = e.target.closest(".tab");
    if (b) showTab(b.dataset.tab);
  });
  showTab(store.get("tab", "map"));
}

function showTab(name) {
  panes.dataset.tab = name;
  for (const b of document.querySelectorAll(".tab")) b.classList.toggle("active", b.dataset.tab === name);
  store.set("tab", name);
}

function setSplit(frac) {
  const w = panes.clientWidth || 1200;
  const clamped = Math.min(1 - MIN_PANE / w, Math.max(MIN_PANE / w, frac));
  panes.style.setProperty("--split", (clamped * 100).toFixed(2) + "%");
  store.set("split", clamped);
}

function initSplitter() {
  const splitter = $("splitter");
  setSplit(+store.get("split", 0.5) || 0.5);
  let pointer = null;
  splitter.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    pointer = e.pointerId;
    splitter.setPointerCapture(pointer);
    splitter.classList.add("active");
    panes.classList.add("resizing");
    e.preventDefault();
  });
  splitter.addEventListener("pointermove", (e) => {
    if (e.pointerId !== pointer) return;
    const r = panes.getBoundingClientRect();
    setSplit((e.clientX - r.left) / r.width);
  });
  const end = (e) => {
    if (e.pointerId !== pointer) return;
    pointer = null;
    splitter.classList.remove("active");
    panes.classList.remove("resizing");
  };
  splitter.addEventListener("pointerup", end);
  splitter.addEventListener("pointercancel", end);
  splitter.addEventListener("dblclick", () => setSplit(0.5));
}

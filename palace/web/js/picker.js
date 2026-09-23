/* The icon picker: a grid of MDI_PICK icons next to a card's icon. Picking the card's own default icon removes
 * the override; `onPick` is called after the layout changed. */
import { el, icon } from "./dom.js";
import { cardById, iconOf, placed, setDirty } from "./state.js";

const WIDTH = 292, MAX_HEIGHT = 300, GAP = 6, MARGIN = 8;   // px, as in the CSS

let picker = null;
let openFor = null;

export const pickerOpen = () => openFor !== null;

export function initPicker(element, { onPick }) {
  picker = element;
  picker.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-icon]");
    if (!b || !openFor) return;
    const card = cardById(openFor);
    const entry = placed(openFor);
    if (b.dataset.icon === card.icon) delete entry.icon;
    else entry.icon = b.dataset.icon;
    setDirty(true);
    closePicker();
    onPick();
  });
  document.addEventListener("pointerdown", (e) => {
    if (pickerOpen() && !picker.contains(e.target) && !e.target.closest(".ico")) closePicker();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePicker(); });
}

export function togglePicker(id, anchor) {
  if (openFor === id) { closePicker(); return; }
  openFor = id;
  const current = iconOf(cardById(id));
  picker.replaceChildren(...window.MDI_PICK.map((name) => {
    const b = el("button", name === current ? "current" : "");
    b.dataset.icon = name;
    b.title = name;
    b.appendChild(icon(name));
    return b;
  }));
  picker.hidden = false;
  const r = anchor.getBoundingClientRect(), height = Math.min(MAX_HEIGHT, picker.scrollHeight);
  picker.style.left = Math.max(MARGIN, Math.min(innerWidth - WIDTH - MARGIN, r.left)) + "px";
  picker.style.top = (r.bottom + height + 2 * GAP < innerHeight ? r.bottom + GAP : Math.max(MARGIN, r.top - height - GAP)) + "px";
}

export function closePicker() {
  if (picker) picker.hidden = true;
  openFor = null;
}

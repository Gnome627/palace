/* Dropdowns in the page's own look, the same in Chromium and Gecko: a button that shows the choice, and one list
 * (#dropdown) that opens under whichever button was pressed — fixed, like the icon picker, so no card clips it.
 *
 * `dropdown(options, current, onChange)` makes the button; options are [value, text, title?]. `onChange(value)` is
 * called on a pick by the user; `setChoice(button, value)` shows another choice without calling it.
 * Keys: ↓/↑ open the list; in it ↓/↑, Home/End, a letter to jump, Enter or Space to pick, Esc or Tab to leave.
 */
import { el, icon } from "./dom.js";

const GAP = 4, MARGIN = 8;           // px: between the button and the list; the list and the window edge

const specs = new WeakMap();         // button → { options, onChange }
let list = null;
let openFor = null;                  // the button whose list is open
let active = -1;                     // the option under the keyboard or the mouse

export const dropdownOpen = () => openFor !== null;

export function initDropdown(element) {
  list = element;
  list.tabIndex = -1;
  list.addEventListener("pointermove", (e) => {
    const o = e.target.closest("[role=option]");
    if (o) highlight(+o.dataset.i, false);
  });
  list.addEventListener("click", (e) => {
    const o = e.target.closest("[role=option]");
    if (o) pick(+o.dataset.i);
  });
  list.addEventListener("keydown", keys);
  document.addEventListener("pointerdown", (e) => {
    if (openFor && !list.contains(e.target) && !openFor.contains(e.target)) closeDropdown();
  });
  // the list is placed once, by its button: anything that moves the button closes it
  addEventListener("resize", () => closeDropdown());
  document.addEventListener("scroll", (e) => { if (e.target !== list) closeDropdown(); }, true);
}

export function dropdown(options, current, onChange, button = el("button")) {
  button.type = "button";
  button.classList.add("dropdown");
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", "false");
  button.replaceChildren(el("span", "choice"), icon("chevron-down"));
  specs.set(button, { options, onChange });
  setChoice(button, current);
  button.addEventListener("click", () => (openFor === button ? closeDropdown() : openList(button)));
  button.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); openList(button); }
  });
  return button;
}

/** Show `value` as the choice; a value that is not among the options (an effect of none) shows as a dash. */
export function setChoice(button, value) {
  const found = specs.get(button).options.find(([v]) => v === value);
  button.dataset.value = value ?? "";
  button.querySelector(".choice").textContent = found ? found[1] : "—";
}

export function closeDropdown(refocus = false) {
  if (!openFor) return;
  const button = openFor;
  openFor = null;
  active = -1;
  list.hidden = true;
  button.setAttribute("aria-expanded", "false");
  if (refocus) button.focus({ preventScroll: true });
}

function openList(button) {
  closeDropdown();
  const { options } = specs.get(button);
  openFor = button;
  button.setAttribute("aria-expanded", "true");
  list.replaceChildren(...options.map(([value, text, title], i) => {
    const o = el("div", "", text);
    Object.assign(o.dataset, { i, value });
    o.id = `dropdown-${i}`;
    o.setAttribute("role", "option");
    o.setAttribute("aria-selected", value === button.dataset.value);
    if (title) o.title = title;
    return o;
  }));
  if (button.hasAttribute("aria-label")) list.setAttribute("aria-label", button.getAttribute("aria-label"));
  else list.removeAttribute("aria-label");
  // the list speaks in its button's type: serif in a card, mono in the ribbon
  const s = getComputedStyle(button);
  Object.assign(list.style, { fontFamily: s.fontFamily, fontSize: s.fontSize, letterSpacing: s.letterSpacing });
  list.hidden = false;
  place(button);
  highlight(Math.max(0, options.findIndex(([v]) => v === button.dataset.value)));
  list.focus({ preventScroll: true });
}

/** Under the button, right edges together; above it when there is no room below. */
function place(button) {
  const r = button.getBoundingClientRect();
  list.style.minWidth = r.width + "px";
  const w = list.offsetWidth, h = list.offsetHeight;
  list.style.left = Math.max(MARGIN, Math.min(innerWidth - w - MARGIN, r.right - w)) + "px";
  list.style.top = (r.bottom + GAP + h + MARGIN <= innerHeight ? r.bottom + GAP : Math.max(MARGIN, r.top - GAP - h)) + "px";
}

function highlight(i, scroll = true) {
  const items = list.children;
  if (!items.length) return;
  active = Math.max(0, Math.min(items.length - 1, i));
  for (const o of items) o.classList.toggle("active", +o.dataset.i === active);
  list.setAttribute("aria-activedescendant", items[active].id);
  if (scroll) items[active].scrollIntoView({ block: "nearest" });
}

function pick(i) {
  const button = openFor, { options, onChange } = specs.get(button);
  closeDropdown(true);
  const [value] = options[i];
  if (value === button.dataset.value) return;
  setChoice(button, value);
  onChange(value);
}

function keys(e) {
  const last = list.children.length - 1;
  switch (e.key) {
    case "ArrowDown": highlight(active + 1); break;
    case "ArrowUp": highlight(active - 1); break;
    case "Home": highlight(0); break;
    case "End": highlight(last); break;
    case "Enter": case " ": pick(active); break;
    case "Escape": closeDropdown(true); break;
    case "Tab": closeDropdown(true); return;   // the browser moves on from the button
    default: {
      if (e.key.length !== 1 || e.ctrlKey || e.metaKey || e.altKey) return;
      // a letter: the next option that starts with it, round from the one after the active
      const texts = [...list.children].map((o) => o.textContent.toLocaleLowerCase());
      const key = e.key.toLocaleLowerCase();
      for (let step = 1; step <= texts.length; step++) {
        const i = (active + step) % texts.length;
        if (texts[i].startsWith(key)) { highlight(i); break; }
      }
    }
  }
  e.preventDefault();
}

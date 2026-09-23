/* Notes in the corner: a title, a line, optionally small print. A click dismisses one; they leave by themselves. */
import { el } from "./dom.js";

const KEEP_MS = 8000;
const MAX_SHOWN = 4;

let box = null;

export function initToasts(element) { box = element; }

export function toast(kind, title, text, smallPrint = "") {
  const note = el("div", "toast " + kind);
  note.setAttribute("role", "alert");
  note.append(el("b", null, title), el("span", null, text));
  if (smallPrint) note.append(el("small", null, smallPrint));
  note.addEventListener("click", () => note.remove());
  box.appendChild(note);
  while (box.children.length > MAX_SHOWN) box.firstChild.remove();
  setTimeout(() => note.remove(), KEEP_MS);
}

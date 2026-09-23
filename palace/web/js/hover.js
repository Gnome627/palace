/* Hover links a node and its card: pointing at one lights both (`.hot`). Mouse only — a finger has no hover, and
 * pointerover from a tap would stick until the next tap elsewhere. `relight()` keeps it through a redraw. */
import { drawnOf } from "./dom.js";

let hot = null;                      // the card id under the mouse

export function initHover(map, rooms) {
  for (const [pane, selector] of [[map, ".node"], [rooms, ".card"]]) {
    for (const [type, on] of [["pointerover", true], ["pointerout", false]]) {
      pane.addEventListener(type, (e) => {
        const target = e.target.closest(selector);
        if (e.pointerType === "mouse" && target && !target.contains(e.relatedTarget)) light(target.dataset.id, on);
      });
    }
  }
}

function light(id, on) {
  hot = on ? id : null;
  for (const n of drawnOf(id)) n.classList.toggle("hot", on);
}

export function relight() {
  if (hot) light(hot, true);
}

/* The pull chain in the corner: a tug switches light/dark (with a click of the chain), remembered per browser.
 * The saved theme is applied before first paint by the inline script in index.html. */
import { $, svg } from "./dom.js";
import { store } from "./store.js";

const LINKS = 27;
const SWITCH_AT_MS = 170;            // the theme flips mid-pull
const PULL_MS = 720;                 // the whole animation

let chain = null;
let sound = null;
let pulling = false;

export function initTheme() {
  chain = $("chain");
  const links = chain.querySelector(".links");
  for (let i = 0; i < LINKS; i++) {
    const wide = i % 2 === 0;
    links.appendChild(svg("rect", {
      x: wide ? 8.5 : 10, y: 2 + i * 9, width: wide ? 7 : 4, height: 11, rx: wide ? 3.5 : 2,
    }));
  }
  sound = new Audio("assets/chain.wav");
  sound.preload = "auto";
  chain.tabIndex = 0;
  chain.addEventListener("click", pull);
  chain.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pull(); }
  });
}

function pull() {
  if (pulling) return;
  pulling = true;
  chain.classList.remove("pulled");
  void chain.offsetWidth;            // restart the animation
  chain.classList.add("pulled");
  try {
    sound.currentTime = 0;
    sound.play().catch(() => {});
  } catch { /* no audio */ }
  setTimeout(() => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    store.set("theme", theme);
  }, SWITCH_AT_MS);
  setTimeout(() => { chain.classList.remove("pulled"); pulling = false; }, PULL_MS);
}

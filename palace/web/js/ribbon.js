/* The ribbon at the top: reload from HA, save the arrangement, show names, show hidden, the language, the link dot. */
import { api } from "./api.js";
import { $, setIcon } from "./dom.js";
import { dropdown, setChoice } from "./dropdown.js";
import { LOCALES, locale, onLocaleChange, setLocale, t, tIn } from "./i18n.js";
import { layoutToSave, onDirtyChange, setDirty, state } from "./state.js";
import { store } from "./store.js";

const ui = {};
let link = "ha_off";                 // the last known link state, a key under "link."
let turns = 0;                       // whole turns of the refresh arrows so far

export function initRibbon({ onReload, onFlags }) {
  Object.assign(ui, { refresh: $("refresh"), save: $("save"), names: $("names"), hidden: $("hidden"), lang: $("lang"), dot: $("haDot") });
  for (const b of document.querySelectorAll(".tool[data-icon]")) setIcon(b, b.dataset.icon);

  ui.refresh.addEventListener("click", () => { turn(); onReload(); });
  ui.save.addEventListener("click", save);
  onDirtyChange((dirty) => ui.save.classList.toggle("dirty", dirty));
  // unsaved arrangement: the browser asks before leaving (returnValue — for browsers before Chrome 119)
  window.addEventListener("beforeunload", (e) => { if (state.dirty) { e.preventDefault(); e.returnValue = ""; } });

  ui.names.addEventListener("click", () => flip("names", onFlags));
  ui.hidden.addEventListener("click", () => flip("hidden", onFlags));

  // each language is named in itself: "RU", "US"; the full name on hover
  dropdown(LOCALES.map((id) => [id, tIn(id, "locale.short"), tIn(id, "locale.name")]), locale(), setLocale, ui.lang);
  onLocaleChange(words);
  words();
}

/** One more whole turn of the refresh arrows: the transition plays it from wherever they are now. */
function turn() {
  ui.refresh.style.rotate = `${++turns * 360}deg`;
}

/** Everything in the ribbon that is worded by state, not by markup. */
function words() {
  const { names, hidden } = state.flags;
  ui.names.classList.toggle("active", names);
  setIcon(ui.names, names ? "label" : "label-off");
  label(ui.names, t(names ? "ribbon.names_hide" : "ribbon.names_show"));
  ui.hidden.classList.toggle("active", hidden);
  setIcon(ui.hidden, hidden ? "eye-off" : "eye");
  label(ui.hidden, t(hidden ? "ribbon.hidden_hide" : "ribbon.hidden_show"));
  setChoice(ui.lang, locale());
  showLink(link);
}

function label(button, text) {
  button.title = text;
  button.setAttribute("aria-label", text);
}

function flip(flag, onFlags) {
  state.flags[flag] = !state.flags[flag];
  store.set(flag, state.flags[flag]);
  words();
  onFlags(flag);
}

async function save() {
  try {
    state.layout = await api("/layout", { method: "PUT", json: layoutToSave() });
    setDirty(false);
  } catch (err) {
    alert(t("ribbon.save_failed", { error: err.message }));
  }
}

/** "ha_on" | "ha_off" | "palace_off" */
export function showLink(kind) {
  link = kind;
  ui.dot.className = "dot " + (kind === "ha_on" ? "on" : "off");
  ui.dot.title = t(`link.${kind}`);
}

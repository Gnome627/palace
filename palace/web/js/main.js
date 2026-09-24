/* Palace — the house on a map and in cards. Plain ES modules, no build step; this one wires them together.
 *
 *   state     what the page holds: the house from the server, the layout the user arranges
 *   i18n      every word on the page, from locales/*.json
 *   api       the server; live — following the house; actions — switching it
 *   map, rooms, controls, reorder, picker, hover — the two panes and what can be done in them
 *   ribbon, panes, theme, toast — the frame around them
 */
import { act, initActions, toggleCard } from "./actions.js";
import { $ } from "./dom.js";
import { closeDropdown, dropdownOpen, initDropdown } from "./dropdown.js";
import { initHover, relight } from "./hover.js";
import { initI18n, onLocaleChange } from "./i18n.js";
import { initLive, load, refresh, startFollowing } from "./live.js";
import { dragging, initMap, renderMap } from "./map.js";
import { initPanes } from "./panes.js";
import { closePicker, initPicker, pickerOpen, togglePicker } from "./picker.js";
import { initReorder, reordering } from "./reorder.js";
import { initRibbon, showLink } from "./ribbon.js";
import { initRooms, renderRooms } from "./rooms.js";
import { placed, placeNew, setDirty, state } from "./state.js";
import { initTheme } from "./theme.js";
import { initToasts } from "./toast.js";

const map = $("map");
const rooms = $("rooms");

function render() {
  closePicker();
  closeDropdown();
  placeNew(map.clientWidth || 600, map.clientHeight || 500);
  renderMap(map);
  renderRooms(rooms, act);
  relight();
}

/** A slider or a field in use: redrawing under it would pull it from under the user's finger. */
function usingControl() {
  const focused = document.activeElement;
  return rooms.contains(focused) && focused.matches("input:not([type=checkbox])");
}

const handsBusy = () => dragging() || reordering() || pickerOpen() || dropdownOpen() || usingControl();

function toggleHidden(id) {
  const entry = placed(id);
  if (entry.hidden) delete entry.hidden;
  else entry.hidden = true;
  setDirty(true);
  render();
}

await initI18n();
initTheme();
initPanes();
initToasts($("toasts"));
initRibbon({
  onReload: () => load(true),
  onFlags: (flag) => (flag === "names" ? map.classList.toggle("names", state.flags.names) : render()),
});
initLive({ render, handsBusy, showLink });
initActions({ refresh });
initMap(map, { onToggle: toggleCard });
initRooms(rooms, { onIcon: togglePicker, onToggleHidden: toggleHidden });
initReorder(rooms, { onDrop: () => renderRooms(rooms, act) });
initPicker($("picker"), { onPick: render });
initDropdown($("dropdown"));
initHover(map, rooms);
onLocaleChange(render);

await load();
startFollowing();

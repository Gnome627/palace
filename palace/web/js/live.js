/* Following the house: the first load, the refresh button, and the live stream.
 *
 * /api/events says when something changed (an automation, a wall switch, another tab). A new `version` (something
 * switchable, availability, the registry) is fetched at once; new `readings` (sensor values) at most every
 * READINGS_MS. A fetch never happens under the user's hands (`handsBusy`: dragging, a slider in use, the icon
 * picker open) — it waits. One fetch at a time: calls that come in meanwhile share one more round after it,
 * so an older answer can never land on top of a newer one.
 */
import { api, events } from "./api.js";
import { sleep } from "./dom.js";
import { state } from "./state.js";

const READINGS_MS = 30000;
const WAIT_MS = 500;                 // how often a waiting fetch looks whether the user is done

let render = () => {};
let handsBusy = () => false;
let showLink = () => {};
let seen = { version: 0, readings: 0 };
let fetchedAt = 0;
let readingsTimer = null;
let running = null;
let again = false;

export function initLive(hooks) {
  ({ render, handsBusy, showLink } = hooks);
}

function take(house) {
  state.house = house;
  seen = { version: house.version, readings: house.readings };
  fetchedAt = Date.now();
  showLink(house.ha_connected ? "ha_on" : "ha_off");
}

/** The first load (the layout comes with it) and the refresh button (`resync`: HA's registry read anew). */
export async function load(resync = false) {
  try {
    const house = resync ? await api("/refresh", { method: "POST" }) : await api("/house");
    const first = !state.house.cards.length && !state.dirty;
    take(house);
    if (first) state.layout = house.layout;   // later loads keep what the user is arranging
    render();
  } catch (err) {
    console.warn("load", err.message);
  }
}

/** Take the current picture quietly; resolves when it is on screen. */
export function refresh() {
  if (running) { again = true; return running; }
  running = (async () => {
    do {
      again = false;
      while (handsBusy()) await sleep(WAIT_MS);
      try {
        take(await api("/house"));
        render();
      } catch (err) {
        console.warn("refresh", err.message);
      }
    } while (again);
    running = null;
  })();
  return running;
}

function follow(s) {
  state.confirmTimeout = s.confirm_timeout ?? state.confirmTimeout;
  showLink(s.ha_connected ? "ha_on" : "ha_off");
  if (!fetchedAt) return;                     // the first load is still on its way
  if (s.version !== seen.version) {
    clearTimeout(readingsTimer);
    readingsTimer = null;
    refresh();
  } else if (s.readings !== seen.readings && !readingsTimer) {
    const wait = Math.max(0, fetchedAt + READINGS_MS - Date.now());
    readingsTimer = setTimeout(() => { readingsTimer = null; refresh(); }, wait);
  }
}

export function startFollowing() {
  events({ onState: follow, onLost: () => showLink("palace_off") });
}

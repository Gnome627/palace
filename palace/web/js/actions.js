/* Acting on the house: a click on the map (the card's `next` service) or a control in a card.
 *
 * One action per card at a time: the card and its node are locked (`busy`) from the click until the server
 * answers — it does so only when HA has reported the change — and the refresh has shown the result. Nothing is
 * drawn ahead of HA. A failure marks the card and the node for a while and says in a note what was tried and
 * what went wrong, by the server's failure code.
 */
import { api } from "./api.js";
import { drawnOf } from "./dom.js";
import { has, t } from "./i18n.js";
import { busy, cardById, cardOfEntity, failed, state } from "./state.js";
import { toast } from "./toast.js";

const MARK_MS = 6000;                // how long a failed card stays marked
const CALL_MARGIN = 15;              // s on top of CONFIRM_TIMEOUT: the call itself

// what went wrong → how it looks: red when the command failed, yellow when its fate is unknown
const KIND = { unconfirmed: "unconfirmed", busy: "unconfirmed" };

let refresh = async () => {};

export function initActions({ refresh: fn }) { refresh = fn; }

export async function toggleCard(id) {
  const card = cardById(id);
  if (!card || card.on === null || !card.available || busy.has(id)) return;
  await locked(id, verb(card.next), () => api("/toggle", { method: "POST", json: { id }, timeout: callTimeout() }));
}

export async function act(entityId, service, data) {
  const card = cardOfEntity(entityId);
  if (!card) return;
  if (busy.has(card.id)) { refresh(); return; }   // the control already moved — the refresh moves it back
  // turn_on with data is a lamp that is already on getting a new brightness or colour
  const what = service === "turn_on" && data ? t("verb.adjust") : verb(service);
  const json = { entity_id: entityId, service, data: data || null };
  await locked(card.id, what, () => api("/call", { method: "POST", json, timeout: callTimeout() }));
}

const verb = (service) => (has(`verb.${service}`) ? t(`verb.${service}`) : t("verb.adjust"));
const callTimeout = () => (state.confirmTimeout + CALL_MARGIN) * 1000;

async function locked(id, what, send) {
  busy.add(id);
  failed.delete(id);
  mark(id);
  // a slider keeps focus after release, and a focused control holds the refresh back — this card is locked anyway
  if (document.activeElement?.closest(`.card[data-id="${CSS.escape(id)}"]`)) document.activeElement.blur();
  try {
    await send();
  } catch (err) {
    report(id, what, err);
  }
  await refresh();                   // the confirmed state — or, after a failure, the controls back to what HA says
  busy.delete(id);
  mark(id);
}

function mark(id) {
  for (const n of drawnOf(id)) {
    n.classList.toggle("busy", busy.has(id));
    n.classList.remove("failed", "unconfirmed");
    if (failed.has(id)) n.classList.add(failed.get(id));
  }
}

function report(id, what, err) {
  console.warn("action", id, err.status, err.code, err.message);
  const kind = KIND[err.code] || "failed";
  failed.set(id, kind);
  mark(id);
  setTimeout(() => { if (failed.get(id) === kind) { failed.delete(id); mark(id); } }, MARK_MS);
  toast(kind, ...describe(id, what, err));
}

/** [title, text, small print] for a failure, in the user's language. */
function describe(id, what, err) {
  const name = t("fmt.quoted", { name: cardById(id)?.name || id });
  const failedTo = t("failure.title", { verb: what, name });
  switch (err.code) {
    case "unconfirmed":
      return [t("failure.unconfirmed_title", { name }), t("failure.unconfirmed", { verb: what, seconds: state.confirmTimeout })];
    case "busy":
      return [t("failure.busy_title", { name }), t("failure.busy")];
    case "ha_error":
    case "refused":
      return [failedTo, t(`failure.${err.code}`), err.message];
    case "ha_offline":
    case "network":
    case "unauthorized":
      return [failedTo, t(`failure.${err.code}`)];
    case "timeout":
      return [failedTo, t("failure.timeout", { seconds: Math.round(callTimeout() / 1000) })];
    default:
      return [failedTo, err.message];
  }
}

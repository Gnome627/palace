/* The server's /api. Relative paths: the page works behind a proxy under a sub-path too.
 *
 * A failure is an ApiError: `status` is the HTTP code, or 0 when the server did not answer at all; `code` is the
 * server's failure code (unauthorized, refused, busy, ha_error, ha_offline, unconfirmed), or "timeout" / "network"
 * for status 0. `message` is the server's English detail — for logs and the small print, not for the user.
 */
import { t } from "./i18n.js";
import { store } from "./store.js";

const BASE = "api";
const DEFAULT_TIMEOUT = 20000;       // ms

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message || code || String(status));
    this.status = status;
    this.code = code;
  }
}

let key = store.get("key", "");

async function send(path, { method, json, timeout }) {
  const headers = {};
  if (json !== undefined) headers["Content-Type"] = "application/json";
  if (key) headers["X-Api-Key"] = key;
  try {
    return await fetch(BASE + path, {
      method, headers, body: json === undefined ? undefined : JSON.stringify(json), signal: AbortSignal.timeout(timeout),
    });
  } catch (err) {
    throw new ApiError(0, err.name === "TimeoutError" ? "timeout" : "network");
  }
}

async function failure(res) {
  let detail = null;
  try { detail = (await res.json()).detail; } catch { /* not json */ }
  if (detail && typeof detail === "object") return new ApiError(res.status, detail.code, detail.message);
  return new ApiError(res.status, null, typeof detail === "string" ? detail : res.statusText);
}

/** JSON in, JSON out. A 401 asks for the key once, remembers it and tries again. */
export async function api(path, { method = "GET", json, timeout = DEFAULT_TIMEOUT } = {}) {
  let res = await send(path, { method, json, timeout });
  if (res.status === 401) {
    const typed = prompt(t("auth.prompt"));
    if (typed === null) throw new ApiError(401, "unauthorized");
    key = typed.trim();
    store.set("key", key);
    res = await send(path, { method, json, timeout });
  }
  if (!res.ok) throw await failure(res);
  return res.json();
}

/** The live stream of counters (/api/events); the browser reconnects by itself when it drops. */
export function events({ onState, onLost }) {
  const source = new EventSource(BASE + "/events");
  source.onmessage = (e) => {
    try {
      onState(JSON.parse(e.data));
    } catch (err) {
      console.warn("event", err.message);
    }
  };
  source.onerror = onLost;
  return source;
}

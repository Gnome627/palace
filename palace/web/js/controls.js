/* The rows of a card: one or more per entity — a switch, sliders, buttons, a reading.
 *
 * `entityRows(entity, act)` builds them; `act(entity_id, service, data)` is called on every change the user makes.
 * Labels: the entity's own name when HA gives one, else a word for what it is.
 */
import { el, icon } from "./dom.js";
import { has, t, tOr } from "./i18n.js";

const COLOR_MODES = ["hs", "rgb", "rgbw", "rgbww", "xy"];

const pct = (v) => t("fmt.percent", { v });
const deg = (v) => t("fmt.degrees", { v });

function row(label, control, { value } = {}) {
  const r = el("div", "row");
  const l = el("span", "lbl", label);
  if (value !== undefined) l.appendChild(el("span", "v", value));
  r.appendChild(l);
  if (control) r.appendChild(control);
  return r;
}

function toggle(e, act, onService = "turn_on", offService = "turn_off") {
  const lab = el("label", "sw");
  const inp = el("input");
  inp.type = "checkbox";
  inp.checked = e.on;
  inp.disabled = e.state === "unavailable";
  inp.addEventListener("change", () => act(e.entity_id, inp.checked ? onService : offService));
  lab.append(inp, el("span"));
  return lab;
}

/** A range input with its value shown in the label as it moves; `onChange` fires on release. */
function range({ min, max, step, value, format, onChange, cls }) {
  const inp = el("input", cls);
  Object.assign(inp, { type: "range", min, max, step, value });
  const shown = el("span", "v", format(value));
  inp.addEventListener("input", () => { shown.textContent = format(+inp.value); });
  inp.addEventListener("change", () => onChange(+inp.value));
  return { inp, shown };
}

/** A full-width row: the label with the live value, the slider under it. */
function sliderRow(label, { inp, shown }) {
  const l = el("span", "lbl", label);
  l.appendChild(shown);
  const r = el("div", "row wide");
  r.append(l, inp);
  return r;
}

const slider = (label, spec) => sliderRow(label, range(spec));

function button(content, title, onClick) {
  const b = el("button", "btn", content);
  if (title) { b.title = title; b.setAttribute("aria-label", title); }
  b.addEventListener("click", onClick);
  return b;
}

function select(options, current, onChange) {
  const s = el("select");
  for (const [value, text] of options) s.appendChild(new Option(text, value, false, value === current));
  s.addEventListener("change", () => onChange(s.value));
  return s;
}

// colour as HA thinks of it: hue 0–360 and saturation 0–100, two sliders; brightness is its own slider
function colorRows(e, act) {
  const [h0, s0] = e.attributes.hs_color || [0, 0];
  const send = () => act(e.entity_id, "turn_on", { hs_color: [+hue.inp.value, +sat.inp.value] });
  const hue = range({ min: 0, max: 360, step: 1, value: Math.round(h0), format: deg, onChange: send, cls: "hue" });
  const sat = range({ min: 0, max: 100, step: 1, value: Math.round(s0), format: pct, onChange: send, cls: "sat" });
  const paint = () => sat.inp.style.setProperty("--h", hue.inp.value);
  hue.inp.addEventListener("input", paint);
  paint();
  return [sliderRow(t("control.hue"), hue), sliderRow(t("control.saturation"), sat)];
}

function lightRows(e, act) {
  const a = e.attributes, rows = [row(e.name || t("control.light"), toggle(e, act))];
  if (!e.on) return rows;
  const modes = a.supported_color_modes || [];
  if (modes.some((m) => m !== "onoff")) {
    rows.push(slider(t("control.brightness"), {
      min: 1, max: 255, step: 1, value: a.brightness ?? 255, format: (v) => pct(Math.round(v / 2.55)),
      onChange: (v) => act(e.entity_id, "turn_on", { brightness: v }),
    }));
  }
  if (modes.some((m) => COLOR_MODES.includes(m))) rows.push(...colorRows(e, act));
  if (modes.includes("color_temp")) {
    const lo = a.min_color_temp_kelvin || 2000, hi = a.max_color_temp_kelvin || 6500;
    rows.push(slider(t("control.color_temp"), {
      min: lo, max: hi, step: 50, value: a.color_temp_kelvin ?? Math.round((lo + hi) / 2), format: (v) => t("fmt.kelvin", { v }),
      onChange: (v) => act(e.entity_id, "turn_on", { color_temp_kelvin: v }),
    }));
  }
  if (a.effect_list?.length) {
    const options = a.effect_list.map((name) => [name, name]);
    rows.push(row(t("control.effect"), select(options, a.effect, (v) => act(e.entity_id, "turn_on", { effect: v }))));
  }
  return rows;
}

function switchRows(e, act) {
  const fallback = { switch: t("control.power"), automation: t("control.automation") }[e.domain] || t("control.switch");
  const rows = [row(e.name || fallback, toggle(e, act))];
  if (e.domain === "automation") rows.push(row("", button(t("control.run"), null, () => act(e.entity_id, "trigger"))));
  return rows;
}

function fanRows(e, act) {
  const rows = [row(e.name || t("control.fan"), toggle(e, act))];
  if (e.on && e.attributes.percentage !== undefined) {
    rows.push(slider(t("control.speed"), {
      min: 0, max: 100, step: 5, value: e.attributes.percentage ?? 0, format: pct,
      onChange: (v) => act(e.entity_id, "set_percentage", { percentage: v }),
    }));
  }
  return rows;
}

function humidifierRows(e, act) {
  const a = e.attributes, rows = [row(e.name || t("control.humidifier"), toggle(e, act))];
  if (a.humidity !== undefined) {
    rows.push(slider(t("control.humidity"), {
      min: a.min_humidity ?? 0, max: a.max_humidity ?? 100, step: 1, value: a.humidity, format: pct,
      onChange: (v) => act(e.entity_id, "set_humidity", { humidity: v }),
    }));
  }
  return rows;
}

function coverRows(e, act) {
  const buttons = el("span", "btns");
  buttons.append(
    button("▲", t("control.open"), () => act(e.entity_id, "open_cover")),
    button("■", t("control.stop"), () => act(e.entity_id, "stop_cover")),
    button("▼", t("control.close"), () => act(e.entity_id, "close_cover")),
  );
  const rows = [row(e.name || t("control.cover"), buttons, { value: tOr(`state.cover.${e.state}`, e.state) })];
  if (e.attributes.current_position !== undefined) {
    rows.push(slider(t("control.position"), {
      min: 0, max: 100, step: 5, value: e.attributes.current_position, format: pct,
      onChange: (v) => act(e.entity_id, "set_cover_position", { position: v }),
    }));
  }
  return rows;
}

function climateRows(e, act) {
  const a = e.attributes;
  const modes = (a.hvac_modes || []).map((m) => [m, tOr(`hvac.${m}`, m)]);
  const now = a.current_temperature !== undefined ? deg(a.current_temperature) : undefined;
  const rows = [row(e.name || t("control.climate"), select(modes, e.state, (v) => act(e.entity_id, "set_hvac_mode", { hvac_mode: v })),
    { value: now })];
  if (a.temperature !== undefined && a.temperature !== null) {
    const n = el("input");
    Object.assign(n, { type: "number", min: a.min_temp ?? 7, max: a.max_temp ?? 35, step: a.target_temp_step ?? 0.5, value: a.temperature });
    n.addEventListener("change", () => act(e.entity_id, "set_temperature", { temperature: +n.value }));
    rows.push(row(t("control.target"), n));
  }
  return rows;
}

function mediaRows(e, act) {
  const a = e.attributes;
  const playing = e.state !== "on" && e.on ? tOr(`state.media.${e.state}`, e.state) : undefined;
  const rows = [row(e.name || t("control.player"), toggle(e, act), { value: playing })];
  if (e.on && a.volume_level !== undefined) {
    rows.push(slider(t("control.volume"), {
      min: 0, max: 1, step: 0.01, value: a.volume_level, format: (v) => pct(Math.round(v * 100)),
      onChange: (v) => act(e.entity_id, "volume_set", { volume_level: v }),
    }));
  }
  if (a.media_title) {
    const r = el("div", "row wide");
    r.appendChild(el("span", "sub", a.media_title));
    rows.push(r);
  }
  return rows;
}

function lockRows(e, act) {
  const value = t(e.on ? "control.locked" : "control.unlocked");
  return [row(e.name || t("control.lock"), toggle(e, act, "lock", "unlock"), { value })];
}

function vacuumRows(e, act) {
  const buttons = el("span", "btns");
  buttons.append(
    button(t("control.vacuum_start"), null, () => act(e.entity_id, "start")),
    button(t("control.vacuum_pause"), null, () => act(e.entity_id, "pause")),
    button(t("control.vacuum_home"), null, () => act(e.entity_id, "return_to_base")),
  );
  return [row(e.name || t("control.vacuum"), buttons, { value: tOr(`state.vacuum.${e.state}`, e.state) })];
}

const readoutLabel = (e) => e.name || tOr(`class.${e.device_class}`, e.device_class || t("control.sensor"));

function sensorRows(e) {
  const unit = e.attributes.unit_of_measurement ? " " + e.attributes.unit_of_measurement : "";
  const value = e.state === "unavailable" ? "—" : e.state === "unknown" ? "?" : e.state + unit;
  return [row(readoutLabel(e), el("span", "val", value))];
}

function binarySensorRows(e) {
  const on = e.state === "on";
  const cls = has(`binary.${e.device_class}.on`) ? e.device_class : "default";
  const text = e.state === "unavailable" ? "—" : t(`binary.${cls}.${on ? "on" : "off"}`);
  return [row(readoutLabel(e), el("span", on ? "val on" : "val", text))];
}

const BY_DOMAIN = {
  light: lightRows,
  switch: switchRows, input_boolean: switchRows, automation: switchRows, siren: switchRows, water_heater: switchRows,
  fan: fanRows,
  humidifier: humidifierRows,
  cover: coverRows,
  climate: climateRows,
  media_player: mediaRows,
  lock: lockRows,
  vacuum: vacuumRows,
  sensor: sensorRows,
  binary_sensor: binarySensorRows,
};

export function entityRows(e, act) {
  const build = BY_DOMAIN[e.domain];
  return build ? build(e, act) : [row(e.name || e.domain, el("span", "val", e.state))];
}

/** The battery footer of a card: an icon by level and the number. */
export function batteryBadge(level) {
  if (level === null || level === undefined) return null;
  const glyph = level >= 95 ? "battery" : level < 5 ? "battery-outline" : "battery-" + Math.max(10, Math.floor(level / 10) * 10);
  const b = el("span", level <= 20 ? "bat low" : "bat");
  b.title = t("card.battery");
  b.append(icon(glyph), document.createTextNode(pct(level)));
  return b;
}

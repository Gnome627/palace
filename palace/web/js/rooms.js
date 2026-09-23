/* The list: an area block per area, a card per device inside, in the user's order.
 * The icon opens the icon picker (`onIcon`), the eye hides or shows the card (`onToggleHidden`). */
import { batteryBadge, entityRows } from "./controls.js";
import { el, icon } from "./dom.js";
import { t } from "./i18n.js";
import { busy, cardsOf, failed, iconOf, isHidden, NONE, orderedAreas, state } from "./state.js";

export function renderRooms(rooms, act) {
  rooms.replaceChildren();
  let any = false;
  for (const area of orderedAreas()) {
    const cards = cardsOf(area.id).filter((c) => state.flags.hidden || !isHidden(c.id));
    if (!cards.length) continue;
    any = true;
    rooms.appendChild(areaBlock(area, cards, act));
  }
  if (!any) rooms.appendChild(el("p", "empty", t(state.house.cards.length ? "rooms.all_hidden" : "rooms.empty")));
}

function areaBlock(area, cards, act) {
  const block = el("section", "area");
  block.dataset.area = area.id;
  const head = el("div", "area-head");
  head.append(el("h2", null, area.id === NONE ? t("rooms.no_area") : area.name), el("span", "count", String(cards.length)));
  const grid = el("div", "cards");
  for (const c of cards) grid.appendChild(card(c, act));
  block.append(head, grid);
  return block;
}

function card(c, act) {
  const hidden = isHidden(c.id);
  const box = el("article", "card");
  box.dataset.id = c.id;
  if (!c.available) box.classList.add("unavailable");
  else if (c.on) box.classList.add("on");
  if (hidden) box.classList.add("ghost");
  if (busy.has(c.id)) box.classList.add("busy");
  if (failed.has(c.id)) box.classList.add(failed.get(c.id));

  const head = el("div", "card-head");
  const ico = el("button", "ico");
  ico.title = t("card.change_icon");
  ico.appendChild(icon(iconOf(c)));
  const title = el("span", "title", c.name);
  title.title = c.name;
  const eye = el("button", "eye");
  eye.title = t(hidden ? "card.show" : "card.hide");
  eye.appendChild(icon(hidden ? "eye-off" : "eye"));
  head.append(ico, title, eye);

  const body = el("div", "card-body");
  if (!c.available) body.appendChild(el("p", "note", t("card.unavailable")));
  for (const e of c.entities) {
    if (e.domain === "sensor" && e.device_class === "battery") continue;   // lives in the footer
    for (const r of entityRows(e, act)) {
      if (e.category) r.classList.add("aux");
      body.appendChild(r);
    }
  }

  box.append(head, body);
  const foot = footer(c);
  if (foot) box.appendChild(foot);
  return box;
}

function footer(c) {
  const foot = el("div", "card-foot");
  const battery = batteryBadge(c.battery);
  if (battery) foot.appendChild(battery);
  if (c.platform) {
    const via = el("span", "via", c.platform);
    via.title = [c.manufacturer, c.model].filter(Boolean).join(" · ") || c.platform;
    foot.appendChild(via);
  }
  return foot.childNodes.length ? foot : null;
}

export function initRooms(rooms, { onIcon, onToggleHidden }) {
  rooms.addEventListener("click", (e) => {
    const box = e.target.closest(".card");
    if (!box) return;
    if (e.target.closest(".eye")) onToggleHidden(box.dataset.id);
    else if (e.target.closest(".ico")) onIcon(box.dataset.id, e.target.closest(".ico"));
  });
}

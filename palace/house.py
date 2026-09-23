"""The house as Palace shows it: one card per HA device, the device's entities inside.

Pure functions over the Registry, so all of it is testable from the JSON fixture.
A card is either a device from the HA device registry ("dev:<id>", its entities grouped)
or a lone entity that has no device ("ent:<entity_id>" — helpers, templates).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .registry import Entity, Registry


@dataclass(frozen=True)
class Control:
    """How a domain is switched: which states count as off, which services flip it."""
    on: str
    off: str
    off_states: frozenset[str] = frozenset({"off"})
    # services the page may call on the domain besides on/off
    services: frozenset[str] = frozenset()


# domains that can be switched from the map; anything else is a readout or ignored
CONTROLS: dict[str, Control] = {
    "light": Control("turn_on", "turn_off", services=frozenset({"toggle"})),
    "switch": Control("turn_on", "turn_off", services=frozenset({"toggle"})),
    "fan": Control("turn_on", "turn_off", services=frozenset({"set_percentage"})),
    "input_boolean": Control("turn_on", "turn_off"),
    "automation": Control("turn_on", "turn_off", services=frozenset({"trigger"})),
    "humidifier": Control("turn_on", "turn_off", services=frozenset({"set_humidity"})),
    "siren": Control("turn_on", "turn_off"),
    "water_heater": Control("turn_on", "turn_off", services=frozenset({"set_temperature"})),
    "climate": Control("turn_on", "turn_off", services=frozenset({"set_temperature", "set_hvac_mode"})),
    "media_player": Control("turn_on", "turn_off", frozenset({"off", "standby"}),
                            services=frozenset({"volume_set", "media_play", "media_pause", "volume_mute"})),
    "cover": Control("open_cover", "close_cover", frozenset({"closed", "closing"}),
                     services=frozenset({"set_cover_position", "stop_cover"})),
    "lock": Control("lock", "unlock", frozenset({"unlocked", "unlocking", "open", "opening"})),
    "vacuum": Control("start", "return_to_base", frozenset({"docked", "idle", "returning", "paused"}),
                      services=frozenset({"stop", "pause"})),
}
READOUTS = frozenset({"sensor", "binary_sensor"})
NOT_AVAILABLE = frozenset({"unavailable"})
# states that mean "nothing is known" — shown as off, but not as broken
NOT_KNOWN = frozenset({"unknown", "none", ""})

# attributes the page draws controls from; everything else stays on the server
SHOWN_ATTRIBUTES = (
    "brightness", "color_mode", "supported_color_modes", "rgb_color", "hs_color", "color_temp_kelvin",
    "min_color_temp_kelvin", "max_color_temp_kelvin", "effect", "effect_list",
    "percentage", "current_position", "current_tilt_position",
    "temperature", "current_temperature", "hvac_modes", "hvac_action", "min_temp", "max_temp", "target_temp_step",
    "humidity", "current_humidity", "min_humidity", "max_humidity",
    "volume_level", "is_volume_muted", "media_title", "source",
    "unit_of_measurement", "state_class", "icon",
)

# default icon (mdi id without "mdi:") by domain, refined by device_class
ICONS: dict[str, str] = {
    "light": "lightbulb", "switch": "toggle-switch", "fan": "fan", "cover": "window-shutter", "climate": "thermostat",
    "media_player": "cast", "lock": "lock", "vacuum": "robot-vacuum", "humidifier": "air-humidifier",
    "automation": "robot", "input_boolean": "toggle-switch", "siren": "alarm-light", "water_heater": "water-boiler",
    "sensor": "gauge", "binary_sensor": "bell",
}
CLASS_ICONS: dict[tuple[str, str], str] = {
    ("switch", "outlet"): "power-socket-eu",
    ("cover", "garage"): "garage", ("cover", "gate"): "gate", ("cover", "curtain"): "curtains",
    ("cover", "blind"): "blinds", ("cover", "shade"): "blinds", ("cover", "door"): "door", ("cover", "window"): "window-closed",
    ("media_player", "tv"): "television", ("media_player", "speaker"): "speaker", ("media_player", "receiver"): "radio",
    ("sensor", "temperature"): "thermometer", ("sensor", "humidity"): "water-percent", ("sensor", "battery"): "battery",
    ("sensor", "power"): "flash", ("sensor", "energy"): "flash", ("sensor", "voltage"): "flash", ("sensor", "current"): "flash",
    ("sensor", "illuminance"): "weather-sunny", ("sensor", "moisture"): "water",
    ("binary_sensor", "motion"): "motion-sensor", ("binary_sensor", "occupancy"): "motion-sensor",
    ("binary_sensor", "door"): "door", ("binary_sensor", "window"): "window-closed", ("binary_sensor", "opening"): "door",
    ("binary_sensor", "smoke"): "smoke-detector", ("binary_sensor", "moisture"): "water", ("binary_sensor", "battery"): "battery",
}


def is_on(e: Entity) -> bool:
    ctl = CONTROLS.get(e.domain)
    if ctl is None:
        return False
    return e.state not in ctl.off_states and e.state not in NOT_AVAILABLE and e.state not in NOT_KNOWN


def _aux(e: Entity) -> int:
    return 1 if e.entity_category else 0


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Card:
    id: str
    name: str
    area_id: str | None
    platform: str | None
    manufacturer: str | None
    model: str | None
    controls: list[Entity] = field(default_factory=list)
    readouts: list[Entity] = field(default_factory=list)

    @property
    def entities(self) -> list[Entity]:
        """Controls first, then readouts; within each the device itself before its config/diagnostic knobs."""
        return [*sorted(self.controls, key=_aux), *sorted(self.readouts, key=_aux)]

    @property
    def switches(self) -> list[Entity]:
        """What a click on the map flips: the device's own controls. A lamp's "do not disturb" switch
        (entity_category=config) is not the lamp — unless config knobs are all the device has."""
        main = [e for e in self.controls if not e.entity_category]
        return main or self.controls

    @property
    def on(self) -> bool | None:
        """True/False for something switchable, None for a pure readout (drawn as off, not clickable)."""
        if not self.controls:
            return None
        return any(is_on(e) for e in self.switches)

    @property
    def available(self) -> bool:
        pool = self.controls or self.readouts
        return any(e.state not in NOT_AVAILABLE for e in pool)

    @property
    def battery(self) -> int | None:
        for e in self.readouts:
            if e.device_class == "battery" and (v := _number(e.state)) is not None:
                return round(v)
        for e in self.entities:
            for key in ("battery_level", "battery"):
                if (v := _number(e.attributes.get(key))) is not None:
                    return round(v)
        return None

    @property
    def icon(self) -> str:
        """By domain and class of the device's leading entity; the HA-side icon travels separately (`ha_icon`),
        the page uses it when it has that glyph."""
        return CLASS_ICONS.get((self.lead.domain, self.lead.device_class or ""), ICONS.get(self.lead.domain, "cog"))

    @property
    def ha_icon(self) -> str | None:
        icon = self.lead.attributes.get("icon")
        return icon[4:] if isinstance(icon, str) and icon.startswith("mdi:") else None

    @property
    def lead(self) -> Entity:
        if self.switches:
            return self.switches[0]
        # a readout-only device: not the battery, and the device's own reading before a diagnostic one
        return min(self.readouts, key=lambda e: (e.device_class == "battery", _aux(e)))

    @property
    def next_service(self) -> str | None:
        """What a click on the map will do, as the lead entity's service: turn_off, open_cover, lock…"""
        if self.on is None:
            return None
        ctl = CONTROLS[self.lead.domain]
        return ctl.off if self.on else ctl.on

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "area_id": self.area_id,
            "platform": self.platform,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "on": self.on,
            "available": self.available,
            "battery": self.battery,
            "icon": self.icon,
            "ha_icon": self.ha_icon,
            "next": self.next_service,
            "entities": [entity_view(e, self.name) for e in self.entities],
        }


def entity_view(e: Entity, card_name: str) -> dict:
    name = e.name
    # HA names an entity after its device when it is the device's only face; the card already says so
    if name == card_name or not name:
        name = ""
    elif name.startswith(card_name + " "):
        name = name[len(card_name) + 1:]
    return {
        "entity_id": e.entity_id,
        "domain": e.domain,
        "name": name,
        "state": e.state,
        "device_class": e.device_class,
        "on": is_on(e) if e.domain in CONTROLS else None,
        "category": e.entity_category,
        "attributes": {k: e.attributes[k] for k in SHOWN_ATTRIBUTES if k in e.attributes},
    }


def build_cards(registry: Registry) -> list[Card]:
    """Group the registry into cards: by device, lone entities on their own. Sorted by name."""
    by_id: dict[str, Card] = {}
    for e in sorted(registry.entities.values(), key=lambda e: e.entity_id):
        if e.domain in CONTROLS:
            bucket = "controls"
        elif e.domain in READOUTS:
            bucket = "readouts"
        else:
            continue
        device = registry.devices.get(e.device_id or "")
        if device is not None:
            cid = "dev:" + device.id
            card = by_id.get(cid)
            if card is None:
                card = by_id[cid] = Card(cid, device.name, device.area_id or e.area_id, e.platform,
                                         device.manufacturer, device.model)
        else:
            cid = "ent:" + e.entity_id
            card = by_id[cid] = Card(cid, e.name, e.area_id, e.platform, None, None)
        getattr(card, bucket).append(e)
    return sorted(by_id.values(), key=lambda c: (c.name.lower(), c.id))


def toggle_calls(card: Card) -> list[tuple[str, str, list[str]]]:
    """(domain, service, entity_ids) to flip the whole card: on → everything off, else everything on."""
    turn_off = bool(card.on)
    calls: dict[tuple[str, str], list[str]] = {}
    for e in card.switches:
        ctl = CONTROLS[e.domain]
        if e.state in NOT_AVAILABLE:
            continue
        calls.setdefault((e.domain, ctl.off if turn_off else ctl.on), []).append(e.entity_id)
    return [(d, s, ids) for (d, s), ids in calls.items()]


def allowed_service(domain: str, service: str) -> bool:
    ctl = CONTROLS.get(domain)
    return ctl is not None and service in (ctl.on, ctl.off, *ctl.services)

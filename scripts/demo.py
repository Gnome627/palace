"""Palace without a Home Assistant: the page on a pretend house, service calls change states locally.

    .venv/bin/python scripts/demo.py [--port 8080] [--layout /tmp/palace-demo.yaml] [--confirm-timeout 10]

The house: the test fixture registry plus a few multi-entity devices, so cards with batteries, integrations,
sliders and unavailable things are all on screen. Nothing is sent anywhere. Someone else lives there too: every
25 s a light flips or the thermometer moves — the page should follow by itself.
Two devices misbehave on purpose: a plug that takes commands and never reports back (no change in time)
and a lamp whose integration fails (an HA error) — to see how the page says so.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
from pathlib import Path

import uvicorn

from palace.ha import HAError
from palace.house import CONTROLS
from palace.panel import Panel
from palace.registry import Area, Device, Entity, Registry
from palace.server import create_app

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "registry.json"
CALL_DELAY = 0.3                     # s: a cloud integration takes its time
SILENT = {"switch.silent_plug"}      # takes a command, never reports back
BROKEN = {"light.broken"}            # its integration fails
# the state a domain lands in after its "on" / "off" service, where it is not simply on/off
ON_STATES = {"cover": "open", "lock": "locked", "vacuum": "cleaning", "climate": "heat"}
OFF_STATES = {"cover": "closed", "lock": "unlocked", "vacuum": "docked"}
# service → the attribute its data sets
SETS = {"set_cover_position": ("current_position", "position"), "set_percentage": ("percentage", "percentage"),
        "volume_set": ("volume_level", "volume_level"), "set_temperature": ("temperature", "temperature")}
LIGHT_DATA = ("brightness", "hs_color", "color_temp_kelvin", "effect")


class PretendHA:
    """The part of HAClient the panel uses, over a local registry."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self.connected = asyncio.Event()
        self.connected.set()
        self._state_listeners, self._registry_listeners = [], []

    def on_state(self, fn):
        self._state_listeners.append(fn)

    def on_registry(self, fn):
        self._registry_listeners.append(fn)

    async def resync(self) -> Registry:
        for fn in self._registry_listeners:
            fn(self.registry)
        return self.registry

    async def call_service(self, domain, service, entity_ids, data=None) -> None:
        await asyncio.sleep(CALL_DELAY)
        if BROKEN & set(entity_ids):
            raise HAError(f"Failed to call service {domain}/{service}: device offline in the cloud")
        data = data or {}
        for eid in entity_ids:
            if eid in SILENT:
                continue
            e, ctl = self.registry.entities[eid], CONTROLS[domain]
            state, attrs = e.state, dict(e.attributes)
            if service == ctl.on:
                state = ON_STATES.get(domain, "on")
                attrs.update({k: v for k, v in data.items() if k in LIGHT_DATA})
            elif service == ctl.off:
                state = OFF_STATES.get(domain, "off")
            elif service == "set_hvac_mode":
                state = data["hvac_mode"]
            elif service in SETS:
                attr, key = SETS[service]
                attrs[attr] = data[key]
            self.set(eid, state, attrs)

    def set(self, eid: str, state: str, attrs: dict | None = None) -> None:
        """Change an entity and tell the listeners, the way HA's state_changed does: whole states, attributes too."""
        e = self.registry.entities[eid]
        old = {"state": e.state, "attributes": dict(e.attributes)}
        attrs = dict(e.attributes if attrs is None else attrs)
        self.registry.update_state(eid, state, attrs)
        for fn in self._state_listeners:
            fn(eid, old, {"entity_id": eid, "state": state, "attributes": attrs})


def pretend_house() -> Registry:
    reg = Registry.from_json(FIXTURE)
    for e in reg.entities.values():
        e.platform = random.choice(["tuya", "mqtt", "zha", "yeelight"])

    def add(entity_id: str, name: str, area: str | None, **kw) -> None:
        reg.entities[entity_id] = Entity(entity_id, name, area, **kw)

    reg.areas["vannaya"] = Area("vannaya", "Ванная")
    for d in (Device("d-lustra", "Люстра", "gostinaya", "Tuya", "TS0505B"),
              Device("d-motion", "Датчик движения", "koridor", "Aqara", "RTCGQ11LM"),
              Device("d-fan", "Вентилятор", "vannaya", "Xiaomi", "ZNFJ01"),
              Device("d-lock", "Замок", "koridor", "Aqara", "ZNMS12LM")):
        reg.devices[d.id] = d

    lustra = {"device_id": "d-lustra", "platform": "tuya"}
    add("light.lustra_1", "Люстра лампа 1", "gostinaya", state="on", **lustra, attributes={
        "brightness": 180, "supported_color_modes": ["color_temp", "hs"], "hs_color": [35, 53],
        "color_temp_kelvin": 3000, "min_color_temp_kelvin": 2000, "max_color_temp_kelvin": 6500})
    add("light.lustra_2", "Люстра лампа 2", "gostinaya", state="off", **lustra, attributes={"supported_color_modes": ["brightness"]})
    add("switch.lustra_dnd", "Люстра Не беспокоить", "gostinaya", state="on", **lustra, entity_category="config")

    motion = {"device_id": "d-motion", "platform": "zha"}
    add("binary_sensor.motion", "Датчик движения Движение", "koridor", device_class="motion", state="on", **motion)
    add("sensor.motion_battery", "Датчик движения Батарея", "koridor", device_class="battery", state="17", **motion,
        attributes={"unit_of_measurement": "%"})
    add("sensor.motion_lux", "Датчик движения Освещённость", "koridor", device_class="illuminance", state="120", **motion,
        attributes={"unit_of_measurement": "lx"})
    add("sensor.motion_lq", "Датчик движения Качество связи", "koridor", state="132", **motion, entity_category="diagnostic",
        attributes={"unit_of_measurement": "lqi", "icon": "mdi:signal"})

    add("fan.bath", "Вентилятор", "vannaya", state="unavailable", device_id="d-fan", platform="mqtt", attributes={"percentage": 40})
    add("lock.door", "Замок", "koridor", state="locked", device_id="d-lock", platform="zha", attributes={"battery_level": 88})
    add("switch.silent_plug", "Молчаливая розетка", "vannaya", state="off", platform="tuya")
    add("light.broken", "Сломанная лампа", "vannaya", state="off", platform="tuya", attributes={"supported_color_modes": ["onoff"]})
    add("automation.night", "Ночной режим", None, state="on", platform="automation")

    reg.entities["vacuum.robot"].attributes["battery_level"] = 64
    reg.entities["climate.ac_bedroom"].attributes.update({
        "hvac_modes": ["off", "cool", "heat", "auto"], "temperature": 23, "current_temperature": 25.5, "min_temp": 16, "max_temp": 30})
    reg.entities["cover.curtains_bedroom"].attributes["current_position"] = 30
    reg.entities["media_player.tv"].attributes.update({"volume_level": 0.35, "media_title": "Дживс и Вустер"})
    return reg


async def drift(ha: PretendHA) -> None:
    """Someone else in the house: a light flips now and then, the thermometer wanders."""
    while True:
        await asyncio.sleep(25)
        temp = ha.registry.entities["sensor.bedroom_temp"]
        ha.set(temp.entity_id, f"{float(temp.state or 21) + random.choice((-0.1, 0.1)):.1f}")
        await asyncio.sleep(25)
        lamp = ha.registry.entities["light.kids"]
        ha.set(lamp.entity_id, "off" if lamp.state == "on" else "on")


async def main(port: int, layout: str, confirm_timeout: float) -> None:
    ha = PretendHA(pretend_house())
    app = create_app(Panel(ha, layout, confirm_timeout=confirm_timeout))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1))
    print(f"Palace (pretend house) on http://127.0.0.1:{port}  layout → {layout}")
    await asyncio.gather(server.serve(), drift(ha))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--layout", default="/tmp/palace-demo.yaml")
    ap.add_argument("--confirm-timeout", type=float, default=10)
    args = ap.parse_args()
    logging.basicConfig(level="INFO")
    asyncio.run(main(args.port, args.layout, args.confirm_timeout))

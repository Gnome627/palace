"""Stand-ins for Home Assistant and the test house. The panel talks to HAClient through a small surface:
registry, connected, on_state, on_registry, call_service, resync — these fakes implement just that."""
from __future__ import annotations

import asyncio
from typing import ClassVar

from palace.ha import HAError, HAOffline
from palace.registry import Area, Device, Entity, Registry


def make_house() -> Registry:
    """A lamp with a battery on a Zigbee device, a two-bulb chandelier, curtains, a lone template switch, a thermometer."""
    return Registry(
        areas=[Area("gostinaya", "Гостиная"), Area("spalnya", "Спальня")],
        devices=[
            Device("d-lamp", "Торшер", "gostinaya", "IKEA", "Tradfri"),
            Device("d-lustra", "Люстра", "gostinaya"),
            Device("d-cur", "Шторы", "spalnya"),
            Device("d-therm", "Термометр", "spalnya"),
        ],
        entities=[
            Entity("light.torsher", "Торшер", "gostinaya", state="on", device_id="d-lamp", platform="zha",
                   attributes={"brightness": 120, "supported_color_modes": ["brightness"]}),
            Entity("switch.torsher_dnd", "Торшер Не беспокоить", "gostinaya", state="on", device_id="d-lamp", platform="zha",
                   entity_category="config"),
            Entity("sensor.torsher_battery", "Торшер Батарея", "gostinaya", device_class="battery", state="42",
                   device_id="d-lamp", platform="zha"),
            Entity("light.lustra_1", "Люстра 1", "gostinaya", state="on", device_id="d-lustra", platform="tuya"),
            Entity("light.lustra_2", "Люстра 2", "gostinaya", state="off", device_id="d-lustra", platform="tuya"),
            Entity("cover.curtains", "Шторы", "spalnya", device_class="curtain", state="closed", device_id="d-cur", platform="mqtt"),
            Entity("sensor.temp", "Термометр Температура", "spalnya", device_class="temperature", state="21.5",
                   attributes={"unit_of_measurement": "°C"}, device_id="d-therm", platform="mqtt"),
            Entity("switch.template", "Гирлянда", None, state="unavailable", platform="template"),
            Entity("scene.movie", "Кино", "gostinaya", state="unknown", platform="homeassistant"),
            Entity("weather.home", "Погода", None, state="cloudy"),
        ],
    )


class FakeHA:
    """Records calls and tells listeners about changes made with `change()`; the devices never answer by themselves."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self.calls: list[tuple[str, str, list[str], dict]] = []
        self.state_listeners, self.registry_listeners = [], []
        self.connected = asyncio.Event()
        self.connected.set()
        self.resyncs = 0

    def on_state(self, fn):
        self.state_listeners.append(fn)

    def on_registry(self, fn):
        self.registry_listeners.append(fn)

    async def call_service(self, domain, service, entity_ids, data=None):
        self.calls.append((domain, service, sorted(entity_ids), data or {}))

    async def resync(self):
        self.resyncs += 1
        for fn in self.registry_listeners:
            fn(self.registry)
        return self.registry

    def emit(self, entity_id, old, new):
        """A raw state_changed, as HA sends it."""
        for fn in self.state_listeners:
            fn(entity_id, old, new)

    def change(self, entity_id, state):
        known = self.registry.entities.get(entity_id)
        old = {"state": known.state} if known else None
        self.registry.update_state(entity_id, state, {})
        self.emit(entity_id, old, {"entity_id": entity_id, "state": state})


class ReportingHA(FakeHA):
    """Like HA with a device that answers: after a call the entity reports its new state (or attributes)."""
    STATES: ClassVar[dict[str, str]] = {"turn_on": "on", "turn_off": "off", "open_cover": "open", "close_cover": "closed"}

    def __init__(self, registry, delay=0.0, silent=()):
        super().__init__(registry)
        self.delay, self.silent = delay, set(silent)

    async def call_service(self, domain, service, entity_ids, data=None):
        await super().call_service(domain, service, entity_ids, data)
        await asyncio.sleep(self.delay)
        for eid in entity_ids:
            if eid in self.silent:
                continue
            e = self.registry.entities[eid]
            old = {"state": e.state, "attributes": dict(e.attributes)}
            state = self.STATES.get(service, e.state)
            attrs = {**e.attributes, **(data or {})}
            self.registry.update_state(eid, state, attrs)
            self.emit(eid, old, {"entity_id": eid, "state": state, "attributes": attrs})


class BrokenHA(FakeHA):
    """The integration fails."""

    async def call_service(self, *a, **kw):
        raise HAError("Failed to call service light/turn_off: device offline in the cloud")


class OfflineHA(FakeHA):
    """No link to HA."""

    async def call_service(self, *a, **kw):
        raise HAOffline("not connected to Home Assistant")

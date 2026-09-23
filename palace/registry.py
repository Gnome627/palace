"""The house as HA describes it: areas, devices, entities with their states — an in-memory snapshot.

Built from the HA websocket registries plus the current states (`from_ha`), or from a saved JSON (`from_json`,
tests and the demo). Everything else in the panel works against this snapshot only, so it is testable without HA.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


@dataclass
class Area:
    id: str
    name: str


@dataclass
class Device:
    """A physical thing from the HA device registry; its entities point at it by id."""
    id: str
    name: str
    area_id: str | None = None
    manufacturer: str | None = None
    model: str | None = None


@dataclass
class Entity:
    entity_id: str
    name: str
    area_id: str | None = None
    device_class: str | None = None
    state: str = "unknown"
    attributes: dict[str, Any] = field(default_factory=dict)
    device_id: str | None = None
    platform: str | None = None  # the integration that serves it: tuya, mqtt, zha…
    entity_category: str | None = None  # "config" / "diagnostic" — a knob on the device, not the device itself

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]


def _only(cls, data: dict) -> dict:
    return {k: v for k, v in data.items() if k in cls.__dataclass_fields__}


class Registry:
    def __init__(self, areas: Iterable[Area] = (), entities: Iterable[Entity] = (), devices: Iterable[Device] = ()):
        self.areas: dict[str, Area] = {a.id: a for a in areas}
        self.entities: dict[str, Entity] = {e.entity_id: e for e in entities}
        self.devices: dict[str, Device] = {d.id: d for d in devices}

    def without(
        self, area_ids: Iterable[str] = (), entity_patterns: Iterable[str] = (), platforms: Iterable[str] = ()
    ) -> Registry:
        """Copy minus ignored areas, entity_id patterns and integrations (router ports, the phone app, backups —
        things the panel must not show). A device whose entities are all gone loses its card with them."""
        area_ids = set(area_ids)
        patterns = list(entity_patterns)
        platforms = set(platforms)
        keep = [
            e
            for e in self.entities.values()
            if e.area_id not in area_ids
            and e.platform not in platforms
            and not any(fnmatch(e.entity_id, p) for p in patterns)
        ]
        return Registry([a for a in self.areas.values() if a.id not in area_ids], keep, self.devices.values())

    def update_state(self, entity_id: str, state: str, attributes: dict[str, Any]) -> None:
        e = self.entities.get(entity_id)
        if e is not None:
            e.state = state
            e.attributes = attributes

    @classmethod
    def from_ha(cls, areas: list[dict], devices: list[dict], entities: list[dict], states: list[dict]) -> Registry:
        area_objs = [Area(a["area_id"], a["name"]) for a in areas]
        device_objs = [
            Device(d["id"], d.get("name_by_user") or d.get("name") or d["id"], d.get("area_id"),
                   d.get("manufacturer"), d.get("model"))
            for d in devices
        ]
        device_area = {d.id: d.area_id for d in device_objs}
        state_by_id = {s["entity_id"]: s for s in states}

        result: dict[str, Entity] = {}
        for ent in entities:
            if ent.get("disabled_by") or ent.get("hidden_by"):
                continue
            eid = ent["entity_id"]
            st = state_by_id.get(eid, {})
            attrs = st.get("attributes") or {}
            result[eid] = Entity(
                entity_id=eid,
                name=ent.get("name") or ent.get("original_name") or attrs.get("friendly_name") or eid,
                area_id=ent.get("area_id") or device_area.get(ent.get("device_id") or ""),
                device_class=attrs.get("device_class") or ent.get("original_device_class"),
                state=st.get("state", "unknown"),
                attributes=attrs,
                device_id=ent.get("device_id") or None,
                platform=ent.get("platform") or None,
                entity_category=ent.get("entity_category") or None,
            )

        # Entities without a unique_id never appear in the registry but do have states
        # (YAML-defined helpers, template entities). Include them with no area.
        for eid, st in state_by_id.items():
            if eid in result:
                continue
            attrs = st.get("attributes") or {}
            result[eid] = Entity(
                entity_id=eid,
                name=attrs.get("friendly_name") or eid,
                device_class=attrs.get("device_class"),
                state=st.get("state", "unknown"),
                attributes=attrs,
            )
        return cls(area_objs, result.values(), device_objs)

    @classmethod
    def from_json(cls, path: str | Path) -> Registry:
        """A saved snapshot (tests, the demo). Unknown keys are dropped."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            [Area(**_only(Area, a)) for a in data.get("areas", [])],
            [Entity(**_only(Entity, e)) for e in data.get("entities", [])],
            [Device(**_only(Device, d)) for d in data.get("devices", [])],
        )


def ignore_problems(
    registry: Registry, areas: Iterable[str] = (), patterns: Iterable[str] = (), integrations: Iterable[str] = ()
) -> list[str]:
    """IGNORE_* entries that hide nothing — usually a typo or the wrong variable. Checked once, on the first sync."""
    platforms = {e.platform for e in registry.entities.values() if e.platform}
    out = []
    for a in areas:
        if a not in registry.areas:
            out.append(f"IGNORE_AREAS: no area with id {a!r}")
    for p in patterns:
        if any(fnmatch(eid, p) for eid in registry.entities):
            continue
        hint = ""
        if p in platforms:
            hint = f" — {p!r} is an integration: put it into IGNORE_INTEGRATIONS"
        elif "*" not in p and "?" not in p:
            hint = f" — patterns match the whole entity_id, try *{p}*"
        out.append(f"IGNORE_ENTITIES: {p!r} matches no entity_id{hint}")
    for i in integrations:
        if i not in platforms:
            out.append(f"IGNORE_INTEGRATIONS: no entity comes from {i!r}")
    return out

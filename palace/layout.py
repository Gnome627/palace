"""palace.yaml — what the user arranged by hand: map positions, icons, hidden cards, the order of areas and cards.

    areas: [gostinaya, kuhnya]          # order of the area blocks; unknown areas keep their place, new ones go after
    cards:
      gostinaya: [dev:abc123, ent:light.torsher]   # order inside the block
    devices:
      dev:abc123: {x: 0.31, y: 0.52, icon: chandelier, hidden: true}   # x/y — fractions of the map

Everything is optional: a card the file does not mention is laid out by the page and shown.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

HEADER = "# Palace: map positions, the order of areas and cards, icons, hidden cards. Written by the page.\n"


def empty() -> dict:
    return {"areas": [], "cards": {}, "devices": {}}


def load(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return empty()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return normalize(raw)


def save(path: str | Path, layout: dict) -> dict:
    layout = normalize(layout)
    text = yaml.safe_dump(layout, allow_unicode=True, sort_keys=False, default_flow_style=None, width=120)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(HEADER + text, encoding="utf-8")
    tmp.replace(path)   # a crash mid-write must not leave half a file
    return layout


def _clamp(v: Any) -> float | None:
    try:
        return min(1.0, max(0.0, round(float(v), 4)))
    except (TypeError, ValueError):
        return None


def normalize(raw: Any) -> dict:
    """Keep only what the file may hold, in its shape; drop the rest silently."""
    if not isinstance(raw, dict):
        raise ValueError("layout must be a mapping")
    out = empty()
    areas = raw.get("areas") or []
    if not isinstance(areas, list):
        raise ValueError("areas must be a list")
    out["areas"] = [str(a) for a in areas if isinstance(a, str) and a]

    cards = raw.get("cards") or {}
    if not isinstance(cards, dict):
        raise ValueError("cards must be a mapping")
    for area, ids in cards.items():
        if isinstance(ids, list):
            kept = [str(i) for i in ids if isinstance(i, str) and i]
            if kept:
                out["cards"][str(area)] = kept

    devices = raw.get("devices") or {}
    if not isinstance(devices, dict):
        raise ValueError("devices must be a mapping")
    for cid, spec in devices.items():
        if not isinstance(spec, dict):
            continue
        entry: dict[str, Any] = {}
        x, y = _clamp(spec.get("x")), _clamp(spec.get("y"))
        if x is not None and y is not None:
            entry["x"], entry["y"] = x, y
        icon = spec.get("icon")
        if isinstance(icon, str) and icon:
            entry["icon"] = icon.removeprefix("mdi:")
        if spec.get("hidden"):
            entry["hidden"] = True
        if entry:
            out["devices"][str(cid)] = entry
    return out

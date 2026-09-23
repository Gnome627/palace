"""The panel behind the page: the HA client, the layout file, actions and two change counters.

Following the house. The page listens to /api/events and fetches the picture when a counter moves.
`version` moves when something switchable changes state or a shown attribute (an automation dimming a lamp),
when a device appears or disappears (availability), and on every registry sync — the page applies it at once.
`readings` moves on sensor values; the page takes those at most every half a minute, or a power meter
reporting every second would redraw it all the time.

Acting. An action is done when HA says the state changed, not when the service call returns: the call is sent,
then the panel waits for state_changed of every entity that should move (toggle: the state itself; a call: state
or attributes). Nothing within `confirm_timeout` → PanelUnconfirmed. While an entity waits, another action on it
is refused (PanelBusy) — a second tab or a script cannot pile commands on top of one that is still under way.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from . import layout as layout_file
from .house import CONTROLS, NOT_AVAILABLE, READOUTS, SHOWN_ATTRIBUTES, Card, allowed_service, build_cards, is_on, toggle_calls
from .registry import Registry

log = logging.getLogger(__name__)

# services that may well change nothing (stop what is not moving) — done when HA accepts them
MAY_CHANGE_NOTHING = frozenset({"stop_cover", "stop", "pause"})


class PanelError(ValueError):
    """The panel refuses: no such card, nothing to switch, a service it does not do."""


class PanelBusy(PanelError):
    """The previous action on the same entity is still waiting for HA."""


class PanelUnconfirmed(PanelError):
    """HA took the call, but the state did not change in time."""


@dataclass(eq=False)
class _Waiter:
    """One action waiting for one entity to change."""
    attributes: bool   # an attribute change counts (a brightness), not only the state
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())


def _shown(state: dict | None) -> dict:
    """The attributes the page draws from; the rest (link quality, last_seen…) changes all the time and means nothing here."""
    attrs = (state or {}).get("attributes") or {}
    return {k: attrs[k] for k in SHOWN_ATTRIBUTES if k in attrs}


class Panel:
    def __init__(self, ha, layout_path: str | Path, confirm_timeout: float = 10.0):
        self.ha = ha
        self.layout_path = Path(layout_path)
        self.confirm_timeout = confirm_timeout
        self.version = 1
        self.readings = 1
        self._changed = asyncio.Event()   # set and replaced on every move of either counter
        self._in_flight: set[str] = set()
        self._waiting: dict[str, list[_Waiter]] = {}
        ha.on_state(self._on_state)
        ha.on_registry(self._on_registry)

    # --- what the page sees ------------------------------------------------

    @property
    def registry(self) -> Registry:
        return self.ha.registry

    @property
    def connected(self) -> bool:
        return self.ha.connected.is_set()

    @property
    def idle(self) -> bool:
        """No action under way."""
        return not self._in_flight and not self._waiting

    def cards(self) -> list[Card]:
        return build_cards(self.registry)

    def card(self, card_id: str) -> Card:
        for c in self.cards():
            if c.id == card_id:
                return c
        raise PanelError(f"no such card: {card_id}")

    def state(self) -> dict:
        return {"version": self.version, "readings": self.readings, "ha_connected": self.connected}

    def snapshot(self) -> dict:
        return {
            **self.state(),
            "areas": [{"id": a.id, "name": a.name} for a in self.registry.areas.values()],
            "cards": [c.to_dict() for c in self.cards()],
            "layout": self.layout(),
        }

    async def wait_change(self, timeout: float) -> None:
        """Until a counter moves, or `timeout` seconds pass — whichever first."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._changed.wait(), timeout)

    # --- the layout file ---------------------------------------------------

    def layout(self) -> dict:
        try:
            return layout_file.load(self.layout_path)
        except (ValueError, OSError) as exc:
            log.warning("layout %s unreadable (%s); starting empty", self.layout_path, exc)
            return layout_file.empty()

    def save_layout(self, data: dict) -> dict:
        try:
            saved = layout_file.save(self.layout_path, data)
        except ValueError as exc:
            raise PanelError(str(exc)) from exc
        hidden = sum(1 for d in saved["devices"].values() if d.get("hidden"))
        log.info("layout saved: %d placed, %d hidden", len(saved["devices"]), hidden)
        return saved

    # --- doing things ------------------------------------------------------

    async def toggle(self, card_id: str) -> Card:
        """Flip the card: everything off if it is on, everything on if not. Returns when HA reports it."""
        card = self.card(card_id)
        if card.on is None:
            raise PanelError("nothing to switch")
        calls = toggle_calls(card)
        if not calls:
            raise PanelError("nothing available to switch")
        # only what will move is waited for: a chandelier with one bulb already off must not wait for that bulb
        moving = [e.entity_id for e in card.switches if e.state not in NOT_AVAILABLE and is_on(e) == card.on]
        targets = [eid for _domain, _service, ids in calls for eid in ids]
        with self._claim(targets), self._watch(moving, attributes=False) as changed:
            for domain, service, ids in calls:
                await self.ha.call_service(domain, service, ids)
            await self._confirm(changed)
        return card

    async def call(self, entity_id: str, service: str, data: dict | None = None) -> None:
        """One service on one entity (brightness, position, mode…). Returns when HA reports the change."""
        e = self.registry.entities.get(entity_id)
        if e is None:
            raise PanelError(f"unknown entity: {entity_id}")
        if not allowed_service(e.domain, service):
            raise PanelError(f"{service} is not something Palace does with {e.domain}")
        watched = [] if service in MAY_CHANGE_NOTHING else [entity_id]
        with self._claim([entity_id]), self._watch(watched, attributes=True) as changed:
            await self.ha.call_service(e.domain, service, [entity_id], data or None)
            await self._confirm(changed)

    async def resync(self) -> None:
        if self.connected:
            await self.ha.resync()

    @contextmanager
    def _claim(self, entity_ids: list[str]):
        if any(eid in self._in_flight for eid in entity_ids):
            raise PanelBusy("the previous action is still under way")
        self._in_flight.update(entity_ids)
        try:
            yield
        finally:
            self._in_flight.difference_update(entity_ids)

    @contextmanager
    def _watch(self, entity_ids: list[str], attributes: bool):
        """Futures that resolve when each entity changes. Listening starts before the call goes out:
        an optimistic integration reports the new state before HA even answers the call."""
        mine = [(eid, _Waiter(attributes)) for eid in entity_ids]
        for eid, w in mine:
            self._waiting.setdefault(eid, []).append(w)
        try:
            yield [w.future for _eid, w in mine]
        finally:
            for eid, w in mine:
                w.future.cancel()
                self._waiting[eid].remove(w)
                if not self._waiting[eid]:
                    del self._waiting[eid]

    async def _confirm(self, futures: list[asyncio.Future]) -> None:
        if not futures:
            return
        _done, pending = await asyncio.wait(futures, timeout=self.confirm_timeout)
        if pending:
            raise PanelUnconfirmed(f"HA accepted the command, but the state did not change in {self.confirm_timeout:g} s")

    # --- following the house -------------------------------------------------

    def _on_state(self, entity_id: str, old: dict | None, new: dict) -> None:
        moved = (old or {}).get("state") != new.get("state")
        attributes_moved = (old or {}).get("attributes") != new.get("attributes")
        for w in self._waiting.get(entity_id, ()):
            if not w.future.done() and (moved or (w.attributes and attributes_moved)):
                w.future.set_result(None)
        self._count(entity_id, old, new, moved)

    def _count(self, entity_id: str, old: dict | None, new: dict, moved: bool) -> None:
        e = self.registry.entities.get(entity_id)
        if e is None:
            return
        went = ((old or {}).get("state") in NOT_AVAILABLE) != (new.get("state") in NOT_AVAILABLE)
        if e.domain in CONTROLS:
            if moved or _shown(old) != _shown(new):
                self._bump("version")
        elif went:
            self._bump("version")
        elif e.domain in READOUTS and moved:
            self._bump("readings")

    def _on_registry(self, _registry: Registry) -> None:
        self._bump("version")

    def _bump(self, counter: str) -> None:
        setattr(self, counter, getattr(self, counter) + 1)
        self._changed.set()
        self._changed = asyncio.Event()

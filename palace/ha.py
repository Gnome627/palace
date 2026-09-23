"""Home Assistant websocket client: keeps the Registry fresh and calls services.

One long-lived websocket with a long-lived access token: syncs areas/devices/entities/states on connect
and on registry change events, follows state_changed, calls services, reconnects with backoff.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

import aiohttp

from .registry import Registry, ignore_problems

log = logging.getLogger(__name__)

RegistryListener = Callable[[Registry], Awaitable[None] | None]
# (entity_id, old state dict or None, new state dict) — the raw HA state_changed payload
StateListener = Callable[[str, dict | None, dict], None]


class HAError(RuntimeError):
    pass


class HAOffline(HAError):
    """No link to HA right now: the command did not go out at all."""


class HAAuthError(HAError):
    """The token was refused: retrying will not help, but HA might have been restored from a backup — keep trying slowly."""


class HAClient:
    def __init__(
        self,
        url: str,
        token: str,
        resync_interval: int = 900,
        ignore_areas: Iterable[str] = (),
        ignore_entities: Iterable[str] = (),
        ignore_integrations: Iterable[str] = (),
    ):
        self.url = url.rstrip("/")
        self.token = token
        self.resync_interval = resync_interval
        self.ignore_areas = list(ignore_areas)
        self.ignore_entities = list(ignore_entities)
        self.ignore_integrations = list(ignore_integrations)
        self._checked_ignores = False
        self.registry = Registry()
        self.connected = asyncio.Event()

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subscriptions: dict[int, Callable[[dict], Any]] = {}
        self._listeners: list[RegistryListener] = []
        self._state_listeners: list[StateListener] = []
        self._resync_task: asyncio.Task | None = None

    # --- public API --------------------------------------------------------

    def on_registry(self, listener: RegistryListener) -> None:
        self._listeners.append(listener)

    def on_state(self, listener: StateListener) -> None:
        """Called on every state_changed after the registry has taken the new state."""
        self._state_listeners.append(listener)

    async def run(self) -> None:
        """Connect and keep the connection alive forever."""
        backoff = 1
        while True:
            try:
                await self._connect_and_serve()
                backoff = 1
            except asyncio.CancelledError:
                raise
            except HAAuthError as exc:
                self.connected.clear()
                log.error("%s — check HA_TOKEN; retry in 60s", exc)
                await asyncio.sleep(60)
            except Exception as exc:
                self.connected.clear()
                log.warning("HA connection lost (%s); retry in %ss", exc or type(exc).__name__, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def call_service(self, domain: str, service: str, entity_ids: list[str], data: dict | None = None) -> None:
        if not self.connected.is_set():
            raise HAOffline("not connected to Home Assistant")
        await self._call("call_service", domain=domain, service=service, service_data=data or {},
                         target={"entity_id": entity_ids})

    async def resync(self) -> Registry:
        areas, devices, entities, states = await asyncio.gather(
            self._call("config/area_registry/list"),
            self._call("config/device_registry/list"),
            self._call("config/entity_registry/list"),
            self._call("get_states"),
        )
        full = Registry.from_ha(areas, devices, entities, states)
        if not self._checked_ignores:
            self._checked_ignores = True
            for problem in ignore_problems(full, self.ignore_areas, self.ignore_entities, self.ignore_integrations):
                log.warning("%s", problem)
        self.registry = full.without(self.ignore_areas, self.ignore_entities, self.ignore_integrations)
        log.info("registry synced: %d areas, %d devices, %d entities",
                 len(self.registry.areas), len(self.registry.devices), len(self.registry.entities))
        for listener in self._listeners:
            res = listener(self.registry)
            if asyncio.iscoroutine(res):
                await res
        return self.registry

    # --- internals ---------------------------------------------------------

    async def _connect_and_serve(self) -> None:
        ws_url = self.url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
        async with aiohttp.ClientSession() as session, session.ws_connect(ws_url, heartbeat=30) as ws:
            self._ws = ws
            await self._authenticate(ws)
            reader = asyncio.create_task(self._reader(ws))
            try:
                await self._subscribe("state_changed", self._on_state_changed)
                for event in ("entity_registry_updated", "area_registry_updated", "device_registry_updated"):
                    await self._subscribe(event, self._on_registry_changed)
                await self.resync()
                self.connected.set()
                log.info("connected to Home Assistant at %s", self.url)
                while not reader.done():
                    await asyncio.wait({reader}, timeout=self.resync_interval)
                    if not reader.done():
                        await self.resync()
                reader.result()
            finally:
                self.connected.clear()
                reader.cancel()
                self._fail_pending(HAOffline("connection to Home Assistant closed"))
                self._ws = None

    async def _authenticate(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        hello = await ws.receive_json()
        if hello.get("type") != "auth_required":
            raise HAError(f"unexpected hello: {hello}")
        await ws.send_json({"type": "auth", "access_token": self.token})
        reply = await ws.receive_json()
        if reply.get("type") != "auth_ok":
            raise HAAuthError(f"auth failed: {reply.get('message')}")

    async def _reader(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                break
            data = msg.json()
            mtype = data.get("type")
            if mtype == "result":
                fut = self._pending.pop(data["id"], None)
                if fut is None or fut.done():
                    continue
                if data.get("success"):
                    fut.set_result(data.get("result"))
                else:
                    err = data.get("error") or {}
                    fut.set_exception(HAError(err.get("message") or str(err)))
            elif mtype == "event":
                handler = self._subscriptions.get(data["id"])
                if handler:
                    try:
                        handler(data["event"])
                    except Exception:
                        log.exception("event handler failed")
        raise HAError("websocket closed")

    async def _call(self, msg_type: str, **payload: Any) -> Any:
        if self._ws is None:
            raise HAOffline("not connected to Home Assistant")
        self._msg_id += 1
        mid = self._msg_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self._ws.send_json({"id": mid, "type": msg_type, **payload})
        return await asyncio.wait_for(fut, timeout=30)

    async def _subscribe(self, event_type: str, handler: Callable[[dict], Any]) -> None:
        self._msg_id += 1
        mid = self._msg_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        self._subscriptions[mid] = handler
        await self._ws.send_json({"id": mid, "type": "subscribe_events", "event_type": event_type})
        await asyncio.wait_for(fut, timeout=30)

    def _fail_pending(self, exc: Exception) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()
        self._subscriptions.clear()

    def _on_state_changed(self, event: dict) -> None:
        data = event.get("data", {})
        new = data.get("new_state")
        if new:
            self.registry.update_state(new["entity_id"], new["state"], new.get("attributes") or {})
            for listener in self._state_listeners:
                listener(new["entity_id"], data.get("old_state"), new)

    def _on_registry_changed(self, _event: dict) -> None:
        # Registry events come in bursts during HA reloads; debounce them.
        # Must not block the reader: resync() itself waits for replies the reader delivers.
        if self._resync_task and not self._resync_task.done():
            self._resync_task.cancel()
        self._resync_task = asyncio.create_task(self._debounced_resync())

    async def _debounced_resync(self) -> None:
        await asyncio.sleep(2)
        try:
            await self.resync()
        except Exception as exc:
            log.warning("registry resync failed: %s", exc)

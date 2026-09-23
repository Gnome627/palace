"""HTTP for the panel: /api/* and the page at /.

  GET  /api/state            {version, readings, ha_connected, auth, confirm_timeout} — also the healthcheck
  GET  /api/events           the same as server-sent events, one on every change — the page follows the house by it
  GET  /api/house            areas, cards, layout — the whole picture
  POST /api/refresh          resync the registry from HA, then the same as /house
  POST /api/toggle           {"id": card id} → flip every switchable entity of the card
  POST /api/call             {"entity_id", "service", "data"} → one HA service on one entity
  GET/PUT /api/layout        palace.yaml as JSON; PUT writes the file

Toggle and call answer when HA reports the change. Every failure is {"detail": {"code", "message"}}: the page
words it by the code in the user's language; the message is English, for logs and for the curious —
  401 unauthorized, 400 refused, 429 busy (the entity still waits), 502 ha_error (HA's own message),
  503 ha_offline (the command did not go out), 504 unconfirmed (no change in time).

With API_KEY empty everything is open, otherwise X-Api-Key. /api/state and /api/events stay open: they carry
counters, not the house (and EventSource cannot send a header).
"""
from __future__ import annotations

import hmac
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ha import HAError, HAOffline
from .panel import Panel, PanelBusy, PanelError, PanelUnconfirmed

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"

PING_EVERY = 15.0   # s: a comment line keeps proxies from closing a quiet stream
CHECK_EVERY = 5.0   # s: the HA link has no event of its own — its state is looked at this often

# the first match wins: subclasses before their bases
FAILURES: tuple[tuple[type[Exception], int, str], ...] = (
    (PanelBusy, 429, "busy"),
    (PanelUnconfirmed, 504, "unconfirmed"),
    (PanelError, 400, "refused"),
    (HAOffline, 503, "ha_offline"),
    (HAError, 502, "ha_error"),
)


def failure(exc: Exception) -> HTTPException:
    for cls, status, code in FAILURES:
        if isinstance(exc, cls):
            return HTTPException(status_code=status, detail={"code": code, "message": str(exc)})
    raise exc


async def event_stream(panel: Panel, extra: dict, is_disconnected: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
    """SSE: the state now, then again whenever it differs; a ping when nothing was sent for a while."""
    yield "retry: 3000\n\n"
    last, sent_at = None, time.monotonic()
    while not await is_disconnected():
        now = {**panel.state(), **extra}
        if now != last:
            yield f"data: {json.dumps(now)}\n\n"
            last, sent_at = now, time.monotonic()
        elif time.monotonic() - sent_at >= PING_EVERY:
            yield ": ping\n\n"
            sent_at = time.monotonic()
        await panel.wait_change(CHECK_EVERY)


class ToggleIn(BaseModel):
    id: str


class CallIn(BaseModel):
    entity_id: str
    service: str
    data: dict[str, Any] | None = None


def create_app(panel: Panel, api_key: str = "") -> FastAPI:
    app = FastAPI(title="Palace", docs_url=None, redoc_url=None)
    api = APIRouter(prefix="/api")
    extra = {"auth": bool(api_key), "confirm_timeout": panel.confirm_timeout}

    def require_key(x_api_key: str = Header(default="")) -> None:
        if api_key and not hmac.compare_digest(x_api_key, api_key):
            raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "bad api key"})

    async def do(coro: Awaitable[Any]) -> Any:
        try:
            return await coro
        except (PanelError, HAError) as exc:
            log.warning("action failed: %s", exc)
            raise failure(exc) from exc

    @api.get("/state")
    async def state() -> dict:
        return {**panel.state(), **extra}

    @api.get("/events")
    async def events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            event_stream(panel, extra, request.is_disconnected),
            media_type="text/event-stream",
            # nginx and friends must pass it through as it comes
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @api.get("/house", dependencies=[Depends(require_key)])
    async def house() -> dict:
        return panel.snapshot()

    @api.post("/refresh", dependencies=[Depends(require_key)])
    async def refresh() -> dict:
        await do(panel.resync())
        return panel.snapshot()

    @api.post("/toggle", dependencies=[Depends(require_key)])
    async def toggle(body: ToggleIn) -> dict:
        card = await do(panel.toggle(body.id))
        return {"id": card.id, "was_on": card.on}

    @api.post("/call", dependencies=[Depends(require_key)])
    async def call(body: CallIn) -> dict:
        await do(panel.call(body.entity_id, body.service, body.data))
        return {"ok": True}

    @api.get("/layout", dependencies=[Depends(require_key)])
    async def get_layout() -> dict:
        return panel.layout()

    @api.put("/layout", dependencies=[Depends(require_key)])
    async def put_layout(body: dict) -> dict:
        try:
            return panel.save_layout(body)
        except PanelError as exc:
            raise failure(exc) from exc

    app.include_router(api)
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app

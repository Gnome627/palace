"""The HTTP API: what the page gets, how failures are coded, the event stream."""
import asyncio

import httpx

from palace.panel import Panel
from palace.server import create_app, event_stream
from tests.fakes import BrokenHA, FakeHA, OfflineHA, ReportingHA, make_house


async def test_api(tmp_path):
    ha = ReportingHA(make_house())
    panel = Panel(ha, tmp_path / "palace.yaml")
    app = create_app(panel, "secret")
    h = {"X-Api-Key": "secret"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        state = {"version": 1, "readings": 1, "ha_connected": True, "auth": True, "confirm_timeout": 10.0}
        assert (await c.get("/api/state")).json() == state
        assert (await c.get("/api/house")).status_code == 401

        r = await c.get("/api/house", headers=h)
        body = r.json()
        assert [a["id"] for a in body["areas"]] == ["gostinaya", "spalnya"]
        lamp = next(x for x in body["cards"] if x["id"] == "dev:d-lamp")
        assert lamp["on"] is True and lamp["battery"] == 42 and lamp["platform"] == "zha" and lamp["icon"] == "lightbulb"
        assert lamp["entities"][0]["attributes"]["brightness"] == 120
        assert body["layout"] == {"areas": [], "cards": {}, "devices": {}}

        r = await c.post("/api/toggle", json={"id": "dev:d-lamp"}, headers=h)
        assert r.status_code == 200 and ha.calls[-1] == ("light", "turn_off", ["light.torsher"], {})
        r = await c.post("/api/toggle", json={"id": "dev:d-therm"}, headers=h)
        assert r.status_code == 400

        position = {"entity_id": "cover.curtains", "service": "set_cover_position", "data": {"position": 40}}
        r = await c.post("/api/call", json=position, headers=h)
        assert r.status_code == 200 and ha.calls[-1] == ("cover", "set_cover_position", ["cover.curtains"], {"position": 40})
        r = await c.post("/api/call", json={"entity_id": "cover.curtains", "service": "turn_on"}, headers=h)
        assert r.status_code == 400

        placed = {"areas": ["spalnya"], "devices": {"dev:d-lamp": {"x": 0.1, "y": 0.2, "hidden": True}}}
        r = await c.put("/api/layout", json=placed, headers=h)
        assert r.status_code == 200 and r.json()["devices"]["dev:d-lamp"]["hidden"] is True
        assert (tmp_path / "palace.yaml").exists()
        assert (await c.get("/api/layout", headers=h)).json()["areas"] == ["spalnya"]
        r = await c.put("/api/layout", json={"areas": "x"}, headers=h)
        assert r.status_code == 400

        v = panel.version
        r = await c.post("/api/refresh", headers=h)
        assert r.status_code == 200 and ha.resyncs == 1 and r.json()["version"] == v + 1

        r = await c.get("/")
        assert r.status_code == 200 and "Palace" in r.text
        assert (await c.get("/assets/chain.wav")).status_code == 200


async def test_api_reports_ha_errors(tmp_path):
    panel = Panel(BrokenHA(make_house()), tmp_path / "palace.yaml")
    app = create_app(panel, "")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/toggle", json={"id": "dev:d-lamp"})
        assert r.status_code == 502
        assert r.json()["detail"] == {"code": "ha_error", "message": "Failed to call service light/turn_off: device offline in the cloud"}
    app = create_app(Panel(OfflineHA(make_house()), tmp_path / "palace.yaml"), "")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/toggle", json={"id": "dev:d-lamp"})
        assert r.status_code == 503 and r.json()["detail"]["code"] == "ha_offline"
        r = await c.post("/api/toggle", json={"id": "dev:d-therm"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "refused"


async def test_api_status_codes_for_failures(tmp_path):
    ha = ReportingHA(make_house(), silent={"light.torsher"})
    app = create_app(Panel(ha, tmp_path / "palace.yaml", confirm_timeout=0.05), "")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/toggle", json={"id": "dev:d-lamp"})
        assert r.status_code == 504 and r.json()["detail"]["code"] == "unconfirmed"
        assert (await c.post("/api/toggle", json={"id": "dev:d-lustra"})).status_code == 200
    app = create_app(Panel(BrokenHA(make_house()), tmp_path / "palace.yaml"), "")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post("/api/toggle", json={"id": "dev:d-lamp"})).status_code == 502


async def test_event_stream_sends_the_state_on_every_change(tmp_path):
    ha = FakeHA(make_house())
    panel = Panel(ha, tmp_path / "palace.yaml")
    stream = event_stream(panel, {"auth": False}, lambda: asyncio.sleep(0, False))
    assert await anext(stream) == "retry: 3000\n\n"
    first = await anext(stream)
    assert first.startswith("data: ") and '"version": 1' in first and '"auth": false' in first
    nxt = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.01)
    assert not nxt.done(), "nothing changed, nothing sent"
    ha.change("light.lustra_2", "on")   # an automation switched it
    assert '"version": 2' in await asyncio.wait_for(nxt, 0.5)
    await stream.aclose()

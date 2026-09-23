"""The panel: actions that wait for HA to report the change, and the counters the page follows."""
import asyncio

import pytest

from palace.ha import HAError
from palace.panel import Panel, PanelBusy, PanelError, PanelUnconfirmed
from tests.fakes import BrokenHA, FakeHA, ReportingHA, make_house


def test_version_moves_on_switches_not_on_readings(tmp_path):
    ha = FakeHA(make_house())
    panel = Panel(ha, tmp_path / "palace.yaml")
    v = panel.version
    ha.change("sensor.temp", "22.0")
    assert panel.version == v, "a thermometer must not light the button"
    ha.change("light.lustra_2", "on")
    assert panel.version == v + 1
    ha.change("light.lustra_2", "on")
    assert panel.version == v + 1, "same state again is not a change"
    ha.change("sensor.temp", "unavailable")
    assert panel.version == v + 2, "a device dropping off is worth a look"
    ha.change("sensor.other", "1")   # not in the registry
    assert panel.version == v + 2


async def test_panel_toggle_and_call(tmp_path):
    ha = ReportingHA(make_house())
    panel = Panel(ha, tmp_path / "palace.yaml")
    await panel.toggle("dev:d-lustra")
    assert ha.calls == [("light", "turn_off", ["light.lustra_1", "light.lustra_2"], {})]
    with pytest.raises(PanelError):
        await panel.toggle("dev:d-therm")
    with pytest.raises(PanelError):
        await panel.toggle("dev:nope")
    await panel.call("light.torsher", "turn_on", {"brightness": 200})
    assert ha.calls[-1] == ("light", "turn_on", ["light.torsher"], {"brightness": 200})
    with pytest.raises(PanelError):
        await panel.call("light.torsher", "set_cover_position")
    with pytest.raises(PanelError):
        await panel.call("sensor.temp", "turn_on")
    v = panel.version
    await panel.resync()
    assert ha.resyncs == 1 and panel.snapshot()["version"] == v + 1


async def test_action_returns_when_the_state_changed(tmp_path):
    ha = ReportingHA(make_house(), delay=0.05)
    panel = Panel(ha, tmp_path / "palace.yaml", confirm_timeout=1)
    await panel.toggle("dev:d-lustra")
    assert ha.registry.entities["light.lustra_1"].state == "off", "answered only after HA had the new state"
    await panel.call("light.torsher", "turn_on", {"brightness": 30})   # already on: attributes are the change
    assert ha.registry.entities["light.torsher"].attributes["brightness"] == 30
    assert panel.idle


async def test_change_reported_before_the_call_returns_counts(tmp_path):
    """An optimistic integration: state_changed arrives before HA answers the call."""
    class Optimistic(ReportingHA):
        async def call_service(self, domain, service, entity_ids, data=None):
            await super().call_service(domain, service, entity_ids, data)
            await asyncio.sleep(0.05)   # the answer comes after the event

    panel = Panel(Optimistic(make_house()), tmp_path / "palace.yaml", confirm_timeout=0.02)
    await panel.toggle("dev:d-lamp")


async def test_toggle_waits_only_for_what_moves(tmp_path):
    """A chandelier with one bulb on, one off: switching it off moves only the bulb that is on."""
    ha = ReportingHA(make_house(), silent={"light.lustra_2"})
    panel = Panel(ha, tmp_path / "palace.yaml", confirm_timeout=0.1)
    await panel.toggle("dev:d-lustra")


async def test_no_change_in_time_is_unconfirmed(tmp_path):
    ha = ReportingHA(make_house(), silent={"light.torsher"})
    panel = Panel(ha, tmp_path / "palace.yaml", confirm_timeout=0.05)
    with pytest.raises(PanelUnconfirmed):
        await panel.toggle("dev:d-lamp")
    assert ha.calls == [("light", "turn_off", ["light.torsher"], {})], "the command did go out"
    assert panel.idle
    await panel.call("cover.curtains", "stop_cover")   # may change nothing: done when HA accepts it


async def test_attribute_noise_does_not_confirm_a_toggle(tmp_path):
    """A zigbee lamp updates its link quality all the time; that is not the lamp switching."""
    ha = ReportingHA(make_house(), silent={"light.torsher"})
    panel = Panel(ha, tmp_path / "palace.yaml", confirm_timeout=0.1)
    task = asyncio.create_task(panel.toggle("dev:d-lamp"))
    await asyncio.sleep(0.02)
    for fn in ha.state_listeners:
        fn("light.torsher", {"state": "on", "attributes": {"linkquality": 90}}, {"state": "on", "attributes": {"linkquality": 88}})
    with pytest.raises(PanelUnconfirmed):
        await task


async def test_second_action_while_waiting_is_refused(tmp_path):
    ha = ReportingHA(make_house(), delay=0.05)
    panel = Panel(ha, tmp_path / "palace.yaml", confirm_timeout=1)
    first = asyncio.create_task(panel.toggle("dev:d-lustra"))
    await asyncio.sleep(0.01)
    with pytest.raises(PanelBusy):
        await panel.toggle("dev:d-lustra")
    with pytest.raises(PanelBusy):
        await panel.call("light.lustra_2", "turn_on")   # a bulb of the same chandelier
    await panel.call("light.torsher", "turn_off")      # another device is free
    await first
    await panel.toggle("dev:d-lustra")                 # free again as soon as HA reported the change
    assert len(ha.calls) == 3


async def test_ha_error_frees_the_entity(tmp_path):
    panel = Panel(BrokenHA(make_house()), tmp_path / "palace.yaml", confirm_timeout=1)
    with pytest.raises(HAError):
        await panel.toggle("dev:d-lamp")
    assert panel.idle
    with pytest.raises(HAError):   # not PanelBusy: nothing is waiting any more
        await panel.toggle("dev:d-lamp")


def test_counters_follow_the_house(tmp_path):
    ha = FakeHA(make_house())
    panel = Panel(ha, tmp_path / "palace.yaml")
    emit = ha.emit
    v, r = panel.version, panel.readings

    emit("light.torsher", {"state": "on", "attributes": {"brightness": 120}}, {"state": "on", "attributes": {"brightness": 40}})
    assert (panel.version, panel.readings) == (v + 1, r), "an automation dimming the lamp is a change"
    emit("light.torsher", {"state": "on", "attributes": {"brightness": 40, "linkquality": 90}},
         {"state": "on", "attributes": {"brightness": 40, "linkquality": 80}})
    assert panel.version == v + 1, "link quality is noise"
    emit("sensor.temp", {"state": "21.5"}, {"state": "21.6"})
    assert (panel.version, panel.readings) == (v + 1, r + 1), "a reading moves only the readings"
    emit("sensor.temp", {"state": "21.6"}, {"state": "unavailable"})
    assert panel.version == v + 2, "a thermometer dropping off is a change of the picture"


async def test_wait_change_wakes_on_a_change(tmp_path):
    ha = FakeHA(make_house())
    panel = Panel(ha, tmp_path / "palace.yaml")
    waiter = asyncio.create_task(panel.wait_change(5))
    await asyncio.sleep(0.01)
    ha.change("light.lustra_2", "on")
    await asyncio.wait_for(waiter, 0.5)
    await panel.wait_change(0.01)   # nothing happens: just the timeout

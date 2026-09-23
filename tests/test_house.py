"""Cards out of the registry: grouping, what a click switches, icons, batteries."""
from palace.house import build_cards, entity_view, toggle_calls
from palace.registry import Device, Entity, Registry
from tests.fakes import make_house


def cards_by_id(reg):
    return {c.id: c for c in build_cards(reg)}


def test_cards_group_by_device_and_skip_other_domains():
    cards = cards_by_id(make_house())
    assert set(cards) == {"dev:d-lamp", "dev:d-lustra", "dev:d-cur", "dev:d-therm", "ent:switch.template"}
    lamp = cards["dev:d-lamp"]
    assert lamp.name == "Торшер" and lamp.area_id == "gostinaya" and lamp.platform == "zha"
    assert [e.entity_id for e in lamp.controls] == ["light.torsher", "switch.torsher_dnd"]
    assert lamp.battery == 42 and lamp.on is True and lamp.available
    assert lamp.manufacturer == "IKEA"


def test_config_switch_is_not_the_lamp():
    """A Zigbee bulb's "do not disturb" switch (entity_category=config) must not go with the lamp on the map."""
    lamp = cards_by_id(make_house())["dev:d-lamp"]
    assert [e.entity_id for e in lamp.switches] == ["light.torsher"]
    assert toggle_calls(lamp) == [("light", "turn_off", ["light.torsher"])]
    lamp.controls[0].state = "off"
    assert lamp.on is False, "the dnd switch is on, the lamp is off — the card is off"
    assert toggle_calls(lamp) == [("light", "turn_on", ["light.torsher"])]
    view = lamp.to_dict()["entities"]
    assert [(v["entity_id"], v["category"]) for v in view][:2] == [("light.torsher", None), ("switch.torsher_dnd", "config")]


def test_readout_only_card_is_off_and_not_switchable():
    therm = cards_by_id(make_house())["dev:d-therm"]
    assert therm.on is None and therm.available and therm.icon == "thermometer"
    assert toggle_calls(therm) == []


def test_unavailable_lone_entity():
    c = cards_by_id(make_house())["ent:switch.template"]
    assert c.area_id is None and not c.available and c.on is False
    assert toggle_calls(c) == []   # nothing to send to a dead entity


def test_toggle_mixed_chandelier_turns_everything_off():
    lustra = cards_by_id(make_house())["dev:d-lustra"]
    assert lustra.on is True
    assert toggle_calls(lustra) == [("light", "turn_off", ["light.lustra_1", "light.lustra_2"])]


def test_toggle_cover_opens():
    cur = cards_by_id(make_house())["dev:d-cur"]
    assert cur.on is False and cur.icon == "curtains"
    assert toggle_calls(cur) == [("cover", "open_cover", ["cover.curtains"])]


def test_entity_view_strips_device_name_and_ha_icon_travels():
    e = Entity("sensor.temp", "Термометр Температура", device_class="temperature", state="21.5",
               attributes={"icon": "mdi:thermometer-lines", "unit_of_measurement": "°C"})
    v = entity_view(e, "Термометр")
    assert v["name"] == "Температура" and v["attributes"] == {"unit_of_measurement": "°C", "icon": "mdi:thermometer-lines"}
    card = build_cards(Registry(entities=[e]))[0]
    assert card.icon == "thermometer" and card.ha_icon == "thermometer-lines"
    assert entity_view(Entity("light.x", "Торшер", state="on"), "Торшер")["name"] == ""


def test_card_icon_skips_battery_and_diagnostics():
    """A Zigbee button: battery and link quality only — neither should be its face."""
    reg = Registry(devices=[Device("d-btn", "Кнопка")], entities=[
        Entity("sensor.btn_battery", "Кнопка Батарея", device_class="battery", state="100", device_id="d-btn",
               entity_category="diagnostic"),
        Entity("sensor.btn_lq", "Кнопка Качество связи", state="120", device_id="d-btn", entity_category="diagnostic",
               attributes={"icon": "mdi:signal"}),
    ])
    card = build_cards(reg)[0]
    assert card.on is None and card.battery == 100 and card.ha_icon == "signal" and card.icon == "gauge"


def test_fixture_registry_builds_cards(registry):
    """A registry with no devices at all: every controllable entity becomes its own card."""
    ids = {c.id for c in build_cards(registry)}
    assert "ent:light.torsher_big" in ids and "ent:sensor.hall_temperature" in ids
    assert not any(i.startswith("ent:scene.") or i.startswith("ent:weather.") for i in ids)


def test_next_service_says_what_a_click_does():
    cards = cards_by_id(make_house())
    assert cards["dev:d-lamp"].next_service == "turn_off"
    assert cards["dev:d-cur"].next_service == "open_cover"
    assert cards["dev:d-therm"].next_service is None
    assert cards["dev:d-cur"].to_dict()["next"] == "open_cover"

"""The registry snapshot from HA's lists, and what IGNORE_* hides."""
from palace.house import build_cards
from palace.registry import Area, Device, Entity, Registry, ignore_problems


def test_registry_from_ha_and_ignores():
    reg = Registry.from_ha(
        areas=[{"area_id": "zal", "name": "Зал"}, {"area_id": "router", "name": "Роутер"}],
        devices=[{"id": "d1", "name": "Лампа", "name_by_user": "Торшер", "area_id": "zal", "manufacturer": "IKEA"}],
        entities=[
            {"entity_id": "light.lamp", "device_id": "d1", "platform": "zha", "original_name": None},
            {"entity_id": "switch.mikrotik_ether1", "area_id": "router", "platform": "mikrotik"},
            {"entity_id": "switch.old", "disabled_by": "user"},
        ],
        states=[
            {"entity_id": "light.lamp", "state": "on", "attributes": {"friendly_name": "Торшер", "brightness": 10}},
            {"entity_id": "switch.mikrotik_ether1", "state": "on", "attributes": {}},
            {"entity_id": "input_boolean.guest", "state": "off", "attributes": {"friendly_name": "Гости"}},
        ],
    ).without(["router"], ["switch.mikrotik_*"])
    assert set(reg.entities) == {"light.lamp", "input_boolean.guest"} and set(reg.areas) == {"zal"}
    lamp = reg.entities["light.lamp"]
    assert lamp.name == "Торшер" and lamp.area_id == "zal" and lamp.device_id == "d1" and lamp.platform == "zha"
    assert reg.devices["d1"].name == "Торшер"


def test_ignore_integrations_drop_the_whole_device():
    """The phone app and HA's own backup are integrations, not entity ids: their cards go by platform."""
    reg = Registry(
        devices=[Device("d-phone", "FOA-LX9"), Device("d-lamp", "Торшер")],
        entities=[
            Entity("sensor.foa_lx9_battery_level", "FOA-LX9 Battery", device_class="battery", state="80",
                   device_id="d-phone", platform="mobile_app"),
            Entity("binary_sensor.foa_lx9_charging", "FOA-LX9 Charging", state="off", device_id="d-phone", platform="mobile_app"),
            Entity("sensor.backup_state", "Backup State", state="idle", platform="backup"),
            Entity("light.torsher", "Торшер", state="on", device_id="d-lamp", platform="mqtt"),
        ],
    )
    kept = reg.without(platforms=["mobile_app", "backup"])
    assert {c.id for c in build_cards(kept)} == {"dev:d-lamp"}


def test_ignore_problems_point_at_the_right_variable():
    reg = Registry(
        areas=[Area("zal", "Зал")],
        entities=[
            Entity("sensor.mikrotik_hex_cpu", "CPU", platform="mikrotik_router"),
            Entity("sensor.backup_state", "Backup", platform="backup"),
        ],
    )
    problems = ignore_problems(reg, ["router"], ["backup", "mikrotik", "sensor.mikrotik_*"], ["mobile_app", "mikrotik_router"])
    assert problems == [
        "IGNORE_AREAS: no area with id 'router'",
        "IGNORE_ENTITIES: 'backup' matches no entity_id — 'backup' is an integration: put it into IGNORE_INTEGRATIONS",
        "IGNORE_ENTITIES: 'mikrotik' matches no entity_id — patterns match the whole entity_id, try *mikrotik*",
        "IGNORE_INTEGRATIONS: no entity comes from 'mobile_app'",
    ]

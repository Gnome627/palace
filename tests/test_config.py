"""Settings from the environment."""
from palace.config import Settings


def test_settings_from_env():
    cfg = Settings.from_env({
        "HA_URL": "http://10.0.0.2:8123", "HA_TOKEN": "t", "API_KEY": "",
        "IGNORE_AREAS": "router, servers,", "IGNORE_ENTITIES": "switch.mikrotik_*", "PORT": "9000",
        "IGNORE_INTEGRATIONS": "mobile_app,backup",
    })
    assert cfg.ignore_integrations == ["mobile_app", "backup"]
    assert cfg.ha_url == "http://10.0.0.2:8123" and cfg.ha_token == "t" and cfg.api_key == ""
    assert cfg.ignore_areas == ["router", "servers"] and cfg.ignore_entities == ["switch.mikrotik_*"]
    assert cfg.port == 9000 and cfg.resync_interval == 900 and cfg.layout_file == "palace.yaml"
    assert Settings.from_env({"PORT": " "}).port == 8080, "an empty variable from .env means the default"

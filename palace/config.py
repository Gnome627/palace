"""Settings come from the environment — docker-compose passes them from .env.

    HA_URL            http://192.168.1.10:8123 — Home Assistant, as the container sees it
    HA_TOKEN          long-lived access token (HA → profile → Security)
    API_KEY           key for the page (X-Api-Key); empty = the panel is open to anyone who reaches it
    IGNORE_AREAS      comma-separated area ids the panel does not show: router,servers
    IGNORE_ENTITIES   comma-separated entity_id patterns (fnmatch, the whole id): switch.mikrotik_*,sensor.*_rssi
    IGNORE_INTEGRATIONS  comma-separated integrations (the entity's platform): mikrotik_router,mobile_app,backup
    RESYNC_INTERVAL   seconds between full registry syncs (events keep it fresh in between), 900
    CONFIRM_TIMEOUT   seconds to wait for HA to report the change after an action, 10
    LAYOUT_FILE       where map positions, order, icons, hidden flags live, /data/palace.yaml
    HOST, PORT        where the page listens inside the container, 0.0.0.0:8080
    LOG_LEVEL         INFO
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


def _list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


@dataclass
class Settings:
    ha_url: str = "http://homeassistant.local:8123"
    ha_token: str = ""
    api_key: str = ""
    ignore_areas: list[str] = field(default_factory=list)
    ignore_entities: list[str] = field(default_factory=list)
    ignore_integrations: list[str] = field(default_factory=list)
    resync_interval: int = 900
    confirm_timeout: float = 10.0
    layout_file: str = "palace.yaml"
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        d = cls()

        def get(name: str, default):
            value = env.get(name, "").strip()
            return value if value else default

        return cls(
            ha_url=get("HA_URL", d.ha_url),
            ha_token=get("HA_TOKEN", d.ha_token),
            api_key=get("API_KEY", d.api_key),
            ignore_areas=_list(get("IGNORE_AREAS", "")),
            ignore_entities=_list(get("IGNORE_ENTITIES", "")),
            ignore_integrations=_list(get("IGNORE_INTEGRATIONS", "")),
            resync_interval=int(get("RESYNC_INTERVAL", d.resync_interval)),
            confirm_timeout=float(get("CONFIRM_TIMEOUT", d.confirm_timeout)),
            layout_file=get("LAYOUT_FILE", d.layout_file),
            host=get("HOST", d.host),
            port=int(get("PORT", d.port)),
            log_level=get("LOG_LEVEL", d.log_level),
        )

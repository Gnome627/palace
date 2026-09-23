"""`palace`: the panel process — HA websocket plus the page. Everything is set from the environment (config.py)."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys

import uvicorn

from .config import Settings
from .ha import HAClient
from .panel import Panel
from .server import create_app

log = logging.getLogger("palace")


async def run(cfg: Settings) -> None:
    ha = HAClient(
        cfg.ha_url,
        cfg.ha_token,
        cfg.resync_interval,
        ignore_areas=cfg.ignore_areas,
        ignore_entities=cfg.ignore_entities,
        ignore_integrations=cfg.ignore_integrations,
    )
    panel = Panel(ha, cfg.layout_file, confirm_timeout=cfg.confirm_timeout)
    app = create_app(panel, cfg.api_key)
    # open event streams never end by themselves: on stop, give them a moment and cut them
    config = uvicorn.Config(app, host=cfg.host, port=cfg.port, log_level="warning", timeout_graceful_shutdown=2)
    server = uvicorn.Server(config)
    log.info("Palace on http://%s:%d, Home Assistant at %s, layout in %s", cfg.host, cfg.port, cfg.ha_url, cfg.layout_file)
    if not cfg.api_key:
        log.warning("API_KEY is empty: anyone who reaches the page can switch the house")
    ha_task = asyncio.create_task(ha.run(), name="ha")
    try:
        # uvicorn handles SIGTERM itself (docker stop) and returns from serve()
        await server.serve()
    finally:
        ha_task.cancel()


def cli() -> None:
    ap = argparse.ArgumentParser(prog="palace", description="Palace — a control panel for Home Assistant")
    ap.add_argument("--port", type=int, help="overrides PORT")
    ap.add_argument("--layout", help="overrides LAYOUT_FILE")
    args = ap.parse_args()

    cfg = Settings.from_env()
    if args.port:
        cfg.port = args.port
    if args.layout:
        cfg.layout_file = args.layout
    logging.basicConfig(level=cfg.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not cfg.ha_token:
        log.error("HA_TOKEN is not set: create a long-lived access token in Home Assistant (profile → Security)")
        sys.exit(2)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(cfg))


if __name__ == "__main__":
    cli()

"""Pick the MDI icons Palace ships and write them as one JS object of path data.

    curl -sL https://registry.npmjs.org/@mdi/svg/-/svg-7.4.47.tgz | tar xz -C /tmp
    python scripts/mdi_icons.py /tmp/package/svg palace/web/icons.js
"""
import re
import sys
from pathlib import Path

SVG = Path(sys.argv[1])
OUT = Path(sys.argv[2])

UI = "refresh content-save eye eye-off label label-off close home-assistant chevron-down map-outline view-agenda-outline".split()
DEVICES = """
lightbulb lightbulb-group ceiling-light chandelier lamp floor-lamp desk-lamp wall-sconce light-recessed vanity-light
led-strip-variant string-lights outdoor-lamp spotlight-beam light-switch toggle-switch power-socket-eu power-plug
fan ceiling-fan air-conditioner thermostat radiator heat-wave fireplace snowflake air-humidifier air-purifier
window-shutter blinds curtains garage gate door door-open window-closed window-open lock lock-open-variant valve
television speaker cast radio monitor laptop printer router-wireless server camera cellphone
robot-vacuum robot script-text cog play stop
kettle coffee-maker washing-machine tumble-dryer dishwasher fridge stove microwave pot-steam hair-dryer water-boiler
thermometer water-percent motion-sensor smoke-detector water water-pump sprinkler fountain flower leaf
bell alarm-light flash gauge wifi weather-sunny mirror sofa bed shower toilet car bike home
lightbulb-spot lightbulb-variant lightbulb-outline led-strip light-switch-off track-light track-light-off candle
raspberry-pi speedometer lan key-wireless access-point zigbee signal remote gesture-tap-button human-greeting-proximity
cancel weather-sunset battery-charging power cloud-upload backup-restore
""".split()
BATTERY = """
battery-outline battery-10 battery-20 battery-30 battery-40 battery-50 battery-60 battery-70 battery-80 battery-90 battery
battery-alert-variant-outline battery-unknown
""".split()

names = UI + DEVICES + BATTERY
missing = [n for n in names if not (SVG / f"{n}.svg").exists()]
if missing:
    sys.exit(f"missing: {missing}")

entries = []
for n in names:
    svg = (SVG / f"{n}.svg").read_text()
    d = re.search(r' d="([^"]+)"', svg).group(1)
    entries.append(f'  "{n}": "{d}",')

js = "\n".join([
    "/* Material Design Icons (Pictogrammers, Apache 2.0) — the subset Palace ships, path data for a 24×24 viewBox.",
    " * Regenerate with scripts/mdi_icons.py; names are the mdi:* ids Home Assistant uses. */",
    "window.MDI = {",
    *entries,
    "};",
    "// icons a device can be given by hand, in the order the picker shows them",
    "window.MDI_PICK = " + repr(DEVICES).replace("'", '"') + ";",
    "",
])
OUT.write_text(js, encoding="utf-8")
print(len(names), "icons ->", OUT, OUT.stat().st_size, "bytes")

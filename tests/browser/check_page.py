"""The page in a real browser, on the demo house: every user-facing path once, in both languages.

    tests/browser/run.sh          # in the Playwright container: no browser needed on the host

Starts scripts/demo.py itself (short confirm timeout), drives headless Chromium, stops the demo at the end to see
how the page reports a dead server. Exits non-zero on the first failed check. Screenshots go to $OUT (/out).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.async_api import Page, async_playwright

ROOT = Path(__file__).resolve().parents[2]
PORT = 8799
URL = f"http://127.0.0.1:{PORT}/"
CONFIRM = 2                          # s, the demo's confirm timeout
OUT = Path(os.environ.get("OUT", "/out"))

LAMP = "ent:light.kids"              # a plain lamp: answers after the demo's 0.3 s
CHANDELIER = "dev:d-lustra"          # a device with sliders
BROKEN = "ent:light.broken"          # its integration fails
SILENT = "ent:switch.silent_plug"    # never reports back

passed = 0


def check(ok: bool, what: str) -> None:
    global passed
    if not ok:
        print(f"FAIL  {what}")
        sys.exit(1)
    passed += 1
    print(f"ok    {what}")


def post(path: str, body: dict) -> None:
    """Somebody else acting on the house: an automation, a wall switch, another tab."""
    req = urllib.request.Request(URL + "api/" + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)


def start_demo(layout: Path) -> subprocess.Popen:
    demo = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "demo.py"), "--port", str(PORT), "--layout", str(layout),
                             "--confirm-timeout", str(CONFIRM)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(URL + "api/state", timeout=1)
            return demo
        except OSError:
            time.sleep(0.2)
    sys.exit("the demo did not start")


async def classes(page: Page, card_id: str) -> str:
    return await page.locator(f'.node[data-id="{card_id}"]').evaluate("n => n.className")


async def is_on(page: Page, card_id: str) -> bool:
    return "on" in (await classes(page, card_id)).split()


async def last_toast(page: Page) -> list[str]:
    toasts = await page.locator(".toast").all_inner_texts()
    return toasts[-1].split("\n") if toasts else []


async def language(page: Page) -> None:
    check(await page.evaluate("document.documentElement.lang") == "en-US", "an English browser gets en-US")
    check(await page.locator('.tab[data-tab="map"] span').inner_text() == "Map", "the tabs speak English")
    await page.select_option("#lang", "ru")
    check(await page.locator('.tab[data-tab="map"] span').inner_text() == "Карта", "switching to RU rewords the frame")
    check(await page.get_attribute("#refresh", "title") == "Перечитать всё из Home Assistant", "and the ribbon's titles")
    check("Без зоны" in await page.locator("#rooms").text_content(), "and what is drawn (the no-area block)")
    await page.reload()
    await page.wait_for_selector(".node")
    check(await page.evaluate("document.documentElement.lang") == "ru", "the choice survives a reload")
    await page.select_option("#lang", "en-US")


async def switching(page: Page, sent: list[str]) -> None:
    before = await is_on(page, LAMP)
    sent.clear()
    for _ in range(10):
        await page.locator(f'.node[data-id="{LAMP}"]').click()
        await page.wait_for_timeout(40)
    check("busy" in await classes(page, LAMP), "a clicked node is locked while HA answers")
    await page.wait_for_timeout(1500)
    check(1 <= len(sent) <= 4, f"10 fast clicks → {len(sent)} commands, one per confirmed change")
    check("busy" not in await classes(page, LAMP), "the node unlocks after the change")
    check(await is_on(page, LAMP) == (before if len(sent) % 2 == 0 else not before), "what is shown is what HA has")


async def sliders(page: Page, bodies: list[str]) -> None:
    card = page.locator(f'.card[data-id="{CHANDELIER}"]')
    rng = card.locator("input[type=range]").first
    await rng.scroll_into_view_if_needed()
    box = await rng.bounding_box()
    bodies.clear()
    await page.mouse.move(box["x"] + 5, box["y"] + box["height"] / 2)
    await page.mouse.down()
    await page.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] / 2, steps=5)
    await page.mouse.up()
    await page.wait_for_timeout(1500)
    check(any('"brightness"' in b for b in bodies), "a slider sends its value on release")
    check("busy" not in await card.evaluate("n => n.className"), "and the card unlocks even though the slider kept focus")


async def failures(page: Page) -> None:
    await page.locator(f'.node[data-id="{BROKEN}"]').click()
    await page.wait_for_timeout(1200)
    title, text, *small = await last_toast(page)
    check(title == "Couldn't turn on “Сломанная лампа”", f"an HA error says what was tried: {title}")
    check(text == "Home Assistant returned an error." and small, "and what happened, HA's words in small print")
    check("failed" in await classes(page, BROKEN), "the node is marked red")

    await page.locator(f'.node[data-id="{SILENT}"]').click()
    await page.wait_for_timeout((CONFIRM + 1) * 1000)
    title, text = (await last_toast(page))[:2]
    check(title == "“Молчаливая розетка”: no response" and f"in {CONFIRM} s" in text, f"no change in time is said so: {title}")
    check("unconfirmed" in await classes(page, SILENT), "the node is marked yellow")
    await page.screenshot(path=OUT / "failures-en.png")


async def live(page: Page) -> None:
    before = await is_on(page, LAMP)
    started = time.monotonic()
    await asyncio.get_running_loop().run_in_executor(None, post, "toggle", {"id": LAMP})
    for _ in range(40):
        if await is_on(page, LAMP) != before:
            break
        await page.wait_for_timeout(50)
    check(await is_on(page, LAMP) != before, f"a change from outside shows up by itself ({time.monotonic() - started:.1f} s)")


async def arranging(page: Page) -> None:
    node = page.locator(f'.node[data-id="{LAMP}"]')
    box = await node.bounding_box()
    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    await page.mouse.down()
    await page.mouse.move(box["x"] + 80, box["y"] + 60, steps=6)
    await page.mouse.up()
    check("dirty" in await page.get_attribute("#save", "class"), "dragging a node marks the arrangement unsaved")

    card = page.locator(f'.card[data-id="{CHANDELIER}"]')
    await card.locator(".ico").click()
    check(await page.locator("#picker").is_visible(), "the icon opens the picker")
    await page.locator('#picker button[data-icon="chandelier"]').click()
    check(await page.locator("#picker").is_hidden(), "picking closes it")

    first = page.locator(".area").first
    ids = await first.locator(".card").evaluate_all("cards => cards.map(c => c.dataset.id)")
    if len(ids) >= 2:
        a = await first.locator(f'.card[data-id="{ids[0]}"] .card-head .title').bounding_box()
        b = await first.locator(f'.card[data-id="{ids[1]}"]').bounding_box()
        await page.mouse.move(a["x"] + 5, a["y"] + 5)
        await page.mouse.down()
        await page.mouse.move(b["x"] + b["width"] - 5, b["y"] + b["height"] / 2, steps=8)
        await page.mouse.up()
        after = await first.locator(".card").evaluate_all("cards => cards.map(c => c.dataset.id)")
        check(after[:2] == [ids[1], ids[0]], "a card dragged by its header takes the new place")

    await page.locator(f'.card[data-id="{SILENT}"] .eye').click()
    check(await page.locator(f'.node[data-id="{SILENT}"]').count() == 0, "the eye hides a card from the map")

    await page.locator("#save").click()
    await page.wait_for_timeout(500)
    check("dirty" not in await page.get_attribute("#save", "class"), "saving clears the mark")
    layout = json.loads(urllib.request.urlopen(URL + "api/layout", timeout=5).read())
    check(layout["devices"][CHANDELIER].get("icon") == "chandelier" and layout["devices"][SILENT].get("hidden"),
          "and the file has the icon and the hidden card")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        demo = start_demo(Path(tmp) / "palace.yaml")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(viewport={"width": 1400, "height": 900}, locale="en-US")
                errors, sent, bodies = [], [], []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("request", lambda r: ("/api/toggle" in r.url or "/api/call" in r.url)
                        and (sent.append(r.url), bodies.append(r.post_data or "")))
                await page.goto(URL)
                await page.wait_for_selector(".node")
                await page.wait_for_timeout(300)

                await language(page)
                await switching(page, sent)
                await sliders(page, bodies)
                await failures(page)
                await live(page)
                await arranging(page)

                await page.select_option("#lang", "ru")
                await page.locator(f'.node[data-id="{BROKEN}"]').click()
                await page.wait_for_timeout(1200)
                check((await last_toast(page))[0] == "Не удалось включить «Сломанная лампа»", "the notes speak Russian too")
                await page.screenshot(path=OUT / "page-ru.png")

                demo.terminate()
                demo.wait()
                await page.locator(f'.node[data-id="{LAMP}"]').click()
                await page.wait_for_timeout(1500)
                check((await last_toast(page))[1] == "Нет связи с сервером Palace.", "a dead server is said so")
                check(await page.get_attribute("#haDot", "title") == "Palace не отвечает", "and the dot says it too")
                check(not errors, f"no script errors: {errors}")
                await browser.close()
        finally:
            demo.terminate()
    print(f"\n{passed} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

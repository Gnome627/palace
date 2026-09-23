"""The page's words: every locale has every key, every key the page uses exists, no text is written in the code."""
import json
import re
from pathlib import Path

import pytest

from palace.house import CONTROLS
from palace.server import FAILURES

WEB = Path(__file__).resolve().parent.parent / "palace" / "web"
SOURCES = [WEB / "index.html", *sorted((WEB / "js").glob("*.js"))]


def flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    out = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            out.update(flatten(value, f"{prefix}{key}."))
        else:
            out[prefix + key] = value
    return out


def declared_locales() -> list[str]:
    source = (WEB / "js" / "i18n.js").read_text(encoding="utf-8")
    return re.findall(r'"([\w-]+)"', re.search(r"export const LOCALES = \[(.*?)\]", source).group(1))


LOCALES = {name: flatten(json.loads((WEB / "locales" / f"{name}.json").read_text(encoding="utf-8"))) for name in declared_locales()}
ANY = next(iter(LOCALES.values()))
placeholders = lambda text: set(re.findall(r"\{(\w+)\}", text))  # noqa: E731


def test_every_declared_locale_has_a_file_and_nothing_else_does():
    assert set(LOCALES) == {p.stem for p in (WEB / "locales").glob("*.json")}
    assert {"ru", "en-US"} <= set(LOCALES)


@pytest.mark.parametrize("name", list(LOCALES))
def test_locales_have_the_same_keys_and_placeholders(name):
    words = LOCALES[name]
    assert set(words) == set(ANY), f"{name}: missing {set(ANY) - set(words)}, extra {set(words) - set(ANY)}"
    for key, text in words.items():
        assert text.strip(), f"{name}: {key} is empty"
        assert placeholders(text) == placeholders(ANY[key]), f"{name}: {key} has other placeholders"


def test_every_key_the_page_uses_exists():
    used = set()
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'\bt\(\s*"([\w.]+)"', text))
        used |= set(re.findall(r'data-i18n(?:-title|-label)?="([\w.]+)"', text))
        # t(cond ? "a" : "b") — both branches
        used |= {k for pair in re.findall(r'\bt\(\s*[\w.]+\s*\?\s*"([\w.]+)"\s*:\s*"([\w.]+)"', text) for k in pair}
    assert used, "the scan found nothing — has the calling convention changed?"
    assert used <= set(ANY), f"unknown keys: {sorted(used - set(ANY))}"


def test_every_service_has_a_verb():
    """A failure note says what was tried ("Couldn't open …"): the verb comes from the service name."""
    services = {s for ctl in CONTROLS.values() for s in (ctl.on, ctl.off, *ctl.services)}
    missing = {s for s in services if f"verb.{s}" not in ANY}
    # data-only services are worded as "adjust"
    assert missing <= {"set_percentage", "set_humidity", "set_temperature", "set_hvac_mode", "volume_set", "volume_mute"}, missing


def test_every_failure_code_has_words():
    codes = {code for _cls, _status, code in FAILURES} | {"unauthorized", "timeout", "network"}
    for code in codes:
        assert f"failure.{code}" in ANY, code


def test_no_text_is_written_in_the_code():
    """Russian in a source file is a string that bypassed the locales (English ones the eye has to catch)."""
    for path in SOURCES:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not re.search(r"[А-Яа-яЁё]", line), f"{path.name}:{n}: {line.strip()}"

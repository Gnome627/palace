from pathlib import Path

import pytest

from palace.registry import Registry

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def registry() -> Registry:
    """A bigger house from a JSON snapshot: no devices at all, every entity on its own."""
    return Registry.from_json(FIXTURES / "registry.json")

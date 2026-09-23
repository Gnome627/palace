"""palace.yaml: what the file may hold and how it is written."""
import pytest

from palace import layout as layout_file


def test_layout_roundtrip(tmp_path):
    path = tmp_path / "palace.yaml"
    assert layout_file.load(path) == {"areas": [], "cards": {}, "devices": {}}
    saved = layout_file.save(path, {
        "areas": ["spalnya", "gostinaya", 5],
        "cards": {"gostinaya": ["dev:d-lustra", "dev:d-lamp"], "empty": []},
        "devices": {
            "dev:d-lamp": {"x": 0.25, "y": 1.7, "icon": "mdi:lamp", "hidden": True, "junk": 1},
            "dev:d-cur": {"hidden": False},
            "dev:d-therm": {"x": "0.5", "y": 0.5},
            "bad": "not a mapping",
        },
    })
    assert saved == {
        "areas": ["spalnya", "gostinaya"],
        "cards": {"gostinaya": ["dev:d-lustra", "dev:d-lamp"]},
        "devices": {"dev:d-lamp": {"x": 0.25, "y": 1.0, "icon": "lamp", "hidden": True}, "dev:d-therm": {"x": 0.5, "y": 0.5}},
    }
    assert layout_file.load(path) == saved
    assert path.read_text(encoding="utf-8").startswith("# Palace")


def test_layout_save_creates_the_directory(tmp_path):
    path = tmp_path / "data" / "palace.yaml"
    layout_file.save(path, {"areas": ["kuhnya"]})
    assert layout_file.load(path)["areas"] == ["kuhnya"]
    assert [p.name for p in path.parent.iterdir()] == ["palace.yaml"]


def test_layout_rejects_wrong_shapes():
    with pytest.raises(ValueError):
        layout_file.normalize([1, 2])
    with pytest.raises(ValueError):
        layout_file.normalize({"areas": "gostinaya"})

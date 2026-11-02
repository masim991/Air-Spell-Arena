import json

import pytest

import save_data


def test_fresh_install_hides_debug_camera_windows():
    assert save_data._defaults()["show_debug_windows"] is False


@pytest.mark.real_save
def test_invalid_camera_index_uses_default(tmp_path, monkeypatch):
    path = tmp_path / "save_data.json"
    path.write_text(json.dumps({"camera_index": "bad"}), encoding="utf-8")
    monkeypatch.setattr(save_data, "_path", lambda: path)
    assert save_data.load()["camera_index"] == 0

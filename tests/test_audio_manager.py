"""AudioManager — 설정 로드 / 폴백 / 볼륨 클램프.

실제 오디오 장치 없이(SDL_AUDIODRIVER=dummy) 동작하며, cwd 를 tmp 로 옮겨
sounds/ · audio_config.json 을 격리한다.
"""
from __future__ import annotations

import json

import pytest

import audio_manager
from audio_manager import AudioManager, ALL_SLOTS


@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sounds").mkdir()
    (tmp_path / "sounds" / "custom").mkdir()
    return tmp_path


def _write_cfg(root, data: dict):
    (root / "audio_config.json").write_text(json.dumps(data), encoding="utf-8")


def test_missing_config_yields_none_slots(workdir):
    am = AudioManager()
    assert all(am.get_selected(s) is None for s in ALL_SLOTS)
    assert am.files == []


def test_config_selection_only_kept_if_file_exists(workdir):
    (workdir / "sounds" / "bgm.ogg").write_bytes(b"x")
    _write_cfg(workdir, {"bgm": "bgm.ogg", "FIRE": "ghost.ogg"})
    am = AudioManager()
    assert am.get_selected("bgm") == "bgm.ogg"     # 존재 → 유지
    assert am.get_selected("FIRE") is None          # 없음 → 폴백 None


def test_volume_clamped_and_persisted(workdir):
    am = AudioManager()
    am.set_volume("bgm", 250)
    assert am.get_volume("bgm") == 100
    am.set_volume("bgm", -10)
    assert am.get_volume("bgm") == 0
    am.save_config()
    saved = json.loads((workdir / "audio_config.json").read_text(encoding="utf-8"))
    assert saved["volumes"]["bgm"] == 0


def test_fixed_sfx_excluded_from_file_list(workdir):
    for fn in (audio_manager.CLICK_SFX, "song.ogg"):
        (workdir / "sounds" / fn).write_bytes(b"x")
    am = AudioManager()
    assert "song.ogg" in am.files
    assert audio_manager.CLICK_SFX not in am.files


def test_close_is_idempotent(workdir):
    am = AudioManager()
    am.close()
    am.close()

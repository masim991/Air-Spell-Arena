"""pytest 공통 설정 — Pygame/OpenCV 를 헤드리스로 강제."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 프로젝트 루트를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# GUI/오디오 장치 없이 동작하도록 (CI 포함)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "2")


@pytest.fixture(autouse=True)
def _isolated_save_data(request, monkeypatch):
    """테스트는 실제 플레이어의 save_data.json(점수/난이도/보스 해금)에
    의존하지도, 그것을 덮어쓰지도 않는다 — 항상 초기값으로 시작한다."""
    if request.node.get_closest_marker("real_save"):
        return          # 저장 계층 자체를 검증하는 테스트(경로는 AIR_SPELL_ARENA_HOME 로 격리)
    import save_data as _sd
    monkeypatch.setattr(_sd, "load", lambda: _sd._defaults())
    monkeypatch.setattr(_sd, "save", lambda data: None)

from __future__ import annotations
"""
app_paths.py – 실행 위치(CWD)와 무관한 에셋/저장 경로.

- resource_dir(): 읽기 전용 번들 에셋(sounds/, 기본 audio_config.json) 위치.
  PyInstaller 빌드는 압축 해제 폴더(sys._MEIPASS), 소스 실행은 이 파일이 있는 폴더.
- data_dir(): 쓰기 가능한 사용자 데이터(save_data.json, audio_config.json, clips/, sounds/custom/).
  소스 체크아웃에서는 저장소 폴더(기존 동작 유지), 설치판·빌드판에서는 사용자 데이터 폴더.
  환경변수 AIR_SPELL_ARENA_HOME 이 있으면 항상 그 폴더를 쓴다.
"""

import os
import sys
from pathlib import Path

_APP_NAME = "AirSpellArena"
_HOME_ENV = "AIR_SPELL_ARENA_HOME"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _user_data_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / _APP_NAME


def data_dir() -> Path:
    override = os.environ.get(_HOME_ENV)
    if override:
        return Path(override)
    if not _is_frozen() and (resource_dir() / "pyproject.toml").is_file():
        return resource_dir()            # 소스 체크아웃: 기존처럼 저장소 폴더
    return _user_data_root()


def resource_path(*parts: str) -> Path:
    return resource_dir().joinpath(*parts)


def data_path(*parts: str) -> Path:
    return data_dir().joinpath(*parts)

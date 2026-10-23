from __future__ import annotations

"""
save_data.py – 세션 간 유지되는 진행 상황 저장(JSON).

audio_config.json과 별개로, 점수/난이도/보스 언락/카메라 설정을 저장한다.
파일이 없거나 손상되어도 게임은 항상 기본값으로 계속 진행된다.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

import app_paths

log = logging.getLogger("air_spell_arena.save_data")

_SAVE_FILE = "save_data.json"


def _path() -> Path:
    return app_paths.data_path(_SAVE_FILE)

_DIFFICULTIES = ("easy", "normal", "hard", "impossible")


def _defaults() -> Dict[str, Any]:
    return {
        "schema": 2,
        "first_run_done": False,
        "last_difficulty": "normal",
        "total_runs": 0,
        "total_wins": 0,
        "unlocked_stage": 1,          # 지금까지 도달해 본 최대 스테이지(1..len(STAGE_LADDER))
        "best_score": {d: 0 for d in _DIFFICULTIES},
        "camera_index": 0,
        "use_hand_tracking": True,
        "show_debug_windows": True,
        "show_orb": True,             # 인게임 수정구(웹캠) 표시 — 인게임 V 키로 토글
        "save_cards": True,           # 런 종료 시 공유용 결과 카드 PNG 자동 저장
        "save_clips": True,           # 승리 시 직전 15초 하이라이트 클립 자동 저장
        "calibration_done": False,    # 포즈 확인 온보딩을 한 번이라도 마쳤는지
        "seated_mode": False,         # 앉은 자세(팔꿈치 지지) 프리셋 — 인식 여유↑, 유지시간↓
        "face_in_media": False,       # 공유 카드/클립에 웹캠 얼굴(수정구)을 담을지 — 기본은 가림(메뉴 F 키)
        "daily": {},                  # 일일 챌린지 날짜별 최고 점수 {"YYYY-MM-DD": score}
    }


def _clean_daily(raw: Any) -> Dict[str, int]:
    """손상된 항목은 버리고 {날짜: 점수}만 남긴다."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def load() -> Dict[str, Any]:
    """저장 파일을 읽어 기본값과 병합한다. 없거나 손상돼도 기본값을 반환한다."""
    data = _defaults()
    path = _path()
    if not path.exists():
        return data
    try:
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data.update({k: v for k, v in loaded.items() if k in data})
            if isinstance(loaded.get("best_score"), dict):
                data["best_score"].update({
                    d: int(loaded["best_score"].get(d, 0)) for d in _DIFFICULTIES
                    if d in loaded["best_score"]
                })
            data["daily"] = _clean_daily(loaded.get("daily"))
    except Exception as e:
        log.warning("save_data.json 로드 실패 — 기본값 사용: %s", e)
    return data


def save(data: Dict[str, Any]) -> None:
    """저장 파일에 기록한다. 실패해도 게임 진행에는 영향 없음."""
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("save_data.json 저장 실패: %s", e)

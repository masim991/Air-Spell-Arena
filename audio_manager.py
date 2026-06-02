from __future__ import annotations

"""
audio_manager.py – BGM / SFX 2-슬롯 오디오 관리자.

사용법:
  1. 프로젝트 루트에 sounds/ 폴더를 만들고 오디오 파일을 넣습니다.
     지원 형식: .wav  .ogg  .mp3 (BGM 슬롯)
                .wav  .ogg        (SFX 슬롯 권장 – pygame.mixer.Sound 제한)
  2. 게임 설정 화면에서 각 슬롯에 파일을 선택하면 audio_config.json에 저장됩니다.
  3. 이후 게임 실행 시 자동으로 해당 파일을 불러옵니다.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

import pygame

_SOUNDS_DIR = "sounds"
_CONFIG_FILE = "audio_config.json"
_EXTS = {".wav", ".mp3", ".ogg"}

SPELL_SLOTS: tuple = ("FIRE", "WATER", "WIND", "EARTH", "DARK", "LIGHTNING", "SHIELD")
ALL_SLOTS:   tuple = ("bgm",) + SPELL_SLOTS


class AudioManager:
    """BGM + 주문별 SFX 슬롯 오디오 관리자 (ALL_SLOTS 개 슬롯)."""

    def __init__(self) -> None:
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.pre_init(44100, -16, 2, 512)
                pygame.mixer.init()
            except Exception as e:
                print(f"[AudioManager] mixer 초기화 실패: {e}")

        self._dir = Path(_SOUNDS_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

        self._files: List[str] = []
        self._config: Dict[str, Optional[str]] = {s: None for s in ALL_SLOTS}
        self._sfx_snds: Dict[str, Optional[pygame.mixer.Sound]] = {s: None for s in SPELL_SLOTS}
        self._preview_snd: Optional[pygame.mixer.Sound] = None

        self.refresh()

    # ── 파일 스캔 / 설정 저장 ────────────────────────────────────────────────

    def refresh(self) -> None:
        """sounds/ 폴더를 재스캔하고 설정을 다시 불러옵니다."""
        if self._dir.exists():
            self._files = sorted(
                f.name for f in self._dir.iterdir() if f.suffix.lower() in _EXTS
            )
        else:
            self._files = []

        cfg = self._load_config()
        for slot in ALL_SLOTS:
            v = cfg.get(slot)
            self._config[slot] = v if (v and v in self._files) else None
        for spell in SPELL_SLOTS:
            self._sfx_snds[spell] = self._mk_sound(self._config[spell])

    def _load_config(self) -> dict:
        try:
            return json.loads(Path(_CONFIG_FILE).read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_config(self) -> None:
        Path(_CONFIG_FILE).write_text(
            json.dumps(self._config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _mk_sound(self, filename: Optional[str]) -> Optional[pygame.mixer.Sound]:
        if not filename:
            return None
        path = self._dir / filename
        try:
            snd = pygame.mixer.Sound(str(path))
            snd.set_volume(0.85)
            return snd
        except Exception as e:
            print(f"[AudioManager] SFX 로드 실패 ({filename}): {e}")
            return None

    # ── 슬롯 API ────────────────────────────────────────────────────────────

    @property
    def files(self) -> List[str]:
        return list(self._files)

    def get_selected(self, slot: str) -> Optional[str]:
        return self._config.get(slot)

    def set_selected(self, slot: str, filename: Optional[str]) -> None:
        self._config[slot] = filename
        if slot in SPELL_SLOTS:
            self._sfx_snds[slot] = self._mk_sound(filename)

    # ── 재생 API ────────────────────────────────────────────────────────────

    def play_bgm(self) -> None:
        """BGM 슬롯에 선택된 파일을 루프 재생합니다."""
        fn = self._config.get("bgm")
        if not fn:
            self.stop_bgm()
            return
        try:
            pygame.mixer.music.load(str(self._dir / fn))
            pygame.mixer.music.set_volume(0.45)
            pygame.mixer.music.play(-1)
        except Exception as e:
            print(f"[AudioManager] BGM 재생 실패: {e}")

    def stop_bgm(self) -> None:
        """BGM을 정지합니다."""
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def play_spell_sfx(self, spell_name: str) -> None:
        """spell_name에 해당하는 SFX를 한 번 재생합니다."""
        snd = self._sfx_snds.get(spell_name.upper())
        if snd:
            try:
                snd.play()
            except Exception:
                pass

    def play_sfx(self) -> None:
        """(deprecated) play_spell_sfx 사용 권장."""
        pass

    def preview(self, filename: str) -> None:
        """지정된 파일을 미리 한 번 재생합니다 (이전 미리듣기 중지)."""
        if self._preview_snd:
            try:
                self._preview_snd.stop()
            except Exception:
                pass
        self._preview_snd = self._mk_sound(filename)
        if self._preview_snd:
            try:
                self._preview_snd.play()
            except Exception:
                pass

    def close(self) -> None:
        self.stop_bgm()
        try:
            pygame.mixer.quit()
        except Exception:
            pass

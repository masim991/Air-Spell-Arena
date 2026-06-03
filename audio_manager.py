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
_CUSTOM_DIR = "sounds/custom"
_CONFIG_FILE = "audio_config.json"
_EXTS = {".wav", ".mp3", ".ogg"}
CLICK_SFX = "클릭사운드.mp3"  # UI 클릭음 (설정 목록에서 제외)
BOSS_ATTACK_SFX = "Boss Attack.mp3"  # 보스 공격음 (설정 목록에서 제외)
INTRO_SOUND = "시작사운드.mp3"  # 게임 시작 인트로 사운드 (설정 목록에서 제외)
_FIXED_SFXS = {CLICK_SFX, BOSS_ATTACK_SFX, INTRO_SOUND}  # 파일 선택 목록에서 항상 제외
_DEFAULT_VOLUME: int = 50    # 기본 볼륨 (0-100)
_BATTLE_BGM_VOLUME: int = 20  # 보스전 중 BGM 덕킹 볼륨

SPELL_SLOTS: tuple = ("FIRE", "WATER", "WIND", "EARTH", "DARK", "LIGHT", "LIGHTNING")
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
        self._custom_dir = Path(_CUSTOM_DIR)
        self._custom_dir.mkdir(parents=True, exist_ok=True)

        self._files: List[str] = []
        self._custom_files: List[str] = []
        self._config: Dict[str, Optional[str]] = {s: None for s in ALL_SLOTS}
        self._use_custom: bool = False  # 커스텀 사운드 세트 사용 여부
        self._sfx_snds: Dict[str, Optional[pygame.mixer.Sound]] = {s: None for s in SPELL_SLOTS}
        self._preview_snd: Optional[pygame.mixer.Sound] = None
        self._click_snd: Optional[pygame.mixer.Sound] = None
        self._boss_attack_snd: Optional[pygame.mixer.Sound] = None
        self._intro_snd: Optional[pygame.mixer.Sound] = None
        self._volumes: Dict[str, int] = {s: _DEFAULT_VOLUME for s in ALL_SLOTS}

        self.refresh()

    # ── 파일 스캔 / 설정 저장 ────────────────────────────────────────────────

    def refresh(self) -> None:
        """sounds/ 폴더와 custom/ 폴더를 재스캔하고 설정을 다시 불러옵니다."""
        if self._dir.exists():
            self._files = sorted(
                f.name for f in self._dir.iterdir()
                if f.suffix.lower() in _EXTS and f.is_file() and f.name not in _FIXED_SFXS
            )
        else:
            self._files = []

        click_path = self._dir / CLICK_SFX
        if click_path.exists():
            try:
                self._click_snd = pygame.mixer.Sound(str(click_path))
                self._click_snd.set_volume(0.65)
            except Exception as e:
                print(f"[AudioManager] 클릭음 로드 실패: {e}")
                self._click_snd = None

        boss_path = self._dir / BOSS_ATTACK_SFX
        if boss_path.exists():
            try:
                self._boss_attack_snd = pygame.mixer.Sound(str(boss_path))
                self._boss_attack_snd.set_volume(0.75)
            except Exception as e:
                print(f"[AudioManager] 보스 공격음 로드 실패: {e}")
                self._boss_attack_snd = None

        intro_path = self._dir / INTRO_SOUND
        if intro_path.exists():
            try:
                self._intro_snd = pygame.mixer.Sound(str(intro_path))
                self._intro_snd.set_volume(0.9)
            except Exception as e:
                print(f"[AudioManager] 인트로 사운드 로드 실패: {e}")
                self._intro_snd = None

        if self._custom_dir.exists():
            self._custom_files = sorted(
                f.name for f in self._custom_dir.iterdir()
                if f.suffix.lower() in _EXTS and f.name not in _FIXED_SFXS
            )
        else:
            self._custom_files = []

        cfg = self._load_config()
        self._use_custom = cfg.get("use_custom", False)
        if self._use_custom:
            slot_cfg   = cfg.get("custom", {})
            active_files = self._custom_files
        else:
            slot_cfg   = cfg
            active_files = self._files
        for slot in ALL_SLOTS:
            v = slot_cfg.get(slot)
            self._config[slot] = v if (v and v in active_files) else None

        saved_vols = cfg.get("volumes", {})
        for slot in ALL_SLOTS:
            if slot in saved_vols:
                self._volumes[slot] = max(0, min(100, int(saved_vols[slot])))

        for spell in SPELL_SLOTS:
            self._sfx_snds[spell] = self._mk_sound(self._config[spell])
            if self._sfx_snds[spell]:
                self._sfx_snds[spell].set_volume(self._volumes.get(spell, _DEFAULT_VOLUME) / 100)

    def _load_config(self) -> dict:
        try:
            return json.loads(Path(_CONFIG_FILE).read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_config(self) -> None:
        existing = self._load_config()
        if self._use_custom:
            existing["custom"] = {slot: self._config[slot] for slot in ALL_SLOTS}
        else:
            for slot in ALL_SLOTS:
                existing[slot] = self._config[slot]
        existing["use_custom"] = self._use_custom
        existing["volumes"]    = self._volumes
        Path(_CONFIG_FILE).write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _mk_sound(self, filename: Optional[str]) -> Optional[pygame.mixer.Sound]:
        if not filename:
            return None
        # custom 모드: custom 폴더 우선 → 없으면 기본 폴더
        candidates: list = []
        if self._use_custom:
            candidates.append(self._custom_dir / filename)
        candidates.append(self._dir / filename)

        for path in candidates:
            if path.exists():
                try:
                    snd = pygame.mixer.Sound(str(path))
                    return snd
                except Exception as e:
                    print(f"[AudioManager] SFX 로드 실패 ({path}): {e}")
                    return None

        tried = " | ".join(str(p) for p in candidates)
        print(f"[AudioManager] SFX 파일 없음 ({filename}) — 시도: {tried}")
        return None

    # ── 슬롯 API ────────────────────────────────────────────────────────────

    @property
    def files(self) -> List[str]:
        """현재 활성화된 사운드 세트의 파일 리스트를 반환합니다."""
        return list(self._custom_files if self._use_custom else self._files)

    @property
    def custom_files(self) -> List[str]:
        """커스텀 폴더의 파일 리스트를 반환합니다."""
        return list(self._custom_files)

    @property
    def use_custom(self) -> bool:
        return self._use_custom

    def toggle_custom_mode(self) -> None:
        """기본/커스텀 사운드 세트를 전환합니다."""
        self._use_custom = not self._use_custom
        cfg = self._load_config()
        if self._use_custom:
            slot_cfg   = cfg.get("custom", {})
            active_files = self._custom_files
        else:
            slot_cfg   = cfg
            active_files = self._files
        for slot in ALL_SLOTS:
            v = slot_cfg.get(slot)
            self._config[slot] = v if (v and v in active_files) else None
        # 사운드 재로드
        for spell in SPELL_SLOTS:
            self._sfx_snds[spell] = self._mk_sound(self._config[spell])
            if self._sfx_snds[spell]:
                self._sfx_snds[spell].set_volume(self._volumes.get(spell, _DEFAULT_VOLUME) / 100)
        self.play_bgm()

    def get_selected(self, slot: str) -> Optional[str]:
        return self._config.get(slot)

    def set_selected(self, slot: str, filename: Optional[str]) -> None:
        self._config[slot] = filename
        if slot in SPELL_SLOTS:
            self._sfx_snds[slot] = self._mk_sound(filename)
            if self._sfx_snds[slot]:
                self._sfx_snds[slot].set_volume(self._volumes.get(slot, _DEFAULT_VOLUME) / 100)

    # ── 재생 API ────────────────────────────────────────────────────────────

    def play_bgm(self) -> None:
        """BGM 슬롯에 선택된 파일을 루프 재생합니다."""
        fn = self._config.get("bgm")
        if not fn:
            self.stop_bgm()
            return
        try:
            # custom 모드: custom 폴더 우선 → 없으면 기본 폴더
            bgm_candidates = []
            if self._use_custom:
                bgm_candidates.append(self._custom_dir / fn)
            bgm_candidates.append(self._dir / fn)
            path = next((p for p in bgm_candidates if p.exists()), bgm_candidates[-1])
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(self._volumes.get("bgm", _DEFAULT_VOLUME) / 100)
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

    def play_click(self) -> None:
        """UI 버튼 클릭 사운드를 재생합니다 (고정, 설정 불가)."""
        if self._click_snd:
            try:
                self._click_snd.play()
            except Exception:
                pass

    def get_volume(self, slot: str) -> int:
        """슬롯 볼륨 반환 (0-100)."""
        return self._volumes.get(slot, _DEFAULT_VOLUME)

    def set_volume(self, slot: str, value: int) -> None:
        """슬롯 볼륨 설정 및 즉시 적용 (0-100)."""
        value = max(0, min(100, value))
        self._volumes[slot] = value
        if slot == "bgm":
            try:
                pygame.mixer.music.set_volume(value / 100)
            except Exception:
                pass
        elif slot in SPELL_SLOTS:
            snd = self._sfx_snds.get(slot)
            if snd:
                try:
                    snd.set_volume(value / 100)
                except Exception:
                    pass

    def set_bgm_battle_mode(self, battle: bool) -> None:
        """보스전 진입/퇴장 시 BGM 볼륨 전환 (진입: 20/100, 퇴장: 설정값)."""
        try:
            if battle:
                pygame.mixer.music.set_volume(_BATTLE_BGM_VOLUME / 100)
            else:
                pygame.mixer.music.set_volume(self._volumes.get("bgm", _DEFAULT_VOLUME) / 100)
        except Exception:
            pass

    def play_boss_attack(self) -> None:
        """보스 공격 사운드를 재생합니다."""
        if self._boss_attack_snd:
            try:
                self._boss_attack_snd.play()
            except Exception:
                pass

    def play_intro_sound(self) -> float:
        """인트로 사운드를 재생하고 지속 시간을 ms로 반환합니다."""
        if self._intro_snd:
            try:
                self._intro_snd.play()
                return self._intro_snd.get_length() * 1000.0
            except Exception:
                pass
        return 4000.0  # fallback 4초

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

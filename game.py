from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List

import math
import random
import pygame
from audio_manager import AudioManager, ALL_SLOTS, SPELL_SLOTS
from fp_renderer import FPRenderer


# ── 화면/렌더 상수 ─────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 1280, 720
FPS = 60

# Modern Neon/Cyberpunk Colors (2026 Gaming Trend)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BG = (12, 6, 24)  # Darker, more atmospheric
RED = (255, 70, 100)  # Neon Pink-Red
GREEN = (80, 255, 150)  # Neon Mint Green
YELLOW = (255, 230, 60)  # Electric Yellow
BLUE = (80, 150, 255)  # Bright Sky Blue
CYAN = (0, 240, 255)  # Electric Cyan
GREY = (140, 145, 160)  # Cool Grey
ORANGE = (255, 140, 40)  # Vibrant Orange
PURPLE = (180, 100, 255)  # Neon Purple
PINK = (255, 100, 200)  # Hot Pink
GOLD = (255, 215, 50)  # Bright Gold

# ── 게임 밸런스 상수 ──────────────────────────────────────────────────────────
PLAYER_MAX_HP = 100
BOSS_MAX_HP = 100

LIGHTNING_DMG = 25       # ZIGZAG → LIGHTNING
LIGHTNING_COOLDOWN_MS = 4000

SHIELD_REDUCTION = 0.5   # CIRCLE → SHIELD (입는 피해 50% 감소)
SHIELD_DURATION_MS = 2500

BOSS_DMG = 5

MESSAGE_DURATION_MS = 1500
PROJECTILE_DURATION_MS = 450
RING_DURATION_MS = 350

# Enhanced Element Colors with Neon Vibrancy
FIRE_NEON = (255, 100, 50)  # Bright Fire Orange
WATER_NEON = (60, 180, 255)  # Bright Water Blue
WIND_NEON = (120, 255, 180)  # Mint Wind Green
EARTH_NEON = (200, 160, 100)  # Golden Earth
DARK_NEON = (160, 80, 255)  # Deep Purple
LTNG_NEON = (100, 220, 255)  # Electric Blue

# 주문별 프리셋은 아래 _SPELL_DB 로 통합됨.


# Magic Circle Colors - Enhanced Neon Glow
MAGIC_CIRCLE_COLORS = {
    "FIRE":      (255, 100,  50),  # Bright Fire Orange
    "WATER":     ( 60, 180, 255),  # Bright Water Blue
    "EARTH":     (200, 160, 100),  # Golden Earth
    "WIND":      (120, 255, 180),  # Mint Wind Green
    "LIGHT":     (240, 255, 255),  # Bright White-Cyan
    "DARK":      (160,  80, 255),  # Deep Purple
    "LIGHTNING": (100, 220, 255),  # Electric Blue
    "SHIELD":    (  0, 240, 255),  # Electric Cyan
}

# 난이도별 보스 회피 확률
DIFFICULTY_PROB = {
    "easy": 0.20,
    "normal": 0.40,
    "hard": 0.60,
    "impossible": 0.80,
}

# ── 주문 상성표 ──────────────────────────────────────────────────────────────
# 공격 원소가 방어(보스) 원소에 강하면 1.5×, 약하면 0.6×, 그 외 1.0×.
_STRONG_AGAINST = {
    "WATER": "FIRE", "FIRE": "WIND", "WIND": "EARTH", "EARTH": "WATER",
    "LIGHT": "DARK", "DARK": "LIGHT",
}


def affinity_mult(attacker: str, defender: Optional[str]) -> float:
    """공격 원소 vs 방어 원소 데미지 배수."""
    if not defender or attacker == defender:
        return 1.0
    if _STRONG_AGAINST.get(attacker) == defender:
        return 1.5
    if _STRONG_AGAINST.get(defender) == attacker:
        return 0.6
    return 1.0


# ── 보스 페이즈 (hp 비율 하한, 원소, 공격 주기 ms, 패턴) ─────────────────────
BOSS_PHASES = [
    (0.66, "FIRE",  1667, "single"),
    (0.33, "WATER", 1150, "spread3"),
    (0.0,  "DARK",   850, "aimed"),
]
BOSS_TELEGRAPH_MS = 500   # 보스 시전 전 경고 시간

# ── 통합 주문 레지스트리 ────────────────────────────────────────────────────
# kind: "proj"(투사체) | "shield"(방어막).  cd: 쿨다운 ms(0=없음).
_SPELL_DB: dict = {
    # 기본 원소 (포즈 / 궤적)
    "FIRE":  {"kind": "proj", "element": "FIRE",  "style": "fire",  "color": FIRE_NEON,
              "dmg": 12, "dur": PROJECTILE_DURATION_MS,      "cd": 0,
              "shake": (3.0, 150), "particles": (15, "spark"), "toast": ("FIRE!", YELLOW)},
    "WATER": {"kind": "proj", "element": "WATER", "style": "water", "color": WATER_NEON,
              "dmg": 11, "dur": PROJECTILE_DURATION_MS + 40, "cd": 0,
              "shake": (2.5, 130), "particles": (12, "glow"), "toast": ("WATER!", BLUE)},
    "WIND":  {"kind": "proj", "element": "WIND",  "style": "wind",  "color": WIND_NEON,
              "dmg": 10, "dur": PROJECTILE_DURATION_MS - 40, "cd": 0,
              "shake": (2.0, 120), "particles": (20, "spark"), "toast": ("WIND!", GREEN)},
    "EARTH": {"kind": "proj", "element": "EARTH", "style": "earth", "color": EARTH_NEON,
              "dmg": 14, "dur": PROJECTILE_DURATION_MS + 80, "cd": 0,
              "shake": (4.0, 180), "particles": (10, "spark"), "toast": ("EARTH!", GREY)},
    "DARK":  {"kind": "proj", "element": "DARK",  "style": "dark",  "color": DARK_NEON,
              "dmg": 12, "dur": PROJECTILE_DURATION_MS + 20, "cd": 0,
              "shake": (3.5, 160), "particles": (18, "glow"), "toast": ("DARK!", PURPLE)},
    "LIGHT": {"kind": "shield", "element": "LIGHT", "style": "light", "color": CYAN,
              "dmg": 0, "dur": 0, "cd": 0,
              "shake": (2.0, 140), "particles": (25, "glow"),
              "toast": (f"SHIELD ({SHIELD_DURATION_MS // 1000}s)", CYAN)},
    "LIGHTNING": {"kind": "proj", "element": "LIGHTNING", "style": "lightning", "color": LTNG_NEON,
                  "dmg": LIGHTNING_DMG, "dur": max(280, PROJECTILE_DURATION_MS - 120),
                  "cd": LIGHTNING_COOLDOWN_MS,
                  "shake": (5.0, 200), "particles": (30, "spark"), "toast": ("LIGHTNING!", BLUE)},
    # 콤보 (spell_combo.py 규칙표와 1:1)
    "STEAM":        {"kind": "proj", "element": "WATER", "style": "water", "color": (200, 230, 255),
                     "dmg": 18, "dur": PROJECTILE_DURATION_MS + 30, "cd": 1500,
                     "shake": (3.5, 170), "particles": (22, "glow"), "toast": ("STEAM!", BLUE)},
    "MUD":          {"kind": "proj", "element": "EARTH", "style": "earth", "color": (150, 110, 70),
                     "dmg": 20, "dur": PROJECTILE_DURATION_MS + 90, "cd": 1500,
                     "shake": (4.5, 190), "particles": (14, "spark"), "toast": ("MUD!", GREY)},
    "FLAME_BALL":   {"kind": "proj", "element": "FIRE", "style": "fire", "color": (255, 140, 40),
                     "dmg": 26, "dur": PROJECTILE_DURATION_MS, "cd": 2500,
                     "shake": (5.5, 210), "particles": (34, "spark"), "toast": ("FLAME BALL!", ORANGE)},
    "ICE_SHARD":    {"kind": "proj", "element": "WATER", "style": "water", "color": (170, 240, 255),
                     "dmg": 24, "dur": PROJECTILE_DURATION_MS - 30, "cd": 2500,
                     "shake": (4.0, 180), "particles": (26, "glow"), "toast": ("ICE SHARD!", CYAN)},
    "TORNADO":      {"kind": "proj", "element": "WIND", "style": "wind", "color": (160, 255, 210),
                     "dmg": 22, "dur": PROJECTILE_DURATION_MS - 20, "cd": 2500,
                     "shake": (4.5, 200), "particles": (30, "spark"), "toast": ("TORNADO!", GREEN)},
    "STONE_BULLET": {"kind": "proj", "element": "EARTH", "style": "earth", "color": (210, 180, 140),
                     "dmg": 23, "dur": PROJECTILE_DURATION_MS + 40, "cd": 2500,
                     "shake": (5.0, 200), "particles": (16, "spark"), "toast": ("STONE BULLET!", GOLD)},
    "BLINDNESS":    {"kind": "proj", "element": "DARK", "style": "dark", "color": (120, 90, 180),
                     "dmg": 14, "dur": PROJECTILE_DURATION_MS + 20, "cd": 3000, "blind_ms": 3200,
                     "shake": (3.0, 160), "particles": (20, "glow"), "toast": ("BLINDNESS!", PURPLE)},
    "CURSE_SHOCK":  {"kind": "proj", "element": "DARK", "style": "dark", "color": (200, 60, 255),
                     "dmg": 28, "dur": PROJECTILE_DURATION_MS + 10, "cd": 3200,
                     "shake": (5.5, 220), "particles": (28, "glow"), "toast": ("CURSE SHOCK!", PINK)},
}
_SPELL_ALIASES = {"LINE": "FIRE", "CIRCLE": "LIGHT", "ZIGZAG": "LIGHTNING"}


@dataclass
class SpellResult:
    name: str
    applied: bool
    reason: str = ""


class SpellGame:
    """간단한 주문 반응형 아레나 게임 스켈레톤.

    run_one_frame(spell_name)를 외부 루프에서 반복 호출해,
    주문 이름이 주어지면 그에 대응하는 효과를 게임 상태에 적용합니다.
    """

    def __init__(self) -> None:
        """Pygame, 화면, 폰트, 기본 게임 상태를 초기화합니다."""
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Air Spell Arena – Demo")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 24)
        self.font_big = pygame.font.SysFont(None, 36)
        self._fp = FPRenderer(self.screen, self.font, self.font_big)

        # 엔티티 상태
        self.player_hp = PLAYER_MAX_HP
        self.boss_hp = BOSS_MAX_HP

        self.player_pos = (SCREEN_W // 2, SCREEN_H // 2)
        self.boss_pos = (SCREEN_W - 150, SCREEN_H // 2)
        self.player_r = 40
        self.boss_r = 48
        # 부동소수 좌표(헤드 무브 스무딩용)
        self._player_fx, self._player_fy = float(self.player_pos[0]), float(self.player_pos[1])
        self._player_speed_px_s = 480.0
        self._arena_min_x = self.player_r + 30
        self._arena_max_x = SCREEN_W - (self.player_r + 30)
        self._player_center_x = float(SCREEN_W // 2)  # 기본 복귀 중심

        # 효과/버프/쿨다운
        self.shield_time_left = 0
        self.lightning_cd_left = 0          # HUD 표시용(=_cooldowns["LIGHTNING"])
        self._cooldowns: dict = {}          # 주문명 → 남은 쿨다운 ms
        self._boss_blind_left = 0           # BLINDNESS 적중 시 보스 회피 무력화 시간

        # 보스 공격 주기 타이머 / 페이즈
        self._boss_attack_timer = 0
        self.boss_phase = 0
        self.boss_element = BOSS_PHASES[0][1]
        self._pending_boss_shots: List[dict] = []

        # UI 메시지
        self.message_text = ""
        self.message_time_left = 0
        self.message_color = WHITE

        # 상태/메뉴
        self._state = "menu"   # 'intro' | 'menu' | 'tutorial' | 'playing' | 'game_over' | 'you_win'
        _cx = SCREEN_W // 2
        _by = SCREEN_H // 2 - 18
        self._btn_start    = pygame.Rect(_cx - 160, _by,        320, 58)
        self._btn_exit     = pygame.Rect(_cx - 95,  _by + 76,   190, 46)
        self._btn_guide    = pygame.Rect(_cx - 175, _by + 142,  160, 42)
        self._btn_settings = pygame.Rect(_cx + 15,  _by + 142,  160, 42)

        # 인게임 일시정지
        self._btn_pause = pygame.Rect(SCREEN_W - 68, 10, 58, 28)
        self._pause_vols: dict = {"bgm": 50, "sfx": 50}
        self._pause_clickables: list = []

        # 인트로 화면 상태
        self._INTRO_TEXT: str = "ARE YOU READY TO GAME?"
        self._intro_tick: int = 0
        self._intro_start_ms: int = 0
        self._intro_char_ms: float = 180.0
        self._intro_chars_shown: int = 0
        _icx = SCREEN_W // 2
        _iby = SCREEN_H * 2 // 3
        self._btn_intro_play = pygame.Rect(_icx - 165, _iby, 150, 52)
        self._btn_intro_exit = pygame.Rect(_icx + 15,  _iby, 150, 52)

        # 오디오 매니저
        self._audio = AudioManager()
        self._audio.play_bgm()  # 메뉴부터 BGM 시작

        # 설정 화면 상태
        self._settings_pending: dict = {s: None for s in ALL_SLOTS}
        self._settings_pending_volumes: dict = {s: 50 for s in ALL_SLOTS}
        self._settings_active_slot: str = "bgm"
        self._settings_clickables: list = []
        self._settings_scroll_offset: int = 0  # 스크롤 위치

        # 이펙트
        self._effects: List[dict] = []

        # 난이도(보스 회피 확률)
        self.set_difficulty("normal")

        # 저장된 난이도(리셋 후 유지)
        self._saved_difficulty = "normal"
        # 엔딩/튜토리얼 화면 틱 카운터
        self._tick_ending  = 0
        self._tick_tutorial = 0

    # ── 퍼블릭 API ──────────────────────────────────────────────────────────

    def run_one_frame(self, spell_name: Optional[str], head_dir: Optional[str] = None) -> bool:
        """한 프레임을 처리합니다.

        - Pygame 이벤트 처리(종료 등)
        - 제공된 주문명을 적용
        - 내부 상태 업데이트 및 렌더링

        Returns:
            계속 실행하려면 True, 창 종료/ESC 시 False.
        """
        _prev_state = self._state

        # 이벤트 처리
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self._state == "settings":
                    self._state = "menu"
                elif self._state == "playing":
                    self._state = "pause"
                elif self._state == "pause":
                    self._state = "playing"
                else:
                    return False
            if self._state == "intro":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if self._intro_chars_shown >= len(self._INTRO_TEXT):
                        if self._btn_intro_play.collidepoint(mx, my):
                            self._audio.play_click()
                            self._state = "playing"
                        elif self._btn_intro_exit.collidepoint(mx, my):
                            self._audio.play_click()
                            self._state = "menu"
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._state = "playing"  # SPACE/ENTER로 바로 게임 시작
            elif self._state == "menu":
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._intro_tick = 0; self._intro_chars_shown = 0; self._intro_start_ms = 0
                    self._state = "intro"
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    if event.key == pygame.K_1:
                        self.set_difficulty("easy")
                    elif event.key == pygame.K_2:
                        self.set_difficulty("normal")
                    elif event.key == pygame.K_3:
                        self.set_difficulty("hard")
                    elif event.key == pygame.K_4:
                        self.set_difficulty("impossible")
                    self._saved_difficulty = self.difficulty
                    self._toast(f"Difficulty: {self.difficulty}", WHITE)
                if event.type == pygame.KEYDOWN and event.key == pygame.K_g:
                    self._state = "tutorial"
                    self._tick_tutorial = 0
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if self._btn_start.collidepoint(mx, my):
                        self._audio.play_click()
                        self._intro_tick = 0; self._intro_chars_shown = 0; self._intro_start_ms = 0
                        self._state = "intro"
                    elif self._btn_exit.collidepoint(mx, my):
                        self._audio.play_click()
                        return False
                    elif self._btn_guide.collidepoint(mx, my):
                        self._audio.play_click()
                        self._state = "tutorial"
                        self._tick_tutorial = 0
                    elif self._btn_settings.collidepoint(mx, my):
                        self._audio.play_click()
                        self._audio.refresh()
                        self._settings_pending = {s: self._audio.get_selected(s) for s in ALL_SLOTS}
                        self._settings_pending_volumes = {s: self._audio.get_volume(s) for s in ALL_SLOTS}
                        self._settings_active_slot = "bgm"
                        self._state = "settings"
            elif self._state == "settings":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    for rect, action, value in self._settings_clickables:
                        if rect.collidepoint(mx, my):
                            if action != "preview":
                                self._audio.play_click()
                            if action == "back":
                                self._state = "menu"
                                self._settings_scroll_offset = 0  # 스크롤 초기화
                            elif action == "save":
                                for slot in ALL_SLOTS:
                                    self._audio.set_selected(slot, self._settings_pending.get(slot))
                                    self._audio.set_volume(slot, self._settings_pending_volumes.get(slot, 50))
                                self._audio.save_config()
                                self._state = "menu"
                                self._settings_scroll_offset = 0  # 스크롤 초기화
                            elif action == "slot_tab":
                                self._settings_active_slot = value
                                self._settings_scroll_offset = 0  # 탭 변경 시 스크롤 초기화
                            elif action == "toggle_custom":
                                self._audio.toggle_custom_mode()
                                self._settings_scroll_offset = 0  # 모드 변경 시 스크롤 초기화
                                self._toast(f"{'커스텀' if self._audio.use_custom else '기본'} 사운드 활성화", CYAN)
                            elif action in ALL_SLOTS:
                                self._settings_pending[action] = value
                            elif action == "vol_down":
                                self._settings_pending_volumes[value] = max(
                                    0, self._settings_pending_volumes.get(value, 50) - 5
                                )
                            elif action == "vol_up":
                                self._settings_pending_volumes[value] = min(
                                    100, self._settings_pending_volumes.get(value, 50) + 5
                                )
                            elif action == "preview" and value:
                                self._audio.preview(value)
                            break
                # 마우스 휠로 스크롤
                elif event.type == pygame.MOUSEWHEEL:
                    self._settings_scroll_offset -= event.y  # y가 양수면 위로, 음수면 아래로
                    self._settings_scroll_offset = max(0, self._settings_scroll_offset)
            elif self._state == "tutorial":
                if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE, pygame.K_g
                ):
                    self._state = "menu"
            elif self._state == "playing":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._btn_pause.collidepoint(event.pos):
                        self._audio.play_click()
                        self._state = "pause"
            elif self._state == "pause":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for rect, action, _ in self._pause_clickables:
                        if rect.collidepoint(event.pos):
                            self._audio.play_click()
                            if action == "resume":
                                self._state = "playing"
                            elif action == "vol_bgm_down":
                                self._pause_vols["bgm"] = max(0, self._pause_vols["bgm"] - 5)
                                self._audio.set_volume("bgm", self._pause_vols["bgm"])
                            elif action == "vol_bgm_up":
                                self._pause_vols["bgm"] = min(100, self._pause_vols["bgm"] + 5)
                                self._audio.set_volume("bgm", self._pause_vols["bgm"])
                            elif action == "vol_sfx_down":
                                self._pause_vols["sfx"] = max(0, self._pause_vols["sfx"] - 5)
                                for _slot in SPELL_SLOTS:
                                    self._audio.set_volume(_slot, self._pause_vols["sfx"])
                            elif action == "vol_sfx_up":
                                self._pause_vols["sfx"] = min(100, self._pause_vols["sfx"] + 5)
                                for _slot in SPELL_SLOTS:
                                    self._audio.set_volume(_slot, self._pause_vols["sfx"])
                            elif action == "exit_menu":
                                self._reset_game()
                            break
            elif self._state in ("game_over", "you_win"):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._reset_game()

        # 엔딩/메뉴/설정 상태는 게임 로직 없이 렌더만
        if self._state == "intro":
            self.clock.tick(FPS)
            now = pygame.time.get_ticks()
            if self._intro_tick == 0:
                self._intro_start_ms = now
                duration_ms = self._audio.play_intro_sound()
                self._intro_char_ms = (duration_ms * 0.75) / max(1, len(self._INTRO_TEXT))
            self._intro_tick += 1
            elapsed = now - self._intro_start_ms
            self._intro_chars_shown = min(
                len(self._INTRO_TEXT),
                int(elapsed / self._intro_char_ms) if self._intro_char_ms > 0 else 0,
            )
            show_btns = self._intro_chars_shown >= len(self._INTRO_TEXT)
            self._fp.render_intro(
                self._intro_tick,
                self._intro_chars_shown,
                self._btn_intro_play if show_btns else None,
                self._btn_intro_exit if show_btns else None,
                self._INTRO_TEXT,
            )
            return True
        if self._state == "menu":
            self.clock.tick(FPS)
            self._render_menu()
            return True
        if self._state == "settings":
            self.clock.tick(FPS)
            self._settings_clickables = self._fp.render_settings(
                files=self._audio.files,
                pending=self._settings_pending,
                active_slot=self._settings_active_slot,
                use_custom=self._audio.use_custom,
                has_custom=len(self._audio.custom_files) > 0,
                scroll_offset=self._settings_scroll_offset,
                pending_volumes=self._settings_pending_volumes,
            )
            return True
        if self._state == "tutorial":
            self.clock.tick(FPS)
            self._fp.render_tutorial(self._tick_tutorial)
            self._tick_tutorial += 1
            return True
        if self._state == "pause":
            self.clock.tick(FPS)
            self._pause_clickables = self._fp.render_pause(
                bgm_vol=self._pause_vols["bgm"],
                sfx_vol=self._pause_vols["sfx"],
            )
            return True
        if self._state in ("game_over", "you_win"):
            self.clock.tick(FPS)
            self._fp.render_ending(self._state, self._tick_ending)
            self._tick_ending += 1
            return True

        # 시간 갱신 및 헤드 무브먼트 먼저 반영
        dt = self.clock.tick(FPS)  # milliseconds
        self._update_timers(dt)
        self._update_player_dodge(head_dir, dt)

        # 주문 적용(플레이어 현재 위치에서 투사체가 출발하도록 이동 이후에 적용)
        if spell_name:
            _result = self.apply_spell(spell_name)
            if _result.applied:
                self._audio.play_spell_sfx(_result.name)

        # 나머지 업데이트
        self._update_boss_ai(dt)
        self._update_effects(dt)

        # 승패 판정
        if self.boss_hp <= 0 and self._state == "playing":
            self._state = "you_win"
            self._tick_ending = 0
        elif self.player_hp <= 0 and self._state == "playing":
            self._state = "game_over"
            self._tick_ending = 0

        # BGM 전환: 상태가 바뀌는 순간만 실행
        if _prev_state != self._state:
            if self._state == "pause":
                self._pause_vols = {
                    "bgm": self._audio.get_volume("bgm"),
                    "sfx": self._audio.get_volume(SPELL_SLOTS[0]),
                }
            elif self._state == "intro":
                self._audio.stop_bgm()              # 인트로 중 BGM 없음
            elif self._state == "menu":
                self._audio.play_bgm()              # 메뉴: BGM 정상 볼륨
            elif self._state == "playing":
                self._audio.play_bgm()              # 게임: BGM 시작 (battle 본류가 앞에 있으면 무시)
                self._audio.set_bgm_battle_mode(True)
            elif self._state in ("game_over", "you_win"):
                self._audio.set_bgm_battle_mode(False)  # 엔딩: 볼륨 복원

        # 렌더
        self._render(dt)
        return True

    def apply_spell(self, spell_name: str) -> SpellResult:
        """레지스트리(_SPELL_DB) 기반으로 주문 1건을 적용한다."""
        label = spell_name.upper()
        label = _SPELL_ALIASES.get(label, label)
        spec = _SPELL_DB.get(label)
        if spec is None:
            self._toast(f"UNKNOWN: {spell_name}", GREY)
            return SpellResult("UNKNOWN", False, "unrecognized")

        cd_left = self._cooldowns.get(label, 0)
        if cd_left > 0:
            self._toast(f"{label} (cooldown {cd_left / 1000:.1f}s)", GREY)
            return SpellResult(label, False, "cooldown")
        if spec["cd"] > 0:
            self._cooldowns[label] = spec["cd"]

        # 공통 연출
        wand_x, wand_y = int(SCREEN_W * 0.61), int(SCREEN_H * 0.71)
        pcount, pkind = spec["particles"]
        self._fp.add_particles(wand_x, wand_y, pcount, spec["color"], pkind)
        self._fp.add_camera_shake(*spec["shake"])
        self._spawn_cast_effect(spec["color"], spec["style"])
        self._spawn_magic_circle(spec["element"])
        self._toast(*spec["toast"])

        if spec["kind"] == "shield":
            self.shield_time_left = SHIELD_DURATION_MS
            self._spawn_shield_ring()
        else:
            self._spawn_player_projectile(
                element=spec["element"], color=spec["color"],
                dmg=spec["dmg"], dur_ms=spec["dur"], style=spec["style"],
            )
            if spec.get("blind_ms"):
                self._effects[-1]["blind_ms"] = spec["blind_ms"]
        return SpellResult(label, True)

    def close(self) -> None:
        """게임을 종료하고 Pygame을 정리합니다."""
        self._audio.close()
        pygame.quit()

    # ── 내부 로직 ───────────────────────────────────────────────────────────

    def _deal_boss_damage(self, dmg: int) -> None:
        self.boss_hp = max(0, self.boss_hp - int(dmg))

    def _deal_player_damage(self, dmg: int) -> None:
        red = dmg
        if self.shield_time_left > 0:
            red = int(dmg * (1.0 - SHIELD_REDUCTION))
        self.player_hp = max(0, self.player_hp - red)
        if red != dmg:
            self._toast(f"Shield absorbs {dmg-red}", CYAN, keep_if_longer=True)

    def _update_timers(self, dt_ms: int) -> None:
        if self.shield_time_left > 0:
            self.shield_time_left = max(0, self.shield_time_left - dt_ms)
        for name, left in list(self._cooldowns.items()):
            if left > 0:
                self._cooldowns[name] = max(0, left - dt_ms)
        self.lightning_cd_left = self._cooldowns.get("LIGHTNING", 0)
        if self._boss_blind_left > 0:
            self._boss_blind_left = max(0, self._boss_blind_left - dt_ms)
        if self.message_time_left > 0:
            self.message_time_left = max(0, self.message_time_left - dt_ms)

    def _current_phase(self) -> Tuple[int, str, int, str]:
        """현재 보스 HP 비율에 해당하는 (페이즈 번호, 원소, 공격주기 ms, 패턴)."""
        ratio = self.boss_hp / float(BOSS_MAX_HP)
        for i, (low, elem, interval, pattern) in enumerate(BOSS_PHASES):
            if ratio > low:
                return i + 1, elem, interval, pattern
        last = BOSS_PHASES[-1]
        return len(BOSS_PHASES), last[1], last[2], last[3]

    def _update_boss_ai(self, dt_ms: int) -> None:
        if self.boss_hp <= 0:
            return
        phase, elem, interval, pattern = self._current_phase()
        if phase != self.boss_phase:
            prev, self.boss_phase = self.boss_phase, phase
            self.boss_element = elem
            if prev != 0:
                self._toast(f"BOSS PHASE {phase}: {elem}", RED)

        # 시전 주기마다 텔레그래프(경고) → BOSS_TELEGRAPH_MS 후 실제 발사
        self._boss_attack_timer += dt_ms
        while self._boss_attack_timer >= interval:
            self._boss_attack_timer -= interval
            self._spawn_telegraph()
            self._pending_boss_shots.append({"delay": BOSS_TELEGRAPH_MS, "pattern": pattern})

        still: List[dict] = []
        for shot in self._pending_boss_shots:
            shot["delay"] -= dt_ms
            if shot["delay"] <= 0:
                self._fire_boss_pattern(shot["pattern"])
            else:
                still.append(shot)
        self._pending_boss_shots = still

    def _fire_boss_pattern(self, pattern: str) -> None:
        px, py = self.player_pos
        if pattern == "spread3":
            for dx in (-150, 0, 150):
                self._spawn_boss_projectile(BOSS_DMG, end=(px + dx, py))
        elif pattern == "aimed":
            self._spawn_boss_projectile(BOSS_DMG + 3, end=(px, py),
                                        dur=PROJECTILE_DURATION_MS - 120)
        else:  # single
            self._spawn_boss_projectile(BOSS_DMG)

    def _toast(self, text: str, color: Tuple[int, int, int], keep_if_longer: bool = False) -> None:
        # 간단한 메시지 시스템: 잠시 상단 중앙에 표시
        if keep_if_longer and self.message_time_left > MESSAGE_DURATION_MS // 2:
            # 기존 메시지가 충분히 남아있으면 덮어쓰지 않음
            return
        self.message_text = text
        self.message_color = color
        self.message_time_left = MESSAGE_DURATION_MS

    def _reset_game(self) -> None:
        """게임 상태를 초기화하고 메뉴로 돌아갑니다."""
        self.player_hp = PLAYER_MAX_HP
        self.boss_hp   = BOSS_MAX_HP
        self.player_pos = (SCREEN_W // 2, SCREEN_H // 2)
        self.boss_pos   = (SCREEN_W - 150, SCREEN_H // 2)
        self._player_fx = float(self.player_pos[0])
        self._player_fy = float(self.player_pos[1])
        self.shield_time_left  = 0
        self.lightning_cd_left = 0
        self._cooldowns        = {}
        self._boss_blind_left  = 0
        self._boss_attack_timer = 0
        self.boss_phase        = 0
        self.boss_element      = BOSS_PHASES[0][1]
        self._pending_boss_shots = []
        self.message_text      = ""
        self.message_time_left = 0
        self._effects          = []
        self._state            = "menu"
        self.set_difficulty(self._saved_difficulty)

    def set_difficulty(self, level: str) -> None:
        level = level.lower()
        if level not in DIFFICULTY_PROB:
            level = "normal"
        self.difficulty = level
        self._boss_dodge_prob = DIFFICULTY_PROB[level]

    def _update_player_dodge(self, head_dir: Optional[str], dt_ms: int) -> None:
        dt_s = dt_ms / 1000.0
        if head_dir == "LEFT":
            vx = -self._player_speed_px_s
        elif head_dir == "RIGHT":
            vx = self._player_speed_px_s
        else:
            # CENTER: 서서히 기본 위치로 복귀 (속도의 40%)
            diff = self._player_center_x - self._player_fx
            vx = 0.0 if abs(diff) < 1.0 else (diff / abs(diff)) * self._player_speed_px_s * 0.4
        self._player_fx = max(self._arena_min_x, min(self._arena_max_x, self._player_fx + vx * dt_s))
        self.player_pos = (int(round(self._player_fx)), self.player_pos[1])

    # ── 렌더링 ──────────────────────────────────────────────────────────────

    def _render(self, dt_ms: int = 16) -> None:
        player_offset_x = (self._player_fx - SCREEN_W / 2) / (SCREEN_W / 2)
        self._fp.render_frame(
            player_hp=self.player_hp,
            boss_hp=self.boss_hp,
            shield_time_left=self.shield_time_left,
            lightning_cd_left=self.lightning_cd_left,
            message_text=self.message_text,
            message_time_left=self.message_time_left,
            message_color=getattr(self, 'message_color', WHITE),
            effects=self._effects,
            difficulty=self.difficulty,
            player_offset_x=player_offset_x,
            dt_ms=dt_ms,
        )

    # 메뉴 렌더
    def _render_menu(self) -> None:
        self._fp.render_menu(
            btn_start=self._btn_start,
            btn_exit=self._btn_exit,
            btn_guide=self._btn_guide,
            btn_settings=self._btn_settings,
            difficulty=self.difficulty,
        )

    # 이펙트 로직
    def _spawn_player_projectile(
        self,
        element: str,
        color: Tuple[int, int, int],
        dmg: int,
        dur_ms: int,
        style: str,
    ) -> None:
        # 시전 순간의 플레이어 오프셋을 저장 → 렌더러가 시전 위치에서 투사체를 출발시킴
        cast_offset_x = (self._player_fx - SCREEN_W / 2) / (SCREEN_W / 2)
        self._effects.append({
            "type": "proj",
            "element": element,
            "style": style,
            "color": color,
            "start": self.player_pos,
            "end": self.boss_pos,
            "elapsed": 0,
            "dur": dur_ms,
            "r": 8,
            "origin": "player",
            "target": "boss",
            "dmg": int(dmg),
            "dodge_checked": False,
            "dodged": False,
            "cast_offset_x": cast_offset_x,
        })

    def _spawn_boss_projectile(self, dmg: int,
                               end: Optional[Tuple[int, int]] = None,
                               dur: Optional[int] = None) -> None:
        self._audio.play_boss_attack()
        self._effects.append({
            "type": "proj",
            "element": "BOSS",
            "style": "boss",
            "color": RED,
            "start": self.boss_pos,
            "end": end if end is not None else self.player_pos,
            "elapsed": 0,
            "dur": dur if dur is not None else PROJECTILE_DURATION_MS,
            "r": 8,
            "origin": "boss",
            "target": "player",
            "dmg": int(dmg),
        })

    def _spawn_telegraph(self) -> None:
        """보스 시전 전 경고 링(보스 위치)."""
        self._effects.append({
            "type": "telegraph",
            "elapsed": 0,
            "dur": BOSS_TELEGRAPH_MS,
        })

    def _spawn_cast_effect(self, color: Tuple[int, int, int], style: str) -> None:
        self._effects.append({
            "type": "cast",
            "color": color,
            "style": style,
            "elapsed": 0,
            "dur": 180,
            "r0": 10,
            "r1": 34,
        })

    def _spawn_magic_circle(self, element: str) -> None:
        color = MAGIC_CIRCLE_COLORS.get(element, (180, 180, 200))
        self._effects.append({
            "type": "magic_circle",
            "element": element,
            "color": color,
            "elapsed": 0,
            "dur": 1800,
        })

    def _spawn_impact_effect(self, color: Tuple[int, int, int], style: str, hit: bool) -> None:
        self._effects.append({
            "type": "impact",
            "color": color,
            "style": style,
            "elapsed": 0,
            "dur": 260 if hit else 180,
            "r0": 10,
            "r1": 42 if hit else 26,
            "hit": hit,
        })

    def _spawn_shield_ring(self) -> None:
        self._effects.append({
            "type": "ring",
            "color": CYAN,
            "style": "light",
            "center": self.player_pos,
            "elapsed": 0,
            "dur": RING_DURATION_MS,
            "r0": self.player_r + 4,
            "r1": self.player_r + 18,
            "w": 3,
        })

    def _update_effects(self, dt_ms: int) -> None:
        alive: List[dict] = []

        for e in self._effects:
            e["elapsed"] += dt_ms

            if e["type"] == "proj":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))

                if e.get("origin") == "player" and not e.get("dodge_checked", False) and 0.6 <= t <= 0.9:
                    prob = 0.0 if self._boss_blind_left > 0 else getattr(self, "_boss_dodge_prob", 0.4)
                    if random.random() < prob:
                        direction = -1 if random.random() < 0.5 else 1
                        dash_px = max(90, int(self.boss_r * 2))
                        new_x = max(
                            self.boss_r + 30,
                            min(SCREEN_W - (self.boss_r + 30), self.boss_pos[0] + direction * dash_px)
                        )
                        self.boss_pos = (new_x, self.boss_pos[1])
                        e["dodged"] = True
                        self._toast("BOSS DODGE!", GREY, keep_if_longer=True)
                    e["dodge_checked"] = True

                if e["elapsed"] >= e["dur"]:
                    sx, sy = e["start"]
                    ex, ey = e["end"]
                    hit_x = int(sx + (ex - sx))
                    hit_y = int(sy + (ey - sy))

                    if e.get("target") == "boss":
                        tx, ty = self.boss_pos
                        thr = self.boss_r + e.get("r", 8)
                        if math.hypot(hit_x - tx, hit_y - ty) <= thr:
                            mult = affinity_mult(e.get("element", ""), self.boss_element)
                            dmg = int(round(e.get("dmg", 0) * mult))
                            self._deal_boss_damage(dmg)
                            self._spawn_impact_effect(e["color"], e.get("style", "fire"), True)
                            if e.get("blind_ms"):
                                self._boss_blind_left = e["blind_ms"]
                                self._toast("BOSS BLINDED!", PURPLE)
                            else:
                                tag = "  x1.5" if mult > 1.0 else ("  x0.6" if mult < 1.0 else "")
                                self._toast(f"HIT -{dmg} HP{tag}",
                                            YELLOW if mult >= 1.0 else GREY)
                        else:
                            self._spawn_impact_effect(e["color"], e.get("style", "fire"), False)
                            self._toast("MISS", GREY, keep_if_longer=True)
                    else:
                        tx, ty = self.player_pos
                        thr = self.player_r + e.get("r", 8)
                        if math.hypot(hit_x - tx, hit_y - ty) <= thr:
                            self._deal_player_damage(e.get("dmg", 0))
                            self._spawn_impact_effect(e["color"], "boss", True)
                        else:
                            self._toast("DODGED!", CYAN, keep_if_longer=True)
                    continue

            if e["elapsed"] < e["dur"]:
                alive.append(e)

        self._effects = alive


if __name__ == "__main__":
    # 간단한 데모 루프 (주문 입력 없음)
    game = SpellGame()
    try:
        running = True
        while running:
            running = game.run_one_frame(None)
    finally:
        game.close()

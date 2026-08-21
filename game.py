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

FIRE_DMG = 12            # LINE → FIRE
LIGHTNING_DMG = 25       # ZIGZAG → LIGHTNING
LIGHTNING_COOLDOWN_MS = 4000

SHIELD_REDUCTION = 0.5   # CIRCLE → SHIELD (입는 피해 50% 감소)
SHIELD_DURATION_MS = 2500

BOSS_DMG = 5
BOSS_ATTACK_INTERVAL_MS = 1667  # 1000 / 0.6 → 0.6× speed

MESSAGE_DURATION_MS = 1500
PROJECTILE_DURATION_MS = 450
RING_DURATION_MS = 350

# ── 보스 페이즈 / 예고(telegraph) ───────────────────────────────────
PHASE2_HP_RATIO = 0.70
PHASE3_HP_RATIO = 0.30

PHASE_ATTACK_INTERVAL_MS = {1: BOSS_ATTACK_INTERVAL_MS, 2: 1500, 3: 1250}
PHASE_ATTACK_KINDS = {
    1: ("single",),
    2: ("burst", "sweep", "single"),
    3: ("aoe", "burst", "sweep"),
}
TELEGRAPH_MS = {"single": 500, "burst": 600, "sweep": 650, "aoe": 850}
TELEGRAPH_LABELS = {
    "single": "! 조준 중",
    "burst": "!! 3연사 준비",
    "sweep": "!! 좌우 스윕 - 가운데를 피하세요",
    "aoe": "!!! 광역기 - SHIELD!",
}
BURST_SHOTS = 3
BURST_STAGGER_MS = 130
AOE_DMG = 13          # 이동으로 피할 수 없음 → 실드 필수
SWEEP_SPREAD_PX = 260  # 좌우로 갈라지는 스윙 공격 폭

# ── 원소 상성 ──────────────────────────────────────────────
WEAKNESS_CYCLE = ("FIRE", "WATER", "EARTH", "WIND")
RESIST_OF = {"FIRE": "WATER", "WATER": "FIRE", "EARTH": "WIND", "WIND": "EARTH"}
WEAKNESS_MULTIPLIER = 2.0
RESIST_MULTIPLIER = 0.5
WEAKNESS_ROTATE_MS = 15000
WEAK_HIT_STAGGER_MS = 700   # 약점 적중 시 보스 경직

# ── 콤보 상태이상 ─────────────────────────────────────────
BOSS_DOT_INTERVAL_MS = 500
BOSS_SLOW_FACTOR = 0.5      # 둔화: 회피 확률 절반
BOSS_BLIND_MISS_PROB = 0.5  # 실명: 보스 공격이 빗나갈 확률

# Enhanced Element Colors with Neon Vibrancy
FIRE_NEON = (255, 100, 50)  # Bright Fire Orange
WATER_NEON = (60, 180, 255)  # Bright Water Blue
WIND_NEON = (120, 255, 180)  # Mint Wind Green
EARTH_NEON = (200, 160, 100)  # Golden Earth
DARK_NEON = (160, 80, 255)  # Deep Purple
LTNG_NEON = (100, 220, 255)  # Electric Blue

ELEMENT_PRESETS = {
    "FIRE": {
        "color": FIRE_NEON,
        "style": "fire",
        "dmg": FIRE_DMG,
        "dur": PROJECTILE_DURATION_MS,
    },
    "WATER": {
        "color": WATER_NEON,
        "style": "water",
        "dmg": FIRE_DMG - 1,
        "dur": PROJECTILE_DURATION_MS + 40,
    },
    "WIND": {
        "color": WIND_NEON,
        "style": "wind",
        "dmg": FIRE_DMG - 2,
        "dur": PROJECTILE_DURATION_MS - 40,
    },
    "EARTH": {
        "color": EARTH_NEON,
        "style": "earth",
        "dmg": FIRE_DMG + 2,
        "dur": PROJECTILE_DURATION_MS + 80,
    },
    "DARK": {
        "color": DARK_NEON,
        "style": "dark",
        "dmg": FIRE_DMG,
        "dur": PROJECTILE_DURATION_MS + 20,
    },
    "LIGHTNING": {
        "color": LTNG_NEON,
        "style": "lightning",
        "dmg": LIGHTNING_DMG,
        "dur": max(280, PROJECTILE_DURATION_MS - 120),
    },
}


# 콤보 주문 프리셋 (spell_combo.COMBO_RULES의 결과명과 1:1 대응)
#   element : 상성 판정에 사용되는 속성
#   dot     : (틱당 피해, 지속 ms)   slow/root/blind : 지속 ms
#   pierce  : 보스 회피 무시     drain : 명중 시 플레이어 회복량   hits : 다단 히트 수
COMBO_PRESETS = {
    "STEAM": {
        "color": (200, 220, 255), "style": "water", "element": "WATER",
        "dmg": 16, "dot": (3, 3000), "desc": "화상 지속피해",
    },
    "MUD": {
        "color": (150, 110, 70), "style": "earth", "element": "EARTH",
        "dmg": 12, "root": 1500, "desc": "회피 봉쇄",
    },
    "FLAME_BALL": {
        "color": (255, 80, 30), "style": "fire", "element": "FIRE",
        "dmg": 26, "desc": "거대 화염구",
    },
    "ICE_SHARD": {
        "color": (140, 220, 255), "style": "water", "element": "WATER",
        "dmg": 16, "slow": 2500, "desc": "둔화",
    },
    "TORNADO": {
        "color": (120, 255, 180), "style": "wind", "element": "WIND",
        "dmg": 7, "hits": 4, "desc": "4단 히트",
    },
    "STONE_BULLET": {
        "color": (200, 160, 100), "style": "earth", "element": "EARTH",
        "dmg": 20, "pierce": True, "desc": "회피 무시",
    },
    "BLINDNESS": {
        "color": (240, 255, 255), "style": "light", "element": "LIGHT",
        "dmg": 6, "blind": 4000, "desc": "보스 명중률 ↓",
    },
    "CURSE_SHOCK": {
        "color": (160, 80, 255), "style": "dark", "element": "DARK",
        "dmg": 18, "drain": 8, "desc": "HP 흡수",
    },
}


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


@dataclass
class SpellResult:
    name: str
    applied: bool
    reason: str = ""
    element: str = ""


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
        self.lightning_cd_left = 0

        # 보스 공격 주기 타이머
        self._boss_attack_timer = 0

        # 보스 페이즈 / 예고 / 상태이상
        self._boss_phase = 1
        self._telegraph: Optional[dict] = None
        self._boss_stagger_left = 0
        self._boss_root_left = 0
        self._boss_slow_left = 0
        self._boss_blind_left = 0
        self._boss_dots: List[dict] = []

        # 원소 상성(보스 약점)
        self.boss_weakness = random.choice(WEAKNESS_CYCLE)
        self._weakness_timer = 0

        # 콤보 힌트(입력 대기 중인 기본 주문)
        self._combo_hint: Optional[Tuple[str, float]] = None

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

    @property
    def is_playing(self) -> bool:
        """전투(playing) 상태 여부 — 외부 입력 파이프라인의 게이트로 사용합니다."""
        return self._state == "playing"

    def run_one_frame(
        self,
        spell_name: Optional[str],
        head_dir: Optional[str] = None,
        combo_hint: Optional[Tuple[str, float]] = None,
    ) -> bool:
        """한 프레임을 처리합니다.

        - Pygame 이벤트 처리(종료 등)
        - 제공된 주문명을 적용
        - 내부 상태 업데이트 및 렌더링

        Returns:
            계속 실행하려면 True, 창 종료/ESC 시 False.
        """
        _prev_state = self._state
        # 콤보 대기 상태(주문명, 남은 시간 비율)는 렌더러 HUD로 그대로 전달됩니다.
        self._combo_hint = combo_hint

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
                self._audio.play_spell_sfx(_result.element or _result.name)

        # 나머지 업데이트 (순서 중요: 상태이상/페이즈 → AI 판단 → 투사체 판정)
        self._update_boss_status(dt)
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
        label = spell_name.upper()

        # 궤적 분류 결과(LINE/CIRCLE/ZIGZAG)를 주문 이름으로 정규화
        if label in ("LINE", "FIRE"):
            label = "FIRE"

        if label in ("CIRCLE", "LIGHT_SHIELD", "SHIELD"):
            return self._cast_shield()

        if label in ("ZIGZAG", "LIGHTNING"):
            return self._cast_lightning()

        # 콤보 엔진이 승격시킨 상위 주문 (STEAM/TORNADO/...)
        if label in COMBO_PRESETS:
            return self._cast_combo(label)

        if label in ("LIGHT",):
            return self._cast_shield()

        if label in ELEMENT_PRESETS:
            return self._cast_element(label)

        self._toast(f"UNKNOWN: {spell_name}", GREY)
        return SpellResult("UNKNOWN", False, "unrecognized")

    # ── 시전 헬퍼 ───────────────────────────────────────────────────────────

    _CAST_FX = {
        "FIRE":  (15, "spark", 3.0, 150, YELLOW),
        "WATER": (12, "glow",  2.5, 130, BLUE),
        "WIND":  (20, "spark", 2.0, 120, GREEN),
        "EARTH": (10, "spark", 4.0, 180, GREY),
        "DARK":  (18, "glow",  3.5, 160, PURPLE),
    }

    def _cast_element(self, element: str) -> SpellResult:
        p = ELEMENT_PRESETS[element]
        count, pstyle, shake, shake_ms, toast_col = self._CAST_FX.get(
            element, (14, "spark", 3.0, 150, WHITE)
        )
        self._spawn_player_projectile(
            element=element,
            color=p["color"],
            dmg=p["dmg"],
            dur_ms=p["dur"],
            style=p["style"],
        )
        self._spawn_cast_effect(p["color"], p["style"])
        self._spawn_magic_circle(element)
        self._wand_particles(count, p["color"], pstyle)
        self._fp.add_camera_shake(shake, shake_ms)
        self._toast(f"{element}!", toast_col)
        return SpellResult(element, True, element=element)

    def _cast_combo(self, name: str) -> SpellResult:
        """콤보 주문 시전 — 프리셋의 상태이상을 투사체 payload에 실어 명중 시점에 적용합니다."""
        p = COMBO_PRESETS[name]
        hits = int(p.get("hits", 1))
        base_dur = PROJECTILE_DURATION_MS + 40
        # 다단 히트는 도착 시간을 어긋나게 해 연타처럼 보이게 함
        for i in range(hits):
            self._spawn_player_projectile(
                element=p["element"],
                color=p["color"],
                dmg=p["dmg"],
                dur_ms=base_dur + i * 120,
                style=p["style"],
                payload={
                    "combo": name,
                    "pierce": bool(p.get("pierce", False)),
                    "dot": p.get("dot"),
                    "slow": p.get("slow", 0),
                    "root": p.get("root", 0),
                    "blind": p.get("blind", 0),
                    "drain": p.get("drain", 0),
                },
            )
        self._spawn_cast_effect(p["color"], p["style"])
        self._spawn_magic_circle(p["element"])
        self._wand_particles(28, p["color"], "glow")
        self._fp.add_camera_shake(6.0, 220)
        self._toast(f"COMBO {name}! ({p['desc']})", GOLD)
        return SpellResult(name, True, element=p["element"])

    def _cast_shield(self) -> SpellResult:
        self.shield_time_left = SHIELD_DURATION_MS
        self._spawn_shield_ring()
        self._spawn_cast_effect(CYAN, "light")
        self._spawn_magic_circle("LIGHT")
        self._wand_particles(25, CYAN, "glow")
        self._fp.add_camera_shake(2.0, 140)
        self._toast(f"SHIELD ({SHIELD_DURATION_MS // 1000}s)", CYAN)
        return SpellResult("LIGHT", True, element="LIGHT")

    def _cast_lightning(self) -> SpellResult:
        if self.lightning_cd_left > 0:
            self._toast("LIGHTNING (cooldown)", GREY)
            return SpellResult("LIGHTNING", False, "cooldown")

        p = ELEMENT_PRESETS["LIGHTNING"]
        self.lightning_cd_left = LIGHTNING_COOLDOWN_MS
        self._spawn_player_projectile(
            element="LIGHTNING",
            color=p["color"],
            dmg=p["dmg"],
            dur_ms=p["dur"],
            style=p["style"],
        )
        self._spawn_cast_effect(p["color"], p["style"])
        self._spawn_magic_circle("LIGHTNING")
        self._wand_particles(30, p["color"], "spark")
        self._fp.add_camera_shake(5.0, 200)
        self._toast("LIGHTNING!", BLUE)
        return SpellResult("LIGHTNING", True, element="LIGHTNING")

    def _wand_particles(self, count: int, color: Tuple[int, int, int], style: str) -> None:
        wand_x, wand_y = int(SCREEN_W * 0.61), int(SCREEN_H * 0.71)
        self._fp.add_particles(wand_x, wand_y, count, color, style)

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
        if self.lightning_cd_left > 0:
            self.lightning_cd_left = max(0, self.lightning_cd_left - dt_ms)
        if self.message_time_left > 0:
            self.message_time_left = max(0, self.message_time_left - dt_ms)

    # ── 원소 상성 ───────────────────────────────────────────────────────────

    def element_multiplier(self, element: Optional[str]) -> float:
        """공격 원소가 보스 약점이면 2배, 저항 원소면 0.5배."""
        if not element:
            return 1.0
        if element == self.boss_weakness:
            return WEAKNESS_MULTIPLIER
        if element == RESIST_OF.get(self.boss_weakness):
            return RESIST_MULTIPLIER
        return 1.0

    def _rotate_weakness(self) -> None:
        choices = [e for e in WEAKNESS_CYCLE if e != self.boss_weakness]
        self.boss_weakness = random.choice(choices)
        self._weakness_timer = 0
        self._toast(f"WEAKNESS: {self.boss_weakness}", GOLD, keep_if_longer=True)

    # ── 보스 상태이상 / 페이즈 ──────────────────────────────────────────────

    def _compute_phase(self) -> int:
        ratio = self.boss_hp / float(BOSS_MAX_HP)
        if ratio > PHASE2_HP_RATIO:
            return 1
        if ratio > PHASE3_HP_RATIO:
            return 2
        return 3

    def _update_boss_status(self, dt_ms: int) -> None:
        self._boss_stagger_left = max(0, self._boss_stagger_left - dt_ms)
        self._boss_root_left = max(0, self._boss_root_left - dt_ms)
        self._boss_slow_left = max(0, self._boss_slow_left - dt_ms)
        self._boss_blind_left = max(0, self._boss_blind_left - dt_ms)

        # 지속 피해(화상 등)
        alive: List[dict] = []
        for dot in self._boss_dots:
            dot["left"] -= dt_ms
            dot["acc"] += dt_ms
            while dot["acc"] >= BOSS_DOT_INTERVAL_MS:
                dot["acc"] -= BOSS_DOT_INTERVAL_MS
                self._deal_boss_damage(dot["dmg"])
            if dot["left"] > 0:
                alive.append(dot)
        self._boss_dots = alive

        # 약점 원소 로테이션
        self._weakness_timer += dt_ms
        if self._weakness_timer >= WEAKNESS_ROTATE_MS:
            self._rotate_weakness()

        # 페이즈 전환: HP 구간이 바뀌면 예고를 취소하고 약점 원소도 새로 뽑음
        phase = self._compute_phase()
        if phase != self._boss_phase:
            self._boss_phase = phase
            self._telegraph = None
            self._boss_attack_timer = 0
            self._fp.add_camera_shake(7.0, 400)
            self._toast(f"PHASE {phase}!", RED)
            self._rotate_weakness()

    def _update_boss_ai(self, dt_ms: int) -> None:
        """예고(telegraph) → 발사 2단계로 동작하는 페이즈별 보스 AI."""
        if self._boss_stagger_left > 0:
            return

        if self._telegraph is not None:
            self._telegraph["left"] -= dt_ms
            if self._telegraph["left"] <= 0:
                kind = self._telegraph["kind"]
                self._telegraph = None
                self._fire_boss_attack(kind)
            return

        # 페이즈가 올라갈수록 공격 주기가 짧아짐
        self._boss_attack_timer += dt_ms
        interval = PHASE_ATTACK_INTERVAL_MS[self._boss_phase]
        if self._boss_attack_timer >= interval:
            self._boss_attack_timer = 0
            kind = random.choice(PHASE_ATTACK_KINDS[self._boss_phase])
            total = TELEGRAPH_MS[kind]
            self._telegraph = {"kind": kind, "left": total, "total": total}
            self._toast(TELEGRAPH_LABELS[kind], ORANGE, keep_if_longer=True)

    def _fire_boss_attack(self, kind: str) -> None:
        if kind == "burst":
            for i in range(BURST_SHOTS):
                self._spawn_boss_projectile(BOSS_DMG, delay_ms=i * BURST_STAGGER_MS)
        elif kind == "sweep":
            # 현재 위치와 한쪽 방향을 함께 노려, 반대쪽으로 피하도록 강제
            side = random.choice((-1, 1))
            px = self.player_pos[0]
            self._spawn_boss_projectile(BOSS_DMG, target_x=px)
            self._spawn_boss_projectile(
                BOSS_DMG, target_x=px + side * SWEEP_SPREAD_PX, delay_ms=BURST_STAGGER_MS
            )
        elif kind == "aoe":
            self._spawn_boss_projectile(AOE_DMG, aoe=True)
            self._fp.add_camera_shake(6.0, 300)
        else:
            self._spawn_boss_projectile(BOSS_DMG)

    @property
    def telegraph_progress(self) -> Optional[float]:
        """예고 진행률(0~1). 예고 중이 아니면 None."""
        if self._telegraph is None:
            return None
        total = max(1, self._telegraph["total"])
        return 1.0 - max(0, self._telegraph["left"]) / float(total)

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
        self._boss_attack_timer = 0
        self._boss_phase       = 1
        self._telegraph        = None
        self._boss_stagger_left = 0
        self._boss_root_left   = 0
        self._boss_slow_left   = 0
        self._boss_blind_left  = 0
        self._boss_dots        = []
        self.boss_weakness     = random.choice(WEAKNESS_CYCLE)
        self._weakness_timer   = 0
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
            boss_weakness=self.boss_weakness,
            boss_phase=self._boss_phase,
            telegraph_progress=self.telegraph_progress,
            telegraph_kind=self._telegraph["kind"] if self._telegraph else None,
            combo_hint=self._combo_hint,
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

    def _draw_hp_bar(self, rect: Tuple[int, int, int, int], hp: int, hp_max: int, color: Tuple[int, int, int]) -> None:
        x, y, w, h = rect
        pygame.draw.rect(self.screen, GREY, (x, y, w, h), border_radius=4)
        ratio = max(0.0, min(1.0, hp / float(hp_max)))
        pygame.draw.rect(self.screen, color, (x, y, int(w * ratio), h), border_radius=4)
        self._blit_text(f"{hp}/{hp_max}", (x + w + 8, y - 2), WHITE)

    def _blit_text(self, text: str, pos: Tuple[int, int], color: Tuple[int, int, int]) -> None:
        surf = self.font.render(text, True, color)
        self.screen.blit(surf, pos)

    # 이펙트 로직
    def _spawn_player_projectile(
        self,
        element: str,
        color: Tuple[int, int, int],
        dmg: int,
        dur_ms: int,
        style: str,
        payload: Optional[dict] = None,
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
            **(payload or {}),
        })

    def _spawn_boss_projectile(
        self,
        dmg: int,
        delay_ms: int = 0,
        target_x: Optional[int] = None,
        aoe: bool = False,
    ) -> None:
        self._audio.play_boss_attack()
        end_x = self.player_pos[0] if target_x is None else int(target_x)
        # 실명 상태: 일정 확률로 조준이 크게 빗나감
        if self._boss_blind_left > 0 and random.random() < BOSS_BLIND_MISS_PROB:
            end_x += random.choice((-1, 1)) * 220
        self._effects.append({
            "type": "proj",
            "element": "BOSS",
            "style": "boss",
            "color": RED,
            "start": self.boss_pos,
            "end": (end_x, self.player_pos[1]),
            "elapsed": -int(delay_ms),
            "dur": PROJECTILE_DURATION_MS,
            "r": 8,
            "origin": "boss",
            "target": "player",
            "dmg": int(dmg),
            "aoe": aoe,
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

                # 비행 후반부(60~90%)에 보스 회피를 1회만 판정
                if e.get("origin") == "player" and not e.get("dodge_checked", False) and 0.6 <= t <= 0.9:
                    # 관통(STONE_BULLET) 또는 속박(MUD) 상태면 회피 자체가 불가
                    if not e.get("pierce", False) and self._boss_root_left <= 0:
                        prob = self._boss_dodge_prob
                        if self._boss_slow_left > 0:
                            prob *= BOSS_SLOW_FACTOR
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
                            self._resolve_boss_hit(e)
                        else:
                            self._spawn_impact_effect(e["color"], e.get("style", "fire"), False)
                            self._toast("MISS", GREY, keep_if_longer=True)
                    else:
                        tx, ty = self.player_pos
                        thr = self.player_r + e.get("r", 8)
                        # 광역기(aoe)는 위치와 무관하게 명중 → 실드로만 경감 가능
                        if e.get("aoe", False) or math.hypot(hit_x - tx, hit_y - ty) <= thr:
                            self._deal_player_damage(e.get("dmg", 0))
                            self._spawn_impact_effect(e["color"], "boss", True)
                        else:
                            self._toast("DODGED!", CYAN, keep_if_longer=True)
                    continue

            if e["elapsed"] < e["dur"]:
                alive.append(e)

        self._effects = alive

    def _resolve_boss_hit(self, e: dict) -> None:
        """보스 명중 처리: 원소 상성 배율 + 콤보 상태이상 적용."""
        # 최종 피해 = 기본 피해 x 상성 배율 (약점 2배 / 상극 0.5배), 최소 1
        mult = self.element_multiplier(e.get("element"))
        dmg = max(1, int(round(e.get("dmg", 0) * mult)))
        self._deal_boss_damage(dmg)
        self._spawn_impact_effect(e["color"], e.get("style", "fire"), True)

        dot = e.get("dot")
        if dot:
            dot_dmg, dot_ms = dot
            self._boss_dots.append({"dmg": int(dot_dmg), "left": int(dot_ms), "acc": 0})
        if e.get("slow", 0):
            self._boss_slow_left = max(self._boss_slow_left, int(e["slow"]))
        if e.get("root", 0):
            self._boss_root_left = max(self._boss_root_left, int(e["root"]))
        if e.get("blind", 0):
            self._boss_blind_left = max(self._boss_blind_left, int(e["blind"]))
        if e.get("drain", 0):
            healed = min(PLAYER_MAX_HP - self.player_hp, int(e["drain"]))
            self.player_hp += healed

        if mult >= WEAKNESS_MULTIPLIER:
            self._boss_stagger_left = WEAK_HIT_STAGGER_MS
            self._fp.add_camera_shake(6.0, 220)
            self._toast(f"WEAK POINT!  -{dmg} HP", GOLD)
        elif mult <= RESIST_MULTIPLIER:
            self._toast(f"RESISTED  -{dmg} HP", GREY)
        else:
            self._toast(f"HIT -{dmg} HP", YELLOW)

    def _render_effects(self) -> None:
        for e in self._effects:
            if e["type"] == "proj":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])) )
                sx, sy = e["start"]
                ex, ey = e["end"]
                x = int(sx + (ex - sx) * t)
                y = int(sy + (ey - sy) * t)
                pygame.draw.circle(self.screen, e["color"], (x, y), e["r"]) 
            elif e["type"] == "ring":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])) )
                r = int(e["r0"] + (e["r1"] - e["r0"]) * t)
                pygame.draw.circle(self.screen, e["color"], e["center"], r, e["w"])


if __name__ == "__main__":
    # 간단한 데모 루프 (주문 입력 없음)
    game = SpellGame()
    try:
        running = True
        while running:
            running = game.run_one_frame(None)
    finally:
        game.close()

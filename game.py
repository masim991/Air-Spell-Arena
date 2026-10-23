from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List

import datetime as _dt
import math
import os
import random
import pygame
import daily as daily_mod
import highlight
import hud_ext
import mana as mana_mod
import save_data
import share_card
from audio_manager import AudioManager, ALL_SLOTS, SPELL_SLOTS
from fp_renderer import FPRenderer
from mana import ManaPool
from runes import RUNES_BY_ID, RuneState
from webcam_overlay import ScryingOrb


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

# (주문별 색/데미지/쿨다운 프리셋은 DIFFICULTY_PROB 아래 _SPELL_DB 에 통합)


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

# 난이도별 종합 밸런스 — 회피 확률뿐 아니라 보스 공격력/공격 주기도 함께 조정된다.
# ("Impossible"가 회피만 잦아지는 게 아니라 실제로 더 아프고 더 빠르게 때리도록)
DIFFICULTY_CONFIG = {
    "easy":       {"dodge": 0.12, "boss_dmg": 0.75, "interval": 1.25},
    "normal":     {"dodge": 0.30, "boss_dmg": 1.00, "interval": 1.00},
    "hard":       {"dodge": 0.50, "boss_dmg": 1.30, "interval": 0.82},
    "impossible": {"dodge": 0.68, "boss_dmg": 1.65, "interval": 0.65},
}
DIFFICULTY_PROB = {k: v["dodge"] for k, v in DIFFICULTY_CONFIG.items()}  # 하위호환(테스트 참조용)
DIFFICULTY_SCORE_MULT = {"easy": 0.7, "normal": 1.0, "hard": 1.4, "impossible": 1.9}

# 점수 산정 가중치
SCORE_HIT_BASE = 15
SCORE_DMG_MULT = 4
SCORE_MISS_PENALTY = 4
SCORE_WIN_BONUS = 400
SCORE_TIME_BONUS_PER_SEC = 3   # 승리 시 남은 "여유 시간" 1초당 가산(200초 기준)

# 키보드 폴백: 숫자 1~7 → 주문 (SPELL_SLOTS 순서와 동일)
KEYBOARD_SPELLS = {
    pygame.K_1: "FIRE", pygame.K_2: "WATER", pygame.K_3: "WIND",
    pygame.K_4: "EARTH", pygame.K_5: "DARK", pygame.K_6: "LIGHT",
    pygame.K_7: "LIGHTNING",
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

# ── 듀얼 캐스팅(양손 동시 시전) ──────────────────────────────────────────────
# 같은 손모양 두 개 → AMPLIFY(증폭), 다른 손모양 두 개 → FUSION(즉시 융합).
# 증폭은 한 손 시전의 2배 위력을 내지만 마나는 1.6배만 쓴다 — 양손을 드는
# "손해"(트래킹 난이도·팔 피로)를 효율로 보상해 굳이 두 손을 들 이유를 만든다.
AMPLIFY_DMG_MULT = 2.0
AMPLIFY_COST_MULT = 1.6

# 마나가 모자라 시전이 튕겼을 때 같은 토스트가 매 프레임 도배되지 않게 하는 간격.
MANA_FAIL_TOAST_MS = 600

# ── 보스 레지스트리 ──────────────────────────────────────────────────────────
# 세 보스 모두 같은 실루엣을 쓰지만(오라 링 색 + 페이즈 원소 로테이션으로 구분),
# 페이즈 원소 순서가 서로 겹치지 않게 짜서 상성 대응법이 매번 달라지게 했다.
BOSSES: dict = {
    "arcane": {
        "name": "ARCANE BOSS",
        "phases": BOSS_PHASES,                 # FIRE → WATER → DARK
        "accent": None,                        # 기본 배색(레거시 룩) 그대로 사용
        "dmg_mult": 1.0,
    },
    "frost": {
        "name": "FROSTBOUND WRAITH",
        "phases": [                            # WIND → EARTH → LIGHT
            (0.66, "WIND",  1400, "spread3"),
            (0.33, "EARTH", 1550, "single"),
            (0.0,  "LIGHT",  900, "aimed"),
        ],
        "accent": (130, 190, 255),             # 한랭한 청백색 오라 링
        "dmg_mult": 1.1,
    },
    "void": {
        "name": "VOIDBOUND DEVOURER",
        "phases": [                            # DARK → EARTH → FIRE (가장 빠른 최종 페이즈)
            (0.66, "DARK",  1250, "aimed"),
            (0.33, "EARTH", 1000, "spread3"),
            (0.0,  "FIRE",   680, "aimed"),
        ],
        "accent": (225, 60, 220),              # 독기어린 자보라색 오라 링
        "dmg_mult": 1.25,
    },
}

# ── 스테이지 사다리 ──────────────────────────────────────────────────────────
# 한 체인(런) 안에서 1→2→3 순서로 이어 싸운다. 스테이지를 깨면 엔딩 화면에서
# 곧장 다음 스테이지로 이어갈지, 여기서 멈출지 직접 고를 수 있다.
STAGE_LADDER = ["arcane", "frost", "void"]

# 난이도별로 한 체인에서 도달 가능한 최대 스테이지. 난이도가 높을수록 더 깊은
# 가우틀릿(= 더 다양한/강한 보스)에 도전한다 — "난이도별로 다른 보스" 요청 반영.
DIFFICULTY_MAX_STAGE = {"easy": 1, "normal": 2, "hard": 3, "impossible": 3}

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
    mode: str = "single"     # 'single' | 'amplify' | 'fusion'


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
        pygame.display.set_caption("Air Spell Arena")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 24)
        self.font_big = pygame.font.SysFont(None, 36)
        self._fp = FPRenderer(self.screen, self.font, self.font_big)

        # ── 일일 시드 챌린지 ──
        # 활성화되면 보스 순서·룬 후보·변형 규칙이 전부 날짜 시드에서 나온다.
        # _apply_stage 가 아래에서 바로 이 값을 읽으므로 가장 먼저 정의한다.
        self._daily = daily_mod.DailyState()
        self._stage_ladder: list = list(STAGE_LADDER)

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

        # 키보드 폴백 입력 상태
        self._pending_kb_spell: Optional[str] = None
        self._kb_dir: Optional[str] = None

        # 궤적 주문 입력 피드백(비전 파이프라인이 매 프레임 갱신)
        self._gesture_trail: list = []
        self._gesture_drawing: bool = False

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
        # 메뉴 버튼 위계: START(주) > DAILY(부) > GUIDE/SETTINGS > CAMERA > EXIT.
        # EXIT 는 중립 동작이라 가장 작고 조용한 자리로 내린다.
        _cx = SCREEN_W // 2
        self._btn_start     = pygame.Rect(_cx - 160, 326, 320, 58)
        self._btn_daily     = pygame.Rect(_cx - 160, 394, 320, 42)
        self._btn_guide     = pygame.Rect(_cx - 165, 448, 160, 38)
        self._btn_settings  = pygame.Rect(_cx + 5,   448, 160, 38)
        self._btn_no_camera = pygame.Rect(_cx - 140, 596, 280, 32)
        self._btn_exit      = pygame.Rect(_cx - 60,  672, 120, 28)
        # 타이틀 화면의 라이브 수정구 — 버튼 열(480~800px)과 겹치지 않는 왼쪽.
        self._menu_orb_center = (236, 374)

        # 입력 모드: 'camera' | 'keyboard'. main.py가 이 플래그를 보고
        # 노카메라 요청이 오면 비전 파이프라인을 정리한다.
        # 카메라 제어는 양방향이다.
        #   _camera_request : 이번 프레임에 main.py 로 보낼 요청("on" | "off" | None)
        #   _camera_active  : main.py 가 알려준 *실제* 파이프라인 상태
        # 둘을 분리해야 "껐는데 버튼은 켜짐"처럼 UI가 거짓말하는 일이 없다.
        # _input_mode 는 _camera_active 에서 파생되는 읽기 전용 값이다(별도 필드로
        # 두면 둘이 어긋나 "카메라는 꺼졌는데 UI 는 켜짐"이 된다).
        self._camera_request: Optional[str] = None
        self._camera_active = False

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

        # 영구 저장 데이터(점수/난이도/보스 해금/카메라 설정) 로드
        self._save: dict = save_data.load()

        # 난이도(보스 회피 확률 + 공격력/공격주기) — 마지막으로 쓰던 난이도 복원
        self._saved_difficulty = self._save.get("last_difficulty", "normal")
        self.set_difficulty(self._saved_difficulty)

        # 스테이지 사다리 — 항상 1스테이지(ARCANE BOSS)부터 새 체인을 시작한다
        self._stage_index = 1
        self._chain_score = 0
        self._chain_stats: dict = {"dmg_dealt": 0, "dmg_taken": 0, "spells_cast": 0, "time_ms": 0}
        self._apply_stage(self._stage_index)

        # 런 통계 / 점수 (승패 시 _finish_run 이 계산·저장)
        self._run_start_ms = 0
        self._dmg_dealt = 0
        self._dmg_taken = 0
        self._hits_landed = 0
        self._hits_missed = 0
        self._spells_cast = 0
        self.score = 0
        self._last_run_score = 0
        self._last_run_is_record = False
        self._last_run_stats: dict = {}
        self._can_continue_chain = False   # 다음 스테이지로 이어갈 수 있는 상태인지

        # 히트스톱 — 강한 타격/피격 시 아주 짧게 시뮬레이션을 멈춰 타격감을 강화
        self._hitstop_ms = 0

        # 마지막으로 저장한 공유 카드 / 하이라이트 클립 경로(엔딩 화면에 표시)
        self._last_card_path = ""
        self._last_clip_path = ""

        # ── 하이라이트 레코더 ──
        # 직전 15초를 항상 들고 있다가 보스를 쓰러뜨리면 알아서 영상으로 떨군다.
        # 인코딩은 워커 스레드가 하므로 게임 루프는 축소·복사 비용만 낸다.
        self._recorder = highlight.HighlightRecorder(
            enabled=bool(save_data.load().get("save_clips", True))
        )

        # ── 시전 자원(마나) ──
        # 무한 난사를 막고 "언제 쏠지"를 고르게 만든다. 회복을 기다리는 동안
        # 손을 내릴 수 있으므로 팔 피로(고릴라 암)도 함께 완화된다.
        self._mana = ManaPool()
        self._mana_fail_toast_left = 0
        self._last_cast_cost = 0.0      # HUD 비용 미리보기용

        # ── 성장 룬(로그라이크) ──
        self._runes = RuneState()
        self._rune_offers: list = []        # 현재 제시 중인 3장
        self._rune_clickables: list = []    # [(Rect, rune_id), ...]
        self._tick_rune = 0

        # ── 점술 수정구(인게임 웹캠) ──
        # 이 장르의 클립은 "사람이 손을 휘두르는 그림"이 있어야 공유된다.
        self._orb = ScryingOrb(radius=88)
        self._orb_center = (SCREEN_W - 118, SCREEN_H - 132)
        self._orb_accent: Tuple[int, int, int] = (150, 120, 255)
        self._orb.set_enabled(bool(self._save_orb_pref()))

        # 듀얼 캐스팅 HUD 상태(비전 파이프라인이 매 프레임 갱신)
        self._dual_progress = 0.0
        self._dual_poses: Optional[Tuple[str, str]] = None
        self._hands_seen = 0
        self._pose_label: Optional[str] = None
        self._pose_progress = 0.0
        self._last_cast_mode = "single"

        # ── 캘리브레이션 온보딩 ──
        self._calib_step = 0
        self._calib_hold_ms = 0
        self._calib_clickables: list = []
        self._tick_calib = 0

        # 엔딩 화면(RETRY / MAIN MENU) 클릭 영역
        self._ending_clickables: list = []

        # 엔딩/튜토리얼 화면 틱 카운터
        self._tick_ending  = 0
        self._tick_tutorial = 0

        # 최초 실행 — 조작법을 모르는 첫 플레이어가 바로 보스전에 던져지지
        # 않도록, 최초 1회에 한해 메뉴 대신 스펠 가이드를 자동으로 띄운다.
        # (ESC/ENTER/SPACE/G로 언제든 건너뛸 수 있다)
        if not self._save.get("first_run_done", False):
            # 조작법을 읽기 전에 "내 카메라가 내 손을 보는지"부터 확인시킨다 —
            # 인식이 안 되는 채로 가이드만 읽으면 첫 판에서 그대로 이탈한다.
            self._state = ("calibration" if not self._save.get("calibration_done", False)
                           else "tutorial")


    @staticmethod
    def _save_orb_pref() -> bool:
        """수정구 표시 여부(세이브). __init__ 에서 self._save 보다 먼저 필요해 따로 읽는다."""
        try:
            return bool(save_data.load().get("show_orb", True))
        except Exception:
            return True

    # ── 퍼블릭 API ──────────────────────────────────────────────────────────

    def run_one_frame(
        self,
        spell_name: Optional[str],
        head_dir: Optional[str] = None,
        cast_mode: str = "single",
    ) -> bool:
        """한 프레임을 처리합니다.

        - Pygame 이벤트 처리(종료 등)
        - 제공된 주문명을 적용
        - 내부 상태 업데이트 및 렌더링

        Args:
            spell_name: 이번 프레임에 발동된 주문(없으면 None).
            head_dir: 머리 방향('LEFT'/'RIGHT'/None).
            cast_mode: 'single' | 'amplify' | 'fusion' — 양손 시전 여부.

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
                elif self._state == "tutorial":
                    self._dismiss_tutorial()
                elif self._state == "calibration":
                    self._finish_calibration(False)
                elif self._state == "intro":
                    self._state = "menu"
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
                    self._save["last_difficulty"] = self.difficulty
                    save_data.save(self._save)
                    self._toast(f"Difficulty: {self.difficulty}", WHITE)
                if event.type == pygame.KEYDOWN and event.key == pygame.K_s:
                    on = not self._save.get("seated_mode", False)
                    self._save["seated_mode"] = on
                    save_data.save(self._save)
                    self._toast("SEATED MODE " + ("ON — 팔꿈치를 책상에 두고 플레이"
                                                  if on else "OFF"), GREEN if on else GREY)
                    if self._camera_active:
                        self.request_camera(True)     # 새 프리셋으로 파이프라인 재구성
                if event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                    on = not self._save.get("face_in_media", False)
                    self._save["face_in_media"] = on
                    save_data.save(self._save)
                    self._toast("FACE IN SAVED CARDS/CLIPS: ON — 웹캠 얼굴이 PNG/MP4에 저장됩니다" if on
                                else "FACE IN SAVED CARDS/CLIPS: OFF — 얼굴 영역은 가려서 저장", RED if on else GREEN)
                if event.type == pygame.KEYDOWN and event.key == pygame.K_k:
                    self.start_calibration()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_d:
                    self._audio.play_click()
                    self.start_daily_challenge()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_g:
                    self._state = "tutorial"
                    self._tick_tutorial = 0
                if event.type == pygame.KEYDOWN and event.key == pygame.K_c:
                    self.toggle_camera()          # 즉시 적용(재시작 불필요)
                if event.type == pygame.KEYDOWN and event.key == pygame.K_n:
                    # 카메라가 여러 대일 때 인덱스 순환. 켜져 있으면 새 인덱스로 즉시 재연결.
                    self._save["camera_index"] = (self._save.get("camera_index", 0) + 1) % 4
                    save_data.save(self._save)
                    self._toast(f"CAMERA #{self._save['camera_index']}", CYAN)
                    if self._camera_active:
                        self.request_camera(True)   # 새 인덱스로 다시 열도록 재요청
                if event.type == pygame.KEYDOWN and event.key == pygame.K_h:
                    self._save["use_hand_tracking"] = not self._save.get("use_hand_tracking", True)
                    save_data.save(self._save)
                    mode = "MediaPipe Hand" if self._save["use_hand_tracking"] else "HSV Marker"
                    self._toast(f"Tracking mode -> {mode} (restart to apply)", CYAN)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if self._btn_start.collidepoint(mx, my):
                        self._audio.play_click()
                        self._intro_tick = 0; self._intro_chars_shown = 0; self._intro_start_ms = 0
                        self._state = "intro"
                    elif self._btn_daily.collidepoint(mx, my):
                        self._audio.play_click()
                        self.start_daily_challenge()
                    elif self._btn_no_camera.collidepoint(mx, my):
                        # 시작 버튼이 아니라 토글이다 — 메뉴에 머무른 채 카메라만 켜고 끈다.
                        self._audio.play_click()
                        self.toggle_camera()
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
                    self._dismiss_tutorial()
            elif self._state == "playing":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._btn_pause.collidepoint(event.pos):
                        self._audio.play_click()
                        self._state = "pause"
                # 키보드 폴백(데모·테스트·접근성): 1~7 주문, ←/→ 회피
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        # 녹화 자체를 끌 수 있어야 한다(저사양 PC·프라이버시).
                        on = self._recorder.toggle()
                        self._save["save_clips"] = on
                        save_data.save(self._save)
                        self._toast(f"HIGHLIGHT RECORDING {'ON' if on else 'OFF'}", CYAN)
                    elif event.key == pygame.K_c:
                        # 인게임에서도 카메라를 끄고 키보드로 이어갈 수 있어야 한다
                        # (조명이 바뀌거나 인식이 흔들릴 때의 탈출구).
                        self.toggle_camera()
                    elif event.key == pygame.K_v:
                        # 수정구(웹캠) 표시 토글 — 녹화 중 얼굴을 빼고 싶을 수 있다
                        on = self._orb.toggle()
                        self._save["show_orb"] = on
                        save_data.save(self._save)
                        self._toast(f"SCRYING ORB {'ON' if on else 'OFF'}", CYAN)
                    elif event.key in KEYBOARD_SPELLS:
                        self._pending_kb_spell = KEYBOARD_SPELLS[event.key]
                    elif event.key == pygame.K_LEFT:
                        self._kb_dir = "LEFT"
                    elif event.key == pygame.K_RIGHT:
                        self._kb_dir = "RIGHT"
                elif event.type == pygame.KEYUP and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    self._kb_dir = None
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
            elif self._state == "calibration":
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_c:
                        self.toggle_camera()      # 카메라가 꺼져 있으면 여기서 켠다
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if self._calib_step >= len(hud_ext.CALIBRATION_STEPS):
                            self._finish_calibration(True)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for rect, action in self._calib_clickables:
                        if rect.collidepoint(event.pos):
                            self._audio.play_click()
                            if action == "skip":
                                self._finish_calibration(False)
                            elif action == "done":
                                self._finish_calibration(True)
                            elif action == "retry":
                                self._calib_step = 0
                                self._calib_hold_ms = 0
                            break
            elif self._state == "rune_select":
                if event.type == pygame.KEYDOWN:
                    # 1/2/3 — 카드 순서대로. 고를 게 없으면 아무 키나 눌러 통과.
                    idx = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2}.get(event.key)
                    if not self._rune_offers:
                        self._begin_next_stage()
                    elif idx is not None and idx < len(self._rune_offers):
                        self._choose_rune(self._rune_offers[idx].id)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for rect, rune_id in self._rune_clickables:
                        if rect.collidepoint(event.pos):
                            self._choose_rune(rune_id)
                            break
            elif self._state in ("game_over", "you_win"):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # 다음 스테이지로 이어갈 수 있으면 ENTER가 곧장 CONTINUE,
                    # 아니면(패배/최종 클리어) 체인을 처음부터 재도전한다.
                    if self._can_continue_chain:
                        self._continue_to_next_stage()
                    else:
                        self._retry_full_chain()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for rect, action, _ in self._ending_clickables:
                        if rect.collidepoint(event.pos):
                            self._audio.play_click()
                            if action == "continue":
                                self._continue_to_next_stage()
                            elif action == "retry_stage":
                                self._retry_current_stage()
                            elif action == "retry":
                                self._retry_full_chain()
                            elif action == "menu":
                                self._reset_game()
                            break

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
        if self._state == "calibration":
            dt_c = self.clock.tick(FPS)
            self._update_calibration(dt_c)
            self._orb.update(dt_c)
            self._calib_clickables = hud_ext.render_calibration(
                self.screen, self.font, self.font_big,
                step_index=self._calib_step,
                hold_ratio=self._calib_hold_ms / float(self.CALIB_HOLD_MS),
                detected=self._pose_label,
                camera_on=self._camera_active,
                tick=self._tick_calib,
                orb=self._orb if self._orb.has_frame() else None,
                orb_center=(SCREEN_W // 2 - 260, SCREEN_H // 2 - 10),
                draw_icon=self._fp.draw_gesture_icon,
            )
            self._tick_calib += 1
            pygame.display.flip()
            return True
        if self._state == "rune_select":
            self.clock.tick(FPS)
            nxt = self._next_boss_name()
            self._rune_clickables = hud_ext.render_rune_select(
                self.screen, self.font, self.font_big,
                self._rune_offers, self._tick_rune,
                stage_cleared=self._stage_index, next_boss_name=nxt,
            )
            self._tick_rune += 1
            pygame.display.flip()
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
            next_boss_name = self._next_boss_name() if self._can_continue_chain else ""
            self._ending_clickables = self._fp.render_ending(
                self._state, self._tick_ending,
                stats=self._last_run_stats,
                score=self._last_run_score,
                is_new_record=self._last_run_is_record,
                can_continue=self._can_continue_chain,
                chain_score=self._chain_score,
                next_boss_name=next_boss_name,
                card_path=self._last_card_path,
                clip_path=self._last_clip_path,
            )
            self._tick_ending += 1
            return True

        # 시간 갱신 및 헤드/키보드 무브먼트 먼저 반영 (키보드가 우선)
        dt = self.clock.tick(FPS)  # milliseconds

        # 히트스톱: 강한 타격/피격/페이즈 전환 직후 아주 짧게 시뮬레이션만 정지
        # (렌더는 실제 dt로 계속 흘러 카메라 쉐이크·그레인 등은 그대로 재생된다 —
        #  완전 정지가 아니라 "순간 무게감"을 주는 짧은 프리즈프레임)
        if self._hitstop_ms > 0:
            self._hitstop_ms = max(0, self._hitstop_ms - dt)
            sim_dt = max(1, int(dt * 0.06))
        else:
            sim_dt = dt
        self._update_timers(sim_dt)
        self._update_player_dodge(self._kb_dir or head_dir, sim_dt)

        # 주문 적용 — 비전 입력이 없으면 키보드 폴백 사용
        if spell_name is None and self._pending_kb_spell is not None:
            spell_name = self._pending_kb_spell
            cast_mode = "single"          # 키보드 폴백에는 양손 개념이 없다
        self._pending_kb_spell = None

        # (플레이어 현재 위치에서 투사체가 출발하도록 이동 이후에 적용)
        if spell_name:
            _result = self.apply_spell(spell_name, cast_mode)
            if _result.applied:
                _fallback_elem = _SPELL_DB.get(_result.name, {}).get("element")
                self._audio.play_spell_sfx(_result.name, fallback_element=_fallback_elem)

        # 나머지 업데이트
        self._update_boss_ai(sim_dt)
        self._update_effects(sim_dt)

        # 승패 판정
        if self.boss_hp <= 0 and self._state == "playing":
            # 처치 장면: 상태가 바뀌면 이 프레임은 캡처되지 않으므로, 클립을 굽기 전에
            # 마지막 전투 화면을 한 번 그려 링버퍼에 넣는다(애니메이션은 진행시키지 않는다).
            if self._recorder.enabled:
                self._render(0)
                self._recorder.capture(self.screen, force=True, mask=self._clip_mask())
            self._state = "you_win"
            self._tick_ending = 0
            self._finish_run(won=True)
        elif self.player_hp <= 0 and self._state == "playing":
            self._state = "game_over"
            self._tick_ending = 0
            self._finish_run(won=False)

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
                if _prev_state != "pause":
                    self._start_new_run()           # 일시정지 복귀가 아닌 "새 런" 시작
            elif self._state in ("game_over", "you_win"):
                self._audio.set_bgm_battle_mode(False)  # 엔딩: 볼륨 복원

        # 렌더
        self._render(dt)

        # 하이라이트 링버퍼 — 완성된 프레임을 담는다(연출·HUD·수정구까지 포함).
        if self._state == "playing":
            self._recorder.capture(self.screen, dt, mask=self._clip_mask())
        return True

    def apply_spell(self, spell_name: str, mode: str = "single") -> SpellResult:
        """레지스트리(_SPELL_DB) 기반으로 주문 1건을 적용한다.

        Args:
            spell_name: 주문명(별칭 허용).
            mode: 'single'  — 한 손 시전(기본)
                  'amplify' — 양손 같은 포즈. 위력 2배, 마나 1.6배.
                  'fusion'  — 양손 다른 포즈. spell_name 이 이미 상위 주문이다.

        시전이 거부되는 사유는 세 가지고, 검사 순서가 곧 우선순위다:
        미등록 주문 → 쿨다운 → 마나 부족. 마나를 마지막에 보는 이유는,
        어차피 못 쓰는 주문에 "마나 부족" 이라는 틀린 피드백을 주지 않기 위해서다.
        """
        label = spell_name.upper()
        label = _SPELL_ALIASES.get(label, label)
        spec = _SPELL_DB.get(label)
        if spec is None:
            self._toast(f"UNKNOWN: {spell_name}", GREY)
            return SpellResult("UNKNOWN", False, "unrecognized", mode)

        cd_left = self._cooldowns.get(label, 0)
        if cd_left > 0:
            self._toast(f"{label} (cooldown {cd_left / 1000:.1f}s)", GREY)
            return SpellResult(label, False, "cooldown", mode)

        amplified = (mode == "amplify")
        cost_mult = AMPLIFY_COST_MULT if amplified else 1.0
        if not self._mana.try_spend(label, cost_mult):
            self._notify_mana_short(label, cost_mult)
            return SpellResult(label, False, "no_mana", mode)
        self._last_cast_cost = self._mana.effective_cost(label, cost_mult)

        if spec["cd"] > 0:
            self._cooldowns[label] = max(1, int(spec["cd"] * self._runes.mult("cooldown")))

        # ── 연출 강도 — 증폭/융합은 눈에 띄게 커야 "특별한 시전"으로 읽힌다 ──
        fx_scale = 2.0 if amplified else (1.5 if mode == "fusion" else 1.0)
        wand_x, wand_y = self._fp.wand_tip()
        pcount, pkind = spec["particles"]
        self._fp.add_particles(wand_x, wand_y, int(pcount * fx_scale), spec["color"], pkind)
        shake_i, shake_d = spec["shake"]
        self._fp.add_camera_shake(shake_i * (1.0 + 0.5 * (fx_scale - 1.0)), shake_d)
        self._spawn_cast_effect(spec["color"], spec["style"])
        self._spawn_magic_circle(spec["element"])

        # 수정구(웹캠)도 시전에 반응하게 해서 "내 손이 이걸 냈다"를 연결한다
        self._orb_accent = spec["color"]
        self._orb.pulse(1.0 if mode != "single" else 0.55)

        if mode == "single":
            self._toast(*spec["toast"])
        else:
            tag = "AMPLIFIED" if amplified else "FUSION"
            self._toast(f"{tag}  {label}!", GOLD if amplified else PINK)

        if spec["kind"] == "shield":
            dur = SHIELD_DURATION_MS * self._runes.mult("shield_duration")
            if amplified:
                dur *= 1.6
            self.shield_time_left = int(dur)
            self._spawn_shield_ring()
        else:
            dmg = (spec["dmg"] * self._runes.mult("spell_damage")
                   * self._daily.mult("spell_damage"))
            if amplified:
                dmg *= (AMPLIFY_DMG_MULT + self._runes.add("dual_bonus")
                        + self._daily.mult("dual_bonus", 0.0))
            else:
                dmg *= self._daily.mult("single_damage")   # TWINBOUND: 한 손 약화
            self._spawn_player_projectile(
                element=spec["element"], color=spec["color"],
                dmg=int(round(dmg)), dur_ms=spec["dur"], style=spec["style"],
            )
            self._effects[-1]["cast_mode"] = mode
            if spec.get("blind_ms"):
                self._effects[-1]["blind_ms"] = spec["blind_ms"]

        self._spells_cast += 1
        self._last_cast_mode = mode
        return SpellResult(label, True, "", mode)

    def _notify_mana_short(self, label: str, cost_mult: float) -> None:
        """마나 부족 피드백 — 매 프레임 도배되지 않도록 간격을 둔다."""
        if self._mana_fail_toast_left > 0:
            return
        self._mana_fail_toast_left = MANA_FAIL_TOAST_MS
        if self._mana.exhausted:
            self._toast("MANA EXHAUSTED", RED)
        else:
            need = int(round(self._mana.shortfall(label, cost_mult)))
            self._toast(f"NOT ENOUGH MANA  (+{need})", BLUE)

    def start_daily_challenge(self) -> None:
        """오늘의 고정 챌린지를 시작한다 — 보스 순서·룬 후보·난이도가 모두 시드 고정."""
        ch = daily_mod.build(ladder_pool=list(STAGE_LADDER))
        self._daily.start(ch)
        self._stage_ladder = list(ch.ladder)
        self.set_difficulty(ch.difficulty)
        # 룬 후보까지 시드에 묶어야 "같은 판"이 된다.
        self._runes = RuneState(ch.rng())
        self._chain_score = 0
        self._chain_stats = {"dmg_dealt": 0, "dmg_taken": 0, "spells_cast": 0, "time_ms": 0}
        self._sync_rune_effects()
        self._apply_stage(1)
        self._reset_entities()
        best = daily_mod.best_for(self._save, ch.key)
        self._toast(f"{ch.modifier_name} — {ch.modifier_desc}"
                    + (f"   (BEST {best})" if best else ""), GOLD)
        self._intro_tick = 0; self._intro_chars_shown = 0; self._intro_start_ms = 0
        self._state = "intro"

    def exit_daily_challenge(self) -> None:
        """일반 모드로 되돌린다."""
        if not self._daily.active:
            return
        self._daily.stop()
        self._stage_ladder = list(STAGE_LADDER)
        self._runes = RuneState()
        self.set_difficulty(self._saved_difficulty)
        self._sync_rune_effects()

    def consume_camera_request(self) -> Optional[str]:
        """이번 프레임의 카메라 제어 요청을 한 번만 돌려준다.

        Returns:
            "on"  — main.py 가 비전 파이프라인을 새로 띄워야 한다.
            "off" — main.py 가 파이프라인을 정리해야 한다.
            None  — 요청 없음.
        """
        req, self._camera_request = self._camera_request, None
        return req

    def notify_camera_error(self, index: int) -> None:
        """카메라를 열지 못했을 때 — 조용히 실패하지 않고 이유를 보여준다."""
        self._toast(f"CAMERA #{index} UNAVAILABLE — KEYBOARD MODE  (N: next camera)", RED)

    def set_camera_active(self, active: bool) -> None:
        """main.py 가 파이프라인의 실제 상태를 알려준다(UI 가 이 값만 신뢰한다)."""
        active = bool(active)
        if active == self._camera_active:
            return
        self._camera_active = active
        if not active:
            self.clear_vision_feedback()

    @property
    def camera_active(self) -> bool:
        return self._camera_active

    @property
    def _input_mode(self) -> str:
        """'camera' | 'keyboard' — 항상 실제 파이프라인 상태에서 파생된다."""
        return "camera" if self._camera_active else "keyboard"

    def request_camera(self, on: bool) -> None:
        """카메라를 켜거나 끄도록 요청한다(메뉴 버튼 / 인게임 C 키 공용)."""
        self._camera_request = "on" if on else "off"

    def toggle_camera(self) -> None:
        """현재 실제 상태의 반대를 요청한다."""
        turning_on = not self._camera_active
        self.request_camera(turning_on)
        # 카메라를 여는 데는 수백 ms가 걸린다 — 눌렀는데 아무 일도 안 일어난 것처럼
        # 보이지 않도록 접수 사실을 먼저 알린다. 실패 시 main.py 가 덮어쓴다.
        self._toast("CAMERA ON ..." if turning_on else "CAMERA OFF — KEYBOARD MODE",
                    CYAN if turning_on else GREY)

    def close(self) -> None:
        """게임을 종료하고 Pygame을 정리합니다."""
        self._recorder.close()
        self._audio.close()
        hud_ext.reset_font_cache()
        pygame.quit()

    # ── 내부 로직 ───────────────────────────────────────────────────────────

    def _deal_boss_damage(self, dmg: int) -> None:
        self.boss_hp = max(0, self.boss_hp - int(dmg))

    def _deal_player_damage(self, dmg: int) -> None:
        red = int(round(dmg * self._runes.mult("damage_taken")
                        * self._daily.mult("damage_taken")))
        if self.shield_time_left > 0:
            red = int(red * (1.0 - SHIELD_REDUCTION))
        self.player_hp = max(0, self.player_hp - red)
        self._dmg_taken += red
        self._hitstop_ms = max(self._hitstop_ms, 55)
        if red != dmg:
            self._toast(f"Shield absorbs {dmg-red}", CYAN, keep_if_longer=True)

    def _sync_rune_effects(self) -> None:
        """룬 집계값을 각 시스템에 반영한다.

        룬이 늘어나도 게임 로직에 분기가 생기지 않도록, 룬 → 시스템 전달은
        이 함수 한 곳에서만 일어난다.
        """
        d = self._daily            # 일일 변형은 룬 위에 곱해진다(둘 다 중립값이 1.0)
        self._mana.regen_mult = self._runes.mult("mana_regen") * d.mult("mana_regen")
        self._mana.cost_mult = self._runes.mult("mana_cost") * d.mult("mana_cost")
        self._player_speed_px_s = 480.0 * self._runes.mult("dodge_speed")
        self._boss_interval_mult = (DIFFICULTY_CONFIG[self.difficulty]["interval"]
                                    * d.mult("boss_interval"))

    def _max_player_hp(self) -> int:
        """룬(SECOND WIND)으로 늘어난 최대 HP."""
        return int(PLAYER_MAX_HP + self._runes.add("max_hp"))

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
        if self._mana_fail_toast_left > 0:
            self._mana_fail_toast_left = max(0, self._mana_fail_toast_left - dt_ms)
        self._mana.update(dt_ms)
        self._orb.update(dt_ms)

    def _current_phase(self) -> Tuple[int, str, int, str]:
        """현재 보스 HP 비율에 해당하는 (페이즈 번호, 원소, 공격주기 ms, 패턴)."""
        phases = self._boss_phases
        ratio = self.boss_hp / float(BOSS_MAX_HP)
        for i, (low, elem, interval, pattern) in enumerate(phases):
            if ratio > low:
                return i + 1, elem, interval, pattern
        last = phases[-1]
        return len(phases), last[1], last[2], last[3]

    def _update_boss_ai(self, dt_ms: int) -> None:
        if self.boss_hp <= 0:
            return
        phase, elem, interval, pattern = self._current_phase()
        if phase != self.boss_phase:
            prev, self.boss_phase = self.boss_phase, phase
            self.boss_element = elem
            if prev != 0:
                self._toast(f"{self._boss_name} — PHASE {phase}: {elem}", RED)
                self._spawn_flash(MAGIC_CIRCLE_COLORS.get(elem, WHITE))
                self._fp.add_camera_shake(7.0, 280)
                self._hitstop_ms = max(self._hitstop_ms, 130)

        # 시전 주기마다 텔레그래프(경고) → BOSS_TELEGRAPH_MS 후 실제 발사
        # (난이도별 interval 배율 — Impossible은 더 빠르게, Easy는 더 느리게)
        effective_interval = max(200, int(interval * getattr(self, "_boss_interval_mult", 1.0)))
        self._boss_attack_timer += dt_ms
        while self._boss_attack_timer >= effective_interval:
            self._boss_attack_timer -= effective_interval
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
        mult = getattr(self, "_boss_dmg_mult", 1.0) * getattr(self, "_boss_dmg_boss_mult", 1.0)
        base = max(1, int(round(BOSS_DMG * mult)))
        if pattern == "spread3":
            for dx in (-150, 0, 150):
                self._spawn_boss_projectile(base, end=(px + dx, py))
        elif pattern == "aimed":
            self._spawn_boss_projectile(int(round((BOSS_DMG + 3) * mult)), end=(px, py),
                                        dur=PROJECTILE_DURATION_MS - 120)
        else:  # single
            self._spawn_boss_projectile(base)

    def _toast(self, text: str, color: Tuple[int, int, int], keep_if_longer: bool = False) -> None:
        # 간단한 메시지 시스템: 잠시 상단 중앙에 표시
        if keep_if_longer and self.message_time_left > MESSAGE_DURATION_MS // 2:
            # 기존 메시지가 충분히 남아있으면 덮어쓰지 않음
            return
        self.message_text = text
        self.message_color = color
        self.message_time_left = MESSAGE_DURATION_MS

    # ── 캘리브레이션 ────────────────────────────────────────────────────
    CALIB_HOLD_MS = 900        # 한 단계를 통과시키는 유지 시간

    def start_calibration(self) -> None:
        """포즈 확인 온보딩을 연다."""
        self._calib_step = 0
        self._calib_hold_ms = 0
        self._tick_calib = 0
        self._calib_clickables = []
        self._state = "calibration"

    def _finish_calibration(self, completed: bool) -> None:
        """온보딩 종료 — 완주했든 건너뛰었든 다시 강제로 띄우지 않는다."""
        self._save["calibration_done"] = True
        save_data.save(self._save)
        self._state = "menu"
        if completed:
            self._toast("CALIBRATION COMPLETE", GREEN)

    def _update_calibration(self, dt_ms: int) -> None:
        """현재 단계의 목표가 인식되고 있으면 유지 시간을 채운다.

        인식이 끊기면 0으로 리셋하지 않고 절반 속도로 감쇠시킨다 — 손 떨림이나
        한 프레임짜리 인식 실패로 진행도가 날아가면 "안 된다"는 인상만 남는다.
        """
        steps = hud_ext.CALIBRATION_STEPS
        if self._calib_step >= len(steps):
            return
        target = steps[self._calib_step][0]
        if target == "DUAL":
            matched = self._hands_seen >= 2
        else:
            matched = self._pose_label == target

        if matched:
            self._calib_hold_ms = min(self.CALIB_HOLD_MS, self._calib_hold_ms + dt_ms)
        else:
            self._calib_hold_ms = max(0, self._calib_hold_ms - dt_ms // 2)

        if self._calib_hold_ms >= self.CALIB_HOLD_MS:
            self._calib_step += 1
            self._calib_hold_ms = 0
            self._audio.play_click()
            self._fp.add_camera_shake(2.5, 120)

    def _dismiss_tutorial(self) -> None:
        """스펠 가이드를 닫고 메뉴로 돌아간다 — 최초 실행이면 완료 플래그를 저장."""
        self._state = "menu"
        if not self._save.get("first_run_done", False):
            self._save["first_run_done"] = True
            save_data.save(self._save)
            # 최초 1회 고지 — 결과 카드·승리 클립이 자동 저장된다는 사실과 얼굴 기본값.
            self._toast("승리 클립·결과 카드는 자동 저장됩니다. 웹캠 얼굴은 기본으로 가려집니다 (F 키로 변경)",
                        CYAN, keep_if_longer=True)

    def _reset_entities(self) -> None:
        """전투 상태만 초기화한다(난이도/보스 선택/메뉴 전환은 호출부 책임)."""
        self._sync_rune_effects()
        self.player_hp = self._max_player_hp()
        self.boss_hp   = BOSS_MAX_HP
        self.player_pos = (SCREEN_W // 2, SCREEN_H // 2)
        self.boss_pos   = (SCREEN_W - 150, SCREEN_H // 2)
        self._player_fx = float(self.player_pos[0])
        self._player_fy = float(self.player_pos[1])
        self.shield_time_left  = 0
        self.lightning_cd_left = 0
        self._cooldowns        = {}
        self._boss_blind_left  = 0
        self._pending_kb_spell = None
        self._kb_dir           = None
        # 카메라 상태는 건드리지 않는다 — 파이프라인의 생사는 main.py 만 알고 있고,
        # 여기서 "camera" 로 되돌리면 꺼진 카메라를 켜졌다고 표시하게 된다.
        self._gesture_trail    = []
        self._gesture_drawing  = False
        self._boss_attack_timer = 0
        self.boss_phase        = 0
        self._pending_boss_shots = []
        self.message_text      = ""
        self.message_time_left = 0
        self._effects          = []
        self._hitstop_ms       = 0
        self._mana.maximum     = mana_mod.MAX_MANA
        self._mana.reset()
        self._mana_fail_toast_left = 0
        self._dual_progress    = 0.0
        self._dual_poses       = None

    def _reset_chain(self) -> None:
        """스테이지 체인(점수/누적 통계/진행도)을 1스테이지로 되돌린다."""
        self._chain_score = 0
        self._chain_stats = {"dmg_dealt": 0, "dmg_taken": 0, "spells_cast": 0, "time_ms": 0}
        # 룬은 한 체인(런) 동안만 유지된다 — 새 체인은 빈손에서 시작한다.
        # 일일 모드에서는 룬 후보까지 시드 고정이라 같은 난수원으로 다시 만든다.
        if self._daily.active and self._daily.challenge is not None:
            self._runes = RuneState(self._daily.challenge.rng())
        else:
            self._runes.reset()
        self._rune_offers = []
        self._sync_rune_effects()
        self._apply_stage(1)

    def _reset_game(self) -> None:
        """게임 상태를 초기화하고 메뉴로 돌아갑니다(체인 종료)."""
        self.exit_daily_challenge()
        self._reset_entities()
        self._state = "menu"
        self.set_difficulty(self._saved_difficulty)
        self._reset_chain()

    def _retry_current_stage(self) -> None:
        """메뉴를 거치지 않고 지금 스테이지만 다시 시전한다(체인 진행은 유지)."""
        self._reset_entities()
        self._apply_stage(self._stage_index)
        self._state = "playing"

    def _retry_full_chain(self) -> None:
        """체인을 1스테이지부터 다시 시작한다(패배·최종 클리어 후 RETRY)."""
        self._reset_entities()
        self._reset_chain()
        self._state = "playing"

    def _continue_to_next_stage(self) -> None:
        """다음 스테이지로 넘어가기 전에 성장 룬을 고르게 한다.

        보상이 "다음 보스"뿐이면 두 번째 런부터는 이미 아는 것을 반복하게 된다.
        룬을 사이에 끼우면 같은 사다리를 올라가도 매번 다른 빌드가 된다.
        """
        self._rune_offers = self._runes.offer()
        if not self._rune_offers:
            # 더 뽑을 룬이 없다(전부 최대 스택) — 화면을 낭비하지 않고 바로 진행
            self._begin_next_stage()
            return
        self._tick_rune = 0
        self._rune_clickables = []
        self._state = "rune_select"

    def _begin_next_stage(self) -> None:
        """룬 선택이 끝난 뒤 실제로 다음 스테이지를 시작한다."""
        self._reset_entities()
        self._apply_stage(self._stage_index + 1)
        self._state = "playing"

    def _choose_rune(self, rune_id: str) -> None:
        """룬을 확정하고 다음 스테이지로 넘어간다."""
        if self._runes.acquire(rune_id):
            self._sync_rune_effects()
            self._audio.play_click()
        self._rune_offers = []
        self._rune_clickables = []
        self._begin_next_stage()

    def _start_new_run(self) -> None:
        """전투 진입(인트로→playing) 시 런 통계를 리셋하고 총 플레이 횟수를 기록한다."""
        self._run_start_ms = pygame.time.get_ticks()
        self._dmg_dealt = 0
        self._dmg_taken = 0
        self._hits_landed = 0
        self._hits_missed = 0
        self._spells_cast = 0
        self._save["total_runs"] = self._save.get("total_runs", 0) + 1
        save_data.save(self._save)

    def live_score(self) -> int:
        """플레이 중 실시간으로 갱신되는 점수 미리보기(HUD 표시용)."""
        diff_mult = DIFFICULTY_SCORE_MULT.get(self.difficulty, 1.0)
        raw = (self._hits_landed * SCORE_HIT_BASE
               + self._dmg_dealt * SCORE_DMG_MULT
               - self._hits_missed * SCORE_MISS_PENALTY)
        return max(0, int(round(raw * diff_mult)))

    def _finish_run(self, won: bool) -> None:
        """스테이지 승/패 확정 시 점수를 산정해 체인에 누적하고, 다음 스테이지로
        이어갈 수 있는지 판단한 뒤 최고 기록·해금·통계를 저장한다."""
        elapsed_ms = max(0, pygame.time.get_ticks() - self._run_start_ms)
        diff_mult = DIFFICULTY_SCORE_MULT.get(self.difficulty, 1.0)
        raw = (self._hits_landed * SCORE_HIT_BASE
               + self._dmg_dealt * SCORE_DMG_MULT
               - self._hits_missed * SCORE_MISS_PENALTY)
        if won:
            raw += SCORE_WIN_BONUS
            raw += max(0, 200 - elapsed_ms // 1000) * SCORE_TIME_BONUS_PER_SEC
            self._save["total_wins"] = self._save.get("total_wins", 0) + 1

        stage_score = max(0, int(round(raw * diff_mult)))

        # 체인(연속 스테이지 진행)에 이번 스테이지 결과를 누적한다.
        self._chain_score += stage_score
        self._chain_stats["dmg_dealt"] += self._dmg_dealt
        self._chain_stats["dmg_taken"] += self._dmg_taken
        self._chain_stats["spells_cast"] += self._spells_cast
        self._chain_stats["time_ms"] += elapsed_ms

        self._can_continue_chain = won and self._stage_index < self._max_stage_for_difficulty()

        # 일일 챌린지는 보스 순서가 섞여 있어 일반 사다리 해금과 무관하다.
        if (won and not self._daily.active
                and self._stage_index + 1 > self._save.get("unlocked_stage", 1)):
            self._save["unlocked_stage"] = self._stage_index + 1
            if self._stage_index < len(STAGE_LADDER):
                next_boss = BOSSES[STAGE_LADDER[self._stage_index]]["name"]
                self._toast(f"NEW BOSS UNLOCKED: {next_boss}", CYAN, keep_if_longer=True)

        best_scores: dict = self._save.setdefault("best_score", {})
        prev_best = int(best_scores.get(self.difficulty, 0))
        is_record = self._chain_score > prev_best
        if is_record:
            best_scores[self.difficulty] = self._chain_score

        self.score = stage_score
        self._last_run_score = stage_score
        self._last_run_is_record = is_record
        self._last_run_stats = {
            "won": won,
            "time_ms": elapsed_ms,
            "dmg_dealt": self._dmg_dealt,
            "dmg_taken": self._dmg_taken,
            "hits_landed": self._hits_landed,
            "hits_missed": self._hits_missed,
            "spells_cast": self._spells_cast,
            "best_score": best_scores.get(self.difficulty, self._chain_score),
            "boss_name": self._boss_name,
            "stage_index": self._stage_index,
            "stage_count": len(self._stage_ladder),
        }
        # 일일 챌린지 기록 — 체인 점수 기준(하루에 한 판만 세는 게 아니라 최고 기록)
        if self._daily.active and self._daily.challenge is not None:
            if daily_mod.record(self._save, self._daily.challenge.key, self._chain_score):
                self._toast(f"DAILY BEST  {self._chain_score}", GOLD, keep_if_longer=True)

        save_data.save(self._save)
        self._write_share_card(won, stage_score, is_record)
        self._write_highlight_clip(won)

    def _clip_mask(self) -> Optional[Tuple[int, int, int]]:
        """클립에서 가릴 수정구 영역. 얼굴 포함을 허용했거나 수정구가 꺼져 있으면 없음."""
        if self._save.get("face_in_media", False) or not self._orb.enabled:
            return None
        return (self._orb_center[0], self._orb_center[1], self._orb.radius)

    def _next_boss_name(self) -> str:
        """현재 사다리(일일 챌린지면 섞인 순서)에서 다음 스테이지 보스 이름."""
        if self._stage_index < len(self._stage_ladder):
            return BOSSES[self._stage_ladder[self._stage_index]]["name"]
        return ""

    def _write_highlight_clip(self, won: bool) -> None:
        """결정적 순간의 직전 15초를 영상으로 남긴다.

        승리했을 때만 저장한다 — 패배 클립까지 쌓이면 폴더만 지저분해지고,
        실제로 공유되는 건 이기는 장면이다.
        """
        if not won or not self._recorder.enabled:
            return
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(share_card.clips_dir(), f"airspell_{stamp}.mp4")
        self._last_clip_path = self._recorder.save(path) or ""
        self._recorder.clear()      # 다음 스테이지는 새 15초부터 모은다

    def _write_share_card(self, won: bool, score: int, is_record: bool) -> None:
        """런 결과를 공유용 PNG 로 남긴다 — 수정구에 잡힌 플레이어 얼굴째로.

        공유의 마찰을 없애는 게 목적이므로 실패해도 조용히 넘어간다.
        저장 여부는 세이브의 "save_cards" 로 끌 수 있다.
        """
        if not self._save.get("save_cards", True):
            return
        card = share_card.build_card(
            won=won,
            score=score,
            boss_name=self._boss_name,
            stats=self._last_run_stats,
            stage_index=self._stage_index,
            stage_count=len(self._stage_ladder),
            difficulty=self.difficulty,
            rune_summary=self._runes.summary(),
            rune_colors=self._rune_colors(),
            portrait=self._orb.portrait() if self._save.get("face_in_media", False) else None,
            is_record=is_record,
            daily_label=self._daily.label,
        )
        # 토스트로 알리면 보스 해금 같은 더 중요한 메시지를 밀어내므로,
        # 저장 사실은 엔딩 화면에 한 줄로 표시한다.
        self._last_card_path = share_card.save_card(card) or ""

    def set_difficulty(self, level: str) -> None:
        level = level.lower()
        if level not in DIFFICULTY_CONFIG:
            level = "normal"
        self.difficulty = level
        cfg = DIFFICULTY_CONFIG[level]
        self._boss_dodge_prob = cfg["dodge"]
        self._boss_dmg_mult = cfg["boss_dmg"]
        self._boss_interval_mult = cfg["interval"]

    def _apply_boss(self, boss_id: str) -> None:
        """활성 보스를 전환한다 — 페이즈표/이름/오라 컬러/데미지 배율을 함께 바꾼다."""
        bdef = BOSSES.get(boss_id, BOSSES["arcane"])
        self._boss_id = boss_id if boss_id in BOSSES else "arcane"
        self._boss_phases = bdef["phases"]
        self._boss_name = bdef["name"]
        self._boss_accent = bdef["accent"]
        self._boss_dmg_boss_mult = bdef["dmg_mult"]
        self.boss_element = self._boss_phases[0][1]

    def _apply_stage(self, stage_index: int) -> None:
        """현재 사다리에서 stage_index번째 보스를 적용한다.

        사다리는 인스턴스 값이라 일일 챌린지가 자기 순서로 갈아끼울 수 있다.
        """
        ladder = self._stage_ladder or list(STAGE_LADDER)
        stage_index = max(1, min(len(ladder), stage_index))
        self._stage_index = stage_index
        self._apply_boss(ladder[stage_index - 1])

    def _max_stage_for_difficulty(self) -> int:
        return min(len(STAGE_LADDER), DIFFICULTY_MAX_STAGE.get(self.difficulty, 1))

    def _update_player_dodge(self, head_dir: Optional[str], dt_ms: int) -> None:
        # 이동 속도(self._player_speed_px_s)는 _sync_rune_effects 가 룬을 반영해 설정한다.
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

    def set_vision_feedback(
        self,
        mirror=None,
        dual_progress: float = 0.0,
        dual_poses: Optional[Tuple[str, str]] = None,
        hands_seen: int = 0,
        pose_label: Optional[str] = None,
        pose_progress: float = 0.0,
    ) -> None:
        """비전 워커의 연속 신호를 받는다(주문 이벤트와 별개).

        미러 프레임 색보정은 여기서만 일어나므로, 카메라가 없거나 꺼져 있으면
        비용이 전혀 들지 않는다.
        """
        self._dual_progress = dual_progress
        self._dual_poses = dual_poses
        self._hands_seen = hands_seen
        # 캘리브레이션 화면이 "지금 무엇으로 인식되는지"를 실시간으로 보여주려면
        # 발동된 주문뿐 아니라 *진행 중인* 포즈도 알아야 한다.
        self._pose_label = pose_label
        self._pose_progress = pose_progress
        if mirror is not None and self._orb.enabled:
            self._orb.set_frame(mirror, tint=self._orb_accent)

    def clear_vision_feedback(self) -> None:
        """카메라가 해제됐을 때 — 마지막 영상이 화면에 얼어붙지 않게 비운다."""
        self._orb.clear()
        self._dual_progress = 0.0
        self._dual_poses = None
        self._hands_seen = 0
        self._pose_label = None
        self._pose_progress = 0.0

    def set_gesture_feedback(self, trail: list, drawing: bool) -> None:
        """비전 파이프라인이 매 프레임 손끝 트레일(정규화 좌표)을 공급한다."""
        self._gesture_trail = trail or []
        self._gesture_drawing = bool(drawing)

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
            gesture_trail=self._gesture_trail,
            gesture_drawing=self._gesture_drawing,
            boss_name=self._boss_name,
            boss_accent=self._boss_accent,
            score=self.live_score(),
            stage_index=self._stage_index,
            stage_count=len(self._stage_ladder),
            mana_ratio=self._mana.ratio,
            mana_exhausted=self._mana.exhausted,
            mana_cost_preview=self._mana_cost_preview(),
            rune_summary=self._runes.summary(),
            rune_colors=self._rune_colors(),
            dual_progress=self._dual_progress,
            dual_poses=self._dual_poses,
            orb=self._orb,
            orb_center=self._orb_center,
            orb_accent=self._orb_accent,
            player_max_hp=self._max_player_hp(),
        )

    def _mana_cost_preview(self) -> float:
        """게이지에 겹쳐 보여줄 "다음 시전 비용" 비율.

        마지막으로 성공한 시전의 비용을 기준으로 삼는다 — 다음에 무엇을 쓸지는
        알 수 없지만, 방금 쓴 주문을 한 번 더 쓸 여유가 있는지는 보여줄 수 있다.
        """
        if self._last_cast_cost <= 0 or self._mana.maximum <= 0:
            return 0.0
        return min(1.0, self._last_cast_cost / self._mana.maximum)

    def _rune_colors(self) -> list:
        """summary() 와 같은 순서의 룬 색 목록."""
        seen: list = []
        for rid in self._runes.owned:
            if rid not in seen and rid in RUNES_BY_ID:
                seen.append(rid)
        return [RUNES_BY_ID[r].color for r in seen]

    # 메뉴 렌더
    def _render_menu(self) -> None:
        self._fp.render_menu(
            btn_start=self._btn_start,
            btn_exit=self._btn_exit,
            btn_guide=self._btn_guide,
            btn_settings=self._btn_settings,
            btn_no_camera=self._btn_no_camera,
            btn_daily=self._btn_daily,
            orb=self._orb,
            orb_center=self._menu_orb_center,
            camera_active=self._camera_active,
            seated_mode=bool(self._save.get("seated_mode", False)),
            face_in_media=bool(self._save.get("face_in_media", False)),
            daily_best=daily_mod.best_for(self._save, daily_mod.today_key()),
            daily_streak=daily_mod.streak(self._save),
            difficulty=self.difficulty,
            best_score=self._save.get("best_score", {}).get(self.difficulty, 0),
            unlocked_stage=self._save.get("unlocked_stage", 1),
            stage_count=len(STAGE_LADDER),
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
            "color": MAGIC_CIRCLE_COLORS.get(self.boss_element, RED),
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

    def _spawn_flash(self, color: Tuple[int, int, int], dur_ms: int = 420) -> None:
        """화면 전체 색 파동(페이즈 전환 등 리듬 강조)."""
        self._effects.append({
            "type": "flash",
            "color": color,
            "elapsed": 0,
            "dur": dur_ms,
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
                            if mult > 1.0:
                                mult += self._runes.add("affinity_bonus")
                            dmg = int(round(e.get("dmg", 0) * mult))
                            self._deal_boss_damage(dmg)
                            # 적중 보상 룬 — 맞힐수록 계속 싸울 수 있게 해준다
                            self._mana.gain(self._runes.add("mana_on_hit"))
                            heal = int(self._runes.add("hp_on_hit"))
                            if heal > 0:
                                self.player_hp = min(self._max_player_hp(), self.player_hp + heal)
                            self._spawn_impact_effect(e["color"], e.get("style", "fire"), True)
                            self._dmg_dealt += dmg
                            self._hits_landed += 1
                            self._hitstop_ms = max(self._hitstop_ms, 95 if mult > 1.0 else 55)
                            if e.get("blind_ms"):
                                self._boss_blind_left = e["blind_ms"]
                                self._toast("BOSS BLINDED!", PURPLE)
                            else:
                                tag = f"  x{mult:.2g}" if mult != 1.0 else ""
                                if e.get("cast_mode") == "amplify":
                                    tag += "  AMP"
                                elif e.get("cast_mode") == "fusion":
                                    tag += "  FUSION"
                                self._toast(f"HIT -{dmg} HP{tag}",
                                            YELLOW if mult >= 1.0 else GREY)
                        else:
                            self._spawn_impact_effect(e["color"], e.get("style", "fire"), False)
                            self._hits_missed += 1
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

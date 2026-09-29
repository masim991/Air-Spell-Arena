"""
fp_renderer.py – First-person perspective renderer for Air Spell Arena.

Draws:
  - Perspective dungeon/arena background (ceiling, floor, pillars, rune grid)
  - Boss entity at screen center with pulsing aura and HP bar
  - Player wand in bottom-right corner
  - Projectile / shield effects in FP perspective
  - Full themed HUD (HP bars, cooldowns, difficulty badge)
  - Themed menu screen
"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence, Tuple

import pygame

import hud_ext

# ── Minimal Arcade Chrome Palette ──────────────────────────────────────────────
# Menu/HUD/HUD-frame chrome is monochrome + a single danger accent — no rainbow
# neon. Spell/element colours below stay vivid; they're gameplay signal, not chrome.
BLACK    = (0,   0,   0)
WHITE    = (255, 255, 255)
BONE     = (222, 210, 188)   # 만화적인 순백 대신 — 뼈/송곳니용 탁한 아이보리

# Background - neutral near-black, no colour tint
BG_TOP   = (10,  10,  12)
BG_MID   = (14,  14,  16)
BG_BOT   = (7,   7,   8)
FLOOR_C  = (20,  20,  22)

# Ambient ember particles (menu/atmosphere) - grayscale, not coloured runes
RUNE_DIM = (70,  70,  78)
RUNE_GLO = (225, 225, 235)

# Chrome tokens - the only colours used for menu/HUD frame, buttons, text
TEXT_PRIMARY   = (232, 232, 238)   # off-white body/label text
TEXT_SECONDARY = (150, 150, 160)   # dim secondary text
HAIRLINE       = (95,  95,  104)   # thin borders/dividers
ACCENT         = (255, 255, 255)   # primary CTA (hero buttons, focus)
DANGER         = (230, 64,  64)    # exit/danger actions only

# UI Colors - kept for gameplay signal (toasts, slot swatches, spell effects)
RED      = (255, 70,  100)   # Neon Pink-Red
GREEN    = (80,  255, 150)   # Neon Mint Green
YELLOW   = (255, 230, 60)    # Electric Yellow
BLUE     = (80,  150, 255)   # Bright Sky Blue
CYAN     = (0,   240, 255)   # Electric Cyan
GREY     = (140, 145, 160)   # Cool Grey
ORANGE   = (255, 140, 40)    # Vibrant Orange
PURPLE   = (180, 100, 255)   # Neon Purple
GOLD     = (255, 215, 50)    # Bright Gold
PINK     = (255, 100, 200)   # Hot Pink
BROWN    = (180, 130, 80)    # Warm Earth

# Element Colors - Enhanced vibrancy
FIRE_NEON     = (255, 100, 50)   # Bright Fire Orange
WATER_NEON    = (60,  180, 255)  # Bright Water Blue
WIND_NEON     = (120, 255, 180)  # Mint Wind Green
EARTH_NEON    = (200, 160, 100)  # Golden Earth
DARK_NEON     = (160, 80,  255)  # Deep Purple
LIGHT_NEON    = (240, 255, 255)  # Bright White-Cyan
LTNG_NEON     = (100, 220, 255)  # Electric Blue

PLAYER_MAX_HP = 100
BOSS_MAX_HP   = 100

DANGER_HP_RATIO = 0.28   # 이 비율 아래에서 심장박동 경고 비네트 발동

# ── Audio-settings slot definitions ────────────────────────────────────────────
_SLOT_ORDER  = ("bgm", "FIRE", "WATER", "WIND", "EARTH", "DARK", "LIGHT", "SHIELD")
_SLOT_COLORS = {
    "bgm":    GOLD,
    "FIRE":   FIRE_NEON,
    "WATER":  WATER_NEON,
    "WIND":   WIND_NEON,
    "EARTH":  EARTH_NEON,
    "DARK":   DARK_NEON,
    "LIGHT":  LTNG_NEON,
    "SHIELD": LIGHT_NEON,
}
_SLOT_LABELS = {
    "bgm": "BGM",  "FIRE": "FIRE",  "WATER": "WATER", "WIND": "WIND",
    "EARTH": "EARTH", "DARK": "DARK", "LIGHT": "LIGHT", "SHIELD": "SHIELD",
}


class FPRenderer:
    """Handles all first-person rendering for the game."""

    # 완드 끝(주문 시전점) 화면 비율 좌표 — 매직넘버 집약
    WAND_FX = 0.61
    WAND_FY = 0.71
    WAND_SWAY_GAIN = 0.06   # player_offset_x → 완드 좌우 흔들림 픽셀 비율

    def wand_tip(self, player_offset_x: float = 0.0) -> Tuple[int, int]:
        """완드 끝 화면 좌표. player_offset_x(-1~1)만큼 좌우로 흔들린다."""
        shift = int(player_offset_x * self.W * self.WAND_SWAY_GAIN)
        return int(self.W * self.WAND_FX) + shift, int(self.H * self.WAND_FY)

    def __init__(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        font_big: pygame.font.Font,
    ) -> None:
        self.screen   = screen
        self.font     = font
        self.font_big = font_big
        self.W, self.H = screen.get_size()
        self._tick: int = 0
        # 개선된 한글 폰트 (더 크고 선명하게)
        self.font_kor       = FPRenderer._make_kor_font(22)
        self.font_kor_big   = FPRenderer._make_kor_font(28)
        self.font_kor_small = FPRenderer._make_kor_font(20)
        self.font_game_title = FPRenderer._make_game_font(58)
        self.font_game_tab   = FPRenderer._make_game_font(20)
        # 설정 화면 스크롤 위치
        self._settings_scroll_offset: int = 0
        # 배경 그라디언트 캐시 (매 프레임 720줄 draw 대신 blit 1회로 최적화)
        self._bg_cache: Optional[pygame.Surface] = None
        # 파티클 시스템
        self._particles: List[dict] = []
        # 카메라 쉐이크
        self._camera_shake_intensity: float = 0.0
        self._camera_shake_duration: int = 0
        # 보스 애니메이션 상태 추적
        self._boss_prev_hp_ratio: float = 1.0
        self._boss_hit_tick: int = -999  # 마지막으로 피격된 tick
        # SRCALPHA 오버레이 캐시 (매 프레임 재할당 방지)
        self._pause_ov: Optional[pygame.Surface] = None
        self._end_ov: Optional[pygame.Surface] = None
        _blank = pygame.Surface((1, 1), pygame.SRCALPHA)
        self._boss_sh_r: int = -1
        self._boss_sh_surf: pygame.Surface = _blank
        self._boss_hl_r: int = -1
        self._boss_hl_surf: pygame.Surface = _blank
        # 대기 파티클(재/먼지) + 시네마틱 컬러 그레이드 캐시
        self._motes: List[dict] = []
        self._grade_cache: Optional[pygame.Surface] = None
        self._grain_tiles: List[pygame.Surface] = []

    # ── Particle System ────────────────────────────────────────────────────────

    def add_particles(
        self,
        x: int, y: int,
        count: int,
        color: Tuple[int, int, int],
        style: str = "spark",
    ) -> None:
        """파티클 생성 - 마법 시전 시 현실감 향상"""
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(2, 8)
            self._particles.append({
                "x": float(x),
                "y": float(y),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - random.uniform(1, 3),  # 위로 편향
                "color": color,
                "life": random.randint(20, 60),
                "max_life": 60,
                "size": random.randint(2, 5),
                "style": style,
                "gravity": random.uniform(0.1, 0.3),
            })

    def update_particles(self, dt_ms: int) -> None:
        """파티클 업데이트 - 물리 기반 움직임"""
        alive = []
        for p in self._particles:
            p["life"] -= 1
            if p["life"] <= 0:
                continue
            
            # 물리 시뮬레이션
            p["vy"] += p["gravity"]  # 중력
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vx"] *= 0.98  # 공기 저항
            p["vy"] *= 0.98
            
            alive.append(p)
        self._particles = alive

    def render_particles(self) -> None:
        """파티클 렌더링"""
        for p in self._particles:
            fade = p["life"] / p["max_life"]
            color = tuple(int(c * fade) for c in p["color"])
            size = max(1, int(p["size"] * fade))
            
            if p["style"] == "spark":
                pygame.draw.circle(self.screen, color, (int(p["x"]), int(p["y"])), size)
                # 꼬리 효과
                tail_x = int(p["x"] - p["vx"] * 2)
                tail_y = int(p["y"] - p["vy"] * 2)
                pygame.draw.line(self.screen, color, (int(p["x"]), int(p["y"])), (tail_x, tail_y), 1)
            elif p["style"] == "glow":
                self._draw_glow(int(p["x"]), int(p["y"]), size + 4, color, layers=3)
                pygame.draw.circle(self.screen, color, (int(p["x"]), int(p["y"])), size)
            else:
                pygame.draw.circle(self.screen, color, (int(p["x"]), int(p["y"])), size)

    def add_camera_shake(self, intensity: float, duration_ms: int) -> None:
        """카메라 쉐이크 효과 추가"""
        self._camera_shake_intensity = max(self._camera_shake_intensity, intensity)
        self._camera_shake_duration = max(self._camera_shake_duration, duration_ms)

    def update_camera_shake(self, dt_ms: int) -> Tuple[int, int]:
        """카메라 쉐이크 업데이트 및 오프셋 반환"""
        if self._camera_shake_duration > 0:
            self._camera_shake_duration -= dt_ms
            if self._camera_shake_duration <= 0:
                self._camera_shake_intensity = 0.0
                return (0, 0)
            
            # 랜덤 오프셋 생성
            shake_x = int(random.uniform(-self._camera_shake_intensity, self._camera_shake_intensity))
            shake_y = int(random.uniform(-self._camera_shake_intensity, self._camera_shake_intensity))
            return (shake_x, shake_y)
        return (0, 0)

    # ── Public API ─────────────────────────────────────────────────────────────

    def render_intro(
        self,
        tick: int,
        chars_shown: int,
        btn_play: Optional[pygame.Rect],
        btn_exit: Optional[pygame.Rect],
        text: str = "ARE YOU READY TO GAME?",
    ) -> None:
        """드라마틱 인트로: 한 글자씩 나타나는 제목 + PLAY / EXIT 버튼."""
        W, H = self.W, self.H

        self.screen.fill((0, 0, 0))

        # 은은한 배경 파티클 (중립 그레이 — 크롬은 무채색)
        for k in range(5):
            a  = tick * 0.007 + k * math.pi * 2 / 5
            px = int(W // 2 + math.cos(a) * (180 + k * 30))
            py = int(H // 2 + math.sin(a * 0.6) * (55 + k * 18))
            rc = self._pulse_color(RUNE_DIM, RUNE_GLO, tick + k * 20, 100)
            pygame.draw.circle(self.screen, rc, (px, py), 1 + k % 2)

        # 수평 스캔라인 (극적 효과)
        sl = pygame.Surface((W, 1), pygame.SRCALPHA)
        sl.fill((0, 0, 0, 38))
        for y in range(0, H, 5):
            self.screen.blit(sl, (0, y))

        # ── 한 글자씩 나타나기 ─────────────────────────────────────────────
        tf          = self.font_game_title
        char_widths = [tf.size(c)[0] for c in text]
        total_w     = sum(char_widths)
        start_x     = W // 2 - total_w // 2
        ty          = H // 2 - 52

        x = start_x
        for i, (c, cw) in enumerate(zip(text, char_widths)):
            if i < chars_shown and c != ' ':
                age       = chars_shown - i
                glow_frac = max(0.0, 1.0 - age * 0.06)

                sh = tf.render(c, True, (0, 0, 0))
                sh.set_alpha(150)
                self.screen.blit(sh, (x + 3, ty + 3))

                self.screen.blit(tf.render(c, True, TEXT_PRIMARY), (x, ty))

                if glow_frac > 0.04:
                    gs = tf.render(c, True, WHITE)
                    gs.set_alpha(int(140 * glow_frac))
                    self.screen.blit(gs, (x - 1, ty - 1))
            x += cw

        # ── PLAY / EXIT 버튼 (전체 공개 후 표시) ──────────────────────────
        if btn_play is not None:
            self._draw_hero_button(btn_play, "PLAY")
        if btn_exit is not None:
            self._draw_button(btn_exit, "EXIT", danger=True)

        pygame.display.flip()

    def render_menu(
        self,
        btn_start:     pygame.Rect,
        btn_exit:      pygame.Rect,
        btn_guide:     pygame.Rect,
        btn_settings:  pygame.Rect,
        btn_no_camera: pygame.Rect,
        difficulty:    str,
        btn_daily:     Optional[pygame.Rect] = None,
        orb:           Optional[object] = None,
        orb_center:    Optional[Tuple[int, int]] = None,
        camera_active: bool = False,
        seated_mode:   bool = False,
        daily_best:    int = 0,
        daily_streak:  int = 0,
        best_score:    int = 0,
        unlocked_stage: int = 1,
        stage_count:   int = 1,
    ) -> None:
        self._tick += 1
        W, H = self.W, self.H

        self._draw_bg()

        # ── Ambient floating ember particles (grayscale, static chrome) ────
        for k in range(8):
            a   = self._tick * 0.012 + k * math.pi * 2 / 8
            px_ = W // 2 + int(math.cos(a) * (180 + k * 18))
            py_ = H // 2 + int(math.sin(a * 0.7) * (80 + k * 10)) - 40
            rc  = self._pulse_color(RUNE_DIM, RUNE_GLO, self._tick + k * 22, 70)
            pygame.draw.circle(self.screen, rc, (px_, py_), 2 + k % 2)

        # ── Title (flat off-white, single soft shadow — no colour pulse) ───
        tf = self.font_game_title
        ty = 116        # 상단 여백이 130px 비어 있었다 — 타이틀을 끌어올린다

        sh_t = tf.render("AIR SPELL ARENA", True, (0, 0, 0))
        sh_t.set_alpha(90)
        self.screen.blit(sh_t, sh_t.get_rect(center=(W // 2 + 3, ty + 3)))

        title_s = tf.render("AIR SPELL ARENA", True, TEXT_PRIMARY)
        self.screen.blit(title_s, title_s.get_rect(center=(W // 2, ty)))

        # ── Subtitle ────────────────────────────────────────────────────────
        sub_f = self.font_game_tab
        # 태그라인은 "무슨 게임인지"가 아니라 "왜 이 게임인지"를 말해야 한다.
        # 이 장르의 구매 이유는 장비가 필요 없다는 것 하나다.
        sub_s = sub_f.render("NO VR   ·   NO CONTROLLER   ·   JUST YOUR WEBCAM AND YOUR HANDS",
                             True, TEXT_SECONDARY)
        self.screen.blit(sub_s, sub_s.get_rect(center=(W // 2, ty + 56)))

        self._draw_rune_separator(ty + 80)

        # ── Best score / stage-progress hint (progression hook) ────────────
        if best_score > 0:
            bs_txt = f"BEST SCORE ({difficulty.upper()})  {best_score}   •   STAGE {unlocked_stage}/{stage_count} UNLOCKED"
            bs_s = self.font_game_tab.render(bs_txt, True, GOLD)
            self.screen.blit(bs_s, bs_s.get_rect(center=(W // 2, ty + 100)))
        elif stage_count > 1:
            hint_s = self.font_game_tab.render(
                "Clear a stage to unlock the next boss in the gauntlet", True, TEXT_SECONDARY)
            self.screen.blit(hint_s, hint_s.get_rect(center=(W // 2, ty + 100)))

        # ── 수정구(라이브 웹캠) ─────────────────────────────────────────────
        # 웹캠 모션 게임인데 타이틀 화면에 사람이 없으면, 스크린샷 한 장으로는
        # 평범한 다크 메뉴와 구별되지 않는다. 메뉴에서 이미 "이 게임이 나를
        # 보고 있다"를 증명하는 게 어떤 카피보다 강하다.
        if orb is not None and orb_center is not None:
            ocx, ocy = orb_center
            orb.render(self.screen, orb_center, self._tick,
                       accent=RUNE_GLO if camera_active else HAIRLINE)
            cap_col = TEXT_PRIMARY if camera_active else TEXT_SECONDARY
            cap = self.font_game_tab.render(
                "THIS IS YOU" if camera_active else "CAMERA OFF", True, cap_col)
            self.screen.blit(cap, cap.get_rect(center=(ocx, ocy + 116)))
            if not camera_active:
                hint = self.font_game_tab.render("PRESS  C  TO ENABLE", True, HAIRLINE)
                self.screen.blit(hint, hint.get_rect(center=(ocx, ocy + 138)))

        # ── START button (hero — full width, primary CTA) ──────────────────
        self._draw_hero_button(btn_start, "START  GAME")

        # ── DAILY CHALLENGE (secondary CTA — 리텐션 기능은 키로 숨기면 안 된다) ──
        if btn_daily is not None:
            # 메뉴 크롬 폰트에는 한글 글리프가 없다 — 여기서 한글을 쓰면 □ 로 깨진다.
            d_label = "DAILY CHALLENGE"
            if daily_streak > 0:
                d_label += f"   ·   STREAK {daily_streak}"
            self._draw_button(btn_daily, d_label, self.font_game_tab)
            pygame.draw.rect(self.screen, GOLD, btn_daily, 1, border_radius=5)

        # ── GUIDE + SETTINGS (small, side by side) ─────────────────────────
        self._draw_button(btn_guide,    "SPELL GUIDE", self.font_game_tab)
        self._draw_button(btn_settings, "SETTINGS",    self.font_game_tab)

        # ── EXIT — 중립 동작이므로 가장 작고 조용하게(예전엔 붉은 2순위 버튼이었다) ──
        self._draw_button(btn_exit, "EXIT", self.font_game_tab)

        # ── 카메라 토글 — 라벨이 *실제* 파이프라인 상태를 말한다 ──────────────
        # 예전에는 "PLAY WITHOUT CAMERA" 가 단방향 시작 버튼이라 한 번 끄면
        # 재시작 말고는 되돌릴 방법이 없었다. 이제는 상태를 보여주는 토글이다.
        cam_label = "CAMERA  ON" if camera_active else "CAMERA  OFF  (KEYBOARD)"
        self._draw_button(btn_no_camera, cam_label, self.font_game_tab,
                          danger=not camera_active)

        # ── 접근성/챌린지 상태 줄 — 지금 어떤 설정으로 플레이하는지 한눈에 ──
        # 스트릭은 DAILY 버튼이 이미 말하고 있으므로 여기서 반복하지 않는다.
        status_bits = []
        if seated_mode:
            status_bits.append(("SEATED MODE", GREEN))
        if daily_best > 0:
            status_bits.append((f"TODAY BEST {daily_best}", GOLD))
        if status_bits:
            sx = btn_no_camera.centerx - sum(
                self.font_game_tab.size(t)[0] + 22 for t, _ in status_bits) // 2
            sy = btn_no_camera.bottom + 12
            for text, col in status_bits:
                s_img = self.font_game_tab.render(text, True, col)
                self.screen.blit(s_img, (sx, sy))
                sx += s_img.get_width() + 22

        # ── Difficulty badge pill (flat chrome, tier colour on text only) ──
        diff_colors = {"easy": GREEN, "normal": YELLOW, "hard": ORANGE, "impossible": RED}
        dc   = diff_colors.get(difficulty, WHITE)
        dy_  = 516
        pill_w, pill_h = 230, 34
        pill = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pill.fill((255, 255, 255, 14))
        self.screen.blit(pill, (W // 2 - pill_w // 2, dy_ - pill_h // 2))
        pygame.draw.rect(self.screen, HAIRLINE,
                         (W // 2 - pill_w // 2, dy_ - pill_h // 2, pill_w, pill_h), 1, border_radius=17)
        diff_s = self.font_game_tab.render(f"DIFFICULTY :  {difficulty.upper()}", True, dc)
        self.screen.blit(diff_s, diff_s.get_rect(center=(W // 2, dy_)))

        # ── Keyboard shortcut key-caps (flat chrome, tier colour on digit) ──
        # 실제 키 바인딩과 1:1로 맞춘다 — 안 맞는 안내는 없느니만 못하다.
        keys = [("1", "Easy", GREEN), ("2", "Norm", YELLOW),
                ("3", "Hard", ORANGE), ("4", "Impos", RED),
                ("D", "Daily", GOLD), ("K", "Calib", CYAN),
                ("S", "Seated", GREEN if seated_mode else TEXT_SECONDARY),
                ("C", "Camera", TEXT_SECONDARY), ("G", "Guide", TEXT_SECONDARY)]
        _kslot = 104
        total_w = len(keys) * _kslot
        kx0 = W // 2 - total_w // 2
        ky  = 556
        for i, (k_lbl, k_name, k_col) in enumerate(keys):
            kx = kx0 + i * _kslot
            # key cap box
            cap = pygame.Rect(kx, ky - 11, 22, 22)
            cap_bg = pygame.Surface((22, 22), pygame.SRCALPHA)
            cap_bg.fill((255, 255, 255, 14))
            self.screen.blit(cap_bg, cap.topleft)
            pygame.draw.rect(self.screen, HAIRLINE, cap, 1, border_radius=3)
            ks = self.font_game_tab.render(k_lbl, True, k_col)
            self.screen.blit(ks, ks.get_rect(center=cap.center))
            # label next to key
            ns = self.font.render(k_name, True, TEXT_SECONDARY)
            self.screen.blit(ns, (kx + 26, ky - 7))

        pygame.display.flip()

    def _draw_hero_button(
        self,
        rect:  pygame.Rect,
        label: str,
        danger: bool = False,
    ) -> None:
        """Large primary CTA — flat panel + hairline border, no glow/pulse."""
        edge = DANGER if danger else ACCENT
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((255, 255, 255, 22))
        self.screen.blit(bg, rect.topleft)
        pygame.draw.rect(self.screen, edge, rect, 2, border_radius=6)
        lbl_s = self.font_game_title.render(label, True, edge)
        lbl_s = pygame.transform.smoothscale(
            lbl_s, (min(lbl_s.get_width(), rect.w - 20),
                    min(lbl_s.get_height(), rect.h - 8))
        )
        self.screen.blit(lbl_s, lbl_s.get_rect(center=rect.center))

    def render_settings(
        self,
        files: List[str],
        pending: dict,
        active_slot: str,
        use_custom: bool = False,
        has_custom: bool = False,
        scroll_offset: int = 0,
        pending_volumes: Optional[dict] = None,
    ) -> List[Tuple[pygame.Rect, str, Optional[str]]]:
        """탭 기반 오디오 설정 화면. pending={slot: file|None}, active_slot=현재 탭.

        반환 clickables: [(rect, action, value)]
          action: "slot_tab"   → value=slot 이름 (탭 버튼)
                  slot_name    → value=파일명|None (파일 행 선택, action==active_slot)
                  "preview"    → value=파일명
                  "toggle_custom" → None (커스텀 사운드 토글)
                  "save"|"back"
        """
        self._tick += 1
        W, H = self.W, self.H
        clickables: List[Tuple[pygame.Rect, str, Optional[str]]] = []

        # ── 배경 ──────────────────────────────────────────────────────────
        self._draw_bg(0.0)
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 175))
        self.screen.blit(ov, (0, 0))

        # ── 제목 (게임 전용 폰트) ─────────────────────────────────────────
        ts = self.font_game_title.render("AUDIO  SETTINGS", True, TEXT_PRIMARY)
        # 제목 뒤 그림자
        ts_sh = self.font_game_title.render("AUDIO  SETTINGS", True, (0, 0, 0))
        self.screen.blit(ts_sh, ts_sh.get_rect(center=(W // 2 + 3, 42 + 3)))
        self.screen.blit(ts,    ts.get_rect(center=(W // 2, 42)))
        pygame.draw.line(self.screen, RUNE_DIM, (W // 8, 72), (W * 7 // 8, 72), 1)

        # ── 커스텀 사운드 토글 버튼 (오른쪽 상단) ─────────────────────────
        if has_custom:
            toggle_w, toggle_h = 180, 28
            toggle_x = W - 50 - toggle_w
            toggle_y = 38
            toggle_rect = pygame.Rect(toggle_x, toggle_y, toggle_w, toggle_h)
            
            toggle_col = ACCENT if use_custom else HAIRLINE
            toggle_bg = pygame.Surface((toggle_w, toggle_h), pygame.SRCALPHA)
            toggle_bg.fill((255, 255, 255, 16))
            self.screen.blit(toggle_bg, toggle_rect.topleft)
            pygame.draw.rect(self.screen, toggle_col, toggle_rect, 1, border_radius=14)

            toggle_txt = "🎵 CUSTOM" if use_custom else "🎵 DEFAULT"
            toggle_s = self.font_game_tab.render(toggle_txt, True, toggle_col)
            self.screen.blit(toggle_s, toggle_s.get_rect(center=toggle_rect.center))
            clickables.append((toggle_rect, "toggle_custom", None))

        # ── 슬롯 탭 (2줄 × 4 = 8개) ──────────────────────────────────────
        mx = 40    # 좌우 여백
        tab_gap = 8
        tab_w   = (W - mx * 2 - tab_gap * 3) // 4   # ≈199
        tab_h   = 32
        row1_y, row2_y = 78, 118

        for idx, slot in enumerate(_SLOT_ORDER):
            col  = _SLOT_COLORS[slot]
            label = _SLOT_LABELS[slot]
            row   = idx // 4
            col_i = idx % 4
            tx = mx + col_i * (tab_w + tab_gap)
            ty = row1_y if row == 0 else row2_y
            tab_rect = pygame.Rect(tx, ty, tab_w, tab_h)

            is_active = (slot == active_slot)
            if is_active:
                # 활성 탭: 채운 배경
                tab_bg = pygame.Surface((tab_w, tab_h), pygame.SRCALPHA)
                tab_bg.fill((col[0] // 5, col[1] // 5, col[2] // 5, 220))
                self.screen.blit(tab_bg, tab_rect.topleft)
                pygame.draw.rect(self.screen, col, tab_rect, 2, border_radius=6)
                lbl_s = self.font_game_tab.render(label, True, col)
            else:
                tab_bg = pygame.Surface((tab_w, tab_h), pygame.SRCALPHA)
                tab_bg.fill((20, 14, 40, 180))
                self.screen.blit(tab_bg, tab_rect.topleft)
                border_c = tuple(c // 3 for c in col)
                pygame.draw.rect(self.screen, border_c, tab_rect, 1, border_radius=6)  # type: ignore
                lbl_s = self.font_game_tab.render(label, True, tuple(c // 2 for c in col))  # type: ignore

            self.screen.blit(lbl_s, lbl_s.get_rect(center=tab_rect.center))
            clickables.append((tab_rect, "slot_tab", slot))

        # ── 파일 목록 패널 ────────────────────────────────────────────────
        slot_col = _SLOT_COLORS.get(active_slot, GREY)
        panel_x, panel_y = mx, 158
        panel_w, panel_h = W - mx * 2, H - 158 - 70  # 하단 여유 공간 증가
        row_h = 38  # 행 높이 약간 감소

        panel_bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel_bg.fill((14, 9, 28, 220))
        self.screen.blit(panel_bg, (panel_x, panel_y))
        pygame.draw.rect(self.screen, slot_col, (panel_x, panel_y, panel_w, panel_h), 1, border_radius=6)

        # 패널 헤더 (활성 슬롯 이름)
        hdr_txt = _SLOT_LABELS.get(active_slot, active_slot)
        hdr_s   = self.font_game_tab.render(hdr_txt, True, slot_col)
        self.screen.blit(hdr_s, (panel_x + 16, panel_y + 8))

        # ── Volume control (right side of header) ─────────────────────────
        vol = (pending_volumes or {}).get(active_slot, 50)
        vol_dim: Tuple[int, int, int] = (max(0, slot_col[0] // 2), max(0, slot_col[1] // 2), max(0, slot_col[2] // 2))
        vol_lbl_s = self.font_game_tab.render("VOL", True, vol_dim)
        self.screen.blit(vol_lbl_s, (panel_x + panel_w - 128, panel_y + 8))

        btn_vminus = pygame.Rect(panel_x + panel_w - 94, panel_y + 6, 22, 22)
        pygame.draw.rect(self.screen, (42, 32, 62), btn_vminus, border_radius=4)
        pygame.draw.rect(self.screen, slot_col, btn_vminus, 1, border_radius=4)
        vm_s = self.font_game_tab.render("-", True, slot_col)
        self.screen.blit(vm_s, vm_s.get_rect(center=btn_vminus.center))
        clickables.append((btn_vminus, "vol_down", active_slot))

        vol_num_s = self.font_game_tab.render(str(vol), True, WHITE)
        self.screen.blit(vol_num_s, vol_num_s.get_rect(center=(panel_x + panel_w - 59, panel_y + 17)))

        btn_vplus = pygame.Rect(panel_x + panel_w - 32, panel_y + 6, 22, 22)
        pygame.draw.rect(self.screen, (42, 32, 62), btn_vplus, border_radius=4)
        pygame.draw.rect(self.screen, slot_col, btn_vplus, 1, border_radius=4)
        vp_s = self.font_game_tab.render("+", True, slot_col)
        self.screen.blit(vp_s, vp_s.get_rect(center=btn_vplus.center))
        clickables.append((btn_vplus, "vol_up", active_slot))

        pygame.draw.line(self.screen, slot_col,
                         (panel_x + 8, panel_y + 34), (panel_x + panel_w - 8, panel_y + 34), 1)

        list_y0  = panel_y + 38
        list_h   = panel_h - 42
        all_opts: List[Optional[str]] = [None] + files
        sel      = pending.get(active_slot)
        max_visible_rows = list_h // row_h
        total_rows = len(all_opts)
        
        # 스크롤 가능한 최대 오프셋
        max_scroll = max(0, total_rows - max_visible_rows)
        scroll_offset = max(0, min(scroll_offset, max_scroll))
        
        # 스크롤바 표시 (파일이 많을 때)
        if total_rows > max_visible_rows:
            scrollbar_x = panel_x + panel_w - 12
            scrollbar_y = list_y0
            scrollbar_h = list_h
            scrollbar_w = 8
            
            # 스크롤바 배경
            pygame.draw.rect(self.screen, (30, 25, 40), 
                           (scrollbar_x, scrollbar_y, scrollbar_w, scrollbar_h), border_radius=4)
            
            # 스크롤바 핸들
            handle_h = max(20, int(scrollbar_h * (max_visible_rows / total_rows)))
            handle_y = scrollbar_y + int((scrollbar_h - handle_h) * (scroll_offset / max_scroll)) if max_scroll > 0 else scrollbar_y
            pygame.draw.rect(self.screen, slot_col,
                           (scrollbar_x, handle_y, scrollbar_w, handle_h), border_radius=4)
        
        # 파일 목록 렌더링 (스크롤 오프셋 적용)
        for i in range(scroll_offset, min(scroll_offset + max_visible_rows, total_rows)):
            opt = all_opts[i]
            display_idx = i - scroll_offset
            ry = list_y0 + display_idx * row_h
            
            # 파일명 길이 제한 (더 짧게)
            if opt is None:
                disp = "없음"
            else:
                max_len = 35  # 최대 문자 길이 감소
                disp = opt if len(opt) <= max_len else opt[:max_len-2] + "…"
            
            is_sel = (opt == sel)

            row_rect = pygame.Rect(panel_x + 8, ry + 2, panel_w - 90, row_h - 4)  # 스크롤바 공간 확보
            clickables.append((row_rect, active_slot, opt))

            if is_sel:
                hl = pygame.Surface((row_rect.w, row_rect.h), pygame.SRCALPHA)
                rc = slot_col
                hl.fill((rc[0] // 5, rc[1] // 5, rc[2] // 5, 110))
                self.screen.blit(hl, row_rect.topleft)
                pygame.draw.rect(self.screen, slot_col, row_rect, 1, border_radius=4)

            radio_x, radio_y = panel_x + 20, ry + row_h // 2
            pygame.draw.circle(self.screen, GREY, (radio_x, radio_y), 6, 2)
            if is_sel:
                pygame.draw.circle(self.screen, slot_col, (radio_x, radio_y), 3)

            fn_col = slot_col if is_sel else GREY
            fn_s = self.font_kor_small.render(disp, True, fn_col)  # 작은 폰트 사용
            self.screen.blit(fn_s, (panel_x + 36, ry + row_h // 2 - 8))

            if opt is not None:
                pb = pygame.Rect(panel_x + panel_w - 84, ry + row_h // 2 - 11, 68, 22)
                pygame.draw.rect(self.screen, (30, 25, 60), pb, border_radius=5)
                pygame.draw.rect(self.screen, RUNE_GLO, pb, 1, border_radius=5)
                pb_s = self.font_kor_small.render("▶ 듣기", True, GREEN)
                self.screen.blit(pb_s, pb_s.get_rect(center=pb.center))
                clickables.append((pb, "preview", opt))

        if not files:
            no_s = self.font_kor_small.render("sounds/ 폴더에 오디오 파일 없음", True, (70, 60, 90))
            self.screen.blit(no_s, no_s.get_rect(center=(W // 2, list_y0 + 40)))
        
        # 스크롤 힌트 표시
        if total_rows > max_visible_rows:
            hint_s = self.font_kor_small.render("마우스 휠로 스크롤 가능", True, (100, 90, 120))
            self.screen.blit(hint_s, (panel_x + panel_w - hint_s.get_width() - 30, panel_y + panel_h - 20))

        # ── 저장 / 뒤로 버튼 ─────────────────────────────────────────────
        btn_save = pygame.Rect(W // 2 - 125, H - 42, 110, 34)
        btn_back = pygame.Rect(W // 2 + 15,  H - 42, 110, 34)
        self._draw_button(btn_save, "저장", self.font_kor_big)
        self._draw_button(btn_back, "뒤로", self.font_kor_big)
        clickables.append((btn_save, "save", None))
        clickables.append((btn_back, "back", None))
        
        # 스크롤 제어를 위한 특수 영역 (마우스 휠 감지용)
        clickables.append((pygame.Rect(panel_x, panel_y, panel_w, panel_h), "scroll_area", None))

        # 커스텀 모드 표시 (하단 상태바)
        if has_custom:
            status_txt = f"모드: {'커스텀 사운드' if use_custom else '기본 사운드'}  |  파일: {len(files)}개"
            status_s = self.font_kor_small.render(status_txt, True, GREY)
            self.screen.blit(status_s, (50, H - 58))

        pygame.display.flip()
        return clickables

    def render_tutorial(self, tick: int) -> None:
        """Full-screen spell guide — 3-section card layout."""
        self._tick += 1
        W, H = self.W, self.H

        self._draw_bg(0.0)
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 158))
        self.screen.blit(overlay, (0, 0))

        # ── Title (game font + shadow) ─────────────────────────────────────
        ts_sh  = self.font_game_title.render("SPELL  GUIDE", True, (0, 0, 0))
        ts_sh.set_alpha(90)
        ts     = self.font_game_title.render("SPELL  GUIDE", True, TEXT_PRIMARY)
        self.screen.blit(ts_sh, ts_sh.get_rect(center=(W // 2 + 2, 38 + 2)))
        self.screen.blit(ts,    ts.get_rect(center=(W // 2, 38)))
        pygame.draw.line(self.screen, RUNE_DIM, (W // 8, 64), (W * 7 // 8, 64), 1)

        # ── Section definitions ─────────────────────────────────────────────
        SEC_H    = 24   # section header bar height
        CARD_GAP = 8
        MX       = 14   # left/right margin

        sections = [
            {
                "label": "GESTURE SPELLS — ONE HAND", "lc": ORANGE, "ncols": 4, "ch": 74,
                "entries": [
                    ("palm",  "FIRE",    "손바닥 펴기 (Open Palm)", ORANGE),
                    ("fist",  "WATER",   "주먹 쥐기 (Make Fist)",   BLUE),
                    ("thumb", "EARTH",   "엄지 위로 (Thumbs Up)",   (150, 130, 100)),
                    ("index", "WIND",    "검지만 세우기 (Index Up)", GREEN),
                ],
            },
            {
                # 이 게임의 차별점이자 가장 강한 그림. 안 가르치면 존재하지 않는 기능이 된다.
                "label": "DUAL CASTING — BOTH HANDS", "lc": GOLD, "ncols": 3, "ch": 74,
                "entries": [
                    ("dual_same", "AMPLIFY x2", "양손 같은 모양 → 위력 2배", GOLD),
                    ("dual_diff", "FUSION",     "양손 다른 모양 → 상위 주문 즉시", PINK),
                    ("mana",      "MANA",       "시전마다 소모 · 손 내리고 회복", BLUE),
                ],
            },
            {
                "label": "DRAW SPELLS", "lc": CYAN, "ncols": 4, "ch": 74,
                "entries": [
                    ("left",   "LIGHT",     "손을 왼쪽으로 스와이프",   CYAN),
                    ("right",  "DARK",      "손을 오른쪽으로 스와이프", PURPLE),
                    ("circle", "SHIELD",    "허공에 원 그리기",          (80, 200, 220)),
                    ("zigzag", "LIGHTNING", "허공에 지그재그 그리기",           BLUE),
                ],
            },
            {
                "label": "MOVEMENT", "lc": WHITE, "ncols": 2, "ch": 66,
                "entries": [
                    ("head_l", "DODGE LEFT",  "고개 왼쪽으로 (Turn Head Left)",  WHITE),
                    ("head_r", "DODGE RIGHT", "고개 오른쪽으로 (Turn Head Right)", WHITE),
                ],
            },
        ]

        y_cur = 70

        for sec in sections:
            ncols   = sec["ncols"]
            card_h  = sec["ch"]
            lc: Tuple[int, int, int] = sec["lc"]
            card_w  = (W - MX * 2 - CARD_GAP * (ncols - 1)) // ncols

            # Section header bar
            sh_bg = pygame.Surface((W - MX * 2, SEC_H), pygame.SRCALPHA)
            sh_bg.fill((lc[0] // 9, lc[1] // 9, lc[2] // 9, 180))
            self.screen.blit(sh_bg, (MX, y_cur))
            pygame.draw.line(self.screen, lc, (MX, y_cur + SEC_H - 1),
                             (W - MX, y_cur + SEC_H - 1), 1)
            # Left accent bar
            pygame.draw.rect(self.screen, lc, (MX, y_cur, 3, SEC_H))
            sh_s = self.font_game_tab.render(sec["label"], True, lc)
            self.screen.blit(sh_s, (MX + 9, y_cur + (SEC_H - sh_s.get_height()) // 2))
            y_cur += SEC_H + 4

            # Cards
            for ci, (icon, label, desc, ec) in enumerate(sec["entries"]):
                cx_ = MX + ci * (card_w + CARD_GAP)
                cy_ = y_cur

                # Card background
                cb = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
                cb.fill((7, 4, 18, 210))
                self.screen.blit(cb, (cx_, cy_))
                bc: Tuple[int, int, int] = (
                    max(0, ec[0] // 3), max(0, ec[1] // 3), max(0, ec[2] // 3)
                )
                pygame.draw.rect(self.screen, bc, (cx_, cy_, card_w, card_h), 1, border_radius=6)

                # Bottom accent line
                aw = int(card_w * 0.88)
                ax_ = cx_ + (card_w - aw) // 2
                ac: Tuple[int, int, int] = (ec[0] // 2, ec[1] // 2, ec[2] // 2)
                pygame.draw.line(self.screen, ac,
                                 (ax_, cy_ + card_h - 3), (ax_ + aw, cy_ + card_h - 3), 2)

                # Gesture icon (left side)
                self._draw_gesture_icon(cx_ + 28, cy_ + card_h // 2, icon, ec, tick)

                # Vertical divider
                dv_x = cx_ + 54
                pygame.draw.line(self.screen, bc,
                                 (dv_x, cy_ + 6), (dv_x, cy_ + card_h - 6), 1)

                # Spell name
                nm_s = self.font_game_tab.render(label, True, ec)
                tx_  = dv_x + 10
                self.screen.blit(nm_s, (tx_, cy_ + 10))

                # Korean description — 카드 폭을 넘으면 작은 폰트로 떨어뜨린다.
                # (4열 레이아웃에서 긴 설명이 옆 카드를 침범하던 문제)
                avail = card_w - (tx_ - cx_) - 8
                ds_s = self.font_kor.render(desc, True, (130, 118, 148))
                if ds_s.get_width() > avail:
                    ds_s = self.font_kor_small.render(desc, True, (130, 118, 148))
                self.screen.blit(ds_s, (tx_, cy_ + 10 + nm_s.get_height() + 2))

            y_cur += card_h + 7

        # ── NO CAMERA MODE — 웹캠 없이 진행할 때의 키보드 가이드북 ──────────
        nc_lc = GOLD
        sh_bg = pygame.Surface((W - MX * 2, SEC_H), pygame.SRCALPHA)
        sh_bg.fill((nc_lc[0] // 9, nc_lc[1] // 9, nc_lc[2] // 9, 180))
        self.screen.blit(sh_bg, (MX, y_cur))
        pygame.draw.line(self.screen, nc_lc, (MX, y_cur + SEC_H - 1),
                         (W - MX, y_cur + SEC_H - 1), 1)
        pygame.draw.rect(self.screen, nc_lc, (MX, y_cur, 3, SEC_H))
        nc_hdr = self.font_game_tab.render("NO CAMERA MODE — KEYBOARD GUIDE", True, nc_lc)
        self.screen.blit(nc_hdr, (MX + 9, y_cur + (SEC_H - nc_hdr.get_height()) // 2))
        y_cur += SEC_H + 4

        nc_h  = 88
        nc_bg = pygame.Surface((W - MX * 2, nc_h), pygame.SRCALPHA)
        nc_bg.fill((7, 4, 18, 210))
        self.screen.blit(nc_bg, (MX, y_cur))
        nc_border = (nc_lc[0] // 3, nc_lc[1] // 3, nc_lc[2] // 3)
        pygame.draw.rect(self.screen, nc_border, (MX, y_cur, W - MX * 2, nc_h), 1, border_radius=6)

        nc_rows = [
            ("1 2 3 4 5 6 7", "주문 시전 (FIRE · WATER · WIND · EARTH · DARK · LIGHT · LIGHTNING)", True),
            ("<-   ->", "고개 대신 화살표 키로 좌우 회피 (Dodge Left / Right)", True),
            ("ESC / ENTER", "일시정지  ·  재도전 · 다음 스테이지로 이어가기", True),
            ("C / V / R", "카메라 켜고끄기  ·  수정구 표시  ·  하이라이트 녹화 (인게임)", True),
            ("메뉴  D / K / S", "오늘의 챌린지  ·  포즈 재확인  ·  앉은 자세 모드", False),
        ]
        row_h = nc_h // len(nc_rows)
        for i, (key_lbl, desc, key_is_ascii) in enumerate(nc_rows):
            ry = y_cur + i * row_h
            key_font = self.font_game_tab if key_is_ascii else self.font_kor_small
            key_s = key_font.render(key_lbl, True, nc_lc)
            self.screen.blit(key_s, (MX + 16, ry + row_h // 2 - key_s.get_height() // 2))
            desc_s = self.font_kor_small.render(desc, True, (170, 165, 185))
            self.screen.blit(desc_s, (MX + 240, ry + row_h // 2 - desc_s.get_height() // 2))
            if i < len(nc_rows) - 1:
                pygame.draw.line(self.screen, (40, 35, 55),
                                 (MX + 10, ry + row_h), (W - MX - 10, ry + row_h), 1)
        y_cur += nc_h + 7

        # ── Back prompt with styled key-caps ───────────────────────────────
        remaining = H - y_cur
        ky_ = y_cur + remaining // 2 - 14
        prompt_c = WHITE if (tick // 30) % 2 == 0 else GREY

        key_labels = [("ENTER", CYAN), ("SPACE", GREEN), ("ESC", RED)]
        kw_, kh_ = 62, 24
        total_kw  = len(key_labels) * kw_ + (len(key_labels) - 1) * 10
        kx_start  = W // 2 - total_kw // 2

        for ki_, (k_lbl, k_col) in enumerate(key_labels):
            kx_ = kx_start + ki_ * (kw_ + 10)
            k_bg = pygame.Surface((kw_, kh_), pygame.SRCALPHA)
            k_bg.fill((k_col[0] // 6, k_col[1] // 6, k_col[2] // 6, 200))
            self.screen.blit(k_bg, (kx_, ky_))
            pygame.draw.rect(self.screen, k_col, (kx_, ky_, kw_, kh_), 1, border_radius=4)
            ks_ = self.font_game_tab.render(k_lbl, True, k_col)
            self.screen.blit(ks_, ks_.get_rect(center=(kx_ + kw_ // 2, ky_ + kh_ // 2)))

        ret_s = self.font_kor.render("위 키를 눌러 메뉴로 돌아가기", True, prompt_c)
        self.screen.blit(ret_s, ret_s.get_rect(center=(W // 2, ky_ + kh_ + 16)))

        pygame.display.flip()

    def draw_gesture_icon(
        self,
        cx: int,
        cy: int,
        icon: str,
        color: Tuple[int, int, int],
        tick: int,
        scale: float = 1.0,
        target: Optional[pygame.Surface] = None,
    ) -> None:
        """제스처 아이콘 그리기(공개 API — 캘리브레이션 화면도 같은 그림을 쓴다).

        아이콘 원본은 반지름 14px 로 고정돼 있어 온보딩 화면에서는 너무 작다.
        `scale` 을 주면 작은 서피스에 한 번 그린 뒤 확대해서 붙인다.
        """
        dest = target if target is not None else self.screen
        if scale == 1.0 and target is None:
            self._draw_gesture_icon(cx, cy, icon, color, tick)
            return

        size = 48
        tmp = pygame.Surface((size, size), pygame.SRCALPHA)
        prev = self.screen
        self.screen = tmp                      # 그리기 대상만 잠시 바꾼다
        try:
            self._draw_gesture_icon(size // 2, size // 2, icon, color, tick)
        finally:
            self.screen = prev
        out = int(size * scale)
        if out != size:
            tmp = pygame.transform.smoothscale(tmp, (out, out))
        dest.blit(tmp, (cx - tmp.get_width() // 2, cy - tmp.get_height() // 2))

    def _draw_gesture_icon(
        self, cx: int, cy: int, icon: str, color: Tuple[int, int, int], tick: int
    ) -> None:
        """Draw an animated gesture icon at (cx, cy)."""
        pulse = abs(math.sin(tick * 0.06)) * 0.5 + 0.5
        col   = tuple(int(c * pulse) for c in color)
        r = 14

        if icon == "palm":
            # Five short lines radiating upward (spread fingers)
            for i in range(5):
                a = math.radians(-60 + i * 30)
                ex = cx + int(math.sin(a) * r)
                ey = cy - int(math.cos(a) * r)
                pygame.draw.line(self.screen, col, (cx, cy + 4), (ex, ey), 2)
            pygame.draw.circle(self.screen, col, (cx, cy + 4), 5, 1)
        elif icon == "fist":
            # Closed rectangle (knuckles) + thumb nub
            fw, fh = 14, 10
            pygame.draw.rect(self.screen, col, (cx - fw // 2, cy - fh // 2, fw, fh), 2, border_radius=3)
            pygame.draw.circle(self.screen, col, (cx - fw // 2 - 4, cy), 3)
        elif icon == "thumb":
            # Vertical line (thumb) + horizontal bar (fist body)
            pygame.draw.line(self.screen, col, (cx, cy + r), (cx, cy - r), 3)
            pygame.draw.line(self.screen, col, (cx - 6, cy + 3), (cx + 6, cy + 3), 2)
            pygame.draw.circle(self.screen, col, (cx, cy - r), 3)
        elif icon == "index":
            # Single vertical line (index) + curled lines for other fingers
            pygame.draw.line(self.screen, col, (cx, cy + r), (cx, cy - r), 3)
            for offset in (-6, 6):
                curve_y = cy + 4
                pygame.draw.arc(self.screen, col,
                                (cx + offset - 4, curve_y - 5, 8, 8),
                                0, math.pi, 2)
        elif icon == "up":
            self._draw_arrow_shape(cx, cy, 0, col)
        elif icon == "down":
            self._draw_arrow_shape(cx, cy, math.pi, col)
        elif icon == "right":
            self._draw_arrow_shape(cx, cy, math.pi / 2, col)
        elif icon == "left":
            self._draw_arrow_shape(cx, cy, -math.pi / 2, col)
        elif icon == "dual_same":
            # 같은 손 두 개가 마주 본다 → 증폭
            for side in (-1, 1):
                bx = cx + side * 9
                for i in range(3):
                    a = math.radians(-40 + i * 40)
                    pygame.draw.line(self.screen, col, (bx, cy + 5),
                                     (bx + int(math.sin(a) * 8), cy + 5 - int(math.cos(a) * 10)), 2)
            pygame.draw.circle(self.screen, col, (cx, cy - 10), 3)
        elif icon == "dual_diff":
            # 서로 다른 두 손(펼침 + 주먹)이 합쳐지는 모양 → 융합
            for i in range(3):
                a = math.radians(-40 + i * 40)
                pygame.draw.line(self.screen, col, (cx - 9, cy + 5),
                                 (cx - 9 + int(math.sin(a) * 8), cy + 5 - int(math.cos(a) * 10)), 2)
            pygame.draw.circle(self.screen, col, (cx + 9, cy - 2), 6, 2)
            pygame.draw.line(self.screen, col, (cx - 2, cy + 8), (cx + 2, cy + 8), 2)
        elif icon == "mana":
            # 차오르는 물방울 — 자원 회복
            pygame.draw.circle(self.screen, col, (cx, cy + 2), 8, 2)
            pygame.draw.line(self.screen, col, (cx - 6, cy - 5), (cx, cy - 12), 2)
            pygame.draw.line(self.screen, col, (cx + 6, cy - 5), (cx, cy - 12), 2)
            pygame.draw.line(self.screen, col, (cx - 4, cy + 4), (cx + 4, cy + 4), 2)
        elif icon == "circle":
            pygame.draw.circle(self.screen, col, (cx, cy), r, 2)
            dot_a = tick * 0.08
            dx2 = int(cx + math.cos(dot_a) * r)
            dy2 = int(cy + math.sin(dot_a) * r)
            pygame.draw.circle(self.screen, col, (dx2, dy2), 4)
        elif icon == "zigzag":
            pts = []
            for k in range(7):
                zx = cx - 18 + k * 6
                zy = cy + (8 if k % 2 == 0 else -8)
                pts.append((zx, zy))
            pygame.draw.lines(self.screen, col, False, pts, 2)
        elif icon in ("head_l", "head_r"):
            # Simple face circle + direction arrow
            pygame.draw.circle(self.screen, col, (cx, cy), r, 2)
            # Nose nub
            nx = cx + (-6 if icon == "head_l" else 6)
            pygame.draw.circle(self.screen, col, (nx, cy + 3), 3)
            # Direction arrow
            ax = cx + (-22 if icon == "head_l" else 22)
            self._draw_arrow_shape(ax, cy, -math.pi / 2 if icon == "head_l" else math.pi / 2, col)

    def _draw_arrow_shape(
        self, cx: int, cy: int, angle: float, color: Sequence[int]
    ) -> None:
        """Draw a filled arrowhead pointing in the given angle."""
        sz = 12
        tip   = (cx + int(math.sin(angle) * sz),       cy - int(math.cos(angle) * sz))
        left  = (cx + int(math.sin(angle - 2.4) * sz * 0.7),
                 cy - int(math.cos(angle - 2.4) * sz * 0.7))
        right = (cx + int(math.sin(angle + 2.4) * sz * 0.7),
                 cy - int(math.cos(angle + 2.4) * sz * 0.7))
        pygame.draw.polygon(self.screen, color, [tip, left, (cx, cy), right])
        pygame.draw.line(self.screen, color,
                         (cx - int(math.sin(angle) * sz * 0.4),
                          cy + int(math.cos(angle) * sz * 0.4)),
                         (cx, cy), 2)

    def render_frame(
        self,
        player_hp:         int,
        boss_hp:           int,
        shield_time_left:  int,
        lightning_cd_left: int,
        message_text:      str,
        message_time_left: int,
        message_color:     Tuple[int, int, int],
        effects:           List[dict],
        difficulty:        str = "normal",
        player_offset_x:   float = 0.0,
        dt_ms:             int = 16,
        gesture_trail:     Optional[List[Tuple[float, float]]] = None,
        gesture_drawing:   bool = False,
        boss_name:         str = "ARCANE BOSS",
        boss_accent:       Optional[Tuple[int, int, int]] = None,
        score:             int = 0,
        stage_index:       int = 1,
        stage_count:       int = 1,
        # ── 이번 업그레이드에서 추가된 HUD (hud_ext 가 그린다) ──
        mana_ratio:        float = 1.0,
        mana_exhausted:    bool = False,
        mana_cost_preview: float = 0.0,
        rune_summary:      Optional[Sequence[Tuple[str, int]]] = None,
        rune_colors:       Optional[Sequence[Tuple[int, int, int]]] = None,
        dual_progress:     float = 0.0,
        dual_poses:        Optional[Tuple[str, str]] = None,
        orb:               Optional[object] = None,
        orb_center:        Optional[Tuple[int, int]] = None,
        orb_accent:        Tuple[int, int, int] = (150, 120, 255),
        player_max_hp:     int = PLAYER_MAX_HP,
    ) -> None:
        self._tick += 1

        # 파티클 업데이트
        self.update_particles(dt_ms)

        # 카메라 쉐이크 오프셋
        shake_x, shake_y = self.update_camera_shake(dt_ms)

        # 1. Background (with parallax + shake)
        self._draw_bg(player_offset_x)

        # 1.5. 대기 입자 (재/먼지) — 배경 위, 보스 뒤
        self._draw_atmosphere(player_offset_x)

        # 2. Boss (behind effects)
        self._draw_boss(boss_hp / BOSS_MAX_HP, effects, player_offset_x,
                        boss_name=boss_name, accent=boss_accent)

        # 3. Effects (projectiles)
        self._draw_effects(effects, player_offset_x)
        
        # 3.5. 파티클 렌더링 (이펙트 위에)
        self.render_particles()

        # 4. Shield vignette
        if shield_time_left > 0:
            self._draw_shield_vignette(shield_time_left)

        # 5. Wand
        self._draw_wand(player_offset_x)

        # 5.5. 궤적 주문 입력 피드백(허공에 그리는 손끝 트레일)
        if gesture_trail:
            self._draw_gesture_trail(gesture_trail, gesture_drawing)

        # 6. HUD
        self._draw_hud(player_hp, boss_hp, shield_time_left, lightning_cd_left, difficulty,
                       score, stage_index, stage_count, player_max_hp)

        # 6.3. 마나 게이지 — HP 바(좌하단) 바로 위. 플레이어 자원은 한곳에 모은다.
        hud_ext.draw_mana_bar(
            self.screen, self.font,
            pygame.Rect(18, self.H - 86, 210, 12),
            mana_ratio, mana_exhausted, self._tick,
            cost_preview=mana_cost_preview,
        )

        # 6.4. 획득 룬 칩 — 좌상단(전투 중 흘깃 보는 정보라 시야 중앙에서 뺀다)
        if rune_summary:
            hud_ext.draw_rune_chips(self.screen, self.font, 18, 20,
                                    rune_summary, rune_colors, max_width=520)

        # 6.5. 듀얼 캐스팅 게이지 — 화면 하단 중앙(양손이 모이는 중일 때만)
        if dual_progress > 0.0:
            hud_ext.draw_dual_gauge(self.screen, self.font,
                                    (self.W // 2, self.H - 96),
                                    dual_progress, dual_poses)

        # 6.6. 점술 수정구(인게임 웹캠) — 클립에 "사람"이 남게 하는 핵심 요소
        if orb is not None and orb_center is not None:
            orb.render(self.screen, orb_center, self._tick, accent=orb_accent)

        # 6.7. 위급 시 심장박동 비네트 (HP 낮을수록 빠르고 강하게)
        hp_ratio = player_hp / max(1, player_max_hp)
        if 0.0 < hp_ratio < DANGER_HP_RATIO:
            self._draw_danger_vignette(hp_ratio)

        # 7. Spell message
        if message_time_left > 0 and message_text:
            self._draw_spell_message(message_text, message_color, message_time_left)

        # 8. 시네마틱 그레이드(비네트·스플릿톤·그레인)
        self._draw_grade()

        # 9. 카메라 쉐이크 — 최종 합성 프레임을 픽셀 시프트(quick shake)
        if shake_x or shake_y:
            self.screen.scroll(int(shake_x), int(shake_y))

        pygame.display.flip()

    def _draw_gesture_trail(
        self,
        trail: List[Tuple[float, float]],
        drawing: bool,
    ) -> None:
        """정규화(0~1) 손끝 좌표 리스트를 화면 위 페이딩 폴리라인으로 그린다."""
        if not trail or len(trail) < 2:
            return
        W, H = self.W, self.H
        pts = [(int(nx * W), int(ny * H)) for nx, ny in trail]
        n = len(pts)
        for i in range(1, n):
            a = i / n                       # 최근일수록 밝고 굵게
            col = (int(30 + 210 * a), int(150 + 90 * a), 255)
            pygame.draw.line(self.screen, col, pts[i - 1], pts[i], max(1, int(1 + 4 * a)))
        head = pts[-1]
        # 리드미컬한 맥동 헤드 노드
        puls = 0.5 + 0.5 * math.sin(self._tick * 0.32)
        self._draw_glow(head[0], head[1], int(8 + 6 * puls), (0, 200, 255), layers=3)
        pygame.draw.circle(self.screen, (0, 240, 255), head, int(6 + 4 * puls), 2)
        pygame.draw.circle(self.screen, (200, 250, 255), head, 2)
        if drawing:
            lbl = self.font.render("DRAWING", True, (0, 240, 255))
            self.screen.blit(lbl, (head[0] + 14, head[1] - 8))

    def _draw_danger_vignette(self, hp_ratio: float) -> None:
        """저체력 경고 — HP가 낮을수록 박동이 빨라지고 붉은 테두리가 짙어진다."""
        W, H = self.W, self.H
        sev = 1.0 - hp_ratio / DANGER_HP_RATIO           # 0(경계) → 1(빈사)
        period = 46 - int(28 * sev)                       # 박동 주기 단축
        beat = (math.sin(self._tick * 2 * math.pi / max(period, 1)) + 1) / 2
        strength = 0.35 + 0.65 * sev
        peak = int(26 + 30 * strength)
        for w in range(1, 16):
            fade = (1.0 - (w - 1) / 15) * beat * strength
            if fade <= 0:
                continue
            c = (min(255, int(90 + peak * fade)), int(12 * fade), int(24 * fade))
            pygame.draw.rect(self.screen, c, (w, w, W - w * 2, H - w * 2), 1)

    def render_ending(
        self,
        state: str,
        tick: int,
        stats: Optional[dict] = None,
        score: int = 0,
        is_new_record: bool = False,
        can_continue: bool = False,
        chain_score: int = 0,
        next_boss_name: str = "",
        card_path: str = "",
        clip_path: str = "",
    ) -> List[Tuple[pygame.Rect, str, Optional[str]]]:
        """Render game_over/you_win ending screen with run stats + RETRY/MENU buttons.

        Returns clickables [(rect, action, None)] — action: "retry" | "menu".
        """
        self._tick += 1
        W, H = self.W, self.H
        stats = stats or {}
        clickables: List[Tuple[pygame.Rect, str, Optional[str]]] = []

        # Dim background
        self._draw_bg(0.0)
        if self._end_ov is None:
            self._end_ov = pygame.Surface((W, H), pygame.SRCALPHA)
        if state == "game_over":
            self._end_ov.fill((80, 0, 0, 170))
        else:
            self._end_ov.fill((20, 10, 50, 150))
        self.screen.blit(self._end_ov, (0, 0))

        boss_name   = stats.get("boss_name") or "the Arcane Boss"
        stage_idx   = int(stats.get("stage_index", 1))
        stage_count = int(stats.get("stage_count", 1))
        if state == "game_over":
            title_col = self._pulse_color((200, 40, 40), (255, 80, 80), tick, 50)
            title_txt = "GAME OVER"
            sub_txt   = f"You were defeated by {boss_name}..."
        elif can_continue:
            title_col = self._pulse_color((190, 190, 196), WHITE, tick, 50)
            title_txt = f"STAGE {stage_idx} CLEAR!"
            sub_txt   = f"{boss_name} falls — {next_boss_name} awaits."
        elif stage_idx >= stage_count:
            title_col = self._pulse_color((255, 210, 90), WHITE, tick, 40)
            title_txt = "GAUNTLET CLEARED!"
            sub_txt   = f"{boss_name} was the last stand — you beat the full gauntlet!"
        else:
            title_col = self._pulse_color((190, 190, 196), WHITE, tick, 50)
            title_txt = "VICTORY!"
            sub_txt   = f"{boss_name} vanquished — higher difficulty unlocks more stages"

        # Expanding ring animation (behind title)
        ring_cy = H // 2 - 130
        ring_r = int(80 + tick * 1.2) % 300
        ring_col = self._pulse_color(tuple(c // 3 for c in title_col), title_col, tick, 40)
        pygame.draw.circle(self.screen, ring_col, (W // 2, ring_cy), ring_r, 2)
        pygame.draw.circle(self.screen, ring_col, (W // 2, ring_cy), max(1, ring_r - 20), 1)

        # Title
        tf = pygame.font.SysFont(None, 72)
        title_surf = tf.render(title_txt, True, title_col)
        shadow_surf = tf.render(title_txt, True, (0, 0, 0))
        tc = title_surf.get_rect(center=(W // 2, H // 2 - 168))
        self.screen.blit(shadow_surf, (tc.x + 4, tc.y + 4))
        self.screen.blit(title_surf, tc)

        # Subtitle
        sub_surf = self.font_big.render(sub_txt, True, TEXT_SECONDARY)
        self.screen.blit(sub_surf, sub_surf.get_rect(center=(W // 2, H // 2 - 122)))

        # ── Run-stats panel ─────────────────────────────────────────────────
        pw, ph = 560, 186
        px, py = W // 2 - pw // 2, H // 2 - 82
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((10, 10, 14, 215))
        self.screen.blit(panel, (px, py))
        pygame.draw.rect(self.screen, HAIRLINE, (px, py, pw, ph), 1, border_radius=10)

        time_ms = int(stats.get("time_ms", 0))
        tsec = time_ms // 1000
        time_str = f"{tsec // 60:01d}:{tsec % 60:02d}"
        landed = int(stats.get("hits_landed", 0))
        missed = int(stats.get("hits_missed", 0))
        total_shots = landed + missed
        acc = int(round(100 * landed / total_shots)) if total_shots else 0

        rows = [
            ("TIME",        time_str,                           TEXT_PRIMARY),
            ("DMG DEALT",   str(stats.get("dmg_dealt", 0)),      GREEN),
            ("DMG TAKEN",   str(stats.get("dmg_taken", 0)),      RED),
            ("ACCURACY",    f"{acc}%",                           CYAN),
            ("SPELLS CAST", str(stats.get("spells_cast", 0)),    TEXT_PRIMARY),
            ("BEST SCORE",  str(stats.get("best_score", score)), GOLD),
        ]
        col_w = pw // 3
        for i, (label, value, col) in enumerate(rows):
            ccx = px + col_w * (i % 3) + col_w // 2
            ccy = py + 26 + (i // 3) * 80
            lbl_s = self.font_game_tab.render(label, True, TEXT_SECONDARY)
            self.screen.blit(lbl_s, lbl_s.get_rect(center=(ccx, ccy)))
            val_s = self.font_big.render(value, True, col)
            self.screen.blit(val_s, val_s.get_rect(center=(ccx, ccy + 26)))

        pygame.draw.line(self.screen, RUNE_DIM, (px + 16, py + ph - 38), (px + pw - 16, py + ph - 38), 1)

        score_txt = f"STAGE {score}  ·  CHAIN {chain_score}"
        score_col: Tuple[int, int, int] = GOLD if is_new_record else TEXT_PRIMARY
        if is_new_record:
            score_txt += "  ★ BEST"
            score_col = self._pulse_color((255, 210, 60), WHITE, tick, 18)
        score_s = self.font_game_tab.render(score_txt, True, score_col)
        self.screen.blit(score_s, score_s.get_rect(center=(px + pw // 2, py + ph - 18)))

        # ── Buttons ──────────────────────────────────────────────────────────
        if can_continue:
            # 3버튼: 다음 스테이지로 이어가기(주 액션) / 이 스테이지 재도전 / 메인 메뉴
            btn_continue = pygame.Rect(W // 2 - 300, py + ph + 22, 300, 52)
            btn_retry    = pygame.Rect(W // 2 + 4,    py + ph + 22, 148, 52)
            btn_menu     = pygame.Rect(W // 2 + 158,  py + ph + 22, 148, 52)
            self._draw_hero_button(btn_continue, f"CONTINUE -> STAGE {stage_idx + 1}")
            self._draw_button(btn_retry, "RETRY", self.font_game_tab)
            self._draw_button(btn_menu, "MENU", self.font_game_tab)
            clickables.append((btn_continue, "continue", None))
            clickables.append((btn_retry, "retry_stage", None))
            clickables.append((btn_menu, "menu", None))
            hint = "Press ENTER to continue the chain"
        else:
            # 2버튼: 체인 종료 — 처음부터 재도전 / 메인 메뉴
            btn_retry = pygame.Rect(W // 2 - 210, py + ph + 22, 200, 52)
            btn_menu  = pygame.Rect(W // 2 + 10,  py + ph + 22, 200, 52)
            self._draw_hero_button(btn_retry, "RETRY")
            self._draw_button(btn_menu, "MAIN MENU", self.font_game_tab)
            clickables.append((btn_retry, "retry", None))
            clickables.append((btn_menu, "menu", None))
            hint = "Press ENTER to retry from Stage 1"

        # Prompt (blink)
        if (tick // 30) % 2 == 0:
            prompt = self.font.render(hint, True, WHITE)
            self.screen.blit(prompt, prompt.get_rect(center=(W // 2, py + ph + 90)))

        # 저장된 공유물을 알린다 — 찾아가야 할 경로라 깜빡이지 않게 고정 표시
        saved = []
        if clip_path:
            saved.append(("HIGHLIGHT CLIP", clip_path, (255, 205, 110)))
        if card_path:
            saved.append(("SHARE CARD", card_path, (150, 200, 255)))
        for i, (label, path, col) in enumerate(saved):
            y = H - 22 - (len(saved) - 1 - i) * 20
            note = self.font.render(f"{label} SAVED  ->  {path}", True, col)
            self.screen.blit(note, note.get_rect(center=(W // 2, y)))

        pygame.display.flip()
        return clickables

    def render_pause(
        self,
        bgm_vol: int,
        sfx_vol: int,
    ) -> List[Tuple[pygame.Rect, str, Optional[str]]]:
        """인게임 일시정지 오버레이. 반환: clickables [(rect, action, value)]."""
        self._tick += 1
        W, H = self.W, self.H
        clickables: List[Tuple[pygame.Rect, str, Optional[str]]] = []

        self._draw_bg(0.0)

        if self._pause_ov is None:
            self._pause_ov = pygame.Surface((W, H), pygame.SRCALPHA)
            self._pause_ov.fill((0, 0, 0, 190))
        self.screen.blit(self._pause_ov, (0, 0))

        # 패널
        pw, ph = 460, 360
        px, py = W // 2 - pw // 2, H // 2 - ph // 2
        if not hasattr(self, "_pause_panel"):
            self._pause_panel: pygame.Surface = pygame.Surface((pw, ph), pygame.SRCALPHA)
            self._pause_panel.fill((14, 14, 16, 245))
        self.screen.blit(self._pause_panel, (px, py))
        pygame.draw.rect(self.screen, HAIRLINE, (px, py, pw, ph), 1, border_radius=14)

        # 제목
        ts = self.font_game_title.render("PAUSED", True, TEXT_PRIMARY)
        self.screen.blit(ts, ts.get_rect(center=(W // 2, py + 44)))
        pygame.draw.line(self.screen, RUNE_DIM, (px + 20, py + 74), (px + pw - 20, py + 74), 1)

        # RESUME 버튼
        btn_resume = pygame.Rect(W // 2 - 120, py + 84, 240, 50)
        self._draw_hero_button(btn_resume, "RESUME")
        clickables.append((btn_resume, "resume", None))

        # 볼륨 컨트롤 (BGM / SFX 2행)
        vol_rows = [
            ("BGM  VOL", bgm_vol, TEXT_PRIMARY, "vol_bgm_down", "vol_bgm_up"),
            ("SFX  VOL", sfx_vol, TEXT_PRIMARY, "vol_sfx_down", "vol_sfx_up"),
        ]
        for row_i, (label, vol, col, act_m, act_p) in enumerate(vol_rows):
            ry = py + 156 + row_i * 54

            lbl_s = self.font_game_tab.render(label, True, col)
            self.screen.blit(lbl_s, lbl_s.get_rect(midleft=(px + 36, ry + 15)))

            btn_m = pygame.Rect(px + pw - 142, ry + 4, 30, 26)
            pygame.draw.rect(self.screen, (28, 28, 32), btn_m, border_radius=5)
            pygame.draw.rect(self.screen, HAIRLINE, btn_m, 1, border_radius=5)
            ms = self.font_game_tab.render("-", True, col)
            self.screen.blit(ms, ms.get_rect(center=btn_m.center))
            clickables.append((btn_m, act_m, None))

            num_s = self.font_game_tab.render(str(vol), True, WHITE)
            self.screen.blit(num_s, num_s.get_rect(center=(px + pw - 92, ry + 17)))

            btn_p = pygame.Rect(px + pw - 56, ry + 4, 30, 26)
            pygame.draw.rect(self.screen, (28, 28, 32), btn_p, border_radius=5)
            pygame.draw.rect(self.screen, HAIRLINE, btn_p, 1, border_radius=5)
            ps = self.font_game_tab.render("+", True, col)
            self.screen.blit(ps, ps.get_rect(center=btn_p.center))
            clickables.append((btn_p, act_p, None))

        # 구분선
        pygame.draw.line(self.screen, RUNE_DIM, (px + 20, py + 276), (px + pw - 20, py + 276), 1)

        # EXIT TO MENU 버튼
        btn_exit = pygame.Rect(W // 2 - 120, py + 290, 240, 48)
        self._draw_button(btn_exit, "EXIT  TO  MENU", danger=True)
        clickables.append((btn_exit, "exit_menu", None))

        pygame.display.flip()
        return clickables

    # ── Background ─────────────────────────────────────────────────────────────

    def _draw_bg(self, player_offset_x: float = 0.0) -> None:
        W, H = self.W, self.H
        horizon = H // 2

        # 그라디언트는 정적 → 최초 1회만 생성 후 blit으로 재사용 (60fps × 720줄 → 1 blit)
        if self._bg_cache is None:
            self._bg_cache = pygame.Surface((W, H))
            for y in range(horizon):
                t = y / max(horizon, 1)
                pygame.draw.line(self._bg_cache, self._lerp_color(BG_TOP, BG_MID, t), (0, y), (W, y))
            for y in range(horizon, H):
                t = (y - horizon) / max(H - horizon, 1)
                pygame.draw.line(self._bg_cache, self._lerp_color(FLOOR_C, BG_BOT, t), (0, y), (W, y))
        self.screen.blit(self._bg_cache, (0, 0))

        # Horizon accent line
        pygame.draw.line(self.screen, RUNE_DIM, (0, horizon), (W, horizon), 1)

        # Parallax: vanishing point shifts slightly opposite to player movement
        vx_shift = int(-player_offset_x * W * 0.07)
        vx, vy = W // 2 + vx_shift, horizon

        # Perspective floor grid
        for i in range(1, 9):
            d = i / 9.0
            fy = int(horizon + (H - horizon) * d)
            spread = int(W * 0.5 * d)
            alpha = int(35 * (1.0 - d * 0.7))
            line_col = (alpha, alpha, alpha)
            pygame.draw.line(self.screen, line_col, (vx - spread, fy), (vx + spread, fy), 1)

        # Converging side lines (from vanishing point)
        for i in range(-5, 6):
            floor_x = W // 2 + i * (W // 10)
            pygame.draw.line(self.screen, (16, 16, 18), (vx, vy), (floor_x, H), 1)

        # Vanishing-point rune circle
        rune_r = int(55 + 7 * math.sin(self._tick * 0.04))
        rc = self._pulse_color((40, 40, 46), (95, 95, 105), self._tick, 70)
        pygame.draw.circle(self.screen, rc, (vx, vy), rune_r, 2)
        pygame.draw.circle(self.screen, rc, (vx, vy), max(1, rune_r - 18), 1)

        # Pillars (shift more than vanishing point — closer to viewer)
        pillar_shift = int(-player_offset_x * W * 0.13)
        for px in (W // 6 + pillar_shift, W * 5 // 6 + pillar_shift):
            self._draw_pillar(px, horizon, H)

    def _draw_pillar(self, cx: int, top_y: int, H: int) -> None:
        pw, bot_y = 16, H
        top_y = top_y - 80
        pygame.draw.rect(self.screen, (16, 16, 18), (cx - pw // 2, top_y, pw, bot_y - top_y))
        pygame.draw.rect(self.screen, RUNE_DIM,  (cx - pw // 2, top_y, pw, bot_y - top_y), 1)
        for k in range(3):
            dy = top_y + (bot_y - top_y) * (k + 1) // 4
            col = self._pulse_color(RUNE_DIM, RUNE_GLO, self._tick + k * 30, 80)
            pygame.draw.circle(self.screen, col, (cx, dy), 4)
            pygame.draw.circle(self.screen, col, (cx, dy), 6, 1)

    # ── Atmosphere (부유 재/먼지) ──────────────────────────────────────────────

    def _draw_atmosphere(self, player_offset_x: float = 0.0) -> None:
        """공기 중을 떠도는 재·먼지 입자 — 깊이감/현장감(2026 트렌드: volumetric ambience)."""
        W, H = self.W, self.H
        if not self._motes:
            for _ in range(46):
                self._motes.append({
                    "x": random.uniform(0, W),
                    "y": random.uniform(0, H),
                    "z": random.uniform(0.25, 1.0),          # 깊이(1=가까움)
                    "ph": random.uniform(0, math.tau),
                    "spd": random.uniform(4.0, 14.0),
                })
        for m in self._motes:
            m["y"] -= m["spd"] * m["z"] * 0.016
            m["ph"] += 0.03
            if m["y"] < -4:
                m["y"] = H + 4
                m["x"] = random.uniform(0, W)
            drift = math.sin(m["ph"]) * 9 * m["z"]
            px = int(m["x"] + drift - player_offset_x * W * 0.05 * m["z"])
            py = int(m["y"])
            if px < -6 or px > W + 6:
                continue
            z = m["z"]
            twk = 0.55 + 0.45 * math.sin(m["ph"] * 2.3)
            # 아래쪽은 따뜻한 잔불, 위쪽은 차가운 먼지
            warm = max(0.0, 1.0 - py / H)
            r = int((70 + 150 * warm) * z * twk)
            g = int((45 + 70 * warm) * z * twk)
            b = int((60 + 40 * (1 - warm)) * z * twk)
            rad = 1 if z < 0.55 else 2
            if rad == 2:
                pygame.draw.circle(self.screen, (r // 3, g // 3, b // 3), (px, py), 3)
            pygame.draw.circle(self.screen, (min(255, r), min(255, g), min(255, b)), (px, py), rad)

    # ── Cinematic color grade ─────────────────────────────────────────────────

    def _draw_grade(self) -> None:
        """비네트 + 스플릿톤 + 미세 그레인 — 필믹 컬러 그레이드(1 blit + 경량 그레인)."""
        W, H = self.W, self.H
        if self._grade_cache is None:
            g = pygame.Surface((W, H), pygame.SRCALPHA)
            # 스플릿톤: 상단 따뜻하게 / 하단 차갑게 (아주 옅게)
            for y in range(0, H, 2):
                t = y / H
                warm = max(0.0, 1.0 - t * 1.6)
                cool = max(0.0, (t - 0.4) * 1.4)
                col = (int(30 * warm), int(10 * warm), int(24 * cool), 14)
                pygame.draw.line(g, col, (0, y), (W, y), 2)
            # 비네트: 가장자리를 점진적으로 어둡게 (기존보다 살짝 더 깊게 —
            # 아케이드 포스터처럼 화면 전체가 고르게 밝은 느낌을 줄인다)
            steps = 90
            for i in range(steps):
                # 가장자리(i=0)가 가장 어둡고 안쪽으로 갈수록 0으로 사라진다.
                a = int(150 * (1.0 - i / steps) ** 2.3)
                pygame.draw.rect(g, (0, 0, 0, a), (i, i, W - i * 2, H - i * 2), 1)
            self._grade_cache = g
            # 그레인 타일 6장 미리 생성(128×128) → 매 프레임 1장 골라 타일 blit
            for _ in range(6):
                tile = pygame.Surface((128, 128), pygame.SRCALPHA)
                for _p in range(360):
                    tx, ty = random.randint(0, 127), random.randint(0, 127)
                    if random.random() < 0.5:
                        tile.set_at((tx, ty), (255, 255, 255, 10))
                    else:
                        tile.set_at((tx, ty), (0, 0, 0, 14))
                self._grain_tiles.append(tile)
        self.screen.blit(self._grade_cache, (0, 0))
        # 필름 그레인 — 캐시 타일을 프레임마다 위상 이동하며 타일링
        tile = self._grain_tiles[self._tick % len(self._grain_tiles)]
        ox = -(self._tick * 7 % 128)
        oy = -(self._tick * 3 % 128)
        for gy in range(oy, H, 128):
            for gx in range(ox, W, 128):
                self.screen.blit(tile, (gx, gy))

    # ── Boss ───────────────────────────────────────────────────────────────────

    def _draw_boss(
        self,
        hp_ratio: float,
        effects: List[dict],
        player_offset_x: float = 0.0,
        boss_name: str = "ARCANE BOSS",
        accent: Optional[Tuple[int, int, int]] = None,
    ) -> None:
        W, H = self.W, self.H
        enraged = hp_ratio <= 0.35

        # ── 애니메이션 상태 감지 ─────────────────────────────────────────────
        # 공격 판정: 보스 투사체가 수명 35% 이내 (막 발사됨)
        is_attacking = any(
            e.get("type") == "proj" and e.get("origin") == "boss"
            and e.get("elapsed", 0) / max(e.get("dur", 1), 1) < 0.35
            for e in effects
        )
        # 피격 판정: hp_ratio가 전 프레임보다 감소
        if hp_ratio < self._boss_prev_hp_ratio - 0.004:
            self._boss_hit_tick = self._tick
        self._boss_prev_hp_ratio = hp_ratio
        hit_age   = self._tick - self._boss_hit_tick
        is_hit    = hit_age < 14

        # ── 위치 + 부유 애니메이션 ──────────────────────────────────────────
        float_y   = int(14 * math.sin(self._tick * 0.038))
        float_x   = int(6  * math.sin(self._tick * 0.022))
        boss_shift = int(-player_offset_x * W * 0.03)
        atk_lean  = -12 if is_attacking else 0
        recoil    = (min(hit_age, 4) * 4) if is_hit else 0

        cx = W // 2 + boss_shift + float_x + atk_lean + recoil
        cy = H // 2 - 28 + float_y
        R  = int(72 * (1.08 if is_attacking else 1.0))

        # ── 지면 그림자 ──────────────────────────────────────────────────────
        if self._boss_sh_r != R:
            self._boss_sh_surf = pygame.Surface((R * 3, 28), pygame.SRCALPHA)
            pygame.draw.ellipse(self._boss_sh_surf, (0, 0, 0, 55), (0, 0, R * 3, 28))
            self._boss_sh_r = R
        self.screen.blit(self._boss_sh_surf, (cx - R * 3 // 2, cy + R - 8))

        # ── 날개 (박쥐형 막 — 몸통 스케일감·실루엣 확보, 가장 뒤에 배치) ─────
        wing_flap = math.sin(self._tick * 0.045)
        wing_col  = (10, 3, 8)
        wing_rim  = (120, 30, 40) if not enraged else (200, 60, 20)
        for side in (-1, 1):
            wsx = cx + side * 30
            wsy = cy + int(R * 0.55)
            spread = (58 if is_attacking else 40) + 10 * wing_flap * side * -1
            tip_x  = wsx + side * (R * 1.7 + spread)
            tip_y  = wsy - int(R * 0.65) - 14 * wing_flap
            mid_x  = wsx + side * (R * 1.05)
            mid_y  = wsy + int(R * 0.15)
            wing_pts = [
                (wsx, wsy - int(R * 0.25)),
                (tip_x, tip_y),
                (wsx + side * (R * 1.3), wsy - int(R * 0.05)),
                (mid_x, mid_y),
                (wsx + side * (R * 0.6), wsy + int(R * 0.55)),
                (wsx, wsy + int(R * 0.35)),
            ]
            pygame.draw.polygon(self.screen, wing_col, wing_pts)
            pygame.draw.polygon(self.screen, wing_rim, wing_pts, 2)
            # 날개 뼈대(막 힘줄)
            for k in range(3):
                bt = (k + 1) / 4.0
                bone_x = int(wsx + (tip_x - wsx) * bt)
                bone_y = int(wsy - int(R * 0.1) + (tip_y - wsy + int(R * 0.1)) * bt)
                pygame.draw.line(self.screen, wing_rim, (wsx, wsy - int(R * 0.1)), (bone_x, bone_y), 1)

        # ── 클로크 / 로브 (흔들림 애니메이션) ───────────────────────────────
        csway = int(5 * math.sin(self._tick * 0.028))
        cloak_pts = [
            (cx - 60 + csway, cy + 58),
            (cx - 92 + csway, cy + 112), (cx - 54, cy + 124),
            (cx,              cy + 130),
            (cx + 54,         cy + 124), (cx + 92 - csway, cy + 112),
            (cx + 60 - csway, cy + 58),
        ]
        pygame.draw.polygon(self.screen, (6, 2, 14), cloak_pts)
        pygame.draw.polygon(self.screen, (52, 18, 72), cloak_pts, 2)
        # 클로크 내부 음영선
        for k in range(5):
            lx  = cx - 55 + k * 22 + csway * (1 - k * 0.35)
            lx2 = lx + int(3 * math.sin(self._tick * 0.03 + k))
            pygame.draw.line(self.screen, (14, 6, 24), (int(lx), cy + 62), (int(lx2), cy + 122), 1)

        # ── 바깥 오오라 ─────────────────────────────────────────────────────
        if enraged:
            aura_r   = int(R + 30 + 18 * math.sin(self._tick * 0.09))
            aura_col = self._pulse_color((200, 20, 0), (255, 80, 0), self._tick, 28)
        else:
            aura_r   = int(R + 16 + 12 * math.sin(self._tick * 0.05))
            aura_col = self._pulse_color((80, 10, 10), (190, 45, 45), self._tick, 55)
        if is_attacking:
            aura_r   += 22
            aura_col  = (min(255, aura_col[0] + 55), aura_col[1], aura_col[2])
        self._draw_glow(cx, cy, aura_r, aura_col, layers=9)

        # ── 3D 구체 몸체 (상-좌 광원, 레이어드 원으로 구현) ─────────────────
        # 가장 어두운 외곽 → 상-좌 쪽으로 offset된 밝은 레이어 = 입체감
        # 채도를 낮추고 명암 대비를 키운 "그림다크" 팔레트 — 원색 오렌지/빨강
        # 대신 탁한 피·녹 계열로 눌러 아케이드 토이보다 짐승 가죽에 가깝게.
        layers_3d = [
            (0,   0,   R,      (14,  2,  3)),
            (-4, -4,   R - 9,  (72,  16, 16) if not enraged else (120, 20,  9)),
            (-10,-10,  R - 21, (112, 32, 20) if not enraged else (188, 48, 13)),
            (-16,-17,  R - 35, (148, 52, 33) if not enraged else (232, 78, 20)),
            (-21,-23,  R - 49, (176, 78, 48) if not enraged else (255,112, 34)),
        ]
        for ox, oy, lr, lc in layers_3d:
            if lr > 0:
                fc = (255, 240, 210) if is_hit and lr == R - 49 else lc
                pygame.draw.circle(self.screen, fc, (cx + ox, cy + oy), lr)

        # ── 표피하 산란(subsurface) 코어 — 느리게 호흡하는 내부 발광 ───────────
        breathe = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self._tick * 0.03))
        ss_r = int(R * (0.42 + 0.10 * breathe))
        ss_col = aura_col if enraged else (int(120 + 90 * breathe), int(30 + 20 * breathe), 24)
        ss = pygame.Surface((ss_r * 2, ss_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(ss, (*ss_col, int(70 + 60 * breathe)), (ss_r, ss_r), ss_r)
        pygame.draw.circle(ss, (*ss_col, int(40 + 40 * breathe)), (ss_r, ss_r), int(ss_r * 0.6))
        self.screen.blit(ss, (cx - ss_r - 14, cy - ss_r - 16), special_flags=pygame.BLEND_RGBA_ADD)

        # 외곽 림 라이트 (뒷면 역광) — 채도를 낮춰 플라스틱 토이 느낌을 줄임
        if enraged:
            rim_c = self._pulse_color((190, 60, 10), (235, 130, 20), self._tick, 20)
        else:
            rim_c = (120, 42, 42)
        pygame.draw.circle(self.screen, rim_c, (cx, cy), R, 3)

        # 반사광 하이라이트 (소프트, 은은하게 — 광택 대신 젖은 가죽 질감)
        if self._boss_hl_r != R:
            self._boss_hl_surf = pygame.Surface((R, R), pygame.SRCALPHA)
            pygame.draw.circle(self._boss_hl_surf, (210, 160, 130, 55),
                               (R // 2 - 9, R // 2 - 11), R // 3)
            self._boss_hl_r = R
        self.screen.blit(self._boss_hl_surf, (cx - R // 2 - 9, cy - R // 2 - 11))
        # 정반사 점 (작고 은은하게 — 만화적 반짝임 대신 젖은 표면 느낌)
        pygame.draw.circle(self.screen, (200, 160, 140), (cx - 26, cy - 30), 5)
        pygame.draw.circle(self.screen, (235, 210, 195), (cx - 28, cy - 32), 2)

        # ── 턱 (완전한 구체 실루엣을 깨서 해골/얼굴 형태로) ─────────────────
        jaw_col = (150, 34, 20) if not enraged else (200, 48, 10)
        jaw_pts = [
            (cx - int(R * 0.58), cy + int(R * 0.42)),
            (cx - int(R * 0.24), cy + int(R * 1.08)),
            (cx,                 cy + int(R * 1.22)),
            (cx + int(R * 0.24), cy + int(R * 1.08)),
            (cx + int(R * 0.58), cy + int(R * 0.42)),
        ]
        pygame.draw.polygon(self.screen, jaw_col, jaw_pts)
        pygame.draw.polygon(self.screen, (60, 12, 8), jaw_pts, 2)

        # ── 눈썹 (찌푸린 인상 — 눈만 있는 밋밋함 제거) ───────────────────────
        for side in (-1, 1):
            bx0 = cx + side * 36
            by0 = cy - 32
            bx1 = cx + side * 10
            by1 = cy - 26
            pygame.draw.polygon(self.screen, (24, 3, 3), [
                (bx0, by0 - 6), (bx1, by1 - 3), (bx1, by1 + 5), (bx0, by0 + 4),
            ])

        # ── 뿔 (메인 2개 + 보조 2개) ────────────────────────────────────────
        hswing = int(5 * math.sin(self._tick * 0.04)) if is_attacking else 0
        horn_col, horn_rim_c = (78, 10, 10), (195, 65, 48)
        for side, twist in ((-1, -9), (1, 9)):
            hbx  = cx + side * 23
            hby  = cy - R + 10
            htx  = cx + side * (40 + twist + hswing * side)
            hty  = cy - R - 54
            mid  = (hbx + side * 12, (hby + hty) // 2 - 10)
            pts  = [(hbx - 10, hby), mid, (htx, hty), (htx + side * 3, hty),
                    (mid[0] + side * 10, mid[1] + 4), (hbx + 10, hby)]
            pygame.draw.polygon(self.screen, horn_col, pts)
            pygame.draw.polygon(self.screen, horn_rim_c, pts, 1)
            self._draw_glow(htx, hty, 5, horn_rim_c, layers=2)
        # 보조 뿔 (작은 측면)
        for side in (-1, 1):
            sx, sy = cx + side * 54, cy - R + 18
            ex, ey = cx + side * 70, cy - R - 6
            pygame.draw.polygon(self.screen, (58, 8, 8),
                                [(sx - 5, sy), (ex, ey), (sx + 5, sy)])
            pygame.draw.polygon(self.screen, (130, 38, 28),
                                [(sx - 5, sy), (ex, ey), (sx + 5, sy)], 1)

        # ── 아케인 룬 마킹 ────────────────────────────────────────────────────
        rune_a1  = self._tick * 0.020
        rune_a2  = -self._tick * 0.030 + math.pi / 6
        rune_col = self._pulse_color((200, 70, 60), (255, 155, 105), self._tick, 55)
        for i in range(6):
            a  = rune_a1 + i * math.pi / 3
            rx = cx + int(50 * math.cos(a))
            ry = cy + int(50 * math.sin(a))
            pygame.draw.circle(self.screen, rune_col, (rx, ry), 4)
            pygame.draw.line(self.screen, rune_col, (cx, cy), (rx, ry), 1)
        for i in range(4):
            a  = rune_a2 + i * math.pi / 2
            rx = cx + int(28 * math.cos(a))
            ry = cy + int(28 * math.sin(a))
            pygame.draw.circle(self.screen, (218, 108, 78), (rx, ry), 3)

        # ── 눈 (플레이어 방향 추적) ───────────────────────────────────────────
        look_dx = int(player_offset_x * 5)
        for ex_off in (-22, 22):
            ex_abs = cx + ex_off + look_dx // 2
            ey_abs = cy - 14
            pygame.draw.circle(self.screen, (0, 0, 0), (ex_abs, ey_abs), 13)
            # 만화적인 원색 노랑 대신 잉걸불처럼 탁한 호박색 — 더 섬뜩하게
            if is_hit:
                iris_c = (235, 210, 110)
            elif enraged:
                iris_c = self._pulse_color((205, 70, 10), (235, 150, 15), self._tick, 20)
            else:
                iris_c = self._pulse_color((190, 60, 30), (215, 150, 45), self._tick, 50)
            pygame.draw.circle(self.screen, iris_c, (ex_abs, ey_abs), 8)
            p_off = max(-3, min(3, look_dx // 3))
            pupil = [
                (ex_abs + p_off,     ey_abs - 6),
                (ex_abs + p_off + 2, ey_abs),
                (ex_abs + p_off,     ey_abs + 6),
                (ex_abs + p_off - 2, ey_abs),
            ]
            pygame.draw.polygon(self.screen, (0, 0, 0), pupil)
            pygame.draw.circle(self.screen, (200, 190, 160), (ex_abs - 4 + p_off, ey_abs - 4), 2)

        # ── 입 (공격 모션: 열림) ─────────────────────────────────────────────
        if is_attacking:
            pygame.draw.ellipse(self.screen, (10, 0, 0), (cx - 30, cy + 8, 60, 26))
            pygame.draw.arc(self.screen, (240, 80, 40),
                            (cx - 30, cy + 8, 60, 26), math.pi, 2 * math.pi, 3)
            for i in range(5):
                tx = cx - 22 + i * 11
                pygame.draw.polygon(self.screen, BONE,
                                    [(tx, cy + 16), (tx + 5, cy + 16), (tx + 2, cy + 22)])
            ec = self._pulse_color((255, 60, 0), (255, 200, 100), self._tick, 12)
            pygame.draw.ellipse(self.screen, ec, (cx - 14, cy + 24, 28, 10))
        else:
            pygame.draw.arc(self.screen, (240, 80, 40),
                            (cx - 32, cy + 6, 64, 26), math.pi, 2 * math.pi, 3)
            for i in range(5):
                tx = cx - 24 + i * 12
                th = 11 if (enraged and i % 2 == 0) else 7
                pygame.draw.polygon(self.screen, BONE,
                                    [(tx, cy + 16), (tx + 6, cy + 16), (tx + 3, cy + 16 + th)])

        # ── 어깨·팔 (머리만 떠 있지 않도록 몸통 매스를 붙임 — 얼굴을 다 그린
        #    뒤에 그려야 구체/오오라에 덮이지 않고 실제로 보인다) ────────────
        shoulder_w = R * 1.5
        shoulder_y = cy + int(R * 0.62)
        shoulder_pts = [
            (cx - shoulder_w * 0.50, shoulder_y + 46),
            (cx - shoulder_w * 0.64, shoulder_y - 2),
            (cx - shoulder_w * 0.30, shoulder_y - 30),
            (cx - shoulder_w * 0.14, shoulder_y + 52),
            (cx + shoulder_w * 0.14, shoulder_y + 52),
            (cx + shoulder_w * 0.30, shoulder_y - 30),
            (cx + shoulder_w * 0.64, shoulder_y - 2),
            (cx + shoulder_w * 0.50, shoulder_y + 46),
        ]
        pygame.draw.polygon(self.screen, (16, 5, 10), shoulder_pts)
        pygame.draw.polygon(self.screen, (66, 22, 26), shoulder_pts, 2)
        # 견갑 돌기(pauldron spike)
        for side in (-1, 1):
            spx = cx + side * shoulder_w * 0.56
            spy = shoulder_y - 6
            pygame.draw.polygon(self.screen, (74, 16, 16), [
                (spx - 9 * side, spy + 12), (spx, spy - 26), (spx + 15 * side, spy + 8),
            ])
            pygame.draw.polygon(self.screen, (150, 45, 35), [
                (spx - 9 * side, spy + 12), (spx, spy - 26), (spx + 15 * side, spy + 8),
            ], 1)

        # 팔 (공격 시 앞으로 뻗는 포즈로 전환)
        reach = 1.0 if is_attacking else 0.0
        arm_dark, arm_mid = (18, 4, 4), (110, 26, 24)
        for side in (-1, 1):
            shx, shy = cx + side * shoulder_w * 0.58, shoulder_y - 2
            ebx = shx + side * (24 + 16 * reach)
            eby = shy + 44 + int(6 * math.sin(self._tick * 0.05 + side))
            hdx = ebx + side * (14 - 38 * reach)
            hdy = eby + 40 - 22 * reach
            pygame.draw.line(self.screen, arm_dark, (shx, shy), (ebx, eby), 17)
            pygame.draw.line(self.screen, arm_mid,  (shx, shy), (ebx, eby), 12)
            pygame.draw.line(self.screen, arm_dark, (ebx, eby), (hdx, hdy), 14)
            pygame.draw.line(self.screen, arm_mid,  (ebx, eby), (hdx, hdy), 10)
            pygame.draw.circle(self.screen, arm_mid, (int(hdx), int(hdy)), 8)
            # 발톱 3개
            base_ang = math.atan2(hdy - eby, hdx - ebx)
            for k in range(3):
                cang = base_ang + (k - 1) * 0.5
                clx = hdx + math.cos(cang) * 22
                cly = hdy + math.sin(cang) * 22
                pygame.draw.line(self.screen, (225, 220, 205), (hdx, hdy), (clx, cly), 3)

        # ── 에너지 촉수 ─────────────────────────────────────────────────────
        tc_count = 6 if enraged else 4
        if is_attacking:
            tc_count += 2
        for i in range(tc_count):
            base_a = self._tick * 0.038 + i * (math.pi * 2 / tc_count)
            for j in range(12):
                jt   = j / 12.0
                ja   = base_a + math.sin(jt * math.pi * 2 + self._tick * 0.12) * 0.65
                tx_d = cx + int((R + 8 + 46 * jt) * math.cos(ja))
                ty_d = cy + int((R + 8 + 46 * jt) * math.sin(ja))
                fr   = max(1, 4 - j // 3)
                fc_t = tuple(int(c * (1.0 - jt * 0.85)) for c in aura_col)
                pygame.draw.circle(self.screen, fc_t, (tx_d, ty_d), fr)  # type: ignore

        # ── 상승하는 잔불/재 (열원 현장감) ─────────────────────────────────────
        ash_n = 14 if enraged else 9
        for i in range(ash_n):
            life = ((self._tick * 1.7 + i * 37) % 90) / 90.0        # 0→1 반복
            ax = cx + int((i * 53 % (R * 2)) - R + 10 * math.sin(self._tick * 0.05 + i))
            ay = cy + int(R * 0.4 - life * (R * 1.9))
            fade = 1.0 - life
            ec = (int(255 * fade), int((120 if enraged else 70) * fade), int(20 * fade))
            pygame.draw.circle(self.screen, ec, (ax, ay), 1 if life > 0.5 else 2)

        # ── 피격 충격파 링 ────────────────────────────────────────────────────
        if is_hit:
            fr_val = R + 14 + hit_age * 7
            fa     = max(0, int(210 * (1.0 - hit_age / 14.0)))
            if fa > 0:
                fs = pygame.Surface((fr_val * 2 + 6, fr_val * 2 + 6), pygame.SRCALPHA)
                pygame.draw.circle(fs, (255, 255, 255, fa),
                                   (fr_val + 3, fr_val + 3), fr_val, 5)
                self.screen.blit(fs, (cx - fr_val - 3, cy - fr_val - 3))

        # ── 공격 플래시 링 ────────────────────────────────────────────────────
        if is_attacking:
            atk_c = self._pulse_color((255, 100, 0), (255, 230, 0), self._tick, 8)
            pygame.draw.circle(self.screen, atk_c, (cx, cy), R + 8, 5)

        # ── 보스별 오라 링(팔레트 배리언트) ──────────────────────────────────
        # accent가 있으면 실루엣 "바깥"에 얇은 원소색 링 3겹을 두른다. 이전에는
        # SRCALPHA 표면 + BLEND_RGBA_ADD로 그라디언트 도넛을 만들었는데, 알파
        # 채널이 기대만큼 반영되지 않아(가산 블렌드가 알파를 무시) 안쪽까지
        # 거의 불투명하게 덮여 보스가 "그냥 원"처럼 보이는 버그가 났다.
        # 이 코드베이스의 다른 링 이펙트(피격 링/공격 플래시 링 등)와 동일하게
        # — 얇은 stroke만 그려 실루엣을 절대 가리지 않는, 검증된 방식으로 통일.
        if accent is not None:
            base_r = R + 22
            for k in range(3):
                rr = base_r + k * 13 + int(4 * math.sin(self._tick * 0.06 + k * 1.7))
                fade = 1.0 - k * 0.3
                ring_col = tuple(max(0, min(255, int(c * fade))) for c in accent)
                pygame.draw.circle(self.screen, ring_col, (cx, cy), rr, 2)

        # ── HP 바 ─────────────────────────────────────────────────────────────
        bw, bh = 200, 14
        bx = cx - bw // 2
        by = cy - R - 34
        pygame.draw.rect(self.screen, (22, 4, 4),   (bx - 2, by - 2, bw + 4, bh + 4), border_radius=5)
        pygame.draw.rect(self.screen, (38, 14, 14),  (bx, by, bw, bh), border_radius=5)
        if int(bw * hp_ratio) > 0:
            fill_col = self._pulse_color((220, 30, 30), (255, 110, 0), self._tick, 22) \
                if enraged else self._lerp_color((220, 30, 30), GOLD, hp_ratio)
            pygame.draw.rect(self.screen, fill_col,
                             (bx, by, int(bw * hp_ratio), bh), border_radius=5)
        pygame.draw.rect(self.screen, GREY, (bx, by, bw, bh), 1, border_radius=5)
        lbl_txt = f"!! {boss_name} — ENRAGED !!" if enraged else boss_name
        lbl_col = (255, 110, 0) if enraged else GREY
        hp_lbl  = self.font.render(lbl_txt, True, lbl_col)
        self.screen.blit(hp_lbl, hp_lbl.get_rect(center=(cx, by - 14)))

    # ── Wand ───────────────────────────────────────────────────────────────────

    def _draw_wand(self, player_offset_x: float = 0.0) -> None:
        W, H = self.W, self.H
        wand_shift = int(player_offset_x * W * self.WAND_SWAY_GAIN)

        # ── 호흡 + 미세 흔들림 애니메이션 ──────────────────────────────────
        bob   = int(math.sin(self._tick * 0.045) * 5)
        sway  = int(math.sin(self._tick * 0.019) * 2)
        wx_b  = int(W * 0.82) + wand_shift + sway
        wy_b  = H + 12 + bob // 4
        wx_t  = int(W * self.WAND_FX) + wand_shift + sway // 2
        wy_t  = int(H * self.WAND_FY) + bob

        # ── 로브 소매 (전완부) ──────────────────────────────────────────────
        slv_pts = [
            (W,        wy_b + 22),
            (wx_b + 52, wy_b + 20),
            (wx_b + 12, wy_b - 22),
            (wx_b - 42, wy_b - 32),
            (W,        wy_b - 14),
        ]
        pygame.draw.polygon(self.screen, (20, 10, 38), slv_pts)   # 어두운 보라색 로브
        pygame.draw.polygon(self.screen, (52, 28, 88), slv_pts, 2)
        # 소매 주름선
        for k in range(4):
            fx0 = wx_b + 44 - k * 22
            fy0 = wy_b + 14
            fy1 = wy_b - 22
            sc  = (22 + k * 8, 12 + k * 4, 40 + k * 12)
            pygame.draw.line(self.screen, sc, (fx0, fy0), (fx0 - 8, fy1), 1)

        # 소매 커프 (장식 밴드)
        cuff_pts = [
            (wx_b - 40, wy_b - 30), (wx_b + 18, wy_b - 18),
            (wx_b + 22, wy_b - 6),  (wx_b - 42, wy_b - 18),
        ]
        pygame.draw.polygon(self.screen, (58, 32, 98), cuff_pts)
        pygame.draw.polygon(self.screen, (108, 68, 158), cuff_pts, 1)
        for k in range(3):
            gx = wx_b - 20 + k * 16
            gc = self._pulse_color((100, 60, 200), (180, 130, 255), self._tick + k * 22, 60)
            pygame.draw.circle(self.screen, gc, (gx, wy_b - 22), 3)

        # ── 손 그립 기준점 (실제로 완드를 감아쥘 수 있도록 샤프트 위에 배치) ─
        skin     = (196, 150, 110)
        skin_mid = (175, 128,  88)
        skin_shd = (138,  96,  66)
        hx, hy   = wx_b - 22, wy_b - 36 + bob // 4

        # ── 완드 샤프트 (레이어드 목재 + 하이라이트) ─────────────────────────
        pygame.draw.line(self.screen, (22, 12, 4),   (wx_b, wy_b), (wx_t, wy_t), 13)  # 그림자
        pygame.draw.line(self.screen, (50, 32, 12),  (wx_b, wy_b), (wx_t, wy_t), 10)  # 베이스
        pygame.draw.line(self.screen, (74, 50, 20),  (wx_b - 2, wy_b - 3), (wx_t - 2, wy_t - 3), 6)
        pygame.draw.line(self.screen, (102, 72, 32), (wx_b - 3, wy_b - 5), (wx_t - 3, wy_t - 5), 3)
        pygame.draw.line(self.screen, (138, 102, 52),(wx_b - 4, wy_b - 6), (wx_t - 4, wy_t - 6), 1)
        # 나뭇결 (짧은 사선)
        for k in range(6):
            gt = 0.1 + k * 0.14
            gx = int(wx_b + (wx_t - wx_b) * gt)
            gy = int(wy_b + (wy_t - wy_b) * gt)
            pygame.draw.line(self.screen, (60, 40, 14), (gx, gy), (gx - 3, gy + 1), 1)
        # 이동하는 정반사 하이라이트 (광택 래커 느낌 — 표면 재질감)
        st = 0.5 + 0.5 * math.sin(self._tick * 0.08)
        sh0 = st * 0.7
        sgx0 = int(wx_b + (wx_t - wx_b) * sh0)
        sgy0 = int(wy_b + (wy_t - wy_b) * sh0)
        sgx1 = int(wx_b + (wx_t - wx_b) * (sh0 + 0.16))
        sgy1 = int(wy_b + (wy_t - wy_b) * (sh0 + 0.16))
        pygame.draw.line(self.screen, (180, 150, 90), (sgx0 - 4, sgy0 - 6), (sgx1 - 4, sgy1 - 6), 2)
        pygame.draw.line(self.screen, (245, 225, 175), (sgx0 - 4, sgy0 - 6), (sgx1 - 4, sgy1 - 6), 1)

        # ── 메탈 밴드 ────────────────────────────────────────────────────────
        for k in range(3):
            bt  = 0.22 + k * 0.24
            bx_ = int(wx_b + (wx_t - wx_b) * bt)
            by_ = int(wy_b + (wy_t - wy_b) * bt)
            bc  = self._pulse_color((80, 70, 130), (150, 135, 210), self._tick + k * 24, 80)
            pygame.draw.circle(self.screen, (28, 18, 58), (bx_, by_), 9, 5)
            pygame.draw.circle(self.screen, bc,           (bx_, by_), 8, 2)
            pygame.draw.circle(self.screen, (185, 165, 225), (bx_ - 2, by_ - 2), 2)

        # ── 젬 (8각형 다이아몬드) ────────────────────────────────────────────
        gem_col  = self._pulse_color((90,  70, 220), (190, 150, 255), self._tick, 50)
        gem_core = self._pulse_color((150, 120, 255), (220, 200, 255), self._tick, 38)
        gem_hot  = self._pulse_color((200, 180, 255), (255, 245, 255), self._tick, 28)
        gr = 12

        self._draw_glow(wx_t, wy_t, gr + 20, gem_col, layers=10)

        # 8각형 외곽
        gem_pts = [
            (wx_t,           wy_t - gr),
            (wx_t + gr // 2, wy_t - gr // 2),
            (wx_t + gr,      wy_t),
            (wx_t + gr // 2, wy_t + gr // 2),
            (wx_t,           wy_t + gr),
            (wx_t - gr // 2, wy_t + gr // 2),
            (wx_t - gr,      wy_t),
            (wx_t - gr // 2, wy_t - gr // 2),
        ]
        pygame.draw.polygon(self.screen, gem_col, gem_pts)
        # 내부 8각형 (페이셋)
        igem = [
            (int(wx_t + (px - wx_t) * 0.52), int(wy_t + (py - wy_t) * 0.52))
            for px, py in gem_pts
        ]
        pygame.draw.polygon(self.screen, gem_core, igem)
        # 내부 굴절 카우스틱 (움직이는 빛줄기)
        cau = math.sin(self._tick * 0.13)
        pygame.draw.line(self.screen, gem_hot,
                         (int(wx_t - gr * 0.6), int(wy_t + gr * 0.5 * cau)),
                         (int(wx_t + gr * 0.6), int(wy_t - gr * 0.5 * cau)), 1)
        # 페이셋 라인
        for i, gp in enumerate(gem_pts):
            pygame.draw.line(self.screen, gem_hot, gp, igem[i], 1)
        # 프레넬 림 (가장자리 밝은 얇은 테두리)
        pygame.draw.polygon(self.screen, (235, 225, 255), gem_pts, 1)
        pygame.draw.polygon(self.screen, gem_hot, gem_pts, 1)
        # 젬 하이라이트
        pygame.draw.circle(self.screen, (255, 255, 255), (wx_t - 4, wy_t - 5), 3)
        pygame.draw.circle(self.screen, (210, 190, 255), (wx_t + 3, wy_t + 3), 2)
        # 젬이 손을 비추는 반사광 (접촉 바운스 라이트)
        bounce = tuple(min(255, int(c * 0.5)) for c in gem_col)
        self._draw_glow(hx - 2, hy - 4, 16, bounce, layers=3)

        # ── 정방향 궤도 파티클 (5개) ─────────────────────────────────────────
        for k in range(5):
            a   = self._tick * 0.11 + k * math.pi * 2 / 5
            opx = wx_t + int(17 * math.cos(a))
            opy = wy_t + int(11 * math.sin(a))
            oc  = self._pulse_color(gem_col, WHITE, self._tick + k * 14, 22)
            pygame.draw.circle(self.screen, oc, (opx, opy), 2)
        # 역방향 소형 궤도 파티클 (3개)
        for k in range(3):
            a   = -self._tick * 0.18 + k * math.pi * 2 / 3
            opx = wx_t + int(10 * math.cos(a))
            opy = wy_t + int(7  * math.sin(a))
            pygame.draw.circle(self.screen, gem_hot, (opx, opy), 1)

        # ── 손목 브레이서 (가죽 밴드 — 손목이 허공에 떠 보이지 않도록) ───────
        wr_x = int((hx + wx_b) / 2) + 6
        wr_y = int((hy + wy_b) / 2) - 2
        pygame.draw.ellipse(self.screen, (46, 34, 20), (wr_x - 27, wr_y - 15, 54, 28))
        pygame.draw.ellipse(self.screen, (86, 64, 36), (wr_x - 27, wr_y - 15, 54, 28), 2)
        pygame.draw.circle(self.screen, (150, 128, 86), (wr_x, wr_y), 3)

        # ── 손 (완드 방향을 감싸 쥐는 그립 — 샤프트 위에 손가락이 겹치도록) ──
        # 팜 (3레이어로 입체감)
        pygame.draw.ellipse(self.screen, skin_shd, (hx - 22, hy - 16, 50, 40))
        pygame.draw.ellipse(self.screen, skin_mid, (hx - 20, hy - 15, 47, 37))
        pygame.draw.ellipse(self.screen, skin,     (hx - 18, hy - 13, 43, 33))
        # 팜 하이라이트
        pygame.draw.ellipse(self.screen, (216, 170, 130), (hx - 10, hy - 12, 18, 12))
        # 손등 주름
        pygame.draw.line(self.screen, skin_shd, (hx - 16, hy - 11), (hx + 16, hy - 11), 2)
        pygame.draw.line(self.screen, skin_shd, (hx - 12, hy - 6),  (hx + 12, hy - 6),  1)

        # 완드 축 방향으로 감아쥐는 손가락 (4개 — 마디 2개씩, 그립감 강화)
        wang = math.atan2(wy_t - hy, wx_t - hx)
        f_data = [(-0.55, 1), (-0.20, 0), (0.10, 1), (0.42, 0)]
        for fi, (ang_off, bend) in enumerate(f_data):
            fx, fy = hx, hy - 6
            a1   = wang + ang_off
            seg1 = 13 + bend * 2
            ex1  = fx + math.cos(a1) * seg1
            ey1  = fy + math.sin(a1) * seg1
            # 근위 마디 (샤프트를 향해 뻗음)
            pygame.draw.line(self.screen, skin_shd, (fx, fy), (ex1, ey1), 6)
            pygame.draw.line(self.screen, skin_mid, (fx, fy), (ex1, ey1), 5)
            pygame.draw.line(self.screen, skin,     (fx, fy), (ex1, ey1), 3)
            # 원위 마디 (샤프트를 감싸며 안쪽으로 말림)
            a2  = a1 + 0.55
            ex2 = ex1 + math.cos(a2) * 8
            ey2 = ey1 + math.sin(a2) * 8
            pygame.draw.line(self.screen, skin_shd, (ex1, ey1), (ex2, ey2), 5)
            pygame.draw.line(self.screen, skin_mid, (ex1, ey1), (ex2, ey2), 4)
            pygame.draw.line(self.screen, skin,     (ex1, ey1), (ex2, ey2), 2)
            # 손끝 + 손톱
            pygame.draw.circle(self.screen, skin_mid, (int(ex2), int(ey2)), 4)
            pygame.draw.circle(self.screen, skin,     (int(ex2), int(ey2)), 3)
            pygame.draw.circle(self.screen, (216, 175, 148), (int(ex2), int(ey2) - 1), 1)

        # 엄지 (반대쪽에서 감아 그립을 완성)
        tang = wang - 2.35
        tx1  = hx + math.cos(tang) * 15
        ty1  = hy + math.sin(tang) * 15
        pygame.draw.line(self.screen, skin_shd, (hx - 4, hy - 2), (tx1, ty1), 7)
        pygame.draw.line(self.screen, skin_mid, (hx - 4, hy - 2), (tx1, ty1), 6)
        pygame.draw.line(self.screen, skin,     (hx - 4, hy - 2), (tx1, ty1), 4)
        pygame.draw.circle(self.screen, skin_mid, (int(tx1), int(ty1)), 5)
        pygame.draw.circle(self.screen, skin,     (int(tx1), int(ty1)), 4)

    # ── Effects ────────────────────────────────────────────────────────────────

    def _draw_effects(self, effects: List[dict], player_offset_x: float = 0.0) -> None:
        W, H = self.W, self.H
        boss_shift  = int(-player_offset_x * W * 0.03)
        wand_pt     = self.wand_tip(player_offset_x)
        boss_center = (W // 2 + boss_shift, H // 2 - 28)

        for e in effects:
            etype = e["type"]

            if etype == "proj":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                color = e["color"]
                style = e.get("style", "fire")
                r     = e.get("r", 8)

                if e.get("origin") == "player":
                    # 시전 순간의 완드 위치 고정 → 플레이어가 이동해도 궤적 유지
                    cast_off = e.get("cast_offset_x", player_offset_x)
                    sx, sy = self.wand_tip(cast_off)
                    ex, ey = boss_center
                    draw_r = max(3, int(r * (1.0 - t * 0.25)))
                else:
                    sx, sy = boss_center
                    ex, ey = W // 2, H + 60
                    draw_r = max(3, int(r * (0.4 + t * 1.8)))

                px = int(sx + (ex - sx) * t)
                py = int(sy + (ey - sy) * t)
                self._draw_proj_styled(px, py, draw_r, color, style, t, sx, sy, ex, ey)

            elif etype == "cast":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                cx, cy = wand_pt
                r    = int(e["r0"] + (e["r1"] - e["r0"]) * t)
                fade = max(0.0, 1.0 - t)
                col  = tuple(int(c * fade) for c in e["color"])
                self._draw_cast_styled(cx, cy, r, col, e.get("style", "fire"), fade)

            elif etype == "impact":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                cx, cy = boss_center
                r    = int(e["r0"] + (e["r1"] - e["r0"]) * t)
                fade = max(0.0, 1.0 - t)
                col  = tuple(int(c * fade) for c in e["color"])
                self._draw_impact_styled(cx, cy, r, col, e.get("style", "fire"), t)

            elif etype == "magic_circle":
                t    = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                # Fade in (0-0.15), full (0.15-0.80), fade out (0.80-1.0)
                if t < 0.15:
                    alpha = t / 0.15
                elif t > 0.80:
                    alpha = (1.0 - t) / 0.20
                else:
                    alpha = 1.0
                # Scale in during first 0.15
                r_max = 88
                radius = int(r_max * min(1.0, t / 0.15)) if t < 0.15 else r_max
                # Slow forward rotation driven by global tick
                angle = self._tick * 0.022
                self._draw_magic_circle_effect(
                    W // 2, int(H * 0.63), radius, e["color"], angle, alpha
                )

            elif etype == "ring":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                r = int(e["r0"] + (e["r1"] - e["r0"]) * t)
                cx_w, cy_w = wand_pt
                fade = max(0.0, 1.0 - t)
                col = tuple(int(v * fade) for v in e["color"])

                self._draw_glow(cx_w, cy_w, max(8, r // 2), col, layers=4)
                pygame.draw.circle(self.screen, col, (cx_w, cy_w), r, e["w"])
                pygame.draw.circle(self.screen, col, (cx_w, cy_w), max(8, r - 10), 1)

            elif etype == "telegraph":
                # 보스 시전 경고: 보스 중심에서 수축하는 붉은 링 + 점멸
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                cx, cy = boss_center
                r = int(96 - 66 * t)
                pulse = 0.55 + 0.45 * abs(math.sin(self._tick * 0.6))
                col = (int(255 * pulse), int(70 * pulse), int(70 * pulse))
                try:
                    pygame.draw.circle(self.screen, col, (cx, cy), max(6, r), 3)
                    pygame.draw.circle(self.screen, col, (cx, cy), max(3, r // 2), 1)
                except Exception:
                    pass

            elif etype == "flash":
                # 화면 전체 색 파동 — 보스 페이즈 전환 등 리듬 강조용
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                a = int(150 * (1.0 - t) ** 2)
                if a > 0:
                    ov = pygame.Surface((W, H), pygame.SRCALPHA)
                    ov.fill((*e["color"], a))
                    self.screen.blit(ov, (0, 0))
                    band_h = max(2, int(H * 0.5 * (1.0 - t)))
                    cy = int(H * t)
                    pygame.draw.rect(self.screen, e["color"], (0, cy - band_h // 2, W, band_h), 2)

    # ── Shield vignette ────────────────────────────────────────────────────────

    def _draw_shield_vignette(self, time_left: int) -> None:
        W, H = self.W, self.H
        col = self._pulse_color((0, 70, 110), (0, 170, 240), self._tick, 40)
        for w in range(1, 12):
            fade = 1.0 - (w - 1) / 11
            c = tuple(int(v * fade) for v in col)
            pygame.draw.rect(self.screen, c, (w, w, W - w * 2, H - w * 2), 1)

    # ── HUD ────────────────────────────────────────────────────────────────────

    def _draw_hud(
        self,
        player_hp:         int,
        boss_hp:           int,
        shield_time_left:  int,
        lightning_cd_left: int,
        difficulty:        str,
        score:             int = 0,
        stage_index:       int = 1,
        stage_count:       int = 1,
        player_max_hp:     int = PLAYER_MAX_HP,
    ) -> None:
        W, H = self.W, self.H

        # Player HP (bottom-left panel)
        # 최대 HP 는 룬(SECOND WIND)으로 늘어날 수 있으므로 상수가 아니라 인자를 쓴다.
        self._draw_hp_panel(18, H - 56, 210, 18, player_hp, max(1, player_max_hp), GREEN, "HP")

        # Live score readout (top-right, above difficulty badge)
        score_s = self.font_game_tab.render(f"SCORE  {score}", True, TEXT_PRIMARY)
        self.screen.blit(score_s, (W - score_s.get_width() - 82, 44))

        # Stage indicator (only meaningful once there's more than one stage)
        if stage_count > 1:
            stage_s = self.font_game_tab.render(f"STAGE {stage_index}/{stage_count}", True, GOLD)
            self.screen.blit(stage_s, (W - stage_s.get_width() - 82, 68))

        # Status chips (right side, stacked upward)
        chip_x = W - 190
        chip_y = H - 36
        if lightning_cd_left > 0:
            cd_str = f"LIGHTNING  {lightning_cd_left / 1000.0:.1f}s"
            self._draw_chip(chip_x, chip_y, cd_str, BLUE)
            chip_y -= 30
        if shield_time_left > 0:
            sh_str = f"SHIELD  {shield_time_left / 1000.0:.1f}s"
            self._draw_chip(chip_x, chip_y, sh_str, CYAN)

        # Difficulty badge (top-right, 일시정지 버튼 왼쪽)
        diff_colors = {"easy": GREEN, "normal": YELLOW, "hard": ORANGE, "impossible": RED}
        dc = diff_colors.get(difficulty, WHITE)
        badge = self.font.render(f"[{difficulty.upper()}]", True, dc)
        self.screen.blit(badge, (W - badge.get_width() - 82, 14))

        # 일시정지 버튼 (우측 상단)
        pb = pygame.Rect(W - 68, 10, 58, 28)
        pb_bg = pygame.Surface((58, 28), pygame.SRCALPHA)
        pb_bg.fill((0, 0, 0, 160))
        self.screen.blit(pb_bg, pb.topleft)
        pygame.draw.rect(self.screen, HAIRLINE, pb, 1, border_radius=5)
        pb_s = self.font_game_tab.render("II ESC", True, TEXT_PRIMARY)
        self.screen.blit(pb_s, pb_s.get_rect(center=pb.center))

    def _draw_hp_panel(
        self,
        x: int, y: int, w: int, h: int,
        hp: int, hp_max: int,
        color: Tuple[int, int, int],
        label: str,
    ) -> None:
        # Semi-transparent panel background
        panel = pygame.Surface((w + 10, h + 24), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 140))
        self.screen.blit(panel, (x - 4, y - 20))

        lbl = self.font.render(f"{label}  {hp}/{hp_max}", True, WHITE)
        self.screen.blit(lbl, (x, y - 16))

        pygame.draw.rect(self.screen, (25, 25, 35), (x, y, w, h), border_radius=4)
        ratio = max(0.0, min(1.0, hp / float(hp_max)))
        fill_col = self._lerp_color(RED, color, ratio)
        if int(w * ratio) > 0:
            pygame.draw.rect(self.screen, fill_col, (x, y, int(w * ratio), h), border_radius=4)
        pygame.draw.rect(self.screen, HAIRLINE, (x, y, w, h), 1, border_radius=4)

    def _draw_chip(self, x: int, y: int, text: str, color: Tuple[int, int, int]) -> None:
        surf = self.font.render(text, True, color)
        bg = pygame.Surface((surf.get_width() + 12, surf.get_height() + 8), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 160))
        self.screen.blit(bg, (x - 6, y - 4))
        pygame.draw.rect(self.screen, color, (x - 6, y - 4, surf.get_width() + 12, surf.get_height() + 8), 1, border_radius=4)
        self.screen.blit(surf, (x, y))

    # ── Spell message ──────────────────────────────────────────────────────────

    def _draw_spell_message(
        self,
        text:      str,
        color:     Tuple[int, int, int],
        time_left: int,
    ) -> None:
        W, H = self.W, self.H
        fade = min(1.0, time_left / 400.0)
        col = tuple(int(c * fade) for c in color)
        surf = self.font_big.render(text, True, col)
        rect = surf.get_rect(center=(W // 2, H // 3 - 10))
        shad = self.font_big.render(text, True, (0, 0, 0))
        self.screen.blit(shad, (rect.x + 2, rect.y + 2))
        self.screen.blit(surf, rect)

    # ── Element-specific effect helpers ────────────────────────────────────────

    def _draw_proj_styled(
        self,
        px: int, py: int, r: int,
        color: Tuple[int, int, int],
        style: str, t: float,
        sx: int, sy: int, ex: int, ey: int,
    ) -> None:
        """Element-specific projectile drawing."""

        def trail(steps: int = 5, fade_step: float = 0.04, shape: str = "circle") -> None:
            for step in range(1, steps + 1):
                tt = max(0.0, t - step * fade_step)
                tx = int(sx + (ex - sx) * tt)
                ty = int(sy + (ey - sy) * tt)
                tr = max(1, r - step * 2)
                tc: Tuple[int, int, int] = tuple(max(0, int(c * (1.0 - step * 0.22))) for c in color)  # type: ignore
                if shape == "rect":
                    pygame.draw.rect(self.screen, tc, (tx - tr, ty - tr, tr * 2, tr * 2))
                elif shape == "line":
                    pygame.draw.line(self.screen, tc, (tx - tr * 2, ty), (tx + tr * 2, ty), max(1, tr // 2))
                else:
                    pygame.draw.circle(self.screen, tc, (tx, ty), tr)

        if style == "fire":
            self._draw_glow(px, py, r + 10, (255, 80, 10), layers=5)
            pygame.draw.circle(self.screen, (255, 200, 50), (px, py), max(2, r - 2))
            pygame.draw.circle(self.screen, color, (px, py), r)
            for i in range(6):
                a = self._tick * 0.18 + i * math.pi / 3
                fpx = px + int(math.cos(a) * r * 1.6)
                fpy = py + int(math.sin(a) * r * 1.6)
                pygame.draw.circle(self.screen, (255, max(0, 100 - i * 15), 0), (fpx, fpy), max(1, r // 2 - 1))
            trail(6, 0.038, "circle")

        elif style == "water":
            self._draw_glow(px, py, r + 7, color, layers=4)
            pygame.draw.circle(self.screen, (140, 200, 255), (px, py), max(2, r - 2))
            pygame.draw.circle(self.screen, color, (px, py), r, 2)
            pygame.draw.circle(self.screen, (210, 235, 255), (px - r // 3, py - r // 3), max(1, r // 4))
            trail(5, 0.048, "circle")

        elif style == "earth":
            self._draw_glow(px, py, r + 4, color, layers=3)
            wobble = [0.85, 1.0, 0.92, 1.0, 0.88, 0.96]
            rock_pts = [
                (px + int(r * wobble[i] * math.cos(math.pi * 2 * i / 6 + self._tick * 0.02)),
                 py + int(r * wobble[i] * math.sin(math.pi * 2 * i / 6 + self._tick * 0.02)))
                for i in range(6)
            ]
            pygame.draw.polygon(self.screen, color, rock_pts)
            pygame.draw.polygon(self.screen, (90, 50, 10), rock_pts, 1)
            trail(4, 0.055, "rect")

        elif style == "wind":
            self._draw_glow(px, py, r + 10, color, layers=4)
            pygame.draw.circle(self.screen, color, (px, py), max(3, r // 2), 2)
            for k in range(3):
                a_s = self._tick * 0.20 + k * math.pi * 2 / 3
                ar = r + k * 3
                rc: Tuple[int, int, int] = tuple(max(0, int(c * (1.0 - k * 0.25))) for c in color)  # type: ignore
                try:
                    pygame.draw.arc(self.screen, rc, (px - ar, py - ar, ar * 2, ar * 2),
                                    a_s, a_s + math.pi * 1.3, max(1, r // 3))
                except Exception:
                    pass
            trail(5, 0.04, "line")

        elif style == "light":
            self._draw_glow(px, py, r + 14, WHITE, layers=7)
            pygame.draw.circle(self.screen, WHITE, (px, py), max(2, r - 1))
            ray_len = int(r * 2.5)
            for ang in (0.0, math.pi / 4, math.pi / 2, 3 * math.pi / 4):
                a = ang + self._tick * 0.04
                for sign in (1, -1):
                    pygame.draw.line(self.screen, (255, 255, 200),
                                     (px, py),
                                     (px + int(sign * ray_len * math.cos(a)),
                                      py + int(sign * ray_len * math.sin(a))),
                                     max(1, r // 3))
            pygame.draw.circle(self.screen, WHITE, (px, py), max(1, r // 2))

        elif style == "dark":
            self._draw_glow(px, py, r + 8, color, layers=4)
            pygame.draw.circle(self.screen, color, (px, py), r)
            pygame.draw.circle(self.screen, (15, 8, 25), (px, py), max(2, r - 3))
            for k in range(5):
                a = self._tick * 0.12 + k * math.pi * 2 / 5
                tend_x = px + int(r * 2.0 * math.cos(a))
                tend_y = py + int(r * 2.0 * math.sin(a))
                pygame.draw.line(self.screen, color, (px, py), (tend_x, tend_y), 1)
            trail(5, 0.04, "circle")

        elif style in ("lightning", "boss"):
            self._draw_glow(px, py, r + 8, color, layers=4)
            pygame.draw.circle(self.screen, color, (px, py), r, 2)
            prev = (px, py)
            perp_x, perp_y = -(ey - sy), ex - sx
            mag = math.hypot(perp_x, perp_y)
            if mag > 0:
                perp_x /= mag; perp_y /= mag
            for step in range(1, 5):
                tt = max(0.0, t - step * 0.04)
                tx2, ty2 = int(sx + (ex - sx) * tt), int(sy + (ey - sy) * tt)
                jitter = r * 0.7 * (1 if step % 2 else -1)
                mx = int((prev[0] + tx2) / 2 + perp_x * jitter)
                my = int((prev[1] + ty2) / 2 + perp_y * jitter)
                tc2: Tuple[int, int, int] = tuple(max(0, int(c * (1.0 - step * 0.22))) for c in color)  # type: ignore
                pygame.draw.line(self.screen, tc2, prev, (mx, my), max(1, step))
                pygame.draw.line(self.screen, tc2, (mx, my), (tx2, ty2), max(1, step))
                prev = (tx2, ty2)

        else:
            self._draw_glow(px, py, r + 5, color, layers=4)
            pygame.draw.circle(self.screen, color, (px, py), r)
            trail(5)

    def _draw_cast_styled(
        self,
        cx: int, cy: int, r: int,
        col: Sequence[int],
        style: str, fade: float,
    ) -> None:
        """Element-specific cast flash at the wand tip."""
        cf: Tuple[int, int, int] = tuple(int(c * fade) for c in col)  # type: ignore

        if style == "fire":
            self._draw_glow(cx, cy, r + 8, col, layers=5)
            for i in range(5):
                a = self._tick * 0.20 + i * math.pi * 2 / 5
                fpx = cx + int(math.cos(a) * r * 1.3)
                fpy = cy + int(math.sin(a) * r * 1.3)
                pygame.draw.circle(self.screen, cf, (fpx, fpy), max(1, r // 3))
            pygame.draw.circle(self.screen, cf, (cx, cy), max(2, r // 2))
            pygame.draw.circle(self.screen, cf, (cx, cy), max(5, r), 1)
        elif style == "water":
            self._draw_glow(cx, cy, r + 6, col, layers=4)
            for k in range(3):
                rr = max(2, r - k * 6)
                rc: Tuple[int, int, int] = tuple(int(c * fade * (1.0 - k * 0.28)) for c in col)  # type: ignore
                pygame.draw.circle(self.screen, rc, (cx, cy), rr, 1)
        elif style == "earth":
            self._draw_glow(cx, cy, r + 4, col, layers=3)
            for i in range(6):
                a = i * math.pi / 3 + self._tick * 0.05
                sz = max(2, r // 4)
                ex2 = cx + int(math.cos(a) * r)
                ey2 = cy + int(math.sin(a) * r)
                pygame.draw.rect(self.screen, cf, (ex2 - sz, ey2 - sz, sz * 2, sz * 2))
        elif style == "wind":
            self._draw_glow(cx, cy, r + 8, col, layers=4)
            a_s = self._tick * 0.15
            try:
                pygame.draw.arc(self.screen, cf, (cx - r, cy - r, r * 2, r * 2),
                                a_s, a_s + math.pi * 1.4, max(1, r // 3))
            except Exception:
                pass
            pygame.draw.circle(self.screen, cf, (cx, cy), max(3, r // 2), 1)
        elif style == "light":
            self._draw_glow(cx, cy, r + 14, (255, 255, 230), layers=7)
            for i in range(8):
                a = i * math.pi / 4 + self._tick * 0.04
                pygame.draw.line(self.screen, cf, (cx, cy),
                                 (cx + int(math.cos(a) * r * 1.5), cy + int(math.sin(a) * r * 1.5)),
                                 max(1, r // 5))
            pygame.draw.circle(self.screen, cf, (cx, cy), max(2, r // 2))
        elif style == "dark":
            self._draw_glow(cx, cy, r + 6, col, layers=4)
            for i in range(4):
                a = i * math.pi / 2 + self._tick * 0.10
                pygame.draw.line(self.screen, cf, (cx, cy),
                                 (cx + int(math.cos(a) * r * 1.4), cy + int(math.sin(a) * r * 1.4)), 1)
            pygame.draw.circle(self.screen, cf, (cx, cy), max(2, r // 2))
            pygame.draw.circle(self.screen, cf, (cx, cy), max(5, r), 1)
        else:
            self._draw_glow(cx, cy, r, col, layers=5)
            pygame.draw.circle(self.screen, cf, (cx, cy), max(2, r // 3))
            pygame.draw.circle(self.screen, cf, (cx, cy), max(5, r), 1)

    def _draw_impact_styled(
        self,
        cx: int, cy: int, r: int,
        col: Sequence[int],
        style: str, t: float,
    ) -> None:
        """Element-specific impact explosion at boss."""

        def dc(br: float = 1.0) -> Tuple[int, int, int]:
            return tuple(max(0, int(c * (1.0 - t) * br)) for c in col)  # type: ignore

        if style == "fire":
            self._draw_glow(cx, cy, r + 16, (255, 80, 10), layers=6)
            pygame.draw.circle(self.screen, dc(), (cx, cy), r, 3)
            if r > 12:
                pygame.draw.circle(self.screen, dc(0.8), (cx, cy), max(4, r - 10), 2)
            for i in range(8):
                a = i * math.pi / 4 + self._tick * 0.06
                jet_x = cx + int(math.cos(a) * r * 1.4)
                jet_y = cy + int(math.sin(a) * r * 1.4)
                pygame.draw.line(self.screen, dc(0.9), (cx, cy), (jet_x, jet_y), max(1, 3 - int(t * 2)))
            for i in range(12):
                a = self._tick * 0.09 + i * math.pi * 2 / 12
                epx = cx + int(math.cos(a) * r * (0.4 + 0.6 * (i % 3) / 2))
                epy = cy + int(math.sin(a) * r * (0.4 + 0.6 * (i % 3) / 2) * 0.7)
                pygame.draw.circle(self.screen, dc(), (epx, epy), max(1, 4 - int(t * 3)))

        elif style == "water":
            self._draw_glow(cx, cy, r + 8, col, layers=4)
            for k in range(3):
                rr = max(3, r - k * 12)
                rc: Tuple[int, int, int] = tuple(max(0, int(c * (1.0 - k * 0.3 - t * 0.3))) for c in col)  # type: ignore
                pygame.draw.circle(self.screen, rc, (cx, cy), rr, 2)
            for i in range(8):
                a = i * math.pi / 4 + t * 0.5
                dpx = cx + int(math.cos(a) * r * (0.8 + t * 0.3))
                dpy = cy + int(math.sin(a) * r * (0.8 + t * 0.3))
                pygame.draw.circle(self.screen, dc(0.9), (dpx, dpy), max(1, 4 - int(t * 3)))

        elif style == "earth":
            self._draw_glow(cx, cy, r + 6, col, layers=3)
            for i in range(7):
                a = i * math.pi * 2 / 7 + 0.2
                pts = [(cx, cy)]
                for seg in range(1, 5):
                    jitter = (seg * 7 + i * 13) % 7 - 3
                    pts.append((cx + int(math.cos(a) * r * seg / 4) + jitter,
                                cy + int(math.sin(a) * r * seg / 4) + jitter))
                if len(pts) > 1:
                    pygame.draw.lines(self.screen, dc(), False, pts, 2)
            for i in range(6):
                a = i * math.pi / 3 + t
                cpx = cx + int(math.cos(a) * r * (0.5 + 0.5 * t))
                cpy = cy + int(math.sin(a) * r * (0.5 + 0.5 * t))
                cs = max(2, 8 - int(t * 6))
                pygame.draw.rect(self.screen, dc(), (cpx - cs // 2, cpy - cs // 2, cs, cs))

        elif style == "wind":
            self._draw_glow(cx, cy, r + 10, col, layers=4)
            for k in range(4):
                rr = max(3, r - k * 8)
                a_off = self._tick * 0.12 + k * 0.6
                rc2: Tuple[int, int, int] = tuple(max(0, int(c * (1.0 - k * 0.2 - t * 0.3))) for c in col)  # type: ignore
                try:
                    pygame.draw.arc(self.screen, rc2, (cx - rr, cy - rr, rr * 2, rr * 2),
                                    a_off, a_off + math.pi * 1.5, max(1, 3 - k))
                except Exception:
                    pass
            for i in range(5):
                a = self._tick * 0.15 + i * math.pi * 2 / 5
                pygame.draw.line(self.screen, dc(), (cx, cy),
                                 (cx + int(math.cos(a) * r * 1.3), cy + int(math.sin(a) * r * 1.3)), 1)

        elif style == "light":
            self._draw_glow(cx, cy, r + 22, WHITE, layers=8)
            pygame.draw.circle(self.screen, dc(), (cx, cy), r, 2)
            pygame.draw.circle(self.screen, dc(0.7), (cx, cy), max(4, r - 14), 1)
            for i in range(12):
                a = i * math.pi / 6 + self._tick * 0.03
                pygame.draw.line(self.screen, dc(0.9), (cx, cy),
                                 (cx + int(math.cos(a) * r * 1.6), cy + int(math.sin(a) * r * 1.6)), 2)
            pygame.draw.circle(self.screen, dc(), (cx, cy), max(3, r // 3))

        elif style == "dark":
            self._draw_glow(cx, cy, r + 8, col, layers=4)
            pygame.draw.circle(self.screen, dc(), (cx, cy), r, 2)
            for i in range(6):
                a = i * math.pi / 3 + self._tick * 0.08
                tend_len = int(r * (1.5 - t * 0.8))
                tend_x = cx + int(math.cos(a) * tend_len)
                tend_y = cy + int(math.sin(a) * tend_len)
                pygame.draw.line(self.screen, dc(), (cx, cy), (tend_x, tend_y), 2)
            pygame.draw.circle(self.screen, dc(), (cx, cy), max(3, r // 2))

        elif style in ("lightning", "boss"):
            self._draw_glow(cx, cy, r + 10, col, layers=5)
            pygame.draw.circle(self.screen, dc(), (cx, cy), r, 2)
            pygame.draw.line(self.screen, dc(), (cx - r, cy), (cx + r, cy), 3)
            pygame.draw.line(self.screen, dc(), (cx, cy - r), (cx, cy + r), 3)
            for i in range(4):
                a = i * math.pi / 2 + self._tick * 0.1
                perp = a + math.pi / 2
                for j in range(1, 4):
                    seg_r = r * j / 3
                    jitter = r * 0.3 * (1 if j % 2 else -1)
                    bx = cx + int(math.cos(a) * seg_r + math.cos(perp) * jitter)
                    by = cy + int(math.sin(a) * seg_r + math.sin(perp) * jitter)
                    prev_seg_r = r * (j - 1) / 3
                    bxp = cx + int(math.cos(a) * prev_seg_r + math.cos(perp) * (-jitter))
                    byp = cy + int(math.sin(a) * prev_seg_r + math.sin(perp) * (-jitter))
                    pygame.draw.line(self.screen, dc(), (bxp, byp), (bx, by), max(1, 3 - j))

        else:
            self._draw_glow(cx, cy, r, col, layers=4)
            pygame.draw.circle(self.screen, dc(), (cx, cy), r, 2)

    # ── Magic Circle (마법진) ──────────────────────────────────────────────────

    def _draw_magic_circle_effect(
        self,
        cx: int,
        cy: int,
        radius: int,
        color: Tuple[int, int, int],
        angle: float,
        alpha: float,
    ) -> None:
        """Rotating magic circle with layered glow, inspired by the reference image.

        Geometry (all on a temporary SRCALPHA surface):
          - Outer ring + tick marks
          - 8-point fully-connected star on the middle ring (forward rotation)
          - Diamond / rhombus (counter-rotation)
          - 6-point hexagram on inner ring (faster counter-rotation)
          - Small inner triangle (fast forward rotation)
          - Concentric rings
        """
        if radius < 10 or alpha < 0.02:
            return

        sz   = radius * 3
        dim  = sz * 2
        surf = pygame.Surface((dim, dim), pygame.SRCALPHA)
        lx = ly = sz     # local origin = centre of surf

        A = int(alpha * 255)

        def c(br: float = 1.0) -> Tuple[int, int, int, int]:
            return (*color, min(255, int(A * br)))  # type: ignore[return-value]

        r1 = radius
        r2 = int(radius * 0.72)
        r3 = int(radius * 0.46)
        r4 = int(radius * 0.22)

        # ── Glow (simulate blur with concentric transparent rings) ────────────
        for k in range(8, 0, -1):
            gr = r1 + k * 12
            ga = int(alpha * 32 * k / 8)
            if ga > 0 and gr > 0:
                pygame.draw.circle(surf, (*color, ga), (lx, ly), gr, k * 3)

        # ── Concentric rings ──────────────────────────────────────────────────
        if r1 > 0: pygame.draw.circle(surf, c(1.0),  (lx, ly), r1, 2)
        if r2 > 0: pygame.draw.circle(surf, c(0.80), (lx, ly), r2, 1)
        if r3 > 0: pygame.draw.circle(surf, c(0.65), (lx, ly), r3, 1)
        if r4 > 0: pygame.draw.circle(surf, c(0.55), (lx, ly), r4, 1)
        pygame.draw.circle(surf, c(0.50), (lx, ly), max(2, r4 // 3))

        # ── Tick marks on outer ring ──────────────────────────────────────────
        for i in range(16):
            a   = angle * 0.35 + math.pi * 2 * i / 16
            cos_a, sin_a = math.cos(a), math.sin(a)
            tl  = 8 if i % 4 == 0 else 4
            br  = 0.70 if i % 4 == 0 else 0.45
            ix  = lx + int((r1 - tl) * cos_a)
            iy  = ly + int((r1 - tl) * sin_a)
            ox  = lx + int(r1 * cos_a)
            oy  = ly + int(r1 * sin_a)
            pygame.draw.line(surf, c(br), (ix, iy), (ox, oy), 1)

        # ── 8-point fully-connected star (forward rotation) ───────────────────
        pts8 = [
            (lx + int(r2 * math.cos(angle + math.pi * 2 * i / 8)),
             ly + int(r2 * math.sin(angle + math.pi * 2 * i / 8)))
            for i in range(8)
        ]
        for i in range(8):
            for j in range(i + 2, 8):
                pygame.draw.line(surf, c(0.45), pts8[i], pts8[j], 1)
        for pt in pts8:
            pygame.draw.circle(surf, c(0.70), pt, 3)

        # ── Diamond / rhombus (counter-rotates at 0.65× speed) ───────────────
        dia_pts = [
            (lx + int(r2 * 0.90 * math.cos(-angle * 0.65 + math.pi / 4 + k * math.pi / 2)),
             ly + int(r2 * 0.90 * math.sin(-angle * 0.65 + math.pi / 4 + k * math.pi / 2)))
            for k in range(4)
        ]
        pygame.draw.polygon(surf, c(0.85), dia_pts, 2)

        # ── Inner 6-point hexagram (counter-rotates at 1.5× speed) ───────────
        pts6 = [
            (lx + int(r3 * math.cos(-angle * 1.5 + math.pi * 2 * i / 6)),
             ly + int(r3 * math.sin(-angle * 1.5 + math.pi * 2 * i / 6)))
            for i in range(6)
        ]
        for i in range(6):
            for j in range(i + 2, 6):
                pygame.draw.line(surf, c(0.60), pts6[i], pts6[j], 1)

        # ── Inner triangle (forward, 2.5× speed) ─────────────────────────────
        tri_pts = [
            (lx + int(r4 * 1.7 * math.cos(angle * 2.5 + math.pi * 2 * i / 3)),
             ly + int(r4 * 1.7 * math.sin(angle * 2.5 + math.pi * 2 * i / 3)))
            for i in range(3)
        ]
        pygame.draw.polygon(surf, c(0.60), tri_pts, 1)

        self.screen.blit(surf, (cx - sz, cy - sz))

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _draw_glow(
        self,
        cx: int, cy: int, r: int,
        color: Sequence[int],
        layers: int = 4,
    ) -> None:
        for i in range(layers, 0, -1):
            fade = (i / layers) * 0.45
            c = tuple(int(v * fade) for v in color)
            pygame.draw.circle(self.screen, c, (cx, cy), r + i * 3)

    def _draw_rune_separator(self, y: int) -> None:
        """Static hairline divider — chrome stays still, no per-frame pulse."""
        W = self.W
        pygame.draw.line(self.screen, HAIRLINE, (W // 4, y), (W * 3 // 4, y), 1)
        for dx in range(-60, 61, 20):
            pygame.draw.circle(self.screen, HAIRLINE, (W // 2 + dx, y), 2)

    def _draw_button(
        self,
        rect:  pygame.Rect,
        label: str,
        font:  Optional[pygame.font.Font] = None,
        danger: bool = False,
    ) -> None:
        """Flat hairline button — minimal arcade chrome, no glow/pulse."""
        edge = DANGER if danger else HAIRLINE
        text_c = DANGER if danger else TEXT_PRIMARY
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((255, 255, 255, 14))
        self.screen.blit(bg, rect.topleft)
        pygame.draw.rect(self.screen, edge, rect, 1, border_radius=5)
        lbl = (font or self.font_big).render(label, True, text_c)
        self.screen.blit(lbl, lbl.get_rect(center=rect.center))

    @staticmethod
    def _make_game_font(size: int) -> pygame.font.Font:
        """Bold condensed font for game-style headings."""
        for name in ("impact", "arial black", "agency fb", "franklin gothic heavy", "bahnschrift"):
            try:
                f = pygame.font.SysFont(name, size)
                if f is not None:
                    return f
            except Exception:
                pass
        return pygame.font.SysFont(None, size)

    @staticmethod
    def _make_kor_font(size: int) -> pygame.font.Font:
        """한글을 렌더할 수 있는 폰트. 구현은 hud_ext.korean_font 로 일원화되어 있다."""
        return hud_ext.korean_font(size)

    @staticmethod
    def _pulse_color(
        a: Sequence[int],
        b: Sequence[int],
        tick: int,
        period: int,
    ) -> Tuple[int, int, int]:
        t = (math.sin(tick * 2 * math.pi / max(period, 1)) + 1) / 2
        return FPRenderer._lerp_color(a, b, t)

    @staticmethod
    def _lerp_color(
        a: Sequence[int],
        b: Sequence[int],
        t: float,
    ) -> Tuple[int, int, int]:
        return (
            int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t),
        )

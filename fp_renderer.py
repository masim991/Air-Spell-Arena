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
from typing import List, Optional, Tuple

import pygame

# ── Modern Neon/Cyberpunk Colour Palette (2026 Gaming Trend) ──────────────────
# Inspired by Valorant, Apex Legends, Genshin Impact
BLACK    = (0,   0,   0)
WHITE    = (255, 255, 255)

# Background - Deep dark with subtle purple tint
BG_TOP   = (8,   4,  18)
BG_MID   = (12,  6,  24)
BG_BOT   = (6,   3,  14)
FLOOR_C  = (18,  10,  32)

# Runes - Vibrant neon purple/magenta
RUNE_DIM = (60,  30,  100)
RUNE_GLO = (180, 80,  255)

# UI Colors - Bright, saturated, neon-inspired
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
        self._boss_sh_r: int = -1
        self._boss_sh_surf: Optional[pygame.Surface] = None
        self._boss_hl_r: int = -1
        self._boss_hl_surf: Optional[pygame.Surface] = None

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

        # 은은한 배경 파티클
        for k in range(5):
            a  = tick * 0.007 + k * math.pi * 2 / 5
            px = int(W // 2 + math.cos(a) * (180 + k * 30))
            py = int(H // 2 + math.sin(a * 0.6) * (55 + k * 18))
            rc = self._pulse_color((10, 10, 50), (40, 30, 100), tick + k * 20, 100)
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

                sh = tf.render(c, True, (0, 0, 30))
                sh.set_alpha(150)
                self.screen.blit(sh, (x + 3, ty + 3))

                col = self._pulse_color((140, 210, 255), (240, 255, 255), tick + i * 11, 65)
                self.screen.blit(tf.render(c, True, col), (x, ty))

                if glow_frac > 0.04:
                    gc = (int(60 * glow_frac), int(160 * glow_frac), int(255 * glow_frac))
                    gs = tf.render(c, True, gc)
                    gs.set_alpha(int(200 * glow_frac))
                    self.screen.blit(gs, (x - 1, ty - 1))
            x += cw

        # ── PLAY / EXIT 버튼 (전체 공개 후 표시) ──────────────────────────
        if btn_play is not None:
            self._draw_hero_button(btn_play, "PLAY", CYAN)
        if btn_exit is not None:
            self._draw_button(btn_exit, "EXIT", RED)

        pygame.display.flip()

    def render_menu(
        self,
        btn_start:    pygame.Rect,
        btn_exit:     pygame.Rect,
        btn_guide:    pygame.Rect,
        btn_settings: pygame.Rect,
        difficulty:   str,
    ) -> None:
        self._tick += 1
        W, H = self.W, self.H

        self._draw_bg()

        # ── Ambient floating rune particles ────────────────────────────────
        for k in range(8):
            a   = self._tick * 0.012 + k * math.pi * 2 / 8
            px_ = W // 2 + int(math.cos(a) * (180 + k * 18))
            py_ = H // 2 + int(math.sin(a * 0.7) * (80 + k * 10)) - 40
            rc  = self._pulse_color(RUNE_DIM, RUNE_GLO, self._tick + k * 22, 70)
            pygame.draw.circle(self.screen, rc, (px_, py_), 2 + k % 2)

        # ── Title (game bold font, double shadow + glow) ────────────────────
        glow_c = self._pulse_color((140, 70, 255), (230, 160, 255), self._tick, 90)
        tf     = self.font_game_title
        ty     = H // 4 - 10

        for dx, dy, alpha in ((4, 4, 35), (2, 2, 80)):
            sh_t = tf.render("AIR SPELL ARENA", True, (0, 0, 0))
            sh_t.set_alpha(alpha)
            self.screen.blit(sh_t, sh_t.get_rect(center=(W // 2 + dx, ty + dy)))

        title_s = tf.render("AIR SPELL ARENA", True, glow_c)
        self.screen.blit(title_s, title_s.get_rect(center=(W // 2, ty)))

        # ── Subtitle ────────────────────────────────────────────────────────
        sub_c = self._pulse_color((80, 70, 110), (160, 140, 200), self._tick, 120)
        sub_f = self.font_game_tab
        sub_s = sub_f.render("*  Battle the Arcane Boss with Hand Spells  *", True, sub_c)
        self.screen.blit(sub_s, sub_s.get_rect(center=(W // 2, ty + 56)))

        self._draw_rune_separator(ty + 80)

        # ── START button (hero — full width, bright) ───────────────────────
        self._draw_hero_button(btn_start, "START  GAME", CYAN)

        # ── EXIT button (secondary) ────────────────────────────────────────
        self._draw_button(btn_exit, "EXIT", RED)

        # ── GUIDE + SETTINGS (small, side by side) ─────────────────────────
        self._draw_button(btn_guide,    "SPELL GUIDE", GOLD,   self.font_game_tab)
        self._draw_button(btn_settings, "SETTINGS",    PURPLE, self.font_game_tab)

        # ── Difficulty badge pill ───────────────────────────────────────────
        diff_colors = {"easy": GREEN, "normal": YELLOW, "hard": ORANGE, "impossible": RED}
        dc   = diff_colors.get(difficulty, WHITE)
        dy_  = H * 3 // 4 + 6
        pill_w, pill_h = 230, 34
        pill = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pill.fill((dc[0] // 8, dc[1] // 8, dc[2] // 8, 200))
        self.screen.blit(pill, (W // 2 - pill_w // 2, dy_ - pill_h // 2))
        pygame.draw.rect(self.screen, dc,
                         (W // 2 - pill_w // 2, dy_ - pill_h // 2, pill_w, pill_h), 2, border_radius=17)
        diff_s = self.font_game_tab.render(f"DIFFICULTY :  {difficulty.upper()}", True, dc)
        self.screen.blit(diff_s, diff_s.get_rect(center=(W // 2, dy_)))

        # ── Keyboard shortcut key-caps ──────────────────────────────────────
        keys = [("1", "Easy", GREEN), ("2", "Normal", YELLOW),
                ("3", "Hard", ORANGE), ("4", "Impossl", RED), ("G", "Guide", GOLD)]
        _kslot = 110
        total_w = len(keys) * _kslot
        kx0 = W // 2 - total_w // 2
        ky  = H * 3 // 4 + 42
        for i, (k_lbl, k_name, k_col) in enumerate(keys):
            kx = kx0 + i * _kslot
            # key cap box
            cap = pygame.Rect(kx, ky - 11, 22, 22)
            cap_bg = pygame.Surface((22, 22), pygame.SRCALPHA)
            cap_bg.fill((k_col[0] // 6, k_col[1] // 6, k_col[2] // 6, 200))
            self.screen.blit(cap_bg, cap.topleft)
            pygame.draw.rect(self.screen, k_col, cap, 1, border_radius=3)
            ks = self.font_game_tab.render(k_lbl, True, k_col)
            self.screen.blit(ks, ks.get_rect(center=cap.center))
            # label next to key
            ns = self.font.render(k_name, True, tuple(c // 2 + 40 for c in k_col))  # type: ignore
            self.screen.blit(ns, (kx + 26, ky - 7))

        pygame.display.flip()

    def _draw_hero_button(
        self,
        rect:  pygame.Rect,
        label: str,
        color: Tuple[int, int, int],
    ) -> None:
        """Large hero button with gradient-like fill and pulsing border."""
        border = self._pulse_color(tuple(c // 2 for c in color), color, self._tick, 40)
        # Layered glow
        for expand in (8, 4, 2):
            glow_r = pygame.Rect(rect.x - expand, rect.y - expand,
                                 rect.w + expand * 2, rect.h + expand * 2)
            gs = pygame.Surface((glow_r.w, glow_r.h), pygame.SRCALPHA)
            alpha = max(0, 60 - expand * 12)
            gs.fill((color[0] // 4, color[1] // 4, color[2] // 4, alpha))
            self.screen.blit(gs, glow_r.topleft)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((color[0] // 6, color[1] // 6, color[2] // 6, 220))
        self.screen.blit(bg, rect.topleft)
        pygame.draw.rect(self.screen, border, rect, 3, border_radius=10)
        lbl_s = self.font_game_title.render(label, True, color)
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
        tc = self._pulse_color(GOLD, WHITE, self._tick, 80)
        ts = self.font_game_title.render("AUDIO  SETTINGS", True, tc)
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
            
            toggle_col = PINK if use_custom else CYAN
            toggle_bg = pygame.Surface((toggle_w, toggle_h), pygame.SRCALPHA)
            toggle_bg.fill((toggle_col[0] // 5, toggle_col[1] // 5, toggle_col[2] // 5, 200))
            self.screen.blit(toggle_bg, toggle_rect.topleft)
            pygame.draw.rect(self.screen, toggle_col, toggle_rect, 2, border_radius=14)
            
            toggle_txt = "🎵 CUSTOM" if use_custom else "🎵 DEFAULT"
            toggle_s = self.font_game_tab.render(toggle_txt, True, toggle_col)
            self.screen.blit(toggle_s, toggle_s.get_rect(center=toggle_rect.center))
            clickables.append((toggle_rect, "toggle_custom", None))

        # ── 슬롯 탭 (2줄 × 4 = 8개) ──────────────────────────────────────
        mx, my = 40, 40    # margin
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
        self._draw_button(btn_save, "저장", GREEN, self.font_kor_big)
        self._draw_button(btn_back, "뒤로", GREY,  self.font_kor_big)
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
        tc     = self._pulse_color(GOLD, WHITE, tick, 80)
        ts_sh  = self.font_game_title.render("SPELL  GUIDE", True, (0, 0, 0))
        ts_sh.set_alpha(90)
        ts     = self.font_game_title.render("SPELL  GUIDE", True, tc)
        self.screen.blit(ts_sh, ts_sh.get_rect(center=(W // 2 + 2, 38 + 2)))
        self.screen.blit(ts,    ts.get_rect(center=(W // 2, 38)))
        pygame.draw.line(self.screen, RUNE_DIM, (W // 8, 64), (W * 7 // 8, 64), 1)

        # ── Section definitions ─────────────────────────────────────────────
        SEC_H    = 24   # section header bar height
        CARD_GAP = 8
        MX       = 14   # left/right margin

        sections = [
            {
                "label": "GESTURE SPELLS", "lc": ORANGE, "ncols": 4, "ch": 82,
                "entries": [
                    ("palm",  "FIRE",    "손바닥 펴기 (Open Palm)", ORANGE),
                    ("fist",  "WATER",   "주먹 쥐기 (Make Fist)",   BLUE),
                    ("thumb", "EARTH",   "엄지 위로 (Thumbs Up)",   (150, 130, 100)),
                    ("index", "WIND",    "검지만 세우기 (Index Up)", GREEN),
                ],
            },
            {
                "label": "DRAW SPELLS", "lc": CYAN, "ncols": 4, "ch": 82,
                "entries": [
                    ("left",   "LIGHT",     "손 왼쪽 스와이프 (Swipe Left)",   CYAN),
                    ("right",  "DARK",      "손 오른쪽 스와이프 (Swipe Right)", PURPLE),
                    ("circle", "SHIELD",    "원 그리기 (Draw Circle)",          (80, 200, 220)),
                    ("zigzag", "LIGHTNING", "지그재그 (Draw Zigzag)",           BLUE),
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

                # Korean description
                ds_s = self.font_kor.render(desc, True, (130, 118, 148))
                self.screen.blit(ds_s, (tx_, cy_ + 10 + nm_s.get_height() + 2))

            y_cur += card_h + 7

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
        self, cx: int, cy: int, angle: float, color: Tuple[int, int, int]
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
    ) -> None:
        self._tick += 1
        
        # 파티클 업데이트
        self.update_particles(dt_ms)
        
        # 카메라 쉐이크 오프셋
        shake_x, shake_y = self.update_camera_shake(dt_ms)

        # 1. Background (with parallax + shake)
        self._draw_bg(player_offset_x)

        # 2. Boss (behind effects)
        self._draw_boss(boss_hp / BOSS_MAX_HP, effects, player_offset_x)

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
        self._draw_hud(player_hp, boss_hp, shield_time_left, lightning_cd_left, difficulty)

        # 7. Spell message
        if message_time_left > 0 and message_text:
            self._draw_spell_message(message_text, message_color, message_time_left)

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
        pygame.draw.circle(self.screen, (0, 240, 255), head, 7, 2)
        if drawing:
            lbl = self.font.render("DRAWING", True, (0, 240, 255))
            self.screen.blit(lbl, (head[0] + 12, head[1] - 8))

    def render_ending(self, state: str, tick: int) -> None:
        """Render game_over or you_win ending screen."""
        self._tick += 1
        W, H = self.W, self.H
        # Dim background
        self._draw_bg(0.0)
        if self._end_ov is None:
            self._end_ov = pygame.Surface((W, H), pygame.SRCALPHA)
        if state == "game_over":
            self._end_ov.fill((80, 0, 0, 170))
        else:
            self._end_ov.fill((20, 10, 50, 150))
        self.screen.blit(self._end_ov, (0, 0))

        if state == "game_over":
            title_col = self._pulse_color((200, 40, 40), (255, 80, 80), tick, 50)
            title_txt = "GAME OVER"
            sub_txt   = "You were defeated by the Arcane Boss..."
        else:
            title_col = self._pulse_color(GOLD, (255, 240, 180), tick, 50)
            title_txt = "VICTORY!"
            sub_txt   = "The Arcane Boss has been vanquished!"

        # Expanding ring animation
        ring_r = int(80 + tick * 1.2) % 300
        ring_col = self._pulse_color(tuple(c // 3 for c in title_col), title_col, tick, 40)
        pygame.draw.circle(self.screen, ring_col, (W // 2, H // 2), ring_r, 2)
        pygame.draw.circle(self.screen, ring_col, (W // 2, H // 2), max(1, ring_r - 20), 1)

        # Title
        tf = pygame.font.SysFont(None, 80)
        title_surf = tf.render(title_txt, True, title_col)
        shadow_surf = tf.render(title_txt, True, (0, 0, 0))
        tc = title_surf.get_rect(center=(W // 2, H // 2 - 60))
        self.screen.blit(shadow_surf, (tc.x + 4, tc.y + 4))
        self.screen.blit(title_surf, tc)

        # Subtitle
        sub_surf = self.font_big.render(sub_txt, True, GREY)
        self.screen.blit(sub_surf, sub_surf.get_rect(center=(W // 2, H // 2 + 20)))

        # Prompt (blink)
        if (tick // 30) % 2 == 0:
            prompt = self.font.render("Press ENTER or SPACE to return to menu", True, WHITE)
            self.screen.blit(prompt, prompt.get_rect(center=(W // 2, H // 2 + 70)))

        pygame.display.flip()

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
            self._pause_ov.fill((0, 0, 18, 215))
        self.screen.blit(self._pause_ov, (0, 0))

        # 패널
        pw, ph = 460, 360
        px, py = W // 2 - pw // 2, H // 2 - ph // 2
        if not hasattr(self, "_pause_panel"):
            self._pause_panel: pygame.Surface = pygame.Surface((pw, ph), pygame.SRCALPHA)
            self._pause_panel.fill((8, 4, 28, 245))
        self.screen.blit(self._pause_panel, (px, py))
        border_c = self._pulse_color(CYAN, WHITE, self._tick, 60)
        pygame.draw.rect(self.screen, border_c, (px, py, pw, ph), 2, border_radius=14)

        # 제목
        tc = self._pulse_color((80, 220, 255), WHITE, self._tick, 50)
        ts = self.font_game_title.render("PAUSED", True, tc)
        self.screen.blit(ts, ts.get_rect(center=(W // 2, py + 44)))
        pygame.draw.line(self.screen, RUNE_DIM, (px + 20, py + 74), (px + pw - 20, py + 74), 1)

        # RESUME 버튼
        btn_resume = pygame.Rect(W // 2 - 120, py + 84, 240, 50)
        self._draw_hero_button(btn_resume, "RESUME", GREEN)
        clickables.append((btn_resume, "resume", None))

        # 볼륨 컨트롤 (BGM / SFX 2행)
        vol_rows = [
            ("BGM  VOL", bgm_vol, GOLD,   "vol_bgm_down", "vol_bgm_up"),
            ("SFX  VOL", sfx_vol, PURPLE, "vol_sfx_down", "vol_sfx_up"),
        ]
        for row_i, (label, vol, col, act_m, act_p) in enumerate(vol_rows):
            ry = py + 156 + row_i * 54

            lbl_s = self.font_game_tab.render(label, True, col)
            self.screen.blit(lbl_s, lbl_s.get_rect(midleft=(px + 36, ry + 15)))

            btn_m = pygame.Rect(px + pw - 142, ry + 4, 30, 26)
            pygame.draw.rect(self.screen, (40, 30, 60), btn_m, border_radius=5)
            pygame.draw.rect(self.screen, col, btn_m, 1, border_radius=5)
            ms = self.font_game_tab.render("-", True, col)
            self.screen.blit(ms, ms.get_rect(center=btn_m.center))
            clickables.append((btn_m, act_m, None))

            num_s = self.font_game_tab.render(str(vol), True, WHITE)
            self.screen.blit(num_s, num_s.get_rect(center=(px + pw - 92, ry + 17)))

            btn_p = pygame.Rect(px + pw - 56, ry + 4, 30, 26)
            pygame.draw.rect(self.screen, (40, 30, 60), btn_p, border_radius=5)
            pygame.draw.rect(self.screen, col, btn_p, 1, border_radius=5)
            ps = self.font_game_tab.render("+", True, col)
            self.screen.blit(ps, ps.get_rect(center=btn_p.center))
            clickables.append((btn_p, act_p, None))

        # 구분선
        pygame.draw.line(self.screen, RUNE_DIM, (px + 20, py + 276), (px + pw - 20, py + 276), 1)

        # EXIT TO MENU 버튼
        btn_exit = pygame.Rect(W // 2 - 120, py + 290, 240, 48)
        self._draw_button(btn_exit, "EXIT  TO  MENU", RED)
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
            line_col = (alpha, alpha // 2, alpha * 2)
            pygame.draw.line(self.screen, line_col, (vx - spread, fy), (vx + spread, fy), 1)

        # Converging side lines (from vanishing point)
        for i in range(-5, 6):
            floor_x = W // 2 + i * (W // 10)
            pygame.draw.line(self.screen, (18, 10, 32), (vx, vy), (floor_x, H), 1)

        # Vanishing-point rune circle
        rune_r = int(55 + 7 * math.sin(self._tick * 0.04))
        rc = self._pulse_color((25, 15, 60), (55, 35, 120), self._tick, 70)
        pygame.draw.circle(self.screen, rc, (vx, vy), rune_r, 2)
        pygame.draw.circle(self.screen, rc, (vx, vy), max(1, rune_r - 18), 1)

        # Pillars (shift more than vanishing point — closer to viewer)
        pillar_shift = int(-player_offset_x * W * 0.13)
        for px in (W // 6 + pillar_shift, W * 5 // 6 + pillar_shift):
            self._draw_pillar(px, horizon, H)

    def _draw_pillar(self, cx: int, top_y: int, H: int) -> None:
        pw, bot_y = 16, H
        top_y = top_y - 80
        pygame.draw.rect(self.screen, (14, 8, 24), (cx - pw // 2, top_y, pw, bot_y - top_y))
        pygame.draw.rect(self.screen, RUNE_DIM,  (cx - pw // 2, top_y, pw, bot_y - top_y), 1)
        for k in range(3):
            dy = top_y + (bot_y - top_y) * (k + 1) // 4
            col = self._pulse_color(RUNE_DIM, RUNE_GLO, self._tick + k * 30, 80)
            pygame.draw.circle(self.screen, col, (cx, dy), 4)
            pygame.draw.circle(self.screen, col, (cx, dy), 6, 1)

    # ── Boss ───────────────────────────────────────────────────────────────────

    def _draw_boss(self, hp_ratio: float, effects: List[dict], player_offset_x: float = 0.0) -> None:
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
        layers_3d = [
            (0,   0,   R,      (22,  3,  3)),
            (-4, -4,   R - 9,  (105, 18, 18) if not enraged else (148, 22,  8)),
            (-10,-10,  R - 21, (168, 40, 22) if not enraged else (218, 55, 12)),
            (-16,-17,  R - 35, (218, 65, 38) if not enraged else (255, 88, 18)),
            (-21,-23,  R - 49, (248, 96, 58) if not enraged else (255,125, 32)),
        ]
        for ox, oy, lr, lc in layers_3d:
            if lr > 0:
                fc = (255, 240, 210) if is_hit and lr == R - 49 else lc
                pygame.draw.circle(self.screen, fc, (cx + ox, cy + oy), lr)

        # 외곽 림 라이트 (뒷면 역광)
        if enraged:
            rim_c = self._pulse_color((255, 70, 0), (255, 180, 0), self._tick, 20)
        else:
            rim_c = (190, 55, 55)
        pygame.draw.circle(self.screen, rim_c, (cx, cy), R, 3)

        # 반사광 하이라이트 (소프트)
        if self._boss_hl_r != R:
            self._boss_hl_surf = pygame.Surface((R, R), pygame.SRCALPHA)
            pygame.draw.circle(self._boss_hl_surf, (255, 200, 160, 85),
                               (R // 2 - 9, R // 2 - 11), R // 3)
            self._boss_hl_r = R
        self.screen.blit(self._boss_hl_surf, (cx - R // 2 - 9, cy - R // 2 - 11))
        # 정반사 점
        pygame.draw.circle(self.screen, (255, 205, 165), (cx - 26, cy - 30), 7)
        pygame.draw.circle(self.screen, (255, 248, 240), (cx - 28, cy - 32), 3)

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
            if is_hit:
                iris_c = (255, 255, 100)
            elif enraged:
                iris_c = self._pulse_color((255, 100, 0), (255, 220, 0), self._tick, 20)
            else:
                iris_c = self._pulse_color((255, 80, 40), (255, 220, 60), self._tick, 50)
            pygame.draw.circle(self.screen, iris_c, (ex_abs, ey_abs), 8)
            p_off = max(-3, min(3, look_dx // 3))
            pupil = [
                (ex_abs + p_off,     ey_abs - 6),
                (ex_abs + p_off + 2, ey_abs),
                (ex_abs + p_off,     ey_abs + 6),
                (ex_abs + p_off - 2, ey_abs),
            ]
            pygame.draw.polygon(self.screen, (0, 0, 0), pupil)
            pygame.draw.circle(self.screen, WHITE, (ex_abs - 4 + p_off, ey_abs - 4), 2)

        # ── 입 (공격 모션: 열림) ─────────────────────────────────────────────
        if is_attacking:
            pygame.draw.ellipse(self.screen, (10, 0, 0), (cx - 30, cy + 8, 60, 26))
            pygame.draw.arc(self.screen, (240, 80, 40),
                            (cx - 30, cy + 8, 60, 26), math.pi, 2 * math.pi, 3)
            for i in range(5):
                tx = cx - 22 + i * 11
                pygame.draw.polygon(self.screen, WHITE,
                                    [(tx, cy + 16), (tx + 5, cy + 16), (tx + 2, cy + 22)])
            ec = self._pulse_color((255, 60, 0), (255, 200, 100), self._tick, 12)
            pygame.draw.ellipse(self.screen, ec, (cx - 14, cy + 24, 28, 10))
        else:
            pygame.draw.arc(self.screen, (240, 80, 40),
                            (cx - 32, cy + 6, 64, 26), math.pi, 2 * math.pi, 3)
            for i in range(5):
                tx = cx - 24 + i * 12
                th = 11 if (enraged and i % 2 == 0) else 7
                pygame.draw.polygon(self.screen, WHITE,
                                    [(tx, cy + 16), (tx + 6, cy + 16), (tx + 3, cy + 16 + th)])

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
        lbl_txt = "!! ARCANE BOSS — ENRAGED !!" if enraged else "ARCANE BOSS"
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

        # ── 손 (팜 + 손가락 마디 표현) ─────────────────────────────────────
        skin     = (196, 150, 110)
        skin_mid = (175, 128,  88)
        skin_shd = (138,  96,  66)
        hx, hy   = wx_b - 22, wy_b - 36 + bob // 4

        # 팜 (3레이어로 입체감)
        pygame.draw.ellipse(self.screen, skin_shd, (hx - 22, hy - 16, 50, 40))
        pygame.draw.ellipse(self.screen, skin_mid, (hx - 20, hy - 15, 47, 37))
        pygame.draw.ellipse(self.screen, skin,     (hx - 18, hy - 13, 43, 33))
        # 팜 하이라이트
        pygame.draw.ellipse(self.screen, (216, 170, 130), (hx - 10, hy - 12, 18, 12))
        # 손등 주름
        pygame.draw.line(self.screen, skin_shd, (hx - 16, hy - 11), (hx + 16, hy - 11), 2)
        pygame.draw.line(self.screen, skin_shd, (hx - 12, hy - 6),  (hx + 12, hy - 6),  1)

        # 손가락 (4개 — 마디 2개씩)
        f_data = [(-12, 1), (-4, 0), (4, 1), (12, 0)]
        for fi, (fx_off, bend) in enumerate(f_data):
            fx = hx + fx_off
            fy = hy - 15
            seg1 = 10 + fi % 2
            seg2 = 7
            # 근위 마디
            ex1, ey1 = fx + bend, fy - seg1
            pygame.draw.line(self.screen, skin_shd, (fx, fy), (ex1, ey1), 6)
            pygame.draw.line(self.screen, skin_mid, (fx, fy), (ex1, ey1), 5)
            pygame.draw.line(self.screen, skin,     (fx, fy), (ex1, ey1), 3)
            # 원위 마디
            ex2, ey2 = ex1 + bend, ey1 - seg2
            pygame.draw.line(self.screen, skin_shd, (ex1, ey1), (ex2, ey2), 5)
            pygame.draw.line(self.screen, skin_mid, (ex1, ey1), (ex2, ey2), 4)
            pygame.draw.line(self.screen, skin,     (ex1, ey1), (ex2, ey2), 2)
            # 손끝 + 손톱
            pygame.draw.circle(self.screen, skin_mid, (ex2, ey2), 4)
            pygame.draw.circle(self.screen, skin,     (ex2, ey2), 3)
            pygame.draw.circle(self.screen, (216, 175, 148), (ex2, ey2 - 1), 1)

        # 엄지
        pygame.draw.line(self.screen, skin_shd, (hx - 18, hy - 2), (hx - 27, hy - 10), 7)
        pygame.draw.line(self.screen, skin_mid, (hx - 18, hy - 2), (hx - 27, hy - 10), 6)
        pygame.draw.line(self.screen, skin,     (hx - 18, hy - 2), (hx - 27, hy - 10), 4)
        pygame.draw.circle(self.screen, skin_mid, (hx - 27, hy - 14), 5)
        pygame.draw.circle(self.screen, skin,     (hx - 27, hy - 14), 4)

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
        # 페이셋 라인
        for i, gp in enumerate(gem_pts):
            pygame.draw.line(self.screen, gem_hot, gp, igem[i], 1)
        pygame.draw.polygon(self.screen, gem_hot, gem_pts, 1)
        # 젬 하이라이트
        pygame.draw.circle(self.screen, (255, 255, 255), (wx_t - 4, wy_t - 5), 3)
        pygame.draw.circle(self.screen, (210, 190, 255), (wx_t + 3, wy_t + 3), 2)

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

    # ── Effects ────────────────────────────────────────────────────────────────

    def _draw_effects(self, effects: List[dict], player_offset_x: float = 0.0) -> None:
        W, H = self.W, self.H
        wand_shift  = int(player_offset_x * W * self.WAND_SWAY_GAIN)
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
    ) -> None:
        W, H = self.W, self.H

        # Player HP (bottom-left panel)
        self._draw_hp_panel(18, H - 56, 210, 18, player_hp, PLAYER_MAX_HP, GREEN, "HP")

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
        pygame.draw.rect(self.screen, CYAN, pb, 1, border_radius=5)
        pb_s = self.font_game_tab.render("II ESC", True, CYAN)
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
        pygame.draw.rect(self.screen, GREY, (x, y, w, h), 1, border_radius=4)

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
        col: Tuple[int, int, int],
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
        col: Tuple[int, int, int],
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
        color: Tuple[int, int, int],
        layers: int = 4,
    ) -> None:
        for i in range(layers, 0, -1):
            fade = (i / layers) * 0.45
            c = tuple(int(v * fade) for v in color)
            pygame.draw.circle(self.screen, c, (cx, cy), r + i * 3)

    def _draw_rune_separator(self, y: int) -> None:
        W = self.W
        col = self._pulse_color(RUNE_DIM, RUNE_GLO, self._tick, 60)
        pygame.draw.line(self.screen, col, (W // 4, y), (W * 3 // 4, y), 1)
        for dx in range(-60, 61, 20):
            pygame.draw.circle(self.screen, col, (W // 2 + dx, y), 2)

    def _draw_button(
        self,
        rect:  pygame.Rect,
        label: str,
        color: Tuple[int, int, int],
        font:  Optional[pygame.font.Font] = None,
    ) -> None:
        border = self._pulse_color(tuple(c // 3 for c in color), color, self._tick, 50)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((color[0] // 8, color[1] // 8, color[2] // 8, 200))
        self.screen.blit(bg, rect.topleft)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
        lbl = (font or self.font_big).render(label, True, color)
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
        """Returns a bold font capable of rendering Korean characters.

        Windows 폰트 파일을 직접 로드하여 SysFont fallback 시 깨지는 문제를 방지한다.
        """
        import os
        # 직접 파일 로드 (가장 안정적 — Windows 기본 한국어 폰트)
        win_paths = [
            "C:/Windows/Fonts/malgunbd.ttf",   # Malgun Gothic Bold
            "C:/Windows/Fonts/malgun.ttf",     # Malgun Gothic Regular
            "C:/Windows/Fonts/gulim.ttc",      # 굴림
            "C:/Windows/Fonts/dotum.ttc",      # 돋움
            "C:/Windows/Fonts/batang.ttc",     # 바탕
        ]
        for path in win_paths:
            if os.path.exists(path):
                try:
                    return pygame.font.Font(path, size)
                except Exception:
                    pass
        # SysFont fallback (bold 제거 — 깨짐 방지)
        for name in ("malgungothic", "malgun gothic", "gulim", "dotum", "batang"):
            try:
                f = pygame.font.SysFont(name, size)
                if f is not None:
                    return f
            except Exception:
                pass
        # 최후 fallback — 한국어 미지원일 수 있음
        return pygame.font.SysFont(None, size)

    @staticmethod
    def _pulse_color(
        a: Tuple[int, int, int],
        b: Tuple[int, int, int],
        tick: int,
        period: int,
    ) -> Tuple[int, int, int]:
        t = (math.sin(tick * 2 * math.pi / max(period, 1)) + 1) / 2
        return FPRenderer._lerp_color(a, b, t)

    @staticmethod
    def _lerp_color(
        a: Tuple[int, int, int],
        b: Tuple[int, int, int],
        t: float,
    ) -> Tuple[int, int, int]:
        return (
            int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t),
        )

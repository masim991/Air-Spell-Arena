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
from typing import List, Optional, Tuple

import pygame

# ── Colour palette ─────────────────────────────────────────────────────────────
BLACK    = (0,   0,   0)
WHITE    = (255, 255, 255)
BG_TOP   = (10,   6,  20)
BG_MID   = (16,  10,  30)
BG_BOT   = (8,    5,  16)
FLOOR_C  = (22,  14,  36)
RUNE_DIM = (40,  28,  80)
RUNE_GLO = (100, 70, 200)
RED      = (220, 66,  66)
GREEN    = (66, 200, 120)
YELLOW   = (250, 210,  50)
BLUE     = (70,  130, 250)
CYAN     = (80,  210, 255)
GREY     = (120, 130, 150)
ORANGE   = (255, 160,  60)
PURPLE   = (160, 100, 255)
GOLD     = (255, 200,  40)

PLAYER_MAX_HP = 100
BOSS_MAX_HP   = 100
BROWN         = (150, 110, 60)

# ── Audio-settings slot definitions ────────────────────────────────────────────
_SLOT_ORDER  = ("bgm", "FIRE", "WATER", "WIND", "EARTH", "DARK", "LIGHTNING", "SHIELD")
_SLOT_COLORS = {
    "bgm":       GOLD,
    "FIRE":      ORANGE,
    "WATER":     BLUE,
    "WIND":      GREEN,
    "EARTH":     BROWN,
    "DARK":      PURPLE,
    "LIGHTNING": CYAN,
    "SHIELD":    (80, 200, 220),
}
_SLOT_LABELS = {
    "bgm": "BGM",  "FIRE": "FIRE",   "WATER": "WATER", "WIND": "WIND",
    "EARTH": "EARTH", "DARK": "DARK", "LIGHTNING": "LTNG", "SHIELD": "SHIELD",
}


class FPRenderer:
    """Handles all first-person rendering for the game."""

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
        self.font_kor       = FPRenderer._make_kor_font(22)
        self.font_kor_big   = FPRenderer._make_kor_font(28)
        self.font_game_title = FPRenderer._make_game_font(58)
        self.font_game_tab   = FPRenderer._make_game_font(20)

    # ── Public API ─────────────────────────────────────────────────────────────

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
            sh_s = pygame.Surface(tf.size("AIR SPELL ARENA"), pygame.SRCALPHA)
            sh_t = tf.render("AIR SPELL ARENA", True, (0, 0, 0))
            sh_t.set_alpha(alpha)
            r = sh_t.get_rect(center=(W // 2 + dx, ty + dy))
            self.screen.blit(sh_t, r)

        title_s = tf.render("AIR SPELL ARENA", True, glow_c)
        self.screen.blit(title_s, title_s.get_rect(center=(W // 2, ty)))

        # ── Subtitle ────────────────────────────────────────────────────────
        sub_c = self._pulse_color((80, 70, 110), (160, 140, 200), self._tick, 120)
        sub_f = self.font_game_tab
        sub_s = sub_f.render("✦  Battle the Arcane Boss with Hand Spells  ✦", True, sub_c)
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
                ("3", "Hard", ORANGE), ("4", "Impossible", RED), ("G", "Guide", GOLD)]
        total_w = len(keys) * 88
        kx0 = W // 2 - total_w // 2
        ky  = H * 3 // 4 + 36
        for i, (k_lbl, k_name, k_col) in enumerate(keys):
            kx = kx0 + i * 88
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
    ) -> List[Tuple[pygame.Rect, str, Optional[str]]]:
        """탭 기반 오디오 설정 화면. pending={slot: file|None}, active_slot=현재 탭.

        반환 clickables: [(rect, action, value)]
          action: "slot_tab"   → value=slot 이름 (탭 버튼)
                  slot_name    → value=파일명|None (파일 행 선택, action==active_slot)
                  "preview"    → value=파일명
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
        panel_w, panel_h = W - mx * 2, H - 158 - 56
        row_h = 42

        panel_bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel_bg.fill((14, 9, 28, 220))
        self.screen.blit(panel_bg, (panel_x, panel_y))
        pygame.draw.rect(self.screen, slot_col, (panel_x, panel_y, panel_w, panel_h), 1, border_radius=6)

        # 패널 헤더 (활성 슬롯 이름)
        hdr_txt = _SLOT_LABELS.get(active_slot, active_slot)
        hdr_s   = self.font_game_tab.render(hdr_txt, True, slot_col)
        self.screen.blit(hdr_s, (panel_x + 16, panel_y + 8))
        pygame.draw.line(self.screen, slot_col,
                         (panel_x + 8, panel_y + 34), (panel_x + panel_w - 8, panel_y + 34), 1)

        list_y0  = panel_y + 38
        list_h   = panel_h - 42
        all_opts: List[Optional[str]] = [None] + files
        sel      = pending.get(active_slot)
        max_rows = list_h // row_h

        for i, opt in enumerate(all_opts):
            if i >= max_rows:
                # 파일이 더 있음을 표시
                more_s = self.font_kor.render(f"... +{len(all_opts) - max_rows} more", True, (70, 60, 90))
                self.screen.blit(more_s, (panel_x + 16, list_y0 + max_rows * row_h - 14))
                break

            ry = list_y0 + i * row_h
            disp = "(없음)" if opt is None else (opt if len(opt) <= 46 else opt[:43] + "…")
            is_sel = (opt == sel)

            row_rect = pygame.Rect(panel_x + 8, ry + 2, panel_w - 74, row_h - 4)
            clickables.append((row_rect, active_slot, opt))

            if is_sel:
                hl = pygame.Surface((row_rect.w, row_rect.h), pygame.SRCALPHA)
                rc = slot_col
                hl.fill((rc[0] // 5, rc[1] // 5, rc[2] // 5, 110))
                self.screen.blit(hl, row_rect.topleft)
                pygame.draw.rect(self.screen, slot_col, row_rect, 1, border_radius=4)

            radio_x, radio_y = panel_x + 24, ry + row_h // 2
            pygame.draw.circle(self.screen, GREY, (radio_x, radio_y), 7, 2)
            if is_sel:
                pygame.draw.circle(self.screen, slot_col, (radio_x, radio_y), 4)

            fn_col = slot_col if is_sel else GREY
            fn_s = self.font_kor.render(disp, True, fn_col)
            self.screen.blit(fn_s, (panel_x + 40, ry + row_h // 2 - 9))

            if opt is not None:
                pb = pygame.Rect(panel_x + panel_w - 68, ry + row_h // 2 - 13, 60, 26)
                pygame.draw.rect(self.screen, (30, 25, 60), pb, border_radius=5)
                pygame.draw.rect(self.screen, RUNE_GLO, pb, 1, border_radius=5)
                pb_s = self.font_kor.render("▶ 듣기", True, GREEN)
                self.screen.blit(pb_s, pb_s.get_rect(center=pb.center))
                clickables.append((pb, "preview", opt))

        if not files:
            no_s = self.font_kor.render("sounds/ 폴더에 오디오 파일 없음", True, (70, 60, 90))
            self.screen.blit(no_s, no_s.get_rect(center=(W // 2, list_y0 + 40)))

        # ── 저장 / 뒤로 버튼 ─────────────────────────────────────────────
        btn_save = pygame.Rect(W // 2 - 125, H - 48, 110, 38)
        btn_back = pygame.Rect(W // 2 + 15,  H - 48, 110, 38)
        self._draw_button(btn_save, "저  장", GREEN, self.font_kor_big)
        self._draw_button(btn_back, "뒤  로", GREY,  self.font_kor_big)
        clickables.append((btn_save, "save", None))
        clickables.append((btn_back, "back", None))

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
    ) -> None:
        self._tick += 1

        # 1. Background (with parallax)
        self._draw_bg(player_offset_x)

        # 2. Boss (behind effects)
        self._draw_boss(boss_hp / BOSS_MAX_HP, effects, player_offset_x)

        # 3. Effects (projectiles)
        self._draw_effects(effects, player_offset_x)

        # 4. Shield vignette
        if shield_time_left > 0:
            self._draw_shield_vignette(shield_time_left)

        # 5. Wand
        self._draw_wand(player_offset_x)

        # 6. HUD
        self._draw_hud(player_hp, boss_hp, shield_time_left, lightning_cd_left, difficulty)

        # 7. Spell message
        if message_time_left > 0 and message_text:
            self._draw_spell_message(message_text, message_color, message_time_left)

        pygame.display.flip()

    def render_ending(self, state: str, tick: int) -> None:
        """Render game_over or you_win ending screen."""
        self._tick += 1
        W, H = self.W, self.H
        # Dim background
        self._draw_bg(0.0)
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        if state == "game_over":
            overlay.fill((80, 0, 0, 170))
        else:
            overlay.fill((20, 10, 50, 150))
        self.screen.blit(overlay, (0, 0))

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

    # ── Background ─────────────────────────────────────────────────────────────

    def _draw_bg(self, player_offset_x: float = 0.0) -> None:
        W, H = self.W, self.H
        horizon = H // 2

        # Ceiling gradient
        for y in range(horizon):
            t = y / max(horizon, 1)
            c = self._lerp_color(BG_TOP, BG_MID, t)
            pygame.draw.line(self.screen, c, (0, y), (W, y))

        # Floor gradient
        for y in range(horizon, H):
            t = (y - horizon) / max(H - horizon, 1)
            c = self._lerp_color(FLOOR_C, BG_BOT, t)
            pygame.draw.line(self.screen, c, (0, y), (W, y))

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
        boss_shift = int(-player_offset_x * W * 0.03)
        cx, cy = W // 2 + boss_shift, H // 2 - 28
        enraged = hp_ratio <= 0.35

        # ── Shadow-cloak beneath body ───────────────────────────────────────
        cloak_pts = [
            (cx - 58, cy + 62), (cx - 88, cy + 108), (cx - 50, cy + 118),
            (cx, cy + 124),     (cx + 50, cy + 118),  (cx + 88, cy + 108),
            (cx + 58, cy + 62),
        ]
        pygame.draw.polygon(self.screen, (6, 2, 14), cloak_pts)
        cloak_rim = tuple(max(0, c - 10) for c in ((60, 20, 80)))
        pygame.draw.polygon(self.screen, cloak_rim, cloak_pts, 2)  # type: ignore

        # ── Outer aura ──────────────────────────────────────────────────────
        if enraged:
            aura_r   = int(96 + 14 * math.sin(self._tick * 0.09))
            aura_col = self._pulse_color((200, 20, 0), (255, 80, 0), self._tick, 28)
        else:
            aura_r   = int(78 + 10 * math.sin(self._tick * 0.05))
            aura_col = self._pulse_color((80, 10, 10), (190, 45, 45), self._tick, 55)
        self._draw_glow(cx, cy, aura_r, aura_col, layers=8)

        # ── Horns ───────────────────────────────────────────────────────────
        horn_col = (80, 12, 12)
        horn_rim = (160, 55, 55)
        for side, twist in ((-1, -6), (1, 6)):
            hbx = cx + side * 20
            hby = cy - 63
            htx = cx + side * (30 + twist)
            hty = cy - 112
            pts_h = [(hbx - 9, hby), (htx, hty), (hbx + 9, hby)]
            pygame.draw.polygon(self.screen, horn_col, pts_h)
            pygame.draw.polygon(self.screen, horn_rim, pts_h, 1)
            # Horn tip glow
            self._draw_glow(htx, hty, 5, horn_rim, layers=2)

        # ── Body ────────────────────────────────────────────────────────────
        body_col = (200, 40, 20) if enraged else (170, 35, 35)
        rim_col  = (255, 90, 30) if enraged else (220, 70, 70)
        pygame.draw.circle(self.screen, body_col, (cx, cy), 70)
        pygame.draw.circle(self.screen, rim_col,  (cx, cy), 70, 3)
        pygame.draw.circle(self.screen, (90, 16, 16), (cx + 7, cy + 7), 57)

        # ── Rotating arcane rune markings on body ──────────────────────────
        rune_a1  = self._tick * 0.020
        rune_a2  = -self._tick * 0.030 + math.pi / 6
        rune_col = self._pulse_color((200, 70, 60), (255, 150, 100), self._tick, 55)
        for i in range(6):
            a = rune_a1 + i * math.pi / 3
            rx, ry = cx + int(50 * math.cos(a)), cy + int(50 * math.sin(a))
            pygame.draw.circle(self.screen, rune_col, (rx, ry), 4)
            pygame.draw.line(self.screen, rune_col, (cx, cy), (rx, ry), 1)
        for i in range(4):
            a = rune_a2 + i * math.pi / 2
            rx, ry = cx + int(28 * math.cos(a)), cy + int(28 * math.sin(a))
            pygame.draw.circle(self.screen, (220, 110, 80), (rx, ry), 3)

        # ── Eyes (slit pupils) ──────────────────────────────────────────────
        for ex_off in (-22, 22):
            ex_abs, ey_abs = cx + ex_off, cy - 14
            pygame.draw.circle(self.screen, (0, 0, 0), (ex_abs, ey_abs), 11)
            if enraged:
                iris_c = self._pulse_color((255, 100, 0), (255, 220, 0), self._tick, 20)
            else:
                iris_c = self._pulse_color((255, 80, 40), (255, 220, 60), self._tick, 50)
            pygame.draw.circle(self.screen, iris_c, (ex_abs, ey_abs), 7)
            # Slit pupil (vertical diamond)
            pupil = [
                (ex_abs,     ey_abs - 5),
                (ex_abs + 2, ey_abs),
                (ex_abs,     ey_abs + 5),
                (ex_abs - 2, ey_abs),
            ]
            pygame.draw.polygon(self.screen, (0, 0, 0), pupil)
            pygame.draw.circle(self.screen, WHITE, (ex_abs - 3, ey_abs - 3), 2)

        # ── Mouth / grin ────────────────────────────────────────────────────
        pygame.draw.arc(self.screen, (240, 80, 40),
                        (cx - 32, cy + 6, 64, 26), math.pi, 2 * math.pi, 3)
        for i in range(5):
            tx = cx - 24 + i * 12
            th = 11 if (enraged and i % 2 == 0) else 7
            pygame.draw.polygon(self.screen, WHITE, [
                (tx, cy + 16), (tx + 6, cy + 16), (tx + 3, cy + 16 + th)
            ])

        # ── Energy tendrils ─────────────────────────────────────────────────
        tc_count = 5 if enraged else 3
        for i in range(tc_count):
            base_a = self._tick * 0.038 + i * (math.pi * 2 / tc_count)
            for j in range(10):
                jt   = j / 10.0
                ja   = base_a + math.sin(jt * math.pi * 2 + self._tick * 0.12) * 0.55
                tx_d = cx + int((72 + 38 * jt) * math.cos(ja))
                ty_d = cy + int((72 + 38 * jt) * math.sin(ja))
                fr   = max(1, 4 - j // 3)
                fc_t = tuple(int(c * (1.0 - jt * 0.85)) for c in aura_col)
                pygame.draw.circle(self.screen, fc_t, (tx_d, ty_d), fr)  # type: ignore

        # ── HP bar ──────────────────────────────────────────────────────────
        bw, bh = 168, 13
        bx = cx - bw // 2
        by = cy - 102
        pygame.draw.rect(self.screen, (22, 4, 4), (bx - 2, by - 2, bw + 4, bh + 4), border_radius=5)
        pygame.draw.rect(self.screen, (38, 14, 14), (bx, by, bw, bh), border_radius=5)
        if int(bw * hp_ratio) > 0:
            fill_col = self._pulse_color((220, 30, 30), (255, 110, 0), self._tick, 22) \
                if enraged else self._lerp_color((220, 30, 30), GOLD, hp_ratio)
            pygame.draw.rect(self.screen, fill_col, (bx, by, int(bw * hp_ratio), bh), border_radius=5)
        pygame.draw.rect(self.screen, GREY, (bx, by, bw, bh), 1, border_radius=5)
        lbl_txt = "!! ARCANE BOSS — ENRAGED !!" if enraged else "ARCANE BOSS"
        lbl_col = (255, 110, 0) if enraged else GREY
        hp_lbl = self.font.render(lbl_txt, True, lbl_col)
        self.screen.blit(hp_lbl, hp_lbl.get_rect(center=(cx, by - 14)))

    # ── Wand ───────────────────────────────────────────────────────────────────

    def _draw_wand(self, player_offset_x: float = 0.0) -> None:
        W, H = self.W, self.H
        wand_shift = int(player_offset_x * W * 0.06)

        # Idle breathing bob
        bob = int(math.sin(self._tick * 0.045) * 5)
        wx_b = int(W * 0.82) + wand_shift
        wy_b = H + 10 + bob // 4
        wx_t = int(W * 0.61) + wand_shift
        wy_t = int(H * 0.71) + bob

        # ── Hand / palm ────────────────────────────────────────────────────
        skin     = (195, 148, 108)
        skin_shd = (140, 100, 72)
        hx, hy   = wx_b - 22, wy_b - 34 + bob // 4

        pygame.draw.ellipse(self.screen, skin_shd, (hx - 20, hy - 14, 46, 36))
        pygame.draw.ellipse(self.screen, skin,     (hx - 18, hy - 12, 42, 32))

        # Four fingers curled around shaft
        for fi in range(4):
            fx = hx - 10 + fi * 8
            fy = hy - 13 - fi % 2 * 4
            fr = 5 if fi < 3 else 4
            pygame.draw.circle(self.screen, skin, (fx, fy), fr)
        # Thumb
        pygame.draw.circle(self.screen, skin, (hx - 14, hy - 3), 6)

        # Knuckle shadow
        pygame.draw.line(self.screen, skin_shd, (hx - 18, hy - 8), (hx + 18, hy - 8), 2)

        # ── Wand shaft ─────────────────────────────────────────────────────
        pygame.draw.line(self.screen, (44, 28, 10),  (wx_b, wy_b), (wx_t, wy_t), 10)
        pygame.draw.line(self.screen, (82, 56, 24),  (wx_b - 3, wy_b - 5), (wx_t - 3, wy_t - 5), 3)
        pygame.draw.line(self.screen, (120, 88, 44), (wx_b - 4, wy_b - 6), (wx_t - 4, wy_t - 6), 1)

        # ── Rune wrappings along shaft ──────────────────────────────────────
        for k in range(4):
            t_wrap = 0.18 + k * 0.18
            ww_x = int(wx_b + (wx_t - wx_b) * t_wrap)
            ww_y = int(wy_b + (wy_t - wy_b) * t_wrap)
            wc   = self._pulse_color(RUNE_DIM, RUNE_GLO, self._tick + k * 25, 70)
            pygame.draw.circle(self.screen, (30, 50, 90), (ww_x, ww_y), 7, 3)
            pygame.draw.circle(self.screen, wc,           (ww_x, ww_y), 5, 1)

        # ── Faceted gem at tip ──────────────────────────────────────────────
        gem_col  = self._pulse_color((90, 70, 220),  (190, 150, 255), self._tick, 50)
        gem_core = self._pulse_color((150, 120, 255), (220, 200, 255), self._tick, 38)
        gr = 10
        self._draw_glow(wx_t, wy_t, gr + 14, gem_col, layers=7)

        gem_pts = [
            (wx_t,      wy_t - gr),
            (wx_t + gr, wy_t),
            (wx_t,      wy_t + gr),
            (wx_t - gr, wy_t),
        ]
        pygame.draw.polygon(self.screen, gem_col, gem_pts)
        # Facet inner lines
        for gp in gem_pts:
            pygame.draw.line(self.screen, gem_core, (wx_t, wy_t), gp, 1)
        pygame.draw.polygon(self.screen, gem_core, gem_pts, 1)
        pygame.draw.circle(self.screen, WHITE, (wx_t - 3, wy_t - 3), 2)

        # ── Orbiting energy particles ───────────────────────────────────────
        for k in range(3):
            a   = self._tick * 0.11 + k * math.pi * 2 / 3
            opx = wx_t + int(14 * math.cos(a))
            opy = wy_t + int(9  * math.sin(a))
            oc  = self._pulse_color(gem_col, WHITE, self._tick + k * 18, 28)
            pygame.draw.circle(self.screen, oc, (opx, opy), 2)

    # ── Effects ────────────────────────────────────────────────────────────────

    def _draw_effects(self, effects: List[dict], player_offset_x: float = 0.0) -> None:
        W, H = self.W, self.H
        wand_shift  = int(player_offset_x * W * 0.06)
        boss_shift  = int(-player_offset_x * W * 0.03)
        wand_tip    = (int(W * 0.61) + wand_shift, int(H * 0.71))
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
                    cast_wand_shift = int(cast_off * W * 0.06)
                    sx = int(W * 0.61) + cast_wand_shift
                    sy = int(H * 0.71)
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
                cx, cy = wand_tip
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
                cx_w = int(W * 0.61)
                cy_w = int(H * 0.71)
                fade = max(0.0, 1.0 - t)
                col = tuple(int(v * fade) for v in e["color"])

                self._draw_glow(cx_w, cy_w, max(8, r // 2), col, layers=4)
                pygame.draw.circle(self.screen, col, (cx_w, cy_w), r, e["w"])
                pygame.draw.circle(self.screen, col, (cx_w, cy_w), max(8, r - 10), 1)

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

        # Difficulty badge (top-right)
        diff_colors = {"easy": GREEN, "normal": YELLOW, "hard": ORANGE, "impossible": RED}
        dc = diff_colors.get(difficulty, WHITE)
        badge = self.font.render(f"[{difficulty.upper()}]", True, dc)
        self.screen.blit(badge, (W - badge.get_width() - 14, 14))

        # ESC hint
        esc = self.font.render("ESC: quit", True, GREY)
        self.screen.blit(esc, (W - esc.get_width() - 14, H - 22))

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
        """Returns a system font capable of rendering Korean characters."""
        for name in ("malgungothic", "malgun gothic", "gulim", "dotum", "batang"):
            try:
                f = pygame.font.SysFont(name, size)
                if f is not None:
                    return f
            except Exception:
                pass
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

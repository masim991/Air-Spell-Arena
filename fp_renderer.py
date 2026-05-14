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
from typing import List, Tuple

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

    # ── Public API ─────────────────────────────────────────────────────────────

    def render_menu(
        self,
        btn_start:  pygame.Rect,
        btn_exit:   pygame.Rect,
        btn_guide:  pygame.Rect,
        difficulty: str,
    ) -> None:
        self._tick += 1
        W, H = self.W, self.H

        self._draw_bg()

        # Title glow
        glow   = self._pulse_color((120, 60, 255), (220, 150, 255), self._tick, 90)
        title_f = pygame.font.SysFont(None, 64)
        title  = title_f.render("AIR SPELL ARENA", True, glow)
        shadow = title_f.render("AIR SPELL ARENA", True, (20, 10, 50))
        tc = title.get_rect(center=(W // 2, H // 4))
        self.screen.blit(shadow, (tc.x + 3, tc.y + 3))
        self.screen.blit(title, tc)

        sub = self.font.render("Draw spells with your hand to battle the Arcane Boss!", True, GREY)
        self.screen.blit(sub, sub.get_rect(center=(W // 2, H // 4 + 52)))

        self._draw_rune_separator(H // 4 + 76)

        self._draw_button(btn_start, "START",      CYAN)
        self._draw_button(btn_exit,  "EXIT",       RED)
        self._draw_button(btn_guide, "SPELL GUIDE", GOLD)

        diff_colors = {"easy": GREEN, "normal": YELLOW, "hard": ORANGE, "impossible": RED}
        dc = diff_colors.get(difficulty, WHITE)
        diff_surf = self.font_big.render(f"DIFFICULTY: {difficulty.upper()}", True, dc)
        self.screen.blit(diff_surf, diff_surf.get_rect(center=(W // 2, H * 3 // 4)))
        hint = self.font.render("1:Easy  2:Normal  3:Hard  4:Impossible   G:Spell Guide", True, GREY)
        self.screen.blit(hint, hint.get_rect(center=(W // 2, H * 3 // 4 + 34)))

        pygame.display.flip()

    def render_tutorial(self, tick: int) -> None:
        """Full-screen spell & control guide."""
        self._tick += 1
        W, H = self.W, self.H

        self._draw_bg(0.0)

        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 155))
        self.screen.blit(overlay, (0, 0))

        # Title
        tc = self._pulse_color(GOLD, WHITE, tick, 80)
        tf = pygame.font.SysFont(None, 54)
        ts = tf.render("SPELL  GUIDE", True, tc)
        self.screen.blit(ts, ts.get_rect(center=(W // 2, 42)))
        pygame.draw.line(self.screen, RUNE_DIM, (W // 8, 68), (W * 7 // 8, 68), 1)

        # Gesture entries: (icon_type, label, description, color)
        entries = [
            ("palm",    "FIRE",       "Open PALM  (all fingers)",  ORANGE),
            ("fist",    "WATER",      "Make a FIST",               BLUE),
            ("thumb",   "EARTH",      "THUMBS UP",                 GREY),
            ("index",   "WIND",       "INDEX finger only",         GREEN),
            ("left",    "LIGHT",      "Swipe hand LEFT",           CYAN),
            ("right",   "DARK",       "Swipe hand RIGHT",          PURPLE),
            ("circle",  "SHIELD",     "Draw a CIRCLE",             CYAN),
            ("zigzag",  "LIGHTNING",  "Draw a ZIGZAG",             BLUE),
            ("head_l",  "DODGE LEFT", "Turn head LEFT",            WHITE),
            ("head_r",  "DODGE RIGHT","Turn head RIGHT",           WHITE),
        ]

        cols   = 2
        rows   = (len(entries) + 1) // cols
        cx_gap = W // cols
        row_h  = (H - 120) // rows
        y0     = 90

        for i, (icon, label, desc, col) in enumerate(entries):
            col_i = i % cols
            row_i = i // cols
            cx = cx_gap * col_i + cx_gap // 2
            cy = y0 + row_i * row_h + row_h // 2

            # Card background
            cw, ch = cx_gap - 20, row_h - 14
            card = pygame.Surface((cw, ch), pygame.SRCALPHA)
            card.fill((10, 6, 24, 160))
            self.screen.blit(card, (cx - cw // 2, cy - ch // 2))
            pygame.draw.rect(
                self.screen, tuple(max(0, c // 3) for c in col),
                (cx - cw // 2, cy - ch // 2, cw, ch), 1, border_radius=6
            )

            # Icon
            icon_x = cx - cw // 2 + 32
            self._draw_gesture_icon(icon_x, cy, icon, col, tick)

            # Text
            spell_s = self.font_big.render(label, True, col)
            desc_s  = self.font.render(desc,  True, GREY)
            tx = icon_x + 42
            self.screen.blit(spell_s, (tx, cy - spell_s.get_height() // 2 - 2))
            self.screen.blit(desc_s,  (tx, cy + spell_s.get_height() // 2 + 2))

        prompt_col = WHITE if (tick // 35) % 2 == 0 else GREY
        pr = self.font.render("Press ENTER / SPACE / ESC  to return", True, prompt_col)
        self.screen.blit(pr, pr.get_rect(center=(W // 2, H - 22)))

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
        # Boss is far away — very small parallax shift
        boss_shift = int(-player_offset_x * W * 0.03)
        cx, cy = W // 2 + boss_shift, H // 2 - 28

        # Pulsing outer aura
        aura_r = int(76 + 9 * math.sin(self._tick * 0.05))
        aura_col = self._pulse_color((80, 10, 10), (180, 40, 40), self._tick, 55)
        self._draw_glow(cx, cy, aura_r, aura_col, layers=6)

        # Boss body
        body_col = (170, 35, 35)
        rim_col  = (220, 70, 70)
        pygame.draw.circle(self.screen, body_col, (cx, cy), 70)
        pygame.draw.circle(self.screen, rim_col,  (cx, cy), 70, 3)

        # Dark inner shadow
        pygame.draw.circle(self.screen, (100, 20, 20), (cx + 6, cy + 6), 58)

        # Eyes
        for dx, eye_off in ((-22, -1), (22, 1)):
            eye_col = self._pulse_color((255, 80, 40), (255, 220, 60), self._tick + eye_off * 20, 50)
            pygame.draw.circle(self.screen, (0, 0, 0), (cx + dx, cy - 14), 11)
            pygame.draw.circle(self.screen, eye_col,   (cx + dx, cy - 14),  7)
            pygame.draw.circle(self.screen, WHITE,     (cx + dx - 3, cy - 17), 3)

        # Mouth (menacing grin)
        pygame.draw.arc(
            self.screen, (240, 80, 40),
            (cx - 32, cy + 6, 64, 26),
            math.pi, 2 * math.pi, 3,
        )
        # Teeth
        for i in range(4):
            tx = cx - 20 + i * 14
            pygame.draw.rect(self.screen, WHITE, (tx, cy + 16, 8, 8))

        # Boss HP bar above boss
        bw = 150
        bh = 12
        bx = cx - bw // 2
        by = cy - 88
        pygame.draw.rect(self.screen, (30, 8, 8), (bx - 2, by - 2, bw + 4, bh + 4), border_radius=4)
        pygame.draw.rect(self.screen, (40, 15, 15), (bx, by, bw, bh), border_radius=4)
        if int(bw * hp_ratio) > 0:
            fill_col = self._lerp_color((220, 30, 30), GOLD, hp_ratio)
            pygame.draw.rect(self.screen, fill_col, (bx, by, int(bw * hp_ratio), bh), border_radius=4)
        pygame.draw.rect(self.screen, GREY, (bx, by, bw, bh), 1, border_radius=4)
        hp_lbl = self.font.render("BOSS", True, GREY)
        self.screen.blit(hp_lbl, hp_lbl.get_rect(center=(cx, by - 12)))

    # ── Wand ───────────────────────────────────────────────────────────────────

    def _draw_wand(self, player_offset_x: float = 0.0) -> None:
        W, H = self.W, self.H
        # Wand shifts with player (close to camera — large parallax)
        wand_shift = int(player_offset_x * W * 0.06)
        wx_b, wy_b = int(W * 0.82) + wand_shift, H + 10
        wx_t, wy_t = int(W * 0.61) + wand_shift, int(H * 0.71)

        # Wand shaft (wood)
        pygame.draw.line(self.screen, (60, 38, 16),  (wx_b, wy_b), (wx_t, wy_t), 8)
        pygame.draw.line(self.screen, (100, 68, 30), (wx_b - 2, wy_b - 4), (wx_t - 2, wy_t - 4), 3)

        # Gem / tip glow
        tip_col = self._pulse_color((90, 70, 220), (190, 150, 255), self._tick, 50)
        self._draw_glow(wx_t, wy_t, 16, tip_col, layers=5)
        pygame.draw.circle(self.screen, tip_col, (wx_t, wy_t), 6)
        pygame.draw.circle(self.screen, WHITE,   (wx_t - 2, wy_t - 2), 2)

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
                    sx, sy = wand_tip
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
    ) -> None:
        border = self._pulse_color(tuple(c // 3 for c in color), color, self._tick, 50)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((color[0] // 8, color[1] // 8, color[2] // 8, 200))
        self.screen.blit(bg, rect.topleft)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
        lbl = self.font_big.render(label, True, color)
        self.screen.blit(lbl, lbl.get_rect(center=rect.center))

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

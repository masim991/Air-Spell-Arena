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
        btn_start: pygame.Rect,
        btn_exit:  pygame.Rect,
        difficulty: str,
    ) -> None:
        self._tick += 1
        W, H = self.W, self.H

        self._draw_bg()

        # Title glow
        glow = self._pulse_color((120, 60, 255), (220, 150, 255), self._tick, 90)
        title_f = pygame.font.SysFont(None, 64)
        title = title_f.render("AIR SPELL ARENA", True, glow)
        shadow = title_f.render("AIR SPELL ARENA", True, (20, 10, 50))
        tc = title.get_rect(center=(W // 2, H // 4))
        self.screen.blit(shadow, (tc.x + 3, tc.y + 3))
        self.screen.blit(title, tc)

        # Subtitle
        sub = self.font.render("Draw spells with your hand to battle the Arcane Boss!", True, GREY)
        self.screen.blit(sub, sub.get_rect(center=(W // 2, H // 4 + 52)))

        # Rune separator
        self._draw_rune_separator(H // 4 + 76)

        # Buttons
        self._draw_button(btn_start, "START", CYAN)
        self._draw_button(btn_exit,  "EXIT",  RED)

        # Difficulty selector
        diff_colors = {"easy": GREEN, "normal": YELLOW, "hard": ORANGE, "impossible": RED}
        dc = diff_colors.get(difficulty, WHITE)
        diff_surf = self.font_big.render(f"DIFFICULTY: {difficulty.upper()}", True, dc)
        self.screen.blit(diff_surf, diff_surf.get_rect(center=(W // 2, H * 3 // 4)))
        hint = self.font.render("1: Easy   2: Normal   3: Hard   4: Impossible", True, GREY)
        self.screen.blit(hint, hint.get_rect(center=(W // 2, H * 3 // 4 + 34)))

        # Spell legend
        legend_items = [
            ("LINE  →  Fire", ORANGE),
            ("CIRCLE  →  Shield", CYAN),
            ("ZIGZAG  →  Lightning", BLUE),
        ]
        lx = W // 2 - 160
        ly = H * 3 // 4 + 70
        for txt, col in legend_items:
            ls = self.font.render(txt, True, col)
            self.screen.blit(ls, (lx, ly))
            lx += ls.get_width() + 30

        pygame.display.flip()

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

                self._draw_glow(px, py, draw_r + 5, color, layers=4)
                pygame.draw.circle(self.screen, color, (px, py), draw_r)

                for step in range(1, 5):
                    trail_t = max(0.0, t - step * 0.045)
                    tx2 = int(sx + (ex - sx) * trail_t)
                    ty2 = int(sy + (ey - sy) * trail_t)
                    tr = max(1, draw_r - step * 2)
                    tc = tuple(max(0, int(c * (1.0 - step * 0.22))) for c in color)

                    if style in ("wind", "lightning"):
                        pygame.draw.line(
                            self.screen, tc,
                            (tx2 - tr * 2, ty2), (tx2 + tr * 2, ty2),
                            max(1, tr // 2),
                        )
                    elif style == "earth":
                        pygame.draw.rect(self.screen, tc, (tx2 - tr, ty2 - tr, tr * 2, tr * 2))
                    else:
                        pygame.draw.circle(self.screen, tc, (tx2, ty2), tr)

            elif etype == "cast":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                cx, cy = wand_tip
                r = int(e["r0"] + (e["r1"] - e["r0"]) * t)
                fade = max(0.0, 1.0 - t)
                col = tuple(int(c * fade) for c in e["color"])

                self._draw_glow(cx, cy, r, col, layers=5)
                pygame.draw.circle(self.screen, col, (cx, cy), max(2, r // 3))
                pygame.draw.circle(self.screen, col, (cx, cy), max(5, r), 1)

            elif etype == "impact":
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])))
                cx, cy = boss_center
                r = int(e["r0"] + (e["r1"] - e["r0"]) * t)
                fade = max(0.0, 1.0 - t)
                col = tuple(int(c * fade) for c in e["color"])
                style = e.get("style", "fire")

                self._draw_glow(cx, cy, r, col, layers=4)
                pygame.draw.circle(self.screen, col, (cx, cy), r, 2)

                if style == "fire":
                    for i in range(6):
                        ang = self._tick * 0.08 + i * 1.04
                        fpx = int(cx + math.cos(ang) * r * 0.7)
                        fpy = int(cy + math.sin(ang) * r * 0.45)
                        pygame.draw.circle(self.screen, col, (fpx, fpy), max(1, 5 - int(t * 4)))
                elif style == "water":
                    pygame.draw.circle(self.screen, col, (cx, cy), max(3, r // 2), 1)
                elif style == "wind":
                    pygame.draw.circle(self.screen, col, (cx, cy), r, 1)
                    pygame.draw.circle(self.screen, col, (cx, cy), max(4, r - 8), 1)
                elif style == "earth":
                    for i in range(5):
                        epx = cx + (i - 2) * 8
                        epy = cy + 8 + (i % 2) * 6
                        pygame.draw.rect(self.screen, col, (epx, epy, 6, 6))
                elif style == "dark":
                    pygame.draw.circle(self.screen, col, (cx, cy), max(4, r // 2))
                elif style in ("lightning", "boss"):
                    pygame.draw.line(self.screen, col, (cx - r, cy), (cx + r, cy), 2)
                    pygame.draw.line(self.screen, col, (cx, cy - r // 2), (cx, cy + r // 2), 2)

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

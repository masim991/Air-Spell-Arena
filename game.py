from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List

import math
import random
import pygame
from fp_renderer import FPRenderer


# ── 화면/렌더 상수 ─────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 900, 600
FPS = 60

# 색상
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BG = (24, 26, 32)
RED = (220, 66, 66)
GREEN = (66, 200, 120)
YELLOW = (250, 210, 50)
BLUE = (70, 130, 250)
CYAN = (80, 210, 255)
GREY = (120, 130, 150)
ORANGE = (255, 160, 60)
PURPLE = (160, 100, 255)

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

ELEMENT_PRESETS = {
    "FIRE": {
        "color": ORANGE,
        "style": "fire",
        "dmg": FIRE_DMG,
        "dur": PROJECTILE_DURATION_MS,
    },
    "WATER": {
        "color": BLUE,
        "style": "water",
        "dmg": FIRE_DMG - 1,
        "dur": PROJECTILE_DURATION_MS + 40,
    },
    "WIND": {
        "color": GREEN,
        "style": "wind",
        "dmg": FIRE_DMG - 2,
        "dur": PROJECTILE_DURATION_MS - 40,
    },
    "EARTH": {
        "color": GREY,
        "style": "earth",
        "dmg": FIRE_DMG + 2,
        "dur": PROJECTILE_DURATION_MS + 80,
    },
    "DARK": {
        "color": PURPLE,
        "style": "dark",
        "dmg": FIRE_DMG,
        "dur": PROJECTILE_DURATION_MS + 20,
    },
    "LIGHTNING": {
        "color": BLUE,
        "style": "lightning",
        "dmg": LIGHTNING_DMG,
        "dur": max(280, PROJECTILE_DURATION_MS - 120),
    },
}


# 마법진 색상 매핑 (원소별)
MAGIC_CIRCLE_COLORS = {
    "FIRE":      (220,  55,  35),
    "WATER":     ( 40, 110, 255),
    "EARTH":     (160,  95,  30),
    "WIND":      ( 55, 195, 100),
    "LIGHT":     (235, 235, 245),
    "DARK":      (140, 145, 165),
    "LIGHTNING": ( 80, 200, 255),
    "SHIELD":    ( 80, 210, 255),
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

        self.player_pos = (150, SCREEN_H // 2)
        self.boss_pos = (SCREEN_W - 150, SCREEN_H // 2)
        self.player_r = 40
        self.boss_r = 48
        # 부동소수 좌표(헤드 무브 스무딩용)
        self._player_fx, self._player_fy = float(self.player_pos[0]), float(self.player_pos[1])
        self._player_speed_px_s = 520.0
        self._arena_min_x = self.player_r + 30
        self._arena_max_x = SCREEN_W - (self.player_r + 30)

        # 효과/버프/쿨다운
        self.shield_time_left = 0
        self.lightning_cd_left = 0

        # 보스 공격 주기 타이머
        self._boss_attack_timer = 0

        # UI 메시지
        self.message_text = ""
        self.message_time_left = 0
        self.message_color = WHITE

        # 상태/메뉴
        self._state = "menu"  # 'menu' | 'tutorial' | 'playing' | 'game_over' | 'you_win'
        self._btn_start = pygame.Rect(SCREEN_W//2 - 120, SCREEN_H//2 - 30, 110, 50)
        self._btn_exit  = pygame.Rect(SCREEN_W//2 + 10,  SCREEN_H//2 - 30, 110, 50)
        self._btn_guide = pygame.Rect(SCREEN_W//2 - 55,  SCREEN_H//2 + 38,  110, 38)

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
        # 이벤트 처리
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
            if self._state == "menu":
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._state = "playing"
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
                        self._state = "playing"
                    elif self._btn_exit.collidepoint(mx, my):
                        return False
                    elif self._btn_guide.collidepoint(mx, my):
                        self._state = "tutorial"
                        self._tick_tutorial = 0
            elif self._state == "tutorial":
                if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE, pygame.K_g
                ):
                    self._state = "menu"
            elif self._state in ("game_over", "you_win"):
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._reset_game()

        # 엔딩/메뉴 상태는 게임 로직 없이 렌더만
        if self._state == "menu":
            self.clock.tick(FPS)
            self._render_menu()
            return True
        if self._state == "tutorial":
            self.clock.tick(FPS)
            self._fp.render_tutorial(self._tick_tutorial)
            self._tick_tutorial += 1
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
            self.apply_spell(spell_name)

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

        # 렌더
        self._render()
        return True

    def apply_spell(self, spell_name: str) -> SpellResult:
        label = spell_name.upper()

        if label in ("LINE", "FIRE"):
            p = ELEMENT_PRESETS["FIRE"]
            self._spawn_player_projectile(
                element="FIRE",
                color=p["color"],
                dmg=p["dmg"],
                dur_ms=p["dur"],
                style=p["style"],
            )
            self._spawn_cast_effect(p["color"], p["style"])
            self._spawn_magic_circle("FIRE")
            self._toast("FIRE!", YELLOW)
            return SpellResult("FIRE", True)

        if label == "WATER":
            p = ELEMENT_PRESETS["WATER"]
            self._spawn_player_projectile(
                element="WATER",
                color=p["color"],
                dmg=p["dmg"],
                dur_ms=p["dur"],
                style=p["style"],
            )
            self._spawn_cast_effect(p["color"], p["style"])
            self._spawn_magic_circle("WATER")
            self._toast("WATER!", BLUE)
            return SpellResult("WATER", True)

        if label == "WIND":
            p = ELEMENT_PRESETS["WIND"]
            self._spawn_player_projectile(
                element="WIND",
                color=p["color"],
                dmg=p["dmg"],
                dur_ms=p["dur"],
                style=p["style"],
            )
            self._spawn_cast_effect(p["color"], p["style"])
            self._spawn_magic_circle("WIND")
            self._toast("WIND!", GREEN)
            return SpellResult("WIND", True)

        if label == "EARTH":
            p = ELEMENT_PRESETS["EARTH"]
            self._spawn_player_projectile(
                element="EARTH",
                color=p["color"],
                dmg=p["dmg"],
                dur_ms=p["dur"],
                style=p["style"],
            )
            self._spawn_cast_effect(p["color"], p["style"])
            self._spawn_magic_circle("EARTH")
            self._toast("EARTH!", GREY)
            return SpellResult("EARTH", True)

        if label == "DARK":
            p = ELEMENT_PRESETS["DARK"]
            self._spawn_player_projectile(
                element="DARK",
                color=p["color"],
                dmg=p["dmg"],
                dur_ms=p["dur"],
                style=p["style"],
            )
            self._spawn_cast_effect(p["color"], p["style"])
            self._spawn_magic_circle("DARK")
            self._toast("DARK!", PURPLE)
            return SpellResult("DARK", True)

        if label in ("CIRCLE", "LIGHT"):
            self.shield_time_left = SHIELD_DURATION_MS
            self._spawn_shield_ring()
            self._spawn_cast_effect(CYAN, "light")
            self._spawn_magic_circle("LIGHT")
            self._toast(f"SHIELD ({SHIELD_DURATION_MS // 1000}s)", CYAN)
            return SpellResult("SHIELD", True)

        if label in ("ZIGZAG", "LIGHTNING"):
            if self.lightning_cd_left <= 0:
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
                self._toast("LIGHTNING!", BLUE)
                return SpellResult("LIGHTNING", True)
            self._toast("LIGHTNING (cooldown)", GREY)
            return SpellResult("LIGHTNING", False, "cooldown")

        self._toast(f"UNKNOWN: {spell_name}", GREY)
        return SpellResult("UNKNOWN", False, "unrecognized")

    def close(self) -> None:
        """게임을 종료하고 Pygame을 정리합니다."""
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

    def _update_boss_ai(self, dt_ms: int) -> None:
        # 매우 단순한 보스: 주기적으로 투사체 발사(피해는 명중 시점에 적용)
        self._boss_attack_timer += dt_ms
        while self._boss_attack_timer >= BOSS_ATTACK_INTERVAL_MS:
            self._boss_attack_timer -= BOSS_ATTACK_INTERVAL_MS
            self._spawn_boss_projectile(dmg=BOSS_DMG)

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
        self.player_pos = (150, SCREEN_H // 2)
        self.boss_pos   = (SCREEN_W - 150, SCREEN_H // 2)
        self._player_fx = float(self.player_pos[0])
        self._player_fy = float(self.player_pos[1])
        self.shield_time_left  = 0
        self.lightning_cd_left = 0
        self._boss_attack_timer = 0
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
        if head_dir not in ("LEFT", "RIGHT"):
            # 천천히 중심으로 복귀는 생략, 정지
            vx = 0.0
        else:
            vx = (-1.0 if head_dir == "LEFT" else 1.0) * self._player_speed_px_s
        self._player_fx = max(self._arena_min_x, min(self._arena_max_x, self._player_fx + vx * (dt_ms / 1000.0)))
        # 정수 좌표로 반영
        self.player_pos = (int(round(self._player_fx)), self.player_pos[1])

    # ── 렌더링 ──────────────────────────────────────────────────────────────

    def _render(self) -> None:
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
        )

    # 메뉴 렌더
    def _render_menu(self) -> None:
        self._fp.render_menu(
            btn_start=self._btn_start,
            btn_exit=self._btn_exit,
            btn_guide=self._btn_guide,
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
    ) -> None:
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
        })

    def _spawn_boss_projectile(self, dmg: int) -> None:
        self._effects.append({
            "type": "proj",
            "element": "BOSS",
            "style": "boss",
            "color": RED,
            "start": self.boss_pos,
            "end": self.player_pos,
            "elapsed": 0,
            "dur": PROJECTILE_DURATION_MS,
            "r": 8,
            "origin": "boss",
            "target": "player",
            "dmg": int(dmg),
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
                    prob = getattr(self, "_boss_dodge_prob", 0.4)
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
                            self._deal_boss_damage(e.get("dmg", 0))
                            self._spawn_impact_effect(e["color"], e.get("style", "fire"), True)
                            self._toast(f"HIT -{e.get('dmg', 0)} HP", YELLOW)
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

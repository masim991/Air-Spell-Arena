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
BOSS_ATTACK_INTERVAL_MS = 1000

MESSAGE_DURATION_MS = 1500
PROJECTILE_DURATION_MS = 450
RING_DURATION_MS = 350

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
        self._state = "menu"  # 'menu' | 'playing'
        self._btn_start = pygame.Rect(SCREEN_W//2 - 120, SCREEN_H//2 - 30, 110, 50)
        self._btn_exit  = pygame.Rect(SCREEN_W//2 + 10,  SCREEN_H//2 - 30, 110, 50)

        # 이펙트
        self._effects: List[dict] = []

        # 난이도(보스 회피 확률)
        self.set_difficulty("normal")

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
                    self._toast(f"Difficulty: {self.difficulty}", WHITE)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if self._btn_start.collidepoint(mx, my):
                        self._state = "playing"
                    elif self._btn_exit.collidepoint(mx, my):
                        return False

        # 메뉴 상태이면 메뉴만 렌더하고 리턴
        if self._state == "menu":
            self.clock.tick(FPS)
            self._render_menu()
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

        # 렌더
        self._render()
        return True

    def apply_spell(self, spell_name: str) -> SpellResult:
        """주문명을 게임 상태에 반영합니다.

        LINE → FIRE: 보스에게 피해
        CIRCLE → SHIELD: 플레이어 보호막(피해 감소)
        ZIGZAG → LIGHTNING: 높은 피해, 쿨다운 존재
        """
        label = spell_name.upper()
        if label in ("LINE", "FIRE"):
            self._spawn_player_projectile(color=ORANGE, dmg=FIRE_DMG, dur_ms=PROJECTILE_DURATION_MS)
            self._toast("FIRE!", YELLOW)
            return SpellResult("FIRE", True)

        if label in ("CIRCLE", "LIGHT"):
            self.shield_time_left = SHIELD_DURATION_MS
            self._spawn_shield_ring()
            self._toast("SHIELD ({}s)".format(SHIELD_DURATION_MS // 1000), CYAN)
            return SpellResult("SHIELD", True)

        if label in ("ZIGZAG", "LIGHTNING"):
            if self.lightning_cd_left <= 0:
                self.lightning_cd_left = LIGHTNING_COOLDOWN_MS
                self._spawn_player_projectile(color=BLUE, dmg=LIGHTNING_DMG, dur_ms=max(280, PROJECTILE_DURATION_MS - 120))
                self._toast("LIGHTNING!", BLUE)
                return SpellResult("LIGHTNING", True)
            else:
                self._toast("LIGHTNING (cooldown)", GREY)
                return SpellResult("LIGHTNING", False, "cooldown")

        if label in ("WATER", "WIND", "EARTH", "DARK"):
            color = PURPLE if label == "DARK" else BLUE if label == "WATER" else GREEN if label == "WIND" else GREY
            self._spawn_player_projectile(color=color, dmg=FIRE_DMG, dur_ms=PROJECTILE_DURATION_MS)
            self._toast(label, WHITE)
            return SpellResult(label, True)

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
        )

    # 메뉴 렌더
    def _render_menu(self) -> None:
        self._fp.render_menu(
            btn_start=self._btn_start,
            btn_exit=self._btn_exit,
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
    def _spawn_player_projectile(self, color: Tuple[int, int, int], dmg: int, dur_ms: int) -> None:
        self._effects.append({
            "type": "proj",
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

    def _spawn_shield_ring(self) -> None:
        self._effects.append({
            "type": "ring",
            "color": CYAN,
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
                # 보스 회피 체크(플레이어 발사 투사체만)
                t = max(0.0, min(1.0, e["elapsed"] / float(e["dur"])) )
                if e.get("origin") == "player" and not e.get("dodge_checked", False) and 0.6 <= t <= 0.9:
                    prob = getattr(self, "_boss_dodge_prob", 0.4)
                    if random.random() < prob:
                        # 보스 좌우 대시로 회피
                        direction = -1 if random.random() < 0.5 else 1
                        dash_px = max(90, int(self.boss_r * 2))
                        new_x = max(self.boss_r + 30, min(SCREEN_W - (self.boss_r + 30), self.boss_pos[0] + direction * dash_px))
                        self.boss_pos = (new_x, self.boss_pos[1])
                        e["dodged"] = True
                        self._toast("BOSS DODGE!", GREY, keep_if_longer=True)
                    e["dodge_checked"] = True

                # 투사체가 끝점에 도달하면 명중/빗나감 판정하고 종료
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
                            self._toast(f"HIT -{e.get('dmg', 0)} HP", YELLOW)
                        else:
                            self._toast("MISS", GREY, keep_if_longer=True)
                    else:  # target == player
                        tx, ty = self.player_pos
                        thr = self.player_r + e.get("r", 8)
                        if math.hypot(hit_x - tx, hit_y - ty) <= thr:
                            self._deal_player_damage(e.get("dmg", 0))
                        else:
                            self._toast("DODGED!", CYAN, keep_if_longer=True)
                    continue  # 이 이펙트는 완료되어 alive에 추가하지 않음

            # 진행 중 이펙트는 유지
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

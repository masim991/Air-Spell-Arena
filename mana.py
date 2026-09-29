from __future__ import annotations
"""
mana.py — 시전 자원(마나) 시스템.

설계 의도
---------
기존 빌드는 주문 시전에 아무 비용이 없어서 "인식되는 대로 계속 난사"가
유일한 최적해였다. 마나는 그 평면을 세 방향으로 세운다:

1. **선택 압박** — 약한 주문을 자주 쓸지, 마나를 모아 콤보를 터뜨릴지.
2. **리듬** — 회복 대기 구간이 생기며 자연스럽게 손을 내릴 틈이 생긴다.
   (고릴라 암 완화: 팔을 계속 들고 있을 이유 자체를 없앤다.)
3. **룬 훅** — runes.py 의 성장 옵션이 붙을 지점을 제공한다.

수치는 "한 페이즈에서 기본 주문 5~6회, 또는 콤보 2회"를 기준으로 잡았다.
"""

from dataclasses import dataclass
from typing import Dict, Optional


MAX_MANA: float = 100.0

# 초당 자연 회복량. 기본 주문(14)을 약 0.8초마다 한 번 쓸 수 있는 속도.
BASE_REGEN_PER_SEC: float = 18.0

# 마나가 바닥난 직후 짧게 회복이 멈추는 탈진 시간(ms).
# 완전 고갈을 "그냥 기다리면 됨"이 아니라 피해야 할 실수로 만든다.
EXHAUST_LOCK_MS: int = 700

# 주문별 시전 비용. _SPELL_DB 의 위력 등급과 1:1로 맞춘다.
SPELL_COST: Dict[str, float] = {
    # 기본 원소 — 싸고 빠르게
    "FIRE": 14.0,
    "WATER": 13.0,
    "WIND": 11.0,
    "EARTH": 16.0,
    "DARK": 14.0,
    "LIGHT": 20.0,        # 실드는 생존 가치가 높으므로 비싸게
    "LIGHTNING": 30.0,
    # 콤보 — 마나를 모아야만 나가는 피니셔
    "STEAM": 26.0,
    "MUD": 28.0,
    "FLAME_BALL": 36.0,
    "ICE_SHARD": 34.0,
    "TORNADO": 32.0,
    "STONE_BULLET": 33.0,
    "BLINDNESS": 24.0,
    "CURSE_SHOCK": 38.0,
}

DEFAULT_COST: float = 14.0


def cost_of(spell_name: str) -> float:
    """주문 1회 시전 비용. 미등록 주문은 기본값."""
    return SPELL_COST.get(spell_name.upper(), DEFAULT_COST)


@dataclass
class ManaPool:
    """플레이어의 시전 자원.

    게임 루프에서 매 프레임 `update(dt_ms)` 를 호출하고, 주문을 쓸 때
    `try_spend(name)` 로 차감한다. 룬 효과는 `regen_mult` / `cost_mult` 로 주입된다.
    """

    current: float = MAX_MANA
    maximum: float = MAX_MANA
    regen_per_sec: float = BASE_REGEN_PER_SEC

    # 룬/버프 배율 (runes.py 가 갱신)
    regen_mult: float = 1.0
    cost_mult: float = 1.0

    # 내부 상태
    exhaust_left_ms: int = 0
    _last_spend_failed: bool = False

    # ── 프레임 갱신 ─────────────────────────────────────────────────────
    def update(self, dt_ms: int) -> None:
        """자연 회복 + 탈진 타이머 진행."""
        if self.exhaust_left_ms > 0:
            self.exhaust_left_ms = max(0, self.exhaust_left_ms - dt_ms)
            return
        if self.current < self.maximum:
            gain = self.regen_per_sec * self.regen_mult * (dt_ms / 1000.0)
            self.current = min(self.maximum, self.current + gain)

    # ── 시전 ────────────────────────────────────────────────────────────
    # `mult` 는 시전 방식에 따른 추가 배율이다(예: 양손 증폭 시전 1.6배).
    def effective_cost(self, spell_name: str, mult: float = 1.0) -> float:
        """룬 배율과 시전 방식 배율까지 반영한 실제 차감량."""
        return max(0.0, cost_of(spell_name) * self.cost_mult * mult)

    def can_afford(self, spell_name: str, mult: float = 1.0) -> bool:
        if self.exhaust_left_ms > 0:
            return False
        return self.current + 1e-6 >= self.effective_cost(spell_name, mult)

    def try_spend(self, spell_name: str, mult: float = 1.0) -> bool:
        """시전 가능하면 차감하고 True. 불가하면 상태를 건드리지 않고 False."""
        if not self.can_afford(spell_name, mult):
            self._last_spend_failed = True
            return False
        self.current = max(0.0, self.current - self.effective_cost(spell_name, mult))
        self._last_spend_failed = False
        # 완전 고갈 → 짧은 탈진
        if self.current <= 0.5:
            self.current = 0.0
            self.exhaust_left_ms = EXHAUST_LOCK_MS
        return True

    def refund(self, spell_name: str, mult: float = 1.0) -> None:
        """시전이 다른 이유(쿨다운 등)로 취소됐을 때 되돌린다."""
        self.current = min(self.maximum, self.current + self.effective_cost(spell_name, mult))

    # ── 보상/회복 ───────────────────────────────────────────────────────
    def gain(self, amount: float) -> None:
        """적중 보상 등으로 즉시 마나를 회복한다(탈진 중에도 적용)."""
        if amount <= 0:
            return
        self.current = min(self.maximum, self.current + amount)
        if self.current > 0.5:
            self.exhaust_left_ms = 0

    def reset(self) -> None:
        """새 런/스테이지 시작 — 가득 채우고 탈진 해제."""
        self.current = self.maximum
        self.exhaust_left_ms = 0
        self._last_spend_failed = False

    # ── 조회 ────────────────────────────────────────────────────────────
    @property
    def ratio(self) -> float:
        """0.0~1.0 — HUD 게이지용."""
        if self.maximum <= 0:
            return 0.0
        return max(0.0, min(1.0, self.current / self.maximum))

    @property
    def exhausted(self) -> bool:
        return self.exhaust_left_ms > 0

    def shortfall(self, spell_name: str, mult: float = 1.0) -> float:
        """해당 주문까지 모자란 마나량(0이면 시전 가능)."""
        return max(0.0, self.effective_cost(spell_name, mult) - self.current)


def describe_cost(spell_name: str, pool: Optional[ManaPool] = None) -> str:
    """HUD/토스트용 짧은 비용 표기."""
    c = pool.effective_cost(spell_name) if pool is not None else cost_of(spell_name)
    return f"{int(round(c))} MP"

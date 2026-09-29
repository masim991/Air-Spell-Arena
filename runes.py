from __future__ import annotations
"""
runes.py — 스테이지 클리어 보상으로 고르는 성장 룬(로그라이크 레이어).

설계 의도
---------
기존 빌드는 스테이지 1→2→3 사다리가 매 런 동일해서, 두 번째 플레이부터
"이미 아는 것을 반복"하는 구조였다. 룬은 한 런 안에서만 유지되는 빌드를
만들어, 같은 보스라도 매번 다른 해법을 시도하게 한다.

규칙
----
- 스테이지를 클리어할 때마다 3장을 무작위로 뽑아 1장을 고른다.
- 같은 룬은 한 런에서 중복 획득하지 않는다(스택형은 max_stack 으로 예외).
- 효과는 전부 `RuneState` 가 집계한 배율/가산값으로만 표현한다.
  게임 로직은 이 집계값만 읽으면 되므로 룬을 늘려도 분기문이 늘지 않는다.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Rune:
    """한 장의 성장 룬 정의."""

    id: str
    name: str
    desc: str
    color: Tuple[int, int, int]
    # 집계 필드명 → 증감값. RuneState.recompute() 가 그대로 합산/곱산한다.
    mults: Dict[str, float] = field(default_factory=dict)   # 곱연산
    adds: Dict[str, float] = field(default_factory=dict)    # 합연산
    max_stack: int = 1


# ── 룬 카탈로그 ─────────────────────────────────────────────────────────────
# 색은 game.py 의 원소 네온 팔레트와 톤을 맞춘다.
RUNE_POOL: List[Rune] = [
    Rune(
        id="wellspring", name="WELLSPRING", color=(80, 150, 255),
        desc="마나 회복 +40%",
        mults={"mana_regen": 1.40}, max_stack=3,
    ),
    Rune(
        id="frugal", name="FRUGAL WEAVE", color=(120, 255, 180),
        desc="모든 주문의 마나 소모 -20%",
        mults={"mana_cost": 0.80}, max_stack=2,
    ),
    Rune(
        id="overcharge", name="OVERCHARGE", color=(255, 100, 50),
        desc="주문 피해 +25%, 마나 소모 +10%",
        mults={"spell_damage": 1.25, "mana_cost": 1.10}, max_stack=3,
    ),
    Rune(
        id="siphon", name="SIPHON", color=(180, 100, 255),
        desc="주문 적중 시 마나 8 회복",
        adds={"mana_on_hit": 8.0}, max_stack=3,
    ),
    Rune(
        id="vampiric", name="VAMPIRIC SIGIL", color=(255, 100, 200),
        desc="주문 적중 시 HP 2 회복",
        adds={"hp_on_hit": 2.0}, max_stack=3,
    ),
    Rune(
        id="aegis", name="AEGIS", color=(0, 240, 255),
        desc="받는 피해 -20%",
        mults={"damage_taken": 0.80}, max_stack=2,
    ),
    Rune(
        id="swift", name="SWIFT HANDS", color=(255, 230, 60),
        desc="모든 쿨다운 -30%",
        mults={"cooldown": 0.70}, max_stack=2,
    ),
    Rune(
        id="resonance", name="RESONANCE", color=(255, 215, 50),
        desc="상성 우위 피해 배율 1.5× → 2.0×",
        adds={"affinity_bonus": 0.5}, max_stack=1,
    ),
    Rune(
        id="twin_focus", name="TWIN FOCUS", color=(200, 60, 255),
        desc="듀얼 캐스팅 증폭 배율 +0.5×",
        adds={"dual_bonus": 0.5}, max_stack=2,
    ),
    Rune(
        id="bulwark", name="BULWARK", color=(140, 200, 255),
        desc="실드 지속시간 +60%",
        mults={"shield_duration": 1.60}, max_stack=2,
    ),
    Rune(
        id="fleetfoot", name="FLEETFOOT", color=(80, 255, 150),
        desc="회피 이동속도 +35%",
        mults={"dodge_speed": 1.35}, max_stack=2,
    ),
    Rune(
        id="secondwind", name="SECOND WIND", color=(255, 140, 40),
        desc="스테이지 시작 시 최대 HP +15",
        adds={"max_hp": 15.0}, max_stack=3,
    ),
]

RUNES_BY_ID: Dict[str, Rune] = {r.id: r for r in RUNE_POOL}

# 집계 필드 기본값 — 룬이 하나도 없을 때의 중립 상태.
_MULT_DEFAULTS: Dict[str, float] = {
    "mana_regen": 1.0,
    "mana_cost": 1.0,
    "spell_damage": 1.0,
    "damage_taken": 1.0,
    "cooldown": 1.0,
    "shield_duration": 1.0,
    "dodge_speed": 1.0,
}
_ADD_DEFAULTS: Dict[str, float] = {
    "mana_on_hit": 0.0,
    "hp_on_hit": 0.0,
    "affinity_bonus": 0.0,
    "dual_bonus": 0.0,
    "max_hp": 0.0,
}

OFFER_COUNT = 3


class RuneState:
    """한 런 동안 획득한 룬 목록과 그 집계 효과."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()
        self.owned: List[str] = []          # 획득 순서대로의 rune id (중복 = 스택)
        self._mults: Dict[str, float] = dict(_MULT_DEFAULTS)
        self._adds: Dict[str, float] = dict(_ADD_DEFAULTS)

    # ── 조회 ────────────────────────────────────────────────────────────
    def mult(self, key: str) -> float:
        """곱연산 집계값. 미등록 키는 1.0."""
        return self._mults.get(key, 1.0)

    def add(self, key: str) -> float:
        """합연산 집계값. 미등록 키는 0.0."""
        return self._adds.get(key, 0.0)

    def stacks(self, rune_id: str) -> int:
        return self.owned.count(rune_id)

    def owned_runes(self) -> List[Rune]:
        """획득 순서대로의 Rune 객체 목록(중복 포함)."""
        return [RUNES_BY_ID[r] for r in self.owned if r in RUNES_BY_ID]

    def summary(self) -> List[Tuple[str, int]]:
        """HUD 표시용 (룬 이름, 스택 수) — 획득 순서 유지, 중복 병합."""
        out: List[Tuple[str, int]] = []
        seen: List[str] = []
        for rid in self.owned:
            if rid in seen or rid not in RUNES_BY_ID:
                continue
            seen.append(rid)
            out.append((RUNES_BY_ID[rid].name, self.owned.count(rid)))
        return out

    # ── 획득 ────────────────────────────────────────────────────────────
    def offer(self, count: int = OFFER_COUNT) -> List[Rune]:
        """아직 스택 여유가 있는 룬 중 `count` 장을 무작위로 제시한다.

        고를 수 있는 룬이 부족하면 가능한 만큼만 돌려준다(빈 목록도 정상).
        """
        pool = [r for r in RUNE_POOL if self.stacks(r.id) < r.max_stack]
        if not pool:
            return []
        k = min(count, len(pool))
        return self._rng.sample(pool, k)

    def acquire(self, rune_id: str) -> bool:
        """룬을 획득하고 집계를 갱신한다. 스택이 꽉 찼거나 미지의 id면 False."""
        rune = RUNES_BY_ID.get(rune_id)
        if rune is None or self.stacks(rune_id) >= rune.max_stack:
            return False
        self.owned.append(rune_id)
        self._apply(rune)
        return True

    def reset(self) -> None:
        """새 런 시작 — 모든 룬과 집계를 초기화한다."""
        self.owned.clear()
        self._mults = dict(_MULT_DEFAULTS)
        self._adds = dict(_ADD_DEFAULTS)

    # ── 내부 ────────────────────────────────────────────────────────────
    def _apply(self, rune: Rune) -> None:
        for key, value in rune.mults.items():
            self._mults[key] = self._mults.get(key, 1.0) * value
        for key, value in rune.adds.items():
            self._adds[key] = self._adds.get(key, 0.0) + value

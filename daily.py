from __future__ import annotations
"""
daily.py — 날짜에서 파생된 하루짜리 고정 챌린지.

왜 필요한가
-----------
하이라이트 클립과 결과 카드는 "보여줄 것"을 만들어 준다. 그런데 남의 점수를
봐도 **비교할 기준이 없으면** 그냥 흘러간다. 모두가 같은 보스 순서, 같은 룬
후보, 같은 난이도를 받는 하루짜리 시드를 주면 점수가 곧바로 비교 가능해지고,
공유가 자랑에서 경쟁으로 바뀐다.

설계
----
- 시드는 **날짜 문자열만으로** 결정된다. 서버도, 계정도 필요 없다. 같은 날
  실행한 두 사람은 같은 챌린지를 받는다.
- 무작위성이 들어가는 지점(보스 순서 · 룬 후보 · 변형 규칙)은 전부 이 시드
  하나에서 파생된 `random.Random` 을 쓴다. 전역 `random` 은 건드리지 않는다.
- 기록은 날짜별로 로컬에 남는다(`save_data.json`). 하루가 지나면 새 챌린지다.
"""

import datetime as _dt
import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# 오늘의 변형 규칙 — 같은 사다리라도 매일 다른 제약이 붙는다.
# (id, 표시 이름, 한 줄 설명)
MODIFIERS: List[Tuple[str, str, str]] = [
    ("pure", "PURE", "변형 없음 — 순수 실력 승부"),
    ("glass", "GLASS CANNON", "주문 피해 1.5배, 받는 피해도 1.5배"),
    ("drought", "MANA DROUGHT", "마나 회복 30% 감소"),
    ("swift", "SWIFT DOOM", "보스 공격 주기 25% 단축"),
    ("frugal", "ARCANE ECONOMY", "마나 소모 30% 감소, 주문 피해 20% 감소"),
    ("twinbound", "TWINBOUND", "듀얼 캐스팅 증폭 +1.0배, 한 손 주문 피해 25% 감소"),
]

MODIFIERS_BY_ID: Dict[str, Tuple[str, str]] = {m[0]: (m[1], m[2]) for m in MODIFIERS}

# 일일 챌린지에 쓰이는 난이도 풀. easy 는 1스테이지에서 끝나 비교 가치가 없어 뺀다.
_DIFFICULTIES = ("normal", "hard", "impossible")


def today_key(now: Optional[_dt.date] = None) -> str:
    """오늘의 챌린지 키(로컬 날짜 기준, `YYYY-MM-DD`)."""
    return (now or _dt.date.today()).isoformat()


def seed_for(key: str) -> int:
    """날짜 키 → 안정적인 정수 시드.

    파이썬 내장 `hash()` 는 실행마다 달라지므로(PYTHONHASHSEED) 쓸 수 없다.
    같은 날짜면 어떤 기기에서도 같은 값이 나와야 한다.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True)
class DailyChallenge:
    """하루치 고정 챌린지 정의."""

    key: str                      # "2026-09-23"
    seed: int
    difficulty: str
    ladder: List[str]             # 보스 id 순서
    modifier_id: str

    @property
    def modifier_name(self) -> str:
        return MODIFIERS_BY_ID.get(self.modifier_id, ("PURE", ""))[0]

    @property
    def modifier_desc(self) -> str:
        return MODIFIERS_BY_ID.get(self.modifier_id, ("", "변형 없음"))[1]

    @property
    def short_seed(self) -> str:
        """카드/클립에 찍는 짧은 시드 표기 — 같은 판인지 눈으로 대조할 수 있게."""
        return f"{self.seed % 0xFFFFFF:06X}"

    def rng(self) -> random.Random:
        """이 챌린지 전용 난수원(룬 후보 등). 전역 random 과 분리된다."""
        return random.Random(self.seed)

    # 변형 규칙 → 실제 배율. game.py 는 이 값만 읽으면 된다.
    def multipliers(self) -> Dict[str, float]:
        m = self.modifier_id
        if m == "glass":
            return {"spell_damage": 1.5, "damage_taken": 1.5}
        if m == "drought":
            return {"mana_regen": 0.7}
        if m == "swift":
            return {"boss_interval": 0.75}
        if m == "frugal":
            return {"mana_cost": 0.7, "spell_damage": 0.8}
        if m == "twinbound":
            return {"dual_bonus": 1.0, "single_damage": 0.75}
        return {}


def build(key: Optional[str] = None, ladder_pool: Optional[List[str]] = None) -> DailyChallenge:
    """날짜 키로 오늘의 챌린지를 만든다(같은 키 → 항상 같은 결과)."""
    key = key or today_key()
    seed = seed_for(key)
    rng = random.Random(seed)

    pool = list(ladder_pool or ["arcane", "frost", "void"])
    rng.shuffle(pool)
    difficulty = rng.choice(_DIFFICULTIES)
    modifier_id = rng.choice([m[0] for m in MODIFIERS])

    return DailyChallenge(key=key, seed=seed, difficulty=difficulty,
                          ladder=pool, modifier_id=modifier_id)


# ── 기록 ────────────────────────────────────────────────────────────────────
# save_data.json 의 "daily" 아래에 날짜별 최고 점수를 남긴다.
# 하루 한 줄이므로 무한정 커지지 않도록 최근 N일만 유지한다.
_KEEP_DAYS = 60


def best_for(save: Dict[str, Any], key: str) -> int:
    """해당 날짜의 개인 최고 점수(없으면 0)."""
    table = save.get("daily") or {}
    try:
        return int(table.get(key, 0))
    except (TypeError, ValueError):
        return 0


def record(save: Dict[str, Any], key: str, score: int) -> bool:
    """점수를 기록한다. 갱신했으면 True.

    save_data.save() 호출은 호출부 책임이다(한 프레임에 여러 번 쓰지 않도록).
    """
    table = save.setdefault("daily", {})
    if not isinstance(table, dict):
        table = {}
        save["daily"] = table
    prev = best_for(save, key)
    if score <= prev:
        return False
    table[key] = int(score)
    # 오래된 기록 정리 — 날짜 문자열은 사전순 = 시간순이다.
    if len(table) > _KEEP_DAYS:
        for old in sorted(table.keys())[:-_KEEP_DAYS]:
            table.pop(old, None)
    return True


def streak(save: Dict[str, Any], today: Optional[str] = None) -> int:
    """오늘(또는 어제)부터 거슬러 올라가며 연속으로 플레이한 일수.

    오늘 아직 안 했더라도 어제까지의 연속은 살아 있는 것으로 본다 — 하루가
    끝나기 전에 스트릭이 0으로 보이면 오히려 이탈 동기가 된다.
    """
    table = save.get("daily") or {}
    if not isinstance(table, dict) or not table:
        return 0
    today_d = _dt.date.fromisoformat(today or today_key())
    start = today_d if today_d.isoformat() in table else today_d - _dt.timedelta(days=1)
    count = 0
    cur = start
    while cur.isoformat() in table:
        count += 1
        cur -= _dt.timedelta(days=1)
    return count


@dataclass
class DailyState:
    """게임이 들고 다니는 일일 챌린지 진행 상태."""

    challenge: Optional[DailyChallenge] = None
    active: bool = False
    _mults: Dict[str, float] = field(default_factory=dict)

    def start(self, challenge: DailyChallenge) -> None:
        self.challenge = challenge
        self.active = True
        self._mults = challenge.multipliers()

    def stop(self) -> None:
        self.active = False
        self._mults = {}

    def mult(self, key: str, default: float = 1.0) -> float:
        """변형 규칙 배율. 비활성이면 항상 중립값."""
        if not self.active:
            return default
        return self._mults.get(key, default)

    @property
    def label(self) -> str:
        if not self.active or self.challenge is None:
            return ""
        c = self.challenge
        return f"DAILY {c.key}  ·  {c.modifier_name}  ·  #{c.short_seed}"

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Tuple


SpellEvent = Tuple[str, float]

# (직전 주문, 다음 주문) → 콤보 주문명
COMBO_RULES: Dict[Tuple[str, str], str] = {
    ("FIRE", "WATER"): "STEAM",
    ("WATER", "FIRE"): "MUD",
    ("FIRE", "FIRE"): "FLAME_BALL",
    ("WATER", "WATER"): "ICE_SHARD",
    ("WIND", "FIRE"): "TORNADO",
    ("FIRE", "WIND"): "TORNADO",
    ("EARTH", "FIRE"): "STONE_BULLET",
    ("FIRE", "EARTH"): "STONE_BULLET",
    ("LIGHT", "DARK"): "BLINDNESS",
    ("DARK", "LIGHT"): "CURSE_SHOCK",
}


class SpellComboEngine:
    """기본 주문을 시간축 상에서 결합(콤보)하는 엔진.

    combo_window(초) 안에 두 개의 기본 주문이 연속 입력되면 콤보 주문명을 반환합니다.
    콤보가 성립하면 버퍼를 비워, 세 번째 주문이 앞선 콤보와 다시 엮이지 않게 합니다.
    """

    def __init__(self, combo_window: float = 1.2) -> None:
        self.combo_window: float = combo_window
        self._buffer: Deque[SpellEvent] = deque()
        self._rules = dict(COMBO_RULES)

    def push_basic_spell(self, spell_name: str, timestamp: float) -> str:
        """새 기본 주문과 발생 시각(초)을 받아 최종 주문명(콤보 또는 원본)을 반환합니다."""
        self._buffer.append((spell_name, timestamp))
        self._trim(timestamp)

        combo = self._try_combine()
        if combo is not None:
            self._buffer.clear()
            return combo

        return spell_name

    def pending(self, timestamp: float) -> Optional[Tuple[str, float]]:
        """콤보 대기 중인 주문명과 남은 시간 비율(0~1)을 반환합니다."""
        self._trim(timestamp)
        if not self._buffer:
            return None
        name, ts = self._buffer[-1]
        remain = self.combo_window - (timestamp - ts)
        if remain <= 0:
            return None
        return name, remain / self.combo_window

    def next_options(self, spell_name: str) -> List[Tuple[str, str]]:
        """주어진 주문 뒤에 이어붙일 수 있는 (다음 주문, 콤보명) 목록."""
        return [(b, combo) for (a, b), combo in self._rules.items() if a == spell_name]

    def _trim(self, timestamp: float) -> None:
        cutoff = timestamp - self.combo_window
        while self._buffer and self._buffer[0][1] < cutoff:
            self._buffer.popleft()

    def _try_combine(self) -> Optional[str]:
        if len(self._buffer) < 2:
            return None

        a_name, a_time = self._buffer[-2]
        b_name, b_time = self._buffer[-1]

        if b_time - a_time > self.combo_window:
            return None

        return self._rules.get((a_name, b_name))

    def clear(self) -> None:
        self._buffer.clear()

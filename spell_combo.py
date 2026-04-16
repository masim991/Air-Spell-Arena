from __future__ import annotations

from collections import deque
from typing import Deque, Optional, Tuple


SpellEvent = Tuple[str, float]


class SpellComboEngine:
    """
    기본 주문을 시간축 상에서 결합(콤보)하기 위한 엔진의 뼈대.

    combo_window(초) 동안의 주문 시퀀스를 내부 버퍼에 보관합니다.
    현재는 2개 조합 규칙만 적용하며, 없으면 입력 주문명을 그대로 반환합니다.
    """

    def __init__(self, combo_window: float = 1.2) -> None:
        self.combo_window: float = combo_window
        self._buffer: Deque[SpellEvent] = deque()

        self._rules = {
            ("FIRE", "WATER"): "STEAM",
            ("WATER", "FIRE"): "MUD",
            ("FIRE", "FIRE"): "FLAME_BALL",
            ("WATER", "WATER"): "ICE_SHARD",
            ("WIND", "FIRE"): "TORNADO",
            ("EARTH", "FIRE"): "STONE_BULLET",
            ("LIGHT", "DARK"): "BLINDNESS",
            ("DARK", "LIGHT"): "CURSE_SHOCK",
        }

    def push_basic_spell(self, spell_name: str, timestamp: float) -> str:
        """
        새 기본 주문과 그 발생 시각(초)을 입력받아, 최종 주문명을 반환합니다.
        현재는 간단한 2개 조합만 감지합니다.
        """
        self._buffer.append((spell_name, timestamp))
        self._trim(timestamp)

        combo = self._try_combine()
        if combo is not None:
            return combo

        return spell_name

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
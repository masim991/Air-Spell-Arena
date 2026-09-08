"""SpellComboEngine 규칙표 / 시간창 동작."""
from __future__ import annotations

import pytest

from spell_combo import SpellComboEngine

RULES = {
    ("FIRE", "WATER"): "STEAM",
    ("WATER", "FIRE"): "MUD",
    ("FIRE", "FIRE"): "FLAME_BALL",
    ("WATER", "WATER"): "ICE_SHARD",
    ("WIND", "FIRE"): "TORNADO",
    ("EARTH", "FIRE"): "STONE_BULLET",
    ("LIGHT", "DARK"): "BLINDNESS",
    ("DARK", "LIGHT"): "CURSE_SHOCK",
}


@pytest.mark.parametrize(("pair", "expected"), list(RULES.items()))
def test_every_combo_rule(pair, expected):
    eng = SpellComboEngine(combo_window=1.2)
    a, b = pair
    assert eng.push_basic_spell(a, 0.0) == a          # 첫 주문은 그대로
    assert eng.push_basic_spell(b, 0.5) == expected   # 창 안에서 결합


def test_no_combo_passthrough():
    eng = SpellComboEngine(combo_window=1.2)
    assert eng.push_basic_spell("WIND", 0.0) == "WIND"
    assert eng.push_basic_spell("WIND", 0.3) == "WIND"  # 규칙 없음 → 입력 그대로


def test_combo_window_expiry():
    eng = SpellComboEngine(combo_window=1.0)
    assert eng.push_basic_spell("FIRE", 0.0) == "FIRE"
    # 1.5초 뒤 → 창 밖, 이전 FIRE 는 trim 되어 결합 안 됨
    assert eng.push_basic_spell("WATER", 1.5) == "WATER"


def test_clear_resets_history():
    eng = SpellComboEngine(combo_window=2.0)
    eng.push_basic_spell("FIRE", 0.0)
    eng.clear()
    assert eng.push_basic_spell("WATER", 0.1) == "WATER"  # FIRE 기록 사라짐

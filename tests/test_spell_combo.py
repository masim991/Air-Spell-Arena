from spell_combo import SpellComboEngine


def test_single_spell_passes_through():
    eng = SpellComboEngine(combo_window=1.0)
    assert eng.push_basic_spell("FIRE", 0.0) == "FIRE"


def test_combo_within_window():
    eng = SpellComboEngine(combo_window=1.0)
    eng.push_basic_spell("FIRE", 0.0)
    assert eng.push_basic_spell("WATER", 0.5) == "STEAM"


def test_combo_order_matters():
    eng = SpellComboEngine(combo_window=1.0)
    eng.push_basic_spell("WATER", 0.0)
    assert eng.push_basic_spell("FIRE", 0.3) == "MUD"


def test_combo_expires_outside_window():
    eng = SpellComboEngine(combo_window=1.0)
    eng.push_basic_spell("FIRE", 0.0)
    assert eng.push_basic_spell("WATER", 2.0) == "WATER"


def test_buffer_cleared_after_combo():
    """콤보 성립 후 세 번째 입력이 직전 콤보와 다시 엮이면 안 됩니다."""
    eng = SpellComboEngine(combo_window=1.0)
    eng.push_basic_spell("FIRE", 0.0)
    assert eng.push_basic_spell("FIRE", 0.2) == "FLAME_BALL"
    assert eng.push_basic_spell("FIRE", 0.4) == "FIRE"


def test_pending_reports_remaining_ratio():
    eng = SpellComboEngine(combo_window=1.0)
    eng.push_basic_spell("FIRE", 0.0)
    pend = eng.pending(0.25)
    assert pend is not None
    name, ratio = pend
    assert name == "FIRE"
    assert 0.7 < ratio <= 0.8
    assert eng.pending(1.5) is None


def test_next_options_lists_followups():
    eng = SpellComboEngine()
    opts = dict(eng.next_options("FIRE"))
    assert opts["WATER"] == "STEAM"
    assert opts["FIRE"] == "FLAME_BALL"


def test_clear_resets_buffer():
    eng = SpellComboEngine(combo_window=1.0)
    eng.push_basic_spell("FIRE", 0.0)
    eng.clear()
    assert eng.push_basic_spell("WATER", 0.1) == "WATER"

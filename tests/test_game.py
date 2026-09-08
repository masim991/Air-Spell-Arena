"""SpellGame — 레지스트리 / 상성 / 쿨다운 / 보스 페이즈 (헤드리스)."""
from __future__ import annotations

import pytest

from game import SpellGame, _SPELL_DB, _SPELL_ALIASES, affinity_mult, BOSS_PHASES


@pytest.fixture()
def game():
    g = SpellGame()
    g._state = "playing"
    yield g
    g.close()


# ── 상성표 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("atk", "dfn", "mult"), [
    ("WATER", "FIRE", 1.5),
    ("FIRE", "WIND", 1.5),
    ("FIRE", "WATER", 0.6),
    ("WIND", "FIRE", 0.6),
    ("FIRE", "FIRE", 1.0),
    ("LIGHT", None, 1.0),
])
def test_affinity_mult(atk, dfn, mult):
    assert affinity_mult(atk, dfn) == mult


# ── 주문 레지스트리 ─────────────────────────────────────────────────────────

def test_every_registry_and_alias_spell_applies(game):
    for name in list(_SPELL_DB) + list(_SPELL_ALIASES):
        game._cooldowns.clear()
        res = game.apply_spell(name)
        assert res.applied, name


def test_unknown_spell_rejected(game):
    res = game.apply_spell("NONSENSE")
    assert not res.applied and res.reason == "unrecognized"


def test_combo_spells_cover_engine_rules():
    from spell_combo import SpellComboEngine
    outputs = set(SpellComboEngine()._rules.values())
    missing = outputs - set(_SPELL_DB)
    assert not missing, f"apply_spell 이 처리 못 하는 콤보: {missing}"


# ── 쿨다운 일반화 ──────────────────────────────────────────────────────────

def test_cooldown_blocks_then_recovers(game):
    assert game.apply_spell("FLAME_BALL").applied
    blocked = game.apply_spell("FLAME_BALL")
    assert not blocked.applied and blocked.reason == "cooldown"
    game._update_timers(_SPELL_DB["FLAME_BALL"]["cd"] + 1)
    assert game.apply_spell("FLAME_BALL").applied


def test_zero_cd_spell_repeatable(game):
    for _ in range(3):
        assert game.apply_spell("FIRE").applied


# ── 상성 실제 피해 반영 ────────────────────────────────────────────────────

def _cast_and_resolve(game, spell):
    game.boss_pos = game.player_pos = (640, 360)
    game._player_fx = 640.0
    game._cooldowns.clear()
    game.apply_spell(spell)
    proj = [e for e in game._effects
            if e["type"] == "proj" and e.get("origin") == "player"][-1]
    proj["elapsed"] = proj["dur"]
    hp0 = game.boss_hp
    game._update_effects(1)
    return hp0 - game.boss_hp


def test_super_effective_and_resisted_damage(game):
    game.boss_element = "FIRE"
    game.boss_hp = 100
    strong = _cast_and_resolve(game, "WATER")
    game.boss_element = "WATER"
    game.boss_hp = 100
    weak = _cast_and_resolve(game, "FIRE")
    assert strong > _SPELL_DB["WATER"]["dmg"]      # 1.5×
    assert weak < _SPELL_DB["FIRE"]["dmg"]         # 0.6×


# ── 보스 페이즈 + 텔레그래프 ───────────────────────────────────────────────

def test_boss_phases_advance_with_hp():
    g = SpellGame()
    g._state = "playing"
    g.boss_hp = 100
    seen = set()
    flashes = 0
    for i in range(1200):
        g._update_boss_ai(16)
        flashes += sum(1 for e in g._effects if e["type"] == "flash" and e["elapsed"] == 0)
        g._update_effects(16)
        seen.add(g.boss_phase)
        if i % 5 == 0 and g.boss_hp > 3:
            g.boss_hp -= 1
    g.close()
    assert seen >= {1, 2, 3}
    assert g.boss_element == BOSS_PHASES[-1][1]
    assert flashes >= 2          # 페이즈 2·3 진입 시 화면 플래시


def test_low_hp_renders_without_error():
    g = SpellGame()
    g._state = "playing"
    g.player_hp = 8               # 심장박동 비네트 발동 구간
    assert all(g.run_one_frame(None) for _ in range(3))
    g.close()


def test_telegraph_precedes_projectile():
    g = SpellGame()
    g._state = "playing"
    # 첫 시전 주기까지 진행
    for _ in range(BOSS_PHASES[0][2] // 16 + 1):
        g._update_boss_ai(16)
    has_tele = any(e["type"] == "telegraph" for e in g._effects)
    pending = len(g._pending_boss_shots)
    boss_proj = [e for e in g._effects
                 if e["type"] == "proj" and e.get("origin") == "boss"]
    g.close()
    assert has_tele and pending >= 1
    assert not boss_proj                      # 아직 실제 발사 전


# ── 렌더 파이프라인(시네마틱 그레이드/대기 입자/카메라 셰이크) ─────────────

def test_render_pipeline_populates_atmosphere_and_grade(game):
    game._fp.add_camera_shake(6.0, 200)      # 셰이크 스크롤 경로도 태운다
    for _ in range(6):
        game.run_one_frame("FIRE")
    assert len(game._fp._motes) > 0          # 대기 입자 생성됨
    assert game._fp._grade_cache is not None  # 그레이드 캐시 빌드됨
    assert len(game._fp._grain_tiles) > 0


# ── 리셋 ───────────────────────────────────────────────────────────────────

def test_reset_clears_phase2_state(game):
    game.apply_spell("FLAME_BALL")
    game._boss_blind_left = 999
    game.boss_phase = 3
    game._reset_game()
    assert game._cooldowns == {}
    assert game._boss_blind_left == 0
    assert game.boss_phase == 0
    assert game._pending_boss_shots == []

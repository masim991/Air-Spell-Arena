import pytest

import game as g


@pytest.fixture(scope="module")
def game_instance():
    inst = g.SpellGame()
    yield inst
    inst.close()


@pytest.fixture()
def gm(game_instance):
    """SpellGame 인스턴스는 무겁기 때문에 모듈당 1개만 만들고 매 테스트마다 초기화합니다."""
    game_instance._reset_game()
    game_instance.set_difficulty("normal")
    game_instance.boss_weakness = "FIRE"
    game_instance._weakness_timer = 0
    return game_instance


# ── 원소 상성 ──────────────────────────────────────────────────────────────

def test_weakness_doubles_and_resist_halves(gm):
    assert gm.element_multiplier("FIRE") == g.WEAKNESS_MULTIPLIER
    assert gm.element_multiplier("WATER") == g.RESIST_MULTIPLIER
    assert gm.element_multiplier("WIND") == 1.0
    assert gm.element_multiplier(None) == 1.0


def test_weakness_rotation_picks_new_element(gm):
    gm._rotate_weakness()
    assert gm.boss_weakness != "FIRE"
    assert gm.boss_weakness in g.WEAKNESS_CYCLE


def test_weak_hit_staggers_boss(gm):
    gm._resolve_boss_hit({
        "element": "FIRE", "dmg": 10, "color": g.FIRE_NEON, "style": "fire",
    })
    assert gm.boss_hp == g.BOSS_MAX_HP - 20
    assert gm._boss_stagger_left == g.WEAK_HIT_STAGGER_MS


def test_resisted_hit_is_halved(gm):
    gm._resolve_boss_hit({
        "element": "WATER", "dmg": 10, "color": g.WATER_NEON, "style": "water",
    })
    assert gm.boss_hp == g.BOSS_MAX_HP - 5


# ── 콤보 효과 ──────────────────────────────────────────────────────────────

def test_combo_spell_is_applied(gm):
    res = gm.apply_spell("STEAM")
    assert res.applied and res.element == "WATER"
    projs = [e for e in gm._effects if e.get("origin") == "player"]
    assert projs and projs[0]["combo"] == "STEAM"


def test_tornado_spawns_multiple_hits(gm):
    gm.apply_spell("TORNADO")
    projs = [e for e in gm._effects if e.get("combo") == "TORNADO"]
    assert len(projs) == g.COMBO_PRESETS["TORNADO"]["hits"]


def test_dot_ticks_over_time(gm):
    gm._resolve_boss_hit({
        "element": "WIND", "dmg": 0, "color": g.WIND_NEON, "style": "wind",
        "dot": (3, 1000),
    })
    before = gm.boss_hp
    for _ in range(4):
        gm._update_boss_status(250)
    assert gm.boss_hp == before - 6
    assert gm._boss_dots == []


def test_status_effects_are_stored(gm):
    gm._resolve_boss_hit({
        "element": "WIND", "dmg": 1, "color": g.WIND_NEON, "style": "wind",
        "root": 1500, "slow": 2000, "blind": 3000, "drain": 8,
    })
    assert gm._boss_root_left == 1500
    assert gm._boss_slow_left == 2000
    assert gm._boss_blind_left == 3000
    assert gm.player_hp == g.PLAYER_MAX_HP  # 이미 풀피면 흡수는 넘치지 않음


def test_drain_heals_damaged_player(gm):
    gm.player_hp = 50
    gm._resolve_boss_hit({
        "element": "WIND", "dmg": 1, "color": g.WIND_NEON, "style": "wind", "drain": 8,
    })
    assert gm.player_hp == 58


def test_root_blocks_boss_dodge(gm):
    gm.set_difficulty("impossible")
    gm._boss_root_left = 1000
    gm._effects = [{
        "type": "proj", "origin": "player", "target": "boss", "element": "WIND",
        "color": g.WIND_NEON, "style": "wind", "dmg": 10, "r": 8,
        "start": gm.player_pos, "end": gm.boss_pos, "elapsed": 0, "dur": 100,
    }]
    gm._update_effects(80)
    assert gm._effects[0].get("dodged") is not True


# ── 보스 페이즈 / 예고 ─────────────────────────────────────────────────────

def test_phase_thresholds(gm):
    gm.boss_hp = 100
    assert gm._compute_phase() == 1
    gm.boss_hp = 60
    assert gm._compute_phase() == 2
    gm.boss_hp = 20
    assert gm._compute_phase() == 3


def test_phase_transition_resets_telegraph(gm):
    gm._telegraph = {"kind": "single", "left": 100, "total": 500}
    gm.boss_hp = 25
    gm._update_boss_status(16)
    assert gm._boss_phase == 3
    assert gm._telegraph is None


def test_boss_telegraphs_before_firing(gm):
    gm._boss_attack_timer = g.PHASE_ATTACK_INTERVAL_MS[1]
    gm._update_boss_ai(16)
    assert gm._telegraph is not None
    assert gm._effects == []          # 예고 중에는 아직 발사 안 함
    assert gm.telegraph_progress is not None

    gm._update_boss_ai(g.TELEGRAPH_MS["single"])
    assert gm._telegraph is None
    assert any(e.get("origin") == "boss" for e in gm._effects)


def test_staggered_boss_does_not_attack(gm):
    gm._boss_stagger_left = 500
    gm._boss_attack_timer = g.PHASE_ATTACK_INTERVAL_MS[1]
    gm._update_boss_ai(16)
    assert gm._telegraph is None
    assert gm._effects == []


def test_aoe_hits_even_when_player_moves(gm):
    gm._fire_boss_attack("aoe")
    gm.player_pos = (gm._arena_min_x, gm.player_pos[1])
    proj = gm._effects[0]
    gm._update_effects(proj["dur"] + 1)
    assert gm.player_hp == g.PLAYER_MAX_HP - g.AOE_DMG


def test_burst_spawns_delayed_shots(gm):
    gm._fire_boss_attack("burst")
    assert len(gm._effects) == g.BURST_SHOTS
    assert [e["elapsed"] for e in gm._effects] == [
        -i * g.BURST_STAGGER_MS for i in range(g.BURST_SHOTS)
    ]

"""이번 업그레이드로 추가된 시스템 — 마나 / 룬 / 듀얼 캐스팅 / 수정구 (헤드리스)."""
from __future__ import annotations

import random
from types import SimpleNamespace

import numpy as np
import pygame
import pytest

import mana as mana_mod
import runes as runes_mod
from game import AMPLIFY_COST_MULT, AMPLIFY_DMG_MULT, SpellGame, _SPELL_DB
from gesture import DualHandAnalyzer, GestureConfig, fusion_of
from mana import ManaPool
from runes import RUNE_POOL, RuneState
from webcam_overlay import MIRROR_SRC_SIZE, ScryingOrb, prepare_mirror_frame


@pytest.fixture()
def game():
    g = SpellGame()
    g._state = "playing"
    yield g
    g.close()


# ── 마나 ────────────────────────────────────────────────────────────────────

def test_mana_spend_and_regen():
    pool = ManaPool()
    start = pool.current
    assert pool.try_spend("FIRE")
    assert pool.current == pytest.approx(start - mana_mod.cost_of("FIRE"))

    # 상한에 걸리지 않을 만큼만 회복시켜 회복률 자체를 검증한다
    # (기본 주문 하나 값은 1초 회복량보다 적어서, 1초를 돌리면 최대치에 닿는다)
    spent = pool.current
    pool.current = 0.0
    pool.update(500)
    assert pool.current == pytest.approx(mana_mod.BASE_REGEN_PER_SEC * 0.5)
    assert spent < pool.maximum


def test_mana_never_exceeds_maximum():
    pool = ManaPool()
    pool.update(10_000)
    assert pool.current == pool.maximum


def test_mana_rejects_when_short_and_leaves_state_untouched():
    pool = ManaPool(current=5.0)
    assert not pool.try_spend("CURSE_SHOCK")
    assert pool.current == 5.0          # 실패한 시전은 마나를 건드리지 않는다
    assert pool.shortfall("CURSE_SHOCK") > 0


def test_mana_exhaustion_locks_regen_then_recovers():
    pool = ManaPool(current=mana_mod.cost_of("FIRE"))
    assert pool.try_spend("FIRE")
    assert pool.exhausted and pool.current == 0.0

    pool.update(mana_mod.EXHAUST_LOCK_MS // 2)
    assert pool.current == 0.0          # 탈진 중에는 회복하지 않는다

    pool.update(mana_mod.EXHAUST_LOCK_MS)
    assert not pool.exhausted
    pool.update(500)
    assert pool.current > 0.0


def test_mana_cost_and_regen_multipliers():
    pool = ManaPool(cost_mult=0.5, regen_mult=2.0)
    assert pool.effective_cost("FIRE") == pytest.approx(mana_mod.cost_of("FIRE") * 0.5)
    pool.current = 0.0
    pool.update(1000)
    assert pool.current == pytest.approx(mana_mod.BASE_REGEN_PER_SEC * 2.0)


def test_amplify_costs_more_than_single_cast():
    pool = ManaPool()
    assert (pool.effective_cost("FIRE", AMPLIFY_COST_MULT)
            > pool.effective_cost("FIRE"))


def test_every_spell_in_registry_has_a_mana_cost():
    for name in _SPELL_DB:
        assert mana_mod.cost_of(name) > 0, name


# ── 룬 ──────────────────────────────────────────────────────────────────────

def test_rune_state_starts_neutral():
    st = RuneState()
    for key in ("mana_regen", "mana_cost", "spell_damage", "damage_taken", "cooldown"):
        assert st.mult(key) == 1.0
    for key in ("mana_on_hit", "hp_on_hit", "affinity_bonus", "dual_bonus", "max_hp"):
        assert st.add(key) == 0.0


def test_rune_stacking_multiplies_and_sums():
    st = RuneState()
    assert st.acquire("overcharge")
    assert st.acquire("overcharge")
    assert st.mult("spell_damage") == pytest.approx(1.25 ** 2)
    assert st.acquire("siphon")
    assert st.acquire("siphon")
    assert st.add("mana_on_hit") == pytest.approx(16.0)


def test_rune_respects_max_stack():
    st = RuneState()
    rune = next(r for r in RUNE_POOL if r.max_stack == 1)
    assert st.acquire(rune.id)
    assert not st.acquire(rune.id)      # 최대 스택 초과는 거부
    assert st.stacks(rune.id) == 1


def test_rune_offer_excludes_maxed_runes():
    st = RuneState(random.Random(1))
    rune = next(r for r in RUNE_POOL if r.max_stack == 1)
    st.acquire(rune.id)
    for _ in range(30):
        assert rune.id not in [r.id for r in st.offer()]


def test_rune_offer_returns_distinct_cards():
    st = RuneState(random.Random(5))
    offers = st.offer(3)
    assert len(offers) == 3
    assert len({r.id for r in offers}) == 3


def test_rune_offer_empty_when_pool_exhausted():
    st = RuneState()
    for rune in RUNE_POOL:
        for _ in range(rune.max_stack):
            st.acquire(rune.id)
    assert st.offer() == []


def test_unknown_rune_id_rejected():
    st = RuneState()
    assert not st.acquire("no_such_rune")
    assert st.owned == []


def test_rune_reset_clears_effects():
    st = RuneState()
    st.acquire("overcharge")
    st.reset()
    assert st.owned == [] and st.mult("spell_damage") == 1.0


def test_every_rune_key_is_a_known_aggregate():
    """오타 난 키가 조용히 무시되지 않도록, 카탈로그 전체를 검사한다."""
    for rune in RUNE_POOL:
        for key in rune.mults:
            assert key in runes_mod._MULT_DEFAULTS, f"{rune.id}: {key}"
        for key in rune.adds:
            assert key in runes_mod._ADD_DEFAULTS, f"{rune.id}: {key}"


# ── 듀얼 캐스팅 ─────────────────────────────────────────────────────────────

def _hand(pose: str):
    """지정한 포즈로 분류되는 21개 랜드마크 스텁."""
    lm = [SimpleNamespace(x=0.5, y=0.5, z=0.0) for _ in range(21)]

    def extend(tip, pip, up=True):
        lm[pip] = SimpleNamespace(x=0.5, y=0.50, z=0.0)
        lm[tip] = SimpleNamespace(x=0.5, y=0.30 if up else 0.70, z=0.0)

    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        extend(tip, pip, up=False)
    lm[4] = SimpleNamespace(x=0.5, y=0.60, z=0.0)   # 엄지 내림
    lm[2] = SimpleNamespace(x=0.5, y=0.50, z=0.0)

    if pose == "FIRE":
        for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
            extend(tip, pip, up=True)
    elif pose == "WIND":
        extend(8, 6, up=True)
    elif pose == "EARTH":
        lm[4] = SimpleNamespace(x=0.5, y=0.30, z=0.0)
    elif pose != "WATER":
        raise ValueError(pose)
    return lm


@pytest.mark.parametrize("pose", ["FIRE", "WATER", "EARTH", "WIND"])
def test_hand_stub_classifies_as_intended(pose):
    from gesture import _detect_pose
    assert _detect_pose(_hand(pose)) == pose


def test_dual_same_pose_produces_amplify():
    an = DualHandAnalyzer()
    res = None
    for _ in range(GestureConfig().dual_hold_frames):
        res = an.update([_hand("FIRE"), _hand("FIRE")])
    assert res is not None
    assert res.mode == "amplify" and res.spell == "FIRE"


def test_dual_different_poses_produce_fusion():
    an = DualHandAnalyzer()
    res = None
    for _ in range(GestureConfig().dual_hold_frames):
        res = an.update([_hand("FIRE"), _hand("WATER")])
    assert res is not None
    assert res.mode == "fusion" and res.spell == "STEAM"


def test_dual_requires_two_hands():
    an = DualHandAnalyzer()
    for _ in range(20):
        assert an.update([_hand("FIRE")]) is None


def test_dual_fires_once_then_enters_cooldown():
    an = DualHandAnalyzer()
    fired = 0
    for _ in range(GestureConfig().dual_hold_frames * 3):
        if an.update([_hand("FIRE"), _hand("FIRE")]) is not None:
            fired += 1
    assert fired == 1


def test_fusion_table_is_order_independent():
    for a in ("FIRE", "WATER", "WIND", "EARTH"):
        for b in ("FIRE", "WATER", "WIND", "EARTH"):
            if a != b:
                assert fusion_of(a, b) == fusion_of(b, a)


def test_every_fusion_result_exists_in_spell_registry():
    for a in ("FIRE", "WATER", "WIND", "EARTH"):
        for b in ("FIRE", "WATER", "WIND", "EARTH"):
            if a == b:
                continue
            fused = fusion_of(a, b)
            assert fused is not None, (a, b)      # 모든 조합에 결과가 있어야 한다
            assert fused in _SPELL_DB, fused


# ── 게임 통합 ───────────────────────────────────────────────────────────────

def test_cast_fails_without_mana(game):
    game._mana.current = 0.0
    res = game.apply_spell("FIRE")
    assert not res.applied and res.reason == "no_mana"


def test_amplified_cast_deals_double_damage(game):
    game._mana.reset()
    game._effects.clear()
    game.apply_spell("FIRE")
    single = game._effects[-1]["dmg"]

    game._mana.reset()
    game._effects.clear()
    game.apply_spell("FIRE", mode="amplify")
    amplified = game._effects[-1]["dmg"]

    assert amplified == pytest.approx(single * AMPLIFY_DMG_MULT, rel=0.02)
    assert game._effects[-1]["cast_mode"] == "amplify"


def test_overcharge_rune_increases_damage(game):
    game._mana.reset()
    game._effects.clear()
    game.apply_spell("FIRE")
    base = game._effects[-1]["dmg"]

    game._runes.acquire("overcharge")
    game._sync_rune_effects()
    game._mana.reset()
    game._effects.clear()
    game.apply_spell("FIRE")
    assert game._effects[-1]["dmg"] > base


def test_aegis_rune_reduces_damage_taken(game):
    game.player_hp = 100
    game._deal_player_damage(20)
    plain = 100 - game.player_hp

    game._runes.acquire("aegis")
    game._sync_rune_effects()
    game.player_hp = 100
    game._deal_player_damage(20)
    assert 100 - game.player_hp < plain


def test_second_wind_rune_raises_max_hp(game):
    base = game._max_player_hp()
    game._runes.acquire("secondwind")
    assert game._max_player_hp() > base


def test_rune_select_state_entered_between_stages(game):
    game._stage_index = 1
    game._continue_to_next_stage()
    assert game._state == "rune_select"
    assert len(game._rune_offers) == 3

    chosen = game._rune_offers[0].id
    game._choose_rune(chosen)
    assert game._state == "playing"
    assert chosen in game._runes.owned
    assert game._stage_index == 2


def test_rune_select_skipped_when_no_runes_left(game):
    for rune in RUNE_POOL:
        for _ in range(rune.max_stack):
            game._runes.acquire(rune.id)
    game._stage_index = 1
    game._continue_to_next_stage()
    assert game._state == "playing"       # 빈 화면을 띄우지 않고 바로 진행


def test_new_chain_clears_runes(game):
    game._runes.acquire("overcharge")
    game._reset_chain()
    assert game._runes.owned == []
    assert game._runes.mult("spell_damage") == 1.0


def test_run_one_frame_accepts_cast_mode(game):
    game._mana.reset()
    assert game.run_one_frame("FIRE", head_dir=None, cast_mode="amplify") is True


# ── 수정구(웹캠 오버레이) ───────────────────────────────────────────────────

def test_prepare_mirror_frame_returns_square_rgb():
    frame = (np.random.rand(480, 640, 3) * 255).astype(np.uint8)
    out = prepare_mirror_frame(frame)
    assert out.shape == (MIRROR_SRC_SIZE, MIRROR_SRC_SIZE, 3)


def test_orb_ignores_malformed_frames():
    orb = ScryingOrb(radius=40)
    orb.set_frame(None)
    orb.set_frame(np.zeros((10, 10), dtype=np.uint8))       # 채널 없음
    assert not orb.has_frame()


def test_orb_renders_with_and_without_frame():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((640, 480))
    orb = ScryingOrb(radius=40)

    orb.render(screen, (100, 100), 0)                        # 프레임 없음 — 빈 오브
    orb.set_frame((np.random.rand(200, 200, 3) * 255).astype(np.uint8))
    orb.render(screen, (100, 100), 5, accent=(255, 100, 50))
    assert orb.has_frame()

    orb.clear()
    assert not orb.has_frame()


def test_orb_pulse_decays_to_zero():
    orb = ScryingOrb()
    orb.pulse(1.0)
    for _ in range(40):
        orb.update(16)
    assert orb._pulse == 0.0


def test_orb_toggle_disables_render(game):
    assert game._orb.enabled
    assert game._orb.toggle() is False
    game.set_vision_feedback(mirror=(np.random.rand(200, 200, 3) * 255).astype(np.uint8))
    assert not game._orb.has_frame()     # 꺼져 있으면 색보정 비용조차 들지 않는다


# ── 카메라 토글 (양방향) ────────────────────────────────────────────────────

def test_camera_request_is_bidirectional(game):
    game.set_camera_active(True)
    game.toggle_camera()
    assert game.consume_camera_request() == "off"
    game.set_camera_active(False)

    game.toggle_camera()
    assert game.consume_camera_request() == "on"


def test_camera_request_consumed_once(game):
    game.request_camera(True)
    assert game.consume_camera_request() == "on"
    assert game.consume_camera_request() is None


def test_camera_off_clears_stale_video(game):
    game.set_camera_active(True)
    game.set_vision_feedback(mirror=(np.random.rand(200, 200, 3) * 255).astype(np.uint8))
    assert game._orb.has_frame()
    game.set_camera_active(False)
    assert not game._orb.has_frame()      # 꺼진 카메라의 마지막 프레임이 얼어붙지 않는다


def test_camera_state_drives_input_mode(game):
    game.set_camera_active(True)
    assert game._input_mode == "camera"
    game.set_camera_active(False)
    assert game._input_mode == "keyboard"


def test_stage_reset_does_not_clobber_camera_state(game):
    """재도전/다음 스테이지가 카메라 상태를 'camera' 로 되돌리던 불일치 회귀 방지."""
    game.set_camera_active(False)
    game._reset_entities()
    assert game._input_mode == "keyboard"
    assert not game.camera_active


def test_menu_renders_in_both_camera_states(game):
    game._state = "menu"
    for active in (True, False):
        game.set_camera_active(active)
        assert game.run_one_frame(None) is True

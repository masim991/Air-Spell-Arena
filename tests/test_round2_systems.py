"""2차 업그레이드 — 하이라이트 / 일일 챌린지 / 캘리브레이션 / 앉은 자세 (헤드리스)."""
from __future__ import annotations

import datetime as dt
import os
from types import SimpleNamespace

import pygame
import pytest

import daily as daily_mod
import hud_ext
from game import STAGE_LADDER, SpellGame
from gesture import GestureConfig, _detect_pose, seated_config
from head_tracker import HeadTracker
from highlight import HighlightRecorder


@pytest.fixture()
def game():
    g = SpellGame()
    g._state = "playing"
    yield g
    g.close()


@pytest.fixture()
def screen():
    pygame.display.init()
    return pygame.display.set_mode((640, 360))


# ── 하이라이트 레코더 ───────────────────────────────────────────────────────

def test_recorder_thins_to_target_fps(screen):
    rec = HighlightRecorder(seconds=2, fps=10)
    try:
        taken = sum(rec.capture(screen, 16) for _ in range(60))   # 약 1초 분량
        assert 8 <= taken <= 12                                   # 10fps ± 여유
    finally:
        rec.close()


def test_recorder_ring_buffer_is_bounded(screen):
    rec = HighlightRecorder(seconds=1, fps=10)
    try:
        for _ in range(400):
            rec.capture(screen, 100)
        rec.flush(1.0)
        assert len(rec) <= 10                                     # 1초 × 10fps
    finally:
        rec.close()


def test_recorder_disabled_captures_nothing(screen):
    rec = HighlightRecorder(enabled=False)
    try:
        assert rec.capture(screen, 100) is False
        assert len(rec) == 0
    finally:
        rec.close()


def test_recorder_refuses_to_save_too_short(screen, tmp_path):
    rec = HighlightRecorder()
    try:
        rec.capture(screen, 100)
        assert rec.save(str(tmp_path / "x.mp4")) is None
    finally:
        rec.close()


def test_recorder_writes_playable_video(screen, tmp_path):
    import cv2

    rec = HighlightRecorder(seconds=3, fps=10)
    try:
        for i in range(60):
            screen.fill((i * 4 % 255, 90, 160))
            rec.capture(screen, 100)
        rec.flush(2.0)
        out = rec.save(str(tmp_path / "clip.mp4"))
        assert out is not None and os.path.getsize(out) > 0
        cap = cv2.VideoCapture(out)
        try:
            ok, frame = cap.read()
            assert ok and frame is not None
            assert cap.get(cv2.CAP_PROP_FRAME_COUNT) >= 10
        finally:
            cap.release()
    finally:
        rec.close()


def test_recorder_clear_empties_buffer(screen):
    rec = HighlightRecorder(seconds=2, fps=10)
    try:
        for _ in range(30):
            rec.capture(screen, 100)
        rec.flush(1.0)
        assert len(rec) > 0
        rec.clear()
        assert len(rec) == 0
    finally:
        rec.close()


# ── 일일 챌린지 ─────────────────────────────────────────────────────────────

def test_daily_is_deterministic_per_date():
    a, b = daily_mod.build("2026-09-23"), daily_mod.build("2026-09-23")
    assert (a.seed, a.difficulty, a.ladder, a.modifier_id) == \
           (b.seed, b.difficulty, b.ladder, b.modifier_id)


def test_daily_differs_across_dates():
    seeds = {daily_mod.build("2026-09-%02d" % d).seed for d in range(1, 29)}
    assert len(seeds) == 28              # 날짜마다 다른 시드


def test_daily_seed_is_stable_across_processes():
    """내장 hash() 는 실행마다 달라진다 — sha256 기반이어야 한다."""
    assert daily_mod.seed_for("2026-09-23") == daily_mod.seed_for("2026-09-23")
    assert daily_mod.seed_for("2026-09-23") != daily_mod.seed_for("2026-09-24")


def test_daily_ladder_is_a_permutation_of_bosses():
    for d in range(1, 15):
        ch = daily_mod.build("2026-10-%02d" % d, ladder_pool=list(STAGE_LADDER))
        assert sorted(ch.ladder) == sorted(STAGE_LADDER)


def test_daily_rng_is_reproducible():
    ch = daily_mod.build("2026-09-23")
    first = [ch.rng().random() for _ in range(3)]
    second = [ch.rng().random() for _ in range(3)]
    assert first == second


def test_daily_record_keeps_only_improvements():
    save = {}
    assert daily_mod.record(save, "2026-09-23", 100) is True
    assert daily_mod.record(save, "2026-09-23", 50) is False
    assert daily_mod.record(save, "2026-09-23", 400) is True
    assert daily_mod.best_for(save, "2026-09-23") == 400


def test_daily_streak_counts_consecutive_days():
    save = {}
    for d in (21, 22, 23):
        daily_mod.record(save, "2026-09-%d" % d, 10)
    assert daily_mod.streak(save, "2026-09-23") == 3
    assert daily_mod.streak(save, "2026-09-24") == 3     # 오늘 전이면 유지
    assert daily_mod.streak(save, "2026-09-26") == 0     # 끊김


def test_daily_record_table_is_pruned():
    save = {}
    base = dt.date(2026, 1, 1)
    for i in range(120):
        daily_mod.record(save, (base + dt.timedelta(days=i)).isoformat(), i + 1)
    assert len(save["daily"]) <= 60


def test_every_modifier_maps_to_known_multiplier_keys():
    known = {"spell_damage", "damage_taken", "mana_regen", "mana_cost",
             "boss_interval", "dual_bonus", "single_damage"}
    for mid, _name, _desc in daily_mod.MODIFIERS:
        ch = daily_mod.DailyChallenge("k", 1, "normal", ["arcane"], mid)
        assert set(ch.multipliers()) <= known, mid


def test_daily_state_is_neutral_when_inactive():
    st = daily_mod.DailyState()
    for key in ("spell_damage", "mana_regen", "boss_interval"):
        assert st.mult(key) == 1.0
    assert st.label == ""


def test_starting_daily_replaces_ladder_and_difficulty(game):
    game.start_daily_challenge()
    ch = game._daily.challenge
    assert ch is not None
    assert game._stage_ladder == ch.ladder
    assert game.difficulty == ch.difficulty
    assert game._daily.active


def test_leaving_daily_restores_normal_mode(game):
    game.start_daily_challenge()
    game.exit_daily_challenge()
    assert not game._daily.active
    assert game._stage_ladder == list(STAGE_LADDER)


def test_daily_modifier_changes_damage(game):
    """GLASS CANNON 배율이 실제 주문 피해까지 닿는지 확인."""
    game._mana.reset()
    game._effects.clear()
    game.apply_spell("FIRE")
    base = [e for e in game._effects if e.get("type") == "proj"][-1]["dmg"]

    game._daily.start(daily_mod.DailyChallenge("k", 1, "normal", ["arcane"], "glass"))
    game._sync_rune_effects()
    game._mana.reset()
    game._effects.clear()
    game.apply_spell("FIRE")
    boosted = [e for e in game._effects if e.get("type") == "proj"][-1]["dmg"]
    assert boosted > base


# ── 캘리브레이션 ────────────────────────────────────────────────────────────

def test_calibration_advances_when_pose_held(game):
    game.start_calibration()
    game._pose_label = hud_ext.CALIBRATION_STEPS[0][0]
    game._update_calibration(game.CALIB_HOLD_MS + 10)
    assert game._calib_step == 1


def test_calibration_decays_instead_of_resetting(game):
    """한 프레임 인식 실패로 진행도가 0이 되면 안 된다는 인상만 남는다."""
    game.start_calibration()
    game._pose_label = hud_ext.CALIBRATION_STEPS[0][0]
    game._update_calibration(400)
    held = game._calib_hold_ms
    game._pose_label = None
    game._update_calibration(100)
    assert 0 < game._calib_hold_ms < held


def test_calibration_wrong_pose_does_not_advance(game):
    game.start_calibration()
    game._pose_label = "WATER"          # 1단계 목표는 FIRE
    for _ in range(10):
        game._update_calibration(100)
    assert game._calib_step == 0


def test_calibration_final_step_needs_two_hands(game):
    last = len(hud_ext.CALIBRATION_STEPS) - 1
    game.start_calibration()
    game._calib_step = last
    game._hands_seen = 1
    game._update_calibration(game.CALIB_HOLD_MS + 10)
    assert game._calib_step == last

    game._hands_seen = 2
    game._update_calibration(game.CALIB_HOLD_MS + 10)
    assert game._calib_step == last + 1


def test_calibration_marks_done_even_when_skipped(game):
    game.start_calibration()
    game._finish_calibration(False)
    assert game._save.get("calibration_done") is True
    assert game._state == "menu"


def test_calibration_renders_in_every_state(game):
    game.start_calibration()
    for step in range(len(hud_ext.CALIBRATION_STEPS) + 1):
        game._calib_step = step
        for cam in (True, False):
            game.set_camera_active(cam)
            assert game.run_one_frame(None) is True


# ── 앉은 자세 프리셋 ────────────────────────────────────────────────────────

def test_seated_preset_relaxes_thresholds():
    base, seated = GestureConfig(), seated_config()
    assert seated.ext_margin < base.ext_margin          # 기울어진 손도 인정
    assert seated.thumb_margin < base.thumb_margin
    assert seated.pose_hold_frames <= base.pose_hold_frames
    assert seated.dual_hold_frames <= base.dual_hold_frames
    assert seated.min_length_px < base.min_length_px    # 작게 그어도 인식


def test_seated_preset_never_goes_below_usable_floor():
    seated = seated_config()
    assert seated.pose_hold_frames >= 3                 # 너무 낮으면 오인식 폭증
    assert seated.dual_hold_frames >= 3
    assert seated.ext_margin > 0


def test_seated_head_tracker_is_more_sensitive():
    normal = HeadTracker(sensitivity=1.0)
    seated = HeadTracker(sensitivity=1.45)
    assert seated._enter < normal._enter                # 작은 고갯짓으로도 반응
    assert seated._exit < normal._exit


def test_head_sensitivity_is_clamped():
    wild = HeadTracker(sensitivity=99.0)
    assert wild._enter > 0                              # 0 으로 붕괴하지 않는다


def test_seated_pose_detection_accepts_tilted_hand():
    """서 있을 땐 탈락하는 얕은 손가락 각도가 앉은 프리셋에선 인정되어야 한다."""
    lm = [SimpleNamespace(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        lm[pip] = SimpleNamespace(x=0.5, y=0.50, z=0.0)
        lm[tip] = SimpleNamespace(x=0.5, y=0.482, z=0.0)   # 0.018 만 올라감
    lm[4] = SimpleNamespace(x=0.5, y=0.60, z=0.0)
    lm[2] = SimpleNamespace(x=0.5, y=0.50, z=0.0)

    base, seated = GestureConfig(), seated_config()
    assert _detect_pose(lm, base.ext_margin, base.thumb_margin) != "FIRE"
    assert _detect_pose(lm, seated.ext_margin, seated.thumb_margin) == "FIRE"

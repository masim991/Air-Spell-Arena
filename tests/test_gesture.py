"""GestureAnalyzer — 궤적 분류 + 포즈 감지."""
from __future__ import annotations

import math

import pytest

from gesture import GestureAnalyzer, GestureConfig, _detect_pose


# ── 궤적 분류 ───────────────────────────────────────────────────────────────

RIGHT_SWIPE = [(i * 10, 100) for i in range(20)]
LEFT_SWIPE = [(200 - i * 10, 100) for i in range(20)]
V_ZIGZAG = [(0, 0), (50, 15), (0, 30), (50, 45), (0, 60), (50, 75), (0, 90), (50, 105)]
STAR_CLOSED = [
    (int(150 + (80 if k % 2 == 0 else 30) * math.cos(2 * math.pi * k / 10)),
     int(150 + (80 if k % 2 == 0 else 30) * math.sin(2 * math.pi * k / 10)))
    for k in range(11)
]


@pytest.mark.parametrize(("traj", "expected"), [
    (RIGHT_SWIPE, "DARK"),
    (LEFT_SWIPE, "LIGHT"),
    (V_ZIGZAG, "ZIGZAG"),
    (STAR_CLOSED, "CIRCLE"),
])
def test_classify_known_shapes(traj, expected):
    assert GestureAnalyzer().classify(traj) == expected


@pytest.mark.parametrize("traj", [
    [],
    [(5, 5)],
    [(0, 0), (2, 2)],                    # 너무 짧음
    [(0, 0), (1, 0), (1, 1), (0, 1)],    # 4점이지만 총 길이 < min_length_px
])
def test_classify_rejects_degenerate(traj):
    assert GestureAnalyzer().classify(traj) == "UNKNOWN"


def test_classify_terminates_on_clustered_points():
    """리샘플러 무한 루프 회귀 방지 — 겹친 점 다수여도 즉시 반환."""
    traj = [(100, 100)] * 30 + [(101, 100)]
    assert GestureAnalyzer().classify(traj) == "UNKNOWN"


# ── 포즈 감지 ───────────────────────────────────────────────────────────────

class _LM:
    __slots__ = ("x", "y")

    def __init__(self, x=0.5, y=0.5):
        self.x = x
        self.y = y


def _hand(*, fingers_up=(), thumb_up=False):
    """21개 랜드마크 스텁. fingers_up: 'index'|'middle'|'ring'|'pinky' 중 펼친 손가락."""
    lm = [_LM() for _ in range(21)]
    tips_pips = {"index": (8, 6), "middle": (12, 10), "ring": (16, 14), "pinky": (20, 18)}
    for name, (tip, pip) in tips_pips.items():
        if name in fingers_up:
            lm[tip].y = 0.20          # tip 이 pip 보다 확실히 위
            lm[pip].y = 0.50
        else:
            lm[tip].y = 0.55          # 접힘
            lm[pip].y = 0.50
    # thumb: tip(4) vs mcp(2)
    lm[4].y = 0.30 if thumb_up else 0.55
    lm[2].y = 0.50
    return lm


@pytest.mark.parametrize(("kwargs", "expected"), [
    (dict(fingers_up=("index", "middle", "ring", "pinky")), "FIRE"),
    (dict(fingers_up=("index",)), "WIND"),
    (dict(thumb_up=True), "EARTH"),
    (dict(), "WATER"),
])
def test_detect_pose(kwargs, expected):
    assert _detect_pose(_hand(**kwargs)) == expected


def test_pose_requires_hold_then_fires_once():
    cfg = GestureConfig(pose_hold_frames=3, pose_cooldown_frames=5)
    ga = GestureAnalyzer(cfg)
    hand = _hand(fingers_up=("index", "middle", "ring", "pinky"))
    fired = [ga.update_pose(hand) for _ in range(5)]
    assert fired.count("FIRE") == 1          # 유지 후 딱 한 번
    assert ga.update_pose(None) is None

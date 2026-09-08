"""TrajectoryBuffer 개폐 동작."""
from __future__ import annotations

from trajectory import TrajectoryBuffer, TrajectoryConfig


def _feed(buf: TrajectoryBuffer, pts):
    for p in pts:
        buf.update(p)


def test_stroke_closes_after_disappear_frames():
    buf = TrajectoryBuffer(TrajectoryConfig(disappear_frames_to_close=2, min_points_to_keep=4))
    _feed(buf, [(0, 0), (10, 0), (20, 0), (30, 0), (40, 0)])
    assert buf.poll_last_closed() is None      # 아직 진행 중
    buf.update(None)                            # 결손 1
    assert buf.poll_last_closed() is None
    buf.update(None)                            # 결손 2 → 종료
    closed = buf.poll_last_closed()
    assert closed is not None
    assert len(closed) == 5


def test_poll_last_closed_is_one_shot():
    buf = TrajectoryBuffer(TrajectoryConfig(disappear_frames_to_close=1))
    _feed(buf, [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)])
    buf.update(None)
    assert buf.poll_last_closed() is not None
    assert buf.poll_last_closed() is None       # 두 번째 호출은 None


def test_short_stroke_is_discarded():
    buf = TrajectoryBuffer(TrajectoryConfig(disappear_frames_to_close=1, min_points_to_keep=4))
    _feed(buf, [(0, 0), (1, 0)])                # 2점 < 4
    buf.update(None)
    assert buf.poll_last_closed() is None


def test_new_stroke_starts_after_gap():
    buf = TrajectoryBuffer(TrajectoryConfig(disappear_frames_to_close=1, min_points_to_keep=2))
    _feed(buf, [(0, 0), (5, 0), (10, 0)])
    buf.update(None)
    first = buf.poll_last_closed()
    _feed(buf, [(100, 100), (105, 100), (110, 100)])
    buf.update(None)
    second = buf.poll_last_closed()
    assert first[0] == (0, 0)
    assert second[0] == (100, 100)


def test_recent_trajectories_capped():
    buf = TrajectoryBuffer(TrajectoryConfig(disappear_frames_to_close=1, max_trajectories=3,
                                            min_points_to_keep=2))
    for k in range(6):
        _feed(buf, [(k, 0), (k, 1), (k, 2)])
        buf.update(None)
    assert len(buf.get_recent_trajectories()) == 3

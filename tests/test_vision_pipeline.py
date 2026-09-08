"""VisionPipeline — 카메라 / MediaPipe 없이 결정적 부분만 검증.

워커 스레드/카메라는 띄우지 않고 _smooth 데드존·EMA 와 VisionResult 기본값만 확인.
"""
from __future__ import annotations

from vision_loop import VisionPipeline, VisionResult, _EMA_ALPHA


class _Stub:
    """VisionPipeline._smooth 를 빌려 호출하기 위한 최소 상태 컨테이너."""
    _ema = None
    _prev_center = None

_Stub._smooth = VisionPipeline._smooth


def test_smooth_first_sample_passthrough():
    assert _Stub()._smooth((100, 200)) == (100, 200)


def test_smooth_deadzone_holds_previous():
    s = _Stub()
    s._smooth((100, 100))
    assert s._smooth((101, 100)) == (100, 100)   # 이동 < 2px → 이전 값 유지


def test_smooth_ema_tracks_towards_target():
    s = _Stub()
    s._smooth((0, 0))
    out = s._smooth((100, 0))
    assert 0 < out[0] < 100
    assert abs(out[0] - 100 * _EMA_ALPHA) <= 1


def test_smooth_none_returns_none():
    assert _Stub()._smooth(None) is None


def test_vision_result_defaults():
    r = VisionResult()
    assert r.trail == [] and r.drawing is False
    assert r.head_dir is None and r.annotated is None


def test_head_tracker_skips_copy_when_no_debug():
    """draw_debug=False 면 프레임을 복사하지 않고 그대로 반환한다(최적화 경로)."""
    import numpy as np

    from head_tracker import HeadTracker

    ht = HeadTracker(draw_debug=False)
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    out, direction = ht.process_frame(frame)
    ht.close()
    assert out is frame                 # 복사 없음
    assert direction in ("LEFT", "RIGHT", "CENTER")

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


# ── HeadTracker 방향 로직 (합성 랜드마크) ──────────────────────────────────

def _mk_head(monkeypatch):
    """FaceMesh 를 스텁으로 대체한 HeadTracker + yaw 주입 함수 반환."""
    import types

    import numpy as np

    from head_tracker import HeadTracker

    ht = HeadTracker(draw_debug=False)

    class _Res:
        def __init__(self, lm):
            self.multi_face_landmarks = [types.SimpleNamespace(landmark=lm)]

    def feed(nose_dx: float):
        # 얼굴중심 0.5, 볼 폭 0.30 → 코끝 x = 0.5 + nose_dx
        lm = [types.SimpleNamespace(x=0.5, y=0.5) for _ in range(468)]
        lm[4] = types.SimpleNamespace(x=0.5 + nose_dx, y=0.5)
        lm[234] = types.SimpleNamespace(x=0.35, y=0.5)
        lm[454] = types.SimpleNamespace(x=0.65, y=0.5)
        ht._face_mesh = types.SimpleNamespace(process=lambda img: _Res(lm), close=lambda: None)
        _, d = ht.process_frame(np.zeros((32, 32, 3), dtype=np.uint8))
        return d

    return ht, feed


def test_head_no_drift_when_centered(monkeypatch):
    ht, feed = _mk_head(monkeypatch)
    dirs = {feed(0.0) for _ in range(40)}
    ht.close()
    assert dirs == {"CENTER"}                 # 가만히 있으면 절대 안 쏠림


def test_head_small_turn_triggers_direction(monkeypatch):
    ht, feed = _mk_head(monkeypatch)
    for _ in range(15):
        feed(0.0)                             # 캘리브레이션
    left = [feed(-0.04) for _ in range(12)]   # 얼굴폭의 ~13% → 작은 고갯짓
    right = [feed(0.04) for _ in range(12)]
    ht.close()
    assert "LEFT" in left
    assert "RIGHT" in right


def test_head_recenter_resets_calibration(monkeypatch):
    ht, feed = _mk_head(monkeypatch)
    for _ in range(15):
        feed(0.08)                            # 치우친 자세로 시작
    ht.recenter()
    dirs = {feed(0.08) for _ in range(30)}    # 같은 자세를 새 '정면'으로
    ht.close()
    assert dirs == {"CENTER"}


def test_head_rejects_single_frame_spike(monkeypatch):
    ht, feed = _mk_head(monkeypatch)
    for _ in range(20):
        feed(0.0)
    d_spike = feed(0.45)                      # 1프레임 대형 튐
    ht.close()
    assert d_spike == "CENTER"                # 스텝 제한으로 한 프레임에 안 넘어감

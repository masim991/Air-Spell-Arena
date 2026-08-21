import math

from gesture import GestureAnalyzer


def _circle(cx=0, cy=0, r=120, n=48):
    return [
        (int(cx + r * math.cos(2 * math.pi * i / n)), int(cy + r * math.sin(2 * math.pi * i / n)))
        for i in range(n + 1)
    ]


def _zigzag():
    """세로로 내려오면서 좌우로 꺾이는 번개 모양 (수평 이동이 우세하지 않게)."""
    return [(0 if i % 2 == 0 else 140, i * 40) for i in range(7)]


def test_short_trajectory_is_unknown():
    a = GestureAnalyzer()
    assert a.classify([(0, 0), (2, 1)]) == "UNKNOWN"


def test_left_swipe_is_light():
    a = GestureAnalyzer()
    assert a.classify([(x, 0) for x in range(400, -1, -20)]) == "LIGHT"


def test_right_swipe_is_dark():
    a = GestureAnalyzer()
    assert a.classify([(x, 0) for x in range(0, 401, 20)]) == "DARK"


def test_circle_is_shield():
    a = GestureAnalyzer()
    assert a.classify(_circle()) == "CIRCLE"


def test_zigzag_is_lightning():
    a = GestureAnalyzer()
    assert a.classify(_zigzag()) == "ZIGZAG"

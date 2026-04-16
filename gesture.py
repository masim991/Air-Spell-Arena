from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


Point = Tuple[int, int]
Trajectory = List[Point]


@dataclass(frozen=True)
class GestureConfig:
    """간단 규칙 기반 제스처 분류 설정."""

    resample_points: int = 32
    min_length_px: float = 80.0
    circle_close_ratio: float = 0.25
    line_max_perp_ratio: float = 0.06
    zigzag_min_turns: int = 6
    sharp_turn_deg: float = 70.0
    vertical_ratio: float = 1.2
    horizontal_ratio: float = 1.2
    light_dark_min_length_px: float = 120.0
    light_dark_turn_threshold: int = 4


class GestureAnalyzer:
    """간단한 규칙 기반 궤적 분류기.

    반환값:
    - 공격: 'FIRE', 'WATER', 'WIND', 'EARTH'
    - 디버프: 'LIGHT', 'DARK'
    - 보조: 'LINE', 'CIRCLE', 'ZIGZAG', 'UNKNOWN'
    """

    def __init__(self, config: GestureConfig | None = None) -> None:
        self._cfg = config or GestureConfig()

    def classify(self, trajectory: Trajectory) -> str:
        """Return a basic spell tag such as 'FIRE', 'WATER', 'LINE', 'CIRCLE', etc."""
        if len(trajectory) < 2:
            return "UNKNOWN"

        pts = _resample_polyline(trajectory, self._cfg.resample_points)
        length = _path_length(pts)
        if length < self._cfg.min_length_px:
            return "UNKNOWN"

        start_end = _dist(pts[0], pts[-1])

        dx = pts[-1][0] - pts[0][0]
        dy = pts[-1][1] - pts[0][1]

        if abs(dy) >= abs(dx) * self._cfg.vertical_ratio and abs(dy) >= 0.3 * length:
            return "FIRE" if dy < 0 else "WATER"

        if abs(dx) >= abs(dy) * self._cfg.horizontal_ratio and abs(dx) >= 0.3 * length:
            return "WIND" if dx > 0 else "EARTH"

        if self._is_light_like(pts, length):
            return "LIGHT"

        if self._is_dark_like(pts, length):
            return "DARK"

        if start_end <= length * self._cfg.circle_close_ratio:
            turns = _count_turns(pts, deg_threshold=self._cfg.sharp_turn_deg)
            if turns >= 4:
                return "CIRCLE"

        perp = _max_perpendicular_distance(pts, pts[0], pts[-1])
        if perp <= length * self._cfg.line_max_perp_ratio:
            return "LINE"

        turns = _count_turns(pts, deg_threshold=self._cfg.sharp_turn_deg)
        if turns >= self._cfg.zigzag_min_turns:
            return "ZIGZAG"

        return "UNKNOWN"

    def _is_light_like(self, pts: Trajectory, length: float) -> bool:
        turns = _count_turns(pts, deg_threshold=self._cfg.sharp_turn_deg)
        start_end = _dist(pts[0], pts[-1])
        if length < self._cfg.light_dark_min_length_px:
            return False
        if start_end > length * 0.4:
            return False
        return turns >= self._cfg.light_dark_turn_threshold

    def _is_dark_like(self, pts: Trajectory, length: float) -> bool:
        turns = _count_turns(pts, deg_threshold=self._cfg.sharp_turn_deg)
        start_end = _dist(pts[0], pts[-1])
        if length < self._cfg.light_dark_min_length_px:
            return False
        if start_end > length * 0.5:
            return False
        return turns >= self._cfg.light_dark_turn_threshold + 1


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _path_length(pts: Trajectory) -> float:
    return sum(_dist(pts[i - 1], pts[i]) for i in range(1, len(pts)))


def _resample_polyline(pts: Trajectory, n: int) -> Trajectory:
    """폴리라인을 n개의 점으로 균일 아크길이 기준 리샘플링합니다."""
    if len(pts) == 0:
        return []
    if len(pts) == 1:
        return [pts[0]] * n

    total = _path_length(pts)
    if total == 0:
        return [pts[0]] * n

    step = total / (n - 1)
    out: Trajectory = [pts[0]]

    acc = 0.0
    i = 1
    prev = pts[0]
    while i < len(pts):
        cur = pts[i]
        seg = _dist(prev, cur)
        if seg == 0:
            i += 1
            continue

        if acc + seg >= step:
            t = (step - acc) / seg
            nx = prev[0] + (cur[0] - prev[0]) * t
            ny = prev[1] + (cur[1] - prev[1]) * t
            newp = (int(nx), int(ny))
            out.append(newp)
            prev = newp
            acc = 0.0
        else:
            acc += seg
            prev = cur
            i += 1

    while len(out) < n:
        out.append(out[-1])
    return out[:n]


def _max_perpendicular_distance(pts: Trajectory, a: Point, b: Point) -> float:
    """선분 a-b 에 대해 pts의 최대 수직거리(근사)를 반환합니다."""
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    denom = math.hypot(dx, dy)
    if denom == 0:
        return 0.0

    maxd = 0.0
    for px, py in pts:
        d = abs(dy * px - dx * py + bx * ay - by * ax) / denom
        if d > maxd:
            maxd = d
    return maxd


def _angle_deg(a: Point, b: Point, c: Point) -> float:
    """b를 꼭짓점으로 하는 각 abc의 크기를 도(degree)로 반환."""
    bax = a[0] - b[0]
    bay = a[1] - b[1]
    bcx = c[0] - b[0]
    bcy = c[1] - b[1]

    v1 = math.hypot(bax, bay)
    v2 = math.hypot(bcx, bcy)
    if v1 == 0 or v2 == 0:
        return 180.0

    dot = bax * bcx + bay * bcy
    cosv = max(-1.0, min(1.0, dot / (v1 * v2)))
    return math.degrees(math.acos(cosv))


def _count_turns(pts: Trajectory, deg_threshold: float) -> int:
    """연속 3점에서 각도가 (180 - threshold) 보다 작으면 급격한 턴으로 카운트."""
    turns = 0
    for i in range(1, len(pts) - 1):
        ang = _angle_deg(pts[i - 1], pts[i], pts[i + 1])
        if ang <= (180.0 - deg_threshold):
            turns += 1
    return turns
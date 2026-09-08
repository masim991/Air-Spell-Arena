from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


Point = Tuple[int, int]
Trajectory = List[Point]


# ── MediaPipe Hand Landmark Indices ───────────────────────────────────────
_WRIST        = 0
_THUMB_CMC    = 1; _THUMB_MCP = 2; _THUMB_IP = 3; _THUMB_TIP = 4
_INDEX_MCP    = 5; _INDEX_PIP = 6; _INDEX_TIP = 8
_MIDDLE_MCP   = 9; _MIDDLE_PIP = 10; _MIDDLE_TIP = 12
_RING_MCP     = 13; _RING_PIP = 14; _RING_TIP = 16
_PINKY_MCP    = 17; _PINKY_PIP = 18; _PINKY_TIP = 20

_EXT_MARGIN = 0.025   # 랜드마크 정규화 코오디네이트 단위 마진


def _ext(lm: Any, tip: int, pip: int) -> bool:
    """손가락이 펼쳐졌는지 (tip.y < pip.y - margin)."""
    return lm[tip].y < lm[pip].y - _EXT_MARGIN


def _thumb_up(lm: Any) -> bool:
    """엄지가 위를 향하는지: tip이 MCP보다 좌우무관하게 높이 위치."""
    return lm[_THUMB_TIP].y < lm[_THUMB_MCP].y - 0.06


def _detect_pose(lm: Any) -> Optional[str]:
    """손 모양(21랜드마크)으로 마법 발동 포즈를 분류합니다.

    - FIRE  : 손바닥 펼치기  (4손가락 모두 펼쳐짐)
    - WATER : 주먹       (손가락 전소 접힌 + 엄지 접힐)
    - EARTH : 엄지첨  (엄지만 위를 향하고 나머지 접힌)
    - WIND  : 검지만 펼기 (검지만 펼치고 나머지 접힌)
    """
    idx = _ext(lm, _INDEX_TIP,  _INDEX_PIP)
    mid = _ext(lm, _MIDDLE_TIP, _MIDDLE_PIP)
    rng = _ext(lm, _RING_TIP,   _RING_PIP)
    pky = _ext(lm, _PINKY_TIP,  _PINKY_PIP)
    thb = _thumb_up(lm)
    n_ext = idx + mid + rng + pky

    if n_ext >= 4:
        return "FIRE"
    if idx and not mid and not rng and not pky:
        return "WIND"
    if thb and not idx and not mid and not rng and not pky:
        return "EARTH"
    if n_ext == 0 and not thb:
        return "WATER"
    return None


@dataclass(frozen=True)
class GestureConfig:
    """제스처 분류 설정 (trajectory + pose)."""

    # 트래젝토리 기반 (이동 + 원 + 지그재그)
    resample_points: int = 32
    min_length_px: float = 45.0
    circle_close_ratio: float = 0.30
    zigzag_min_turns: int = 3       # 라이트닝(지그재그) 인식 문턱 완화 (4→3)
    sharp_turn_deg: float = 55.0    # 급턴 판정 각도도 소폭 완화
    horizontal_ratio: float = 0.65   # LIGHT/DARK 수평 우세 비율

    # 포즈 기반 (FIRE/WATER/EARTH/WIND)
    pose_hold_frames: int = 10       # 발동까지 유지해야 하는 프레임 수
    pose_cooldown_frames: int = 35   # 연속 발동 방지 쿨다운


class GestureAnalyzer:
    """제스처 인식기 — 포즈 기반 + 트래젝토리 기반 통합.

    반환값:
    - 포즈 (landmark 기반): 'FIRE', 'WATER', 'EARTH', 'WIND'
    - 이동 (trajectory 기반): 'LIGHT' (좌), 'DARK' (우)
    - 트래젝토리 기반: 'CIRCLE' (쉼드), 'ZIGZAG' (라이트닝)
    """

    def __init__(self, config: GestureConfig | None = None) -> None:
        self._cfg = config or GestureConfig()

        # 포즈 상태
        self._current_pose: Optional[str] = None
        self._hold_counter: int           = 0
        self._cooldown:     int           = 0

    # ── 포즈 기반 (FIRE / WATER / EARTH / WIND) ──────────────────────────────

    def update_pose(self, landmarks: Any) -> Optional[str]:
        """매 프레임 MediaPipe 21 랜드마크 리스트를 입력하여
        포즈가 출분히 유지되면 주문명을 1회만 반환합니다.

        Args:
            landmarks: hand_landmarks.landmark (또는 None — 손이 감지되지 않을 때)

        Returns:
            주문명 str 또는 None
        """
        if self._cooldown > 0:
            self._cooldown -= 1
            if landmarks is None:
                self._current_pose = None
                self._hold_counter = 0
            return None

        if landmarks is None:
            self._current_pose = None
            self._hold_counter = 0
            return None

        detected = _detect_pose(landmarks)

        if detected == self._current_pose and detected is not None:
            self._hold_counter += 1
        else:
            self._current_pose = detected
            self._hold_counter = 0

        if detected and self._hold_counter >= self._cfg.pose_hold_frames:
            self._cooldown     = self._cfg.pose_cooldown_frames
            self._hold_counter = 0
            return detected

        return None

    @property
    def current_pose(self) -> Optional[str]:
        """현재 감지 중(유지 카운트 진행 중)인 포즈 이름 또는 None."""
        return self._current_pose

    @property
    def pose_progress(self) -> float:
        """포즈 유지 진행률 (0.0~1.0)."""
        if self._current_pose is None:
            return 0.0
        return min(1.0, self._hold_counter / max(1, self._cfg.pose_hold_frames))

    # ── 트래젝토리 기반 (LIGHT / DARK / CIRCLE / ZIGZAG) ───────────────────

    def classify(self, trajectory: Trajectory) -> str:
        """트래젝토리로 LIGHT/DARK(좌우 이동) 또는 CIRCLE/ZIGZAG(쉼드/라이트닝)을 분류.

        FIRE/WATER/EARTH/WIND는 update_pose()로 인식되므로 여기에서는 반환하지 않습니다.
        """
        if len(trajectory) < 2:
            return "UNKNOWN"

        # 리샘플 전에 원본 경로 길이로 선(先)필터 — 너무 짧으면 바로 탈락.
        # (리샘플러가 극단적으로 짧은 입력에서 진행하지 못하는 경우 방지)
        if _path_length(trajectory) < self._cfg.min_length_px:
            return "UNKNOWN"

        pts    = _resample_polyline(trajectory, self._cfg.resample_points)
        length = _path_length(pts)
        if length < self._cfg.min_length_px:
            return "UNKNOWN"

        dx        = pts[-1][0] - pts[0][0]
        dy        = pts[-1][1] - pts[0][1]
        start_end = _dist(pts[0], pts[-1])

        # 좌우 수평 이동: LIGHT(좌) 또는 DARK(우)
        if abs(dx) >= abs(dy) * self._cfg.horizontal_ratio and abs(dx) >= 0.16 * length:
            return "LIGHT" if dx < 0 else "DARK"

        # 원 그리기 → CIRCLE (쉼드)
        if start_end <= length * self._cfg.circle_close_ratio:
            turns = _count_turns(pts, deg_threshold=self._cfg.sharp_turn_deg)
            if turns >= 4:
                return "CIRCLE"

        # 지그재그 → ZIGZAG (라이트닝)
        turns = _count_turns(pts, deg_threshold=self._cfg.sharp_turn_deg)
        if turns >= self._cfg.zigzag_min_turns:
            return "ZIGZAG"

        return "UNKNOWN"


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
    # prev 를 float 로 유지 → int 절삭으로 인해 진행이 멈추는 무한 루프 방지.
    prev_x, prev_y = float(pts[0][0]), float(pts[0][1])
    while i < len(pts) and len(out) < n:
        cur = pts[i]
        seg = math.hypot(cur[0] - prev_x, cur[1] - prev_y)
        if seg == 0.0:
            i += 1
            continue

        if acc + seg >= step:
            t = (step - acc) / seg
            prev_x += (cur[0] - prev_x) * t
            prev_y += (cur[1] - prev_y) * t
            out.append((int(prev_x), int(prev_y)))
            acc = 0.0
        else:
            acc += seg
            prev_x, prev_y = float(cur[0]), float(cur[1])
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
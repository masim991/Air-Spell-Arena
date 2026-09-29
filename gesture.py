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
_THUMB_MARGIN = 0.06  # 엄지 세움 판정 마진


def _ext(lm: Any, tip: int, pip: int, margin: float = _EXT_MARGIN) -> bool:
    """손가락이 펼쳐졌는지 (tip.y < pip.y - margin)."""
    return lm[tip].y < lm[pip].y - margin


def _thumb_up(lm: Any, margin: float = _THUMB_MARGIN) -> bool:
    """엄지가 위를 향하는지: tip이 MCP보다 좌우무관하게 높이 위치."""
    return lm[_THUMB_TIP].y < lm[_THUMB_MCP].y - margin


def _detect_pose(
    lm: Any,
    ext_margin: float = _EXT_MARGIN,
    thumb_margin: float = _THUMB_MARGIN,
) -> Optional[str]:
    """손 모양(21랜드마크)으로 마법 발동 포즈를 분류합니다.

    - FIRE  : 손바닥 펼치기  (4손가락 모두 펼쳐짐)
    - WATER : 주먹       (손가락 전소 접힌 + 엄지 접힐)
    - EARTH : 엄지첨  (엄지만 위를 향하고 나머지 접힌)
    - WIND  : 검지만 펼기 (검지만 펼치고 나머지 접힌)
    """
    idx = _ext(lm, _INDEX_TIP,  _INDEX_PIP,  ext_margin)
    mid = _ext(lm, _MIDDLE_TIP, _MIDDLE_PIP, ext_margin)
    rng = _ext(lm, _RING_TIP,   _RING_PIP,   ext_margin)
    pky = _ext(lm, _PINKY_TIP,  _PINKY_PIP,  ext_margin)
    thb = _thumb_up(lm, thumb_margin)
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
    # 시전 속도는 이제 마나(mana.py)가 제한하므로, 인식 지연으로 속도를 묶을
    # 이유가 없어졌다. 홀드·쿨다운을 줄여 손짓 → 발동의 체감 지연을 낮춘다.
    pose_hold_frames: int = 5        # 발동까지 유지 프레임 (8 → 5: 즉발감 확보)
    pose_cooldown_frames: int = 13   # 연속 발동 방지 쿨다운 (22 → 13)
    # 양손 동시 시전(듀얼 캐스팅) — 두 손이 같은 순간 판정을 낸다는 것 자체가
    # 강한 신호라, 한 손보다 짧게 잡아도 오인식이 잘 생기지 않는다.
    dual_hold_frames: int = 4
    dual_cooldown_frames: int = 20   # 증폭/융합은 위력이 크므로 쿨다운은 길게

    # 손 모양 판정 여유. 앉아서 팔꿈치를 책상에 둔 채 플레이하면 손이 낮고
    # 기울어져 잡히기 때문에, 서 있을 때와 같은 문턱을 쓰면 인식률이 떨어진다.
    ext_margin: float = _EXT_MARGIN
    thumb_margin: float = _THUMB_MARGIN
    pose_miss_decay: int = 2         # 홀드 중 인식 실패 1프레임당 카운터 감소량
                                     # (리셋 대신 감쇠 → 손 떨림에도 스펠이 잘 나감)


def seated_config(base: GestureConfig | None = None) -> GestureConfig:
    """앉은 자세(팔꿈치 지지) 프리셋.

    고릴라 암 연구의 결론은 "몸 가까이, 낮은 높이, 짧은 유지"다. 그래서
    세 가지를 함께 완화한다 — 판정 여유를 키우고(기울어진 손도 잡히게),
    유지 프레임을 줄이고(팔을 드는 시간 자체를 줄인다), 궤적 최소 길이를
    낮춘다(작게 그어도 인식되게).
    """
    b = base or GestureConfig()
    return GestureConfig(
        resample_points=b.resample_points,
        min_length_px=b.min_length_px * 0.72,    # 작은 손동작도 궤적으로 인정
        circle_close_ratio=b.circle_close_ratio * 1.15,
        zigzag_min_turns=b.zigzag_min_turns,
        sharp_turn_deg=b.sharp_turn_deg - 5.0,
        horizontal_ratio=b.horizontal_ratio * 0.9,
        pose_hold_frames=max(3, b.pose_hold_frames - 1),
        pose_cooldown_frames=b.pose_cooldown_frames,
        dual_hold_frames=max(3, b.dual_hold_frames - 1),
        dual_cooldown_frames=b.dual_cooldown_frames,
        ext_margin=b.ext_margin * 0.6,           # 손이 기울어도 "폈다"로 인정
        thumb_margin=b.thumb_margin * 0.6,
        pose_miss_decay=b.pose_miss_decay,
    )


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

        detected = (_detect_pose(landmarks, self._cfg.ext_margin, self._cfg.thumb_margin)
                    if landmarks is not None else None)

        if detected is not None and detected == self._current_pose:
            # 같은 포즈 유지 → 진행
            self._hold_counter += 1
        elif detected is not None:
            # 새 포즈 시작 / 다른 포즈로 전환
            self._current_pose = detected
            self._hold_counter = 1
        elif self._current_pose is not None:
            # 이번 프레임만 인식 실패(손 떨림/일시적 손실) → 리셋 말고 감쇠
            self._hold_counter -= self._cfg.pose_miss_decay
            if self._hold_counter <= 0:
                self._current_pose = None
                self._hold_counter = 0

        if self._current_pose is not None and self._hold_counter >= self._cfg.pose_hold_frames:
            fired = self._current_pose
            self._cooldown     = self._cfg.pose_cooldown_frames
            self._hold_counter = 0
            return fired

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

# ── 듀얼 캐스팅 (양손 동시 시전) ─────────────────────────────────────────────
# 규칙은 한 줄로 가르칠 수 있을 만큼 단순해야 한다:
#   같은 손모양 두 개  → 증폭(AMPLIFY)  : 그 주문이 강화되어 나간다
#   다른 손모양 두 개  → 융합(FUSION)   : 두 원소가 합쳐진 상위 주문이 나간다
#
# 기존 콤보(spell_combo.py)는 1.2초 안에 두 주문을 "순차로" 성공시켜야 해서
# 실패율이 높았다. 양손을 쓰면 같은 조합을 "동시에" 만들 수 있으므로,
# 콤보가 타이밍 곡예가 아니라 손 모양 문제로 바뀐다.

# 서로 다른 두 원소의 융합 결과. 좌우 구분이 없도록 정렬된 키로 저장한다.
_FUSION_RULES: dict = {
    ("FIRE", "WATER"): "STEAM",         # 불 + 물 → 수증기
    ("FIRE", "WIND"): "TORNADO",        # 불 + 바람 → 화염 회오리
    ("EARTH", "FIRE"): "STONE_BULLET",  # 흙 + 불 → 용암탄
    ("WATER", "WIND"): "ICE_SHARD",     # 물 + 바람 → 얼음 파편
    ("EARTH", "WATER"): "MUD",          # 흙 + 물 → 진흙
    ("EARTH", "WIND"): "BLINDNESS",     # 흙 + 바람 → 모래폭풍(시야 차단)
}


def fusion_of(pose_a: str, pose_b: str) -> Optional[str]:
    """서로 다른 두 포즈의 융합 주문명. 규칙이 없으면 None."""
    return _FUSION_RULES.get(tuple(sorted((pose_a, pose_b))))  # type: ignore[arg-type]


@dataclass(frozen=True)
class DualCastResult:
    """양손 판정 1건.

    mode:
        'amplify' — 양손이 같은 포즈. `spell` 은 그 기본 주문, 게임이 위력을 올린다.
        'fusion'  — 양손이 다른 포즈. `spell` 은 이미 상위 주문(콤보)이다.
    """

    spell: str
    mode: str
    poses: Tuple[str, str]


class DualHandAnalyzer:
    """두 손의 포즈를 동시에 보고 증폭/융합 시전을 판정한다.

    한 손만 잡히면 아무것도 반환하지 않는다 — 그 경우는 기존 단일
    GestureAnalyzer 가 그대로 처리하므로 역할이 겹치지 않는다.
    """

    def __init__(self, config: GestureConfig | None = None) -> None:
        self._cfg = config or GestureConfig()
        self._current: Optional[Tuple[str, str]] = None   # 정렬된 포즈 쌍
        self._hold = 0
        self._cooldown = 0

    def update(self, hands_landmarks: Optional[List[Any]]) -> Optional[DualCastResult]:
        """프레임마다 손 랜드마크 리스트(0~2개)를 넣는다.

        Returns:
            조건이 충족된 프레임에 한 번만 DualCastResult, 그 외에는 None.
        """
        if self._cooldown > 0:
            self._cooldown -= 1
            if not hands_landmarks or len(hands_landmarks) < 2:
                self._reset()
            return None

        pair = self._detect_pair(hands_landmarks)
        if pair is None:
            # 한쪽 손이 잠깐 가려진 정도로 진행도를 날리지 않는다(단일 포즈와 동일한 감쇠).
            if self._current is not None:
                self._hold -= self._cfg.pose_miss_decay
                if self._hold <= 0:
                    self._reset()
            return None

        if pair == self._current:
            self._hold += 1
        else:
            self._current = pair
            self._hold = 1

        if self._hold < self._cfg.dual_hold_frames:
            return None

        result = self._resolve(pair)
        self._cooldown = self._cfg.dual_cooldown_frames
        self._hold = 0
        self._current = None
        return result

    @property
    def progress(self) -> float:
        """듀얼 홀드 진행률(0.0~1.0) — HUD 게이지용."""
        if self._current is None:
            return 0.0
        return min(1.0, self._hold / max(1, self._cfg.dual_hold_frames))

    @property
    def pending(self) -> Optional[Tuple[str, str]]:
        """현재 모이고 있는 포즈 쌍(없으면 None)."""
        return self._current

    def reset(self) -> None:
        """손 추적이 끊겼을 때 외부에서 강제 초기화."""
        self._reset()
        self._cooldown = 0

    # ── 내부 ────────────────────────────────────────────────────────────
    def _reset(self) -> None:
        self._current = None
        self._hold = 0

    def _detect_pair(self, hands_landmarks: Optional[List[Any]]) -> Optional[Tuple[str, str]]:
        """두 손 모두에서 포즈가 읽히면 정렬된 쌍으로 돌려준다."""
        if not hands_landmarks or len(hands_landmarks) < 2:
            return None
        poses = []
        for lm in hands_landmarks[:2]:
            p = (_detect_pose(lm, self._cfg.ext_margin, self._cfg.thumb_margin)
                 if lm is not None else None)
            if p is None:
                return None
            poses.append(p)
        return (poses[0], poses[1]) if poses[0] <= poses[1] else (poses[1], poses[0])

    def _resolve(self, pair: Tuple[str, str]) -> DualCastResult:
        a, b = pair
        if a == b:
            return DualCastResult(spell=a, mode="amplify", poses=pair)
        fused = fusion_of(a, b)
        if fused is not None:
            return DualCastResult(spell=fused, mode="fusion", poses=pair)
        # 융합 규칙이 없는 조합(예: 한쪽이 EARTH 엄지척으로 오인식) —
        # 입력을 버리지 않고 사전순 앞선 원소의 증폭으로 처리한다.
        return DualCastResult(spell=a, mode="amplify", poses=pair)

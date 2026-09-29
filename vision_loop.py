from __future__ import annotations

"""
vision_loop.py – MediaPipe 기반 비전 파이프라인.

VisionPipeline
    카메라 캡처 + MediaPipe Hands / FaceMesh 추론을 전용 워커 스레드에서 수행하고,
    게임 루프는 poll_result() / drain_spells() 로 "최신 결과"만 소비한다.
    - 렌더 스레드(게임)는 카메라·추론 지연에 묶이지 않는다.
    - 함수 속성 전역 상태를 전부 인스턴스 필드로 캡슐화, close() 로 정리.
    - FaceMesh 는 저주파 신호이므로 _FACE_EVERY_N 프레임마다만 추론.
    - 추론 입력은 _INFER_WIDTH 로 다운스케일하여 CPU 부하를 낮춘다.
    - 연속 프레임 획득 실패가 _MAX_CONSEC_READ_FAIL 회를 넘으면 graceful 종료.
"""

import logging
import math
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import cv2
import numpy as np

# MediaPipe Hands 직접 임포트(robust). mediapipe 는 타입 스텁이 없음 → type:ignore.
try:
    from mediapipe.solutions import hands as mp_hands  # type: ignore[import-untyped]
    from mediapipe.solutions import drawing_utils as mp_drawing  # type: ignore[import-untyped]
    from mediapipe.solutions import drawing_styles as mp_styles  # type: ignore[import-untyped]
except Exception:
    try:
        from mediapipe.python.solutions import hands as mp_hands  # type: ignore
        from mediapipe.python.solutions import drawing_utils as mp_drawing  # type: ignore
        from mediapipe.python.solutions import drawing_styles as mp_styles  # type: ignore
    except Exception as e:
        raise ImportError(
            "mediapipe Hands 모듈이 필요합니다.\npip install mediapipe 로 설치해 주세요."
        ) from e

from gesture import DualHandAnalyzer, GestureAnalyzer, GestureConfig, seated_config
from head_tracker import HeadTracker
from webcam_overlay import MIRROR_SRC_SIZE, prepare_mirror_frame
from trajectory import TrajectoryBuffer, TrajectoryConfig

log = logging.getLogger("air_spell_arena.vision")

Point = Tuple[int, int]

# ── 튜닝 상수 ────────────────────────────────────────────────────────────────
_CAP_WIDTH = 1280
_CAP_HEIGHT = 720
_CAP_FPS = 30
_INFER_WIDTH = 640           # 추론용 다운스케일 목표 폭(원본이 더 크면 축소)
_FACE_EVERY_N = 3            # FaceMesh 는 N프레임마다만 추론
_MAX_CONSEC_READ_FAIL = 30   # 연속 프레임 획득 실패 허용 횟수
_HAND_COMPLEXITY = 1        # Hands 모델 복잡도(1=랜드마크 안정성↑, 스펠 인식률↑)
_HAND_DET_CONF = 0.6       # 최초 손 검출 신뢰도
_HAND_TRK_CONF = 0.5       # 추적 유지 신뢰도(낮을수록 빠른 손동작에도 안 끊김)
_EMA_ALPHA = 0.35            # 검지 끝 좌표 EMA 계수
_MIN_MOVE_SQ = 4             # 최소 이동(px^2) 미만이면 이전 좌표 유지
_MAX_JUMP_PX = 230          # 프레임당 손끝 이동 한계(스파이크/튐 제거)
_PAINT_RESET_FRAMES = 300    # 디버그 paint 캔버스 주기적 초기화
_TRAIL_LEN = 24             # 게임 화면 트레일 표시용 최근 좌표 개수
_MAX_HANDS = 2              # 양손 추적(듀얼 캐스팅) — 한 손만 잡히면 기존 단일 경로로 동작
_MIRROR_EVERY_N = 2         # 미러(수정구) 프레임 갱신 주기 — 30fps 캡처 기준 약 15fps로 충분

_POSE_COLORS = {
    "FIRE": (30, 140, 255), "WATER": (255, 150, 50),
    "EARTH": (80, 180, 80), "WIND": (200, 200, 200),
}


@dataclass
class VisionResult:
    """게임 루프가 소비하는 1프레임 비전 산출물(연속 신호)."""

    head_dir: Optional[str] = None
    pose_label: Optional[str] = None
    pose_progress: float = 0.0
    center: Optional[Point] = None
    fps: float = 0.0
    trail: List[Tuple[float, float]] = field(default_factory=list)  # 정규화(0~1) 손끝 궤적
    drawing: bool = False                    # 현재 스트로크 진행 중 여부
    dual_progress: float = 0.0               # 듀얼 캐스팅 홀드 진행률(0~1)
    hands_seen: int = 0                      # 이번 프레임에 잡힌 손 개수(0~2)
    mirror: Optional[np.ndarray] = None      # 수정구용 소형 정사각 RGB 프레임
    annotated: Optional[np.ndarray] = None   # show_debug=True 일 때만
    mask: Optional[np.ndarray] = None
    paint: Optional[np.ndarray] = None


# spell 이벤트: ("pose", "FIRE") / ("traj", "ZIGZAG") 형태의 1회성 이벤트
SpellEvent = Tuple[str, str]


class VisionPipeline:
    """비전 캡처·추론 워커 스레드를 캡슐화한 파이프라인."""

    def __init__(self, camera_index: int = 0, show_debug: bool = True,
                 seated: bool = False) -> None:
        self._show_debug = show_debug
        # 앉은 자세 프리셋 — 판정 여유를 키우고 유지 프레임을 줄인다(고릴라 암 완화).
        cfg: GestureConfig = seated_config() if seated else GestureConfig()
        self._traj = TrajectoryBuffer(TrajectoryConfig())
        self._analyzer = GestureAnalyzer(cfg)
        self._dual = DualHandAnalyzer(cfg)

        self._cap = cv2.VideoCapture(camera_index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, _CAP_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, _CAP_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS, _CAP_FPS)
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 지연 누적 방지
        except Exception:
            pass

        self._hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=_MAX_HANDS,
            model_complexity=_HAND_COMPLEXITY,
            min_detection_confidence=_HAND_DET_CONF,
            min_tracking_confidence=_HAND_TRK_CONF,
        )
        # 앉으면 화면이 가까워 고개를 크게 돌리기 어렵다 → 감도를 올린다.
        self._head = HeadTracker(draw_mesh=False, draw_debug=False,
                                 sensitivity=1.45 if seated else 1.0)

        # ── 스레드 공유 상태 ──
        self._lock = threading.Lock()
        self._latest: Optional[VisionResult] = None
        self._spell_q: "queue.Queue[SpellEvent]" = queue.Queue()
        self._stop = threading.Event()
        self._failed = threading.Event()
        self._thread = threading.Thread(target=self._run, name="vision-worker", daemon=True)

        # ── 워커 전용 상태(워커 스레드에서만 접근) ──
        self._ema: Optional[Tuple[float, float]] = None
        self._prev_center: Optional[Point] = None
        self._trail: Deque[Tuple[float, float]] = deque(maxlen=_TRAIL_LEN)
        self._last_head_dir: Optional[str] = None
        self._mask: Optional[np.ndarray] = None    # 디버그 마스크 버퍼(재사용)
        self._paint: Optional[np.ndarray] = None
        self._paint_count = 0
        self._frame_i = 0
        self._mirror: Optional[np.ndarray] = None   # 최근 미러 프레임(주기적 갱신)
        self._t_prev = time.perf_counter()
        self._fps = 0.0

    # ── 라이프사이클 ────────────────────────────────────────────────────────
    def start(self) -> None:
        if not self._cap.isOpened():
            self._failed.set()
            log.error("카메라를 열 수 없습니다 (CAMERA_INDEX 확인).")
            return
        self._thread.start()
        log.info("비전 워커 스레드 시작")

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        for name, fn in (("hands", self._hands.close), ("head", self._head.close),
                         ("cap", self._cap.release)):
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - 정리 단계는 관대하게
                log.debug("%s 정리 중 예외: %s", name, e)
        log.info("비전 파이프라인 정리 완료")

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    # ── 소비자 API (게임 스레드에서 호출) ──────────────────────────────────
    def poll_result(self) -> Optional[VisionResult]:
        """가장 최근 프레임 결과를 1회 반환(소비 후 비움). 새 결과 없으면 None."""
        with self._lock:
            r, self._latest = self._latest, None
        return r

    def drain_spells(self) -> List[SpellEvent]:
        """누적된 1회성 주문 이벤트를 모두 꺼낸다(오래된 순)."""
        out: List[SpellEvent] = []
        try:
            while True:
                out.append(self._spell_q.get_nowait())
        except queue.Empty:
            pass
        return out

    def recenter_head(self) -> None:
        """머리 방향 기준점을 현재 자세로 재설정(정면 재보정)."""
        self._head.recenter()

    # ── 워커 루프 ──────────────────────────────────────────────────────────
    def _run(self) -> None:
        consec_fail = 0
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok or frame is None:
                consec_fail += 1
                if consec_fail >= _MAX_CONSEC_READ_FAIL:
                    log.error("연속 %d회 프레임 획득 실패 — 비전 파이프라인 종료", consec_fail)
                    self._failed.set()
                    return
                time.sleep(0.01)
                continue
            consec_fail = 0
            try:
                self._process(frame)
            except (cv2.error, ValueError) as e:
                log.warning("프레임 처리 오류 (건너뜀): %s", e)
            except Exception:  # noqa: BLE001 - 워커가 죽지 않도록 최후 방어
                log.exception("예상치 못한 프레임 처리 오류 (건너뜀)")

    def _process(self, frame: np.ndarray) -> None:
        self._frame_i += 1
        frame = cv2.flip(frame, 1)  # 셀피 뷰
        h0, w0 = frame.shape[:2]

        # 추론용 다운스케일
        if w0 > _INFER_WIDTH:
            s = _INFER_WIDTH / float(w0)
            infer = cv2.resize(frame, (0, 0), fx=s, fy=s, interpolation=cv2.INTER_AREA)
        else:
            infer = frame
        infer_rgb = cv2.cvtColor(infer, cv2.COLOR_BGR2RGB)

        # ── Hands (최대 2개) ──
        results = self._hands.process(infer_rgb)
        annotated = frame.copy() if self._show_debug else None
        center: Optional[Point] = None
        # mediapipe 결과는 동적 NamedTuple → getattr 로 안전 접근
        hand_landmarks = getattr(results, "multi_hand_landmarks", None) or []
        all_lms = [h.landmark for h in hand_landmarks]

        # 주(主) 손 = 검지 끝이 가장 높이 올라간 손. "든 손이 그리는 손"이라는
        # 직관과 맞아떨어져, 양손이 잡혀도 궤적이 손 사이를 오가지 않는다.
        primary_i = -1
        if all_lms:
            primary_i = min(
                range(len(all_lms)),
                key=lambda i: all_lms[i][mp_hands.HandLandmark.INDEX_FINGER_TIP].y,
            )
            tip = all_lms[primary_i][mp_hands.HandLandmark.INDEX_FINGER_TIP]
            center = (
                int(np.clip(tip.x * w0, 0, w0 - 1)),
                int(np.clip(tip.y * h0, 0, h0 - 1)),
            )

        if annotated is not None:
            for i, hlm in enumerate(hand_landmarks):
                try:
                    mp_drawing.draw_landmarks(
                        annotated, hlm,
                        mp_hands.HAND_CONNECTIONS,  # type: ignore[arg-type]
                        mp_styles.get_default_hand_landmarks_style(),
                        mp_styles.get_default_hand_connections_style(),
                    )
                except Exception:
                    pass
                if i == primary_i and center is not None:
                    cv2.circle(annotated, center, 8, (0, 255, 255), 2)

        # ── 듀얼 캐스팅 판정이 단일 포즈보다 우선 ──
        # 양손이 동시에 성립했는데 단일 포즈까지 따로 나가면 한 손짓이 두 번
        # 소비된다. 듀얼이 발동한 프레임에는 단일 분석기를 비워 중복을 막는다.
        dual = self._dual.update(all_lms if len(all_lms) >= 2 else None)
        if dual is not None:
            self._spell_q.put((dual.mode, dual.spell))   # ("amplify"|"fusion", 주문명)
            self._analyzer.update_pose(None)
        else:
            # ── 포즈 인식 (FIRE/WATER/EARTH/WIND) — 주 손 기준 ──
            hand_lm = all_lms[primary_i] if primary_i >= 0 else None
            pose_spell = self._analyzer.update_pose(hand_lm)
            if pose_spell:
                self._spell_q.put(("pose", pose_spell))

        # ── center 스무딩(EMA + 최소 이동 임계) ──
        smoothed = self._smooth(center)

        # ── 게임 화면 트레일용 정규화 좌표 누적 ──
        if smoothed is not None:
            self._trail.append((smoothed[0] / w0, smoothed[1] / h0))
        else:
            self._trail.clear()

        # ── 궤적 갱신 + 닫힌 궤적 분류 ──
        self._traj.update(smoothed)
        closed = self._traj.poll_last_closed()
        if closed is not None:
            basic = self._analyzer.classify(closed)
            if basic != "UNKNOWN":
                self._spell_q.put(("traj", basic))
            self._trail.clear()

        # ── FaceMesh (N프레임마다만) ──
        if self._frame_i % _FACE_EVERY_N == 0:
            _, hd = self._head.process_frame(infer)
            self._last_head_dir = hd
        head_dir = self._last_head_dir

        # ── 수정구(미러)용 소형 프레임 ──
        # 크롭/리사이즈는 여기(워커)에서 끝낸다 — 주 스레드는 색보정과 blit 만 한다.
        if self._frame_i % _MIRROR_EVERY_N == 0:
            try:
                self._mirror = prepare_mirror_frame(frame, MIRROR_SRC_SIZE)
            except (cv2.error, ValueError):
                self._mirror = None

        # ── FPS(지수평활) ──
        now = time.perf_counter()
        dt = now - self._t_prev
        self._t_prev = now
        if dt > 0:
            self._fps = 0.9 * self._fps + 0.1 * (1.0 / dt)

        # ── 디버그 레이어 ──
        mask = paint = None
        if annotated is not None:
            self._overlay(annotated, head_dir)
            mask, paint = self._debug_layers(annotated.shape[:2], smoothed)

        res = VisionResult(
            head_dir=head_dir,
            pose_label=self._analyzer.current_pose,
            pose_progress=self._analyzer.pose_progress,
            center=smoothed,
            fps=self._fps,
            trail=list(self._trail),
            drawing=smoothed is not None,
            dual_progress=self._dual.progress,
            hands_seen=len(all_lms),
            mirror=self._mirror,
            annotated=annotated,
            mask=mask,
            paint=paint,
        )
        with self._lock:
            self._latest = res

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────
    def _smooth(self, center: Optional[Point]) -> Optional[Point]:
        if center is None:
            return None
        cx, cy = center
        if self._ema is None:
            ex, ey = float(cx), float(cy)
        else:
            ex, ey = self._ema
            # 스파이크(튐) 억제: 직전 위치에서 너무 멀면 표본을 한계 거리로 당겨서 사용
            ddx, ddy = cx - ex, cy - ey
            dist = math.hypot(ddx, ddy)
            if dist > _MAX_JUMP_PX:
                scale = _MAX_JUMP_PX / dist
                cx, cy = ex + ddx * scale, ey + ddy * scale
            ex = ex * (1.0 - _EMA_ALPHA) + cx * _EMA_ALPHA
            ey = ey * (1.0 - _EMA_ALPHA) + cy * _EMA_ALPHA
        self._ema = (ex, ey)
        cand = (int(round(ex)), int(round(ey)))
        if self._prev_center is not None:
            dx = cand[0] - self._prev_center[0]
            dy = cand[1] - self._prev_center[1]
            if dx * dx + dy * dy < _MIN_MOVE_SQ:
                cand = self._prev_center
        self._prev_center = cand
        return cand

    def _overlay(self, annotated: np.ndarray, head_dir: Optional[str]) -> None:
        w0 = annotated.shape[1]
        if head_dir is not None:
            cv2.putText(annotated, f"HEAD: {head_dir}", (16, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(annotated, f"FPS: {self._fps:4.1f}", (16, 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 180), 2, cv2.LINE_AA)

        pose = self._analyzer.current_pose
        prog = self._analyzer.pose_progress
        if pose:
            col = _POSE_COLORS.get(pose, (200, 200, 200))
            cv2.putText(annotated, f"POSE: {pose}  {int(prog * 100)}%", (16, 78),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, col, 2, cv2.LINE_AA)
            bar_full = int(w0 * 0.35)
            bar_fill = int(bar_full * prog)
            cv2.rectangle(annotated, (16, 88), (16 + bar_full, 100), (50, 50, 50), -1)
            if bar_fill > 0:
                cv2.rectangle(annotated, (16, 88), (16 + bar_fill, 100), col, -1)
            cv2.rectangle(annotated, (16, 88), (16 + bar_full, 100), col, 1)

    def _debug_layers(self, shape_hw: Tuple[int, int],
                      smoothed: Optional[Point]) -> Tuple[np.ndarray, np.ndarray]:
        h, w = shape_hw

        # 마스크: 버퍼 재사용(매 프레임 재할당 방지)
        if self._mask is None or self._mask.shape != (h, w):
            self._mask = np.zeros((h, w), dtype=np.uint8)
        else:
            self._mask.fill(0)
        if smoothed is not None:
            cv2.circle(self._mask, smoothed, 12, 255, -1)

        # 페인트: 주기적 초기화 + 최근 트레일을 페이딩 폴리라인으로
        if self._paint is None or self._paint.shape[:2] != (h, w) \
                or self._paint_count >= _PAINT_RESET_FRAMES:
            self._paint = np.full((h, w, 3), 255, dtype=np.uint8)
            self._paint_count = 0
        pts = [(int(nx * w), int(ny * h)) for nx, ny in self._trail]
        for i in range(1, len(pts)):
            fade = i / len(pts)
            cv2.line(self._paint, pts[i - 1], pts[i],
                     (int(255 * (1 - fade)), 0, int(80 + 175 * fade)), 2)
        if pts:
            cv2.circle(self._paint, pts[-1], 3, (255, 0, 0), -1)
        self._paint_count += 1
        return self._mask, self._paint

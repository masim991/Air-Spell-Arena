from __future__ import annotations

from collections import deque
from typing import Deque, Literal, Optional, Tuple

import cv2
import numpy as np

try:
    from mediapipe.solutions import face_mesh as mp_face_mesh
    from mediapipe.solutions import drawing_utils as mp_drawing
    from mediapipe.solutions import drawing_styles as mp_styles
except Exception:
    try:
        from mediapipe.python.solutions import face_mesh as mp_face_mesh  # type: ignore
        from mediapipe.python.solutions import drawing_utils as mp_drawing  # type: ignore
        from mediapipe.python.solutions import drawing_styles as mp_styles  # type: ignore
    except Exception as e:
        raise ImportError(
            "mediapipe 패키지가 필요합니다.\n"
            "pip install mediapipe 로 설치해주세요."
        ) from e

Point = Tuple[int, int]
HeadDirection = Literal["LEFT", "RIGHT", "CENTER"]

# Landmark indices
_NOSE_TIP    = 4    # 코끝
_LEFT_CHEEK  = 234  # 왼쪽 볼 외곽
_RIGHT_CHEEK = 454  # 오른쪽 볼 외곽

# ── 얼굴 상대(yaw) 신호 기반 감지 ────────────────────────────────────────────
# yaw = (코끝x - 얼굴중심x) / 얼굴폭  → 카메라 위치·거리와 무관, 고개를 조금만
# 돌려도(≈yaw 0.05~0.12) 확실한 신호가 나온다. 절대 화면좌표를 쓰지 않으므로
# "가만히 있어도 LEFT로 쏠리는" 문제(적응형 중심 고착)가 생기지 않는다.
_ENTER = 0.055   # 이 이상 벗어나면 LEFT/RIGHT 진입 (작은 고갯짓으로 충분)
_EXIT  = 0.024   # 이 안쪽으로 복귀하면 CENTER (히스테리시스)
_MIN_HOLD = 2    # 방향 전환 최소 유지 프레임 (진동 방지, 반응 빠르게)

_CALIB_FRAMES = 12       # 초기 하드 캘리브레이션 프레임 수 (절대 고착 안 되도록)
_CALIB_ALPHA  = 0.020    # 중앙 부근일 때 기준점 자동 재보정 속도(자가 치유)
_UNSTICK_HOLD = 90       # 한 방향에 이만큼 오래 갇히면 기준점을 현재로 끌어당김
_MAX_STEP     = 0.18     # 프레임당 허용 yaw 변화량 (스파이크/튐 제거)
_MIN_FACE_W   = 0.06     # 얼굴폭 하한 (0 division·과민 반응 방지)

_NO_FACE_HOLD = 16       # 얼굴 미감지 시 마지막 방향 유지 최대 프레임 수
_EMA_FAST  = 0.60        # 빠르게 움직일 때 EMA 알파 (반응)
_EMA_SLOW  = 0.30        # 안정적일 때 EMA 알파 (떨림 억제)
_VEL_THRESH = 0.012      # 속도 임계 (yaw 단위)


class HeadTracker:
    """
    MediaPipe Face Mesh 기반 머리 방향(좌/우/중앙) 추적기.

    신호: yaw = (코끝x - 얼굴중심x) / 얼굴폭
    - 얼굴 안에서 코끝의 상대 위치 → 카메라 위치·거리와 무관, 고개를 살짝만
      돌려도 뚜렷한 값. (절대 화면좌표를 안 쓰므로 "가만히 있어도 한쪽으로
      쏠리는" 적응형 중심 고착 문제가 없음)
    - 시작 직후 _CALIB_FRAMES 프레임 동안 현재 자세를 기준점으로 하드 캘리브,
      이후 중앙 부근/장시간 고착 시 기준점을 서서히 재보정(자가 치유)
    - 프레임당 변화량 제한(_MAX_STEP) → 랜드마크 튐 제거
    - 속도 적응형 EMA + 히스토리 평균 + 히스테리시스 + 최소 유지 프레임
    """

    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.55,
        min_tracking_confidence: float = 0.50,
        refine_landmarks: bool = False,
        smooth_window: int = 5,
        draw_mesh: bool = False,
        draw_debug: bool = False,
    ) -> None:
        self._face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=max_num_faces,
            refine_landmarks=refine_landmarks,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.draw_mesh = draw_mesh
        # draw_debug=False 면 프레임 복사·오버레이 드로잉을 건너뛴다(방향값만 필요할 때).
        self.draw_debug = draw_debug or draw_mesh

        self._ema_yaw:  Optional[float] = None   # 스무딩된 yaw
        self._prev_raw: Optional[float] = None   # 직전 프레임 raw(스파이크 판정용)
        self._history:  Deque[float]    = deque(maxlen=max(1, smooth_window))

        # 히스테리시스 상태
        self._last_dir:       str = "CENTER"
        self._hold:           int = 0
        self._no_face_frames: int = 0

        # 기준점(캘리브레이션) — 얼굴 비대칭·카메라 기울기 보정
        self._calib:        float = 0.0
        self._calib_count:  int   = 0     # 초기 하드 캘리브레이션 카운터
        self._smooth_yaw:   float = 0.0   # 마지막 스무딩 yaw (디버그/외부 조회용)

    # ── Public ─────────────────────────────────────────────────────────────────

    def process_frame(
        self, frame: np.ndarray
    ) -> tuple[np.ndarray, Optional[HeadDirection]]:
        """
        BGR 프레임 → (주석 프레임, 머리 방향 or None).
        얼굴이 감지되지 않으면 None 반환.
        """
        if frame is None or frame.size == 0:
            return frame, None

        h, w = frame.shape[:2]
        annotated = frame.copy() if self.draw_debug else frame
        img_rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results   = self._face_mesh.process(img_rgb)

        if not results.multi_face_landmarks:
            self._no_face_frames += 1
            if self._no_face_frames > _NO_FACE_HOLD:
                self._last_dir = "CENTER"
                self._ema_yaw = None
                self._prev_raw = None
                self._history.clear()
            return annotated, self._last_dir

        self._no_face_frames = 0
        lm = results.multi_face_landmarks[0].landmark

        if self.draw_mesh:
            mp_drawing.draw_landmarks(
                image=annotated,
                landmark_list=results.multi_face_landmarks[0],
                connections=mp_face_mesh.FACEMESH_CONTOURS,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_styles.get_default_face_mesh_contours_style(),
            )

        # ── 얼굴 상대 yaw 계산 (코끝이 얼굴 안에서 어느 쪽에 있는가) ──────────
        nose_x  = float(np.clip(lm[_NOSE_TIP].x, 0.0, 1.0))
        nose_y  = float(np.clip(lm[_NOSE_TIP].y, 0.0, 1.0))
        left_x  = float(np.clip(lm[_LEFT_CHEEK].x,  0.0, 1.0))
        right_x = float(np.clip(lm[_RIGHT_CHEEK].x, 0.0, 1.0))
        face_cx = (left_x + right_x) * 0.5
        face_w  = max(abs(right_x - left_x), _MIN_FACE_W)
        yaw     = (nose_x - face_cx) / face_w          # ~0 정면, 음수=LEFT, 양수=RIGHT

        # ── 기준점 캘리브레이션 (고착 방지 + 자가 치유) ──────────────────────
        if self._calib_count < _CALIB_FRAMES:
            # 시작 직후: 현재 yaw 로 하드 세팅 → 절대 한쪽에 갇힌 채 시작하지 않음
            self._calib_count += 1
            k = 1.0 / self._calib_count
            self._calib = (1.0 - k) * self._calib + k * yaw
        raw = yaw - self._calib

        # 중앙 부근이면 기준점을 서서히 현재로 재보정(느린 자가 치유)
        if abs(raw) < _ENTER:
            self._calib += _CALIB_ALPHA * (yaw - self._calib)
        # 한 방향에 너무 오래 갇혀 있으면(신호가 안 커지는데도) 기준점을 끌어당김
        elif self._hold > _UNSTICK_HOLD:
            self._calib += (_CALIB_ALPHA * 1.5) * (yaw - self._calib)
        raw = yaw - self._calib

        # ── 스파이크(튐) 제거: 프레임당 변화량 제한 ─────────────────────────
        if self._prev_raw is not None:
            d = raw - self._prev_raw
            if d > _MAX_STEP:
                raw = self._prev_raw + _MAX_STEP
            elif d < -_MAX_STEP:
                raw = self._prev_raw - _MAX_STEP
        self._prev_raw = raw

        # ── 속도 적응형 EMA + 짧은 히스토리 평균 ────────────────────────────
        vel = abs(raw - self._ema_yaw) if self._ema_yaw is not None else 0.0
        ema_a = _EMA_FAST if vel > _VEL_THRESH else _EMA_SLOW
        if self._ema_yaw is None:
            self._ema_yaw = raw
        else:
            self._ema_yaw = ema_a * raw + (1.0 - ema_a) * self._ema_yaw
        self._history.append(self._ema_yaw)
        smooth = sum(self._history) / len(self._history)
        self._smooth_yaw = smooth

        # ── 히스테리시스 상태 머신 ─────────────────────────────────────────────
        head_dir = self._hysteresis(smooth)

        # ── 디버그 오버레이 (draw_debug 일 때만) ──────────────────────────────
        if self.draw_debug:
            px  = int(nose_x * w)
            py  = int(nose_y * h)
            cxp = int(face_cx * w)                                   # 얼굴 중심 x
            cv2.circle(annotated, (px, py), 9, (0, 255, 255), -1)    # 코끝
            cv2.line(annotated, (cxp, 0), (cxp, h), (0, 220, 0), 1)  # 얼굴 중심
            # yaw 게이지 (화면 중앙 기준, ±_ENTER 마킹)
            gx = w // 2
            cv2.line(annotated, (gx, h - 40), (gx + int(smooth * w * 0.9), h - 40), (255, 120, 0), 4)
            for sgn in (-1, 1):
                mx = gx + int(sgn * _ENTER * w * 0.9)
                cv2.line(annotated, (mx, h - 52), (mx, h - 28), (0, 180, 0), 1)
            cv2.putText(annotated,
                        f"HEAD: {head_dir}  yaw={smooth:+.3f}  calib={self._calib:+.3f}",
                        (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2, cv2.LINE_AA)
        return annotated, head_dir

    def recenter(self) -> None:
        """현재 머리 자세를 '정면'으로 재설정(기준점 재캘리브레이션)."""
        self._calib_count = 0
        self._calib = 0.0
        self._ema_yaw = None
        self._prev_raw = None
        self._history.clear()
        self._last_dir = "CENTER"
        self._hold = 0

    @property
    def yaw(self) -> float:
        """마지막으로 계산된 스무딩 yaw(디버그/튜닝용)."""
        return self._smooth_yaw

    def close(self) -> None:
        if hasattr(self, "_face_mesh") and self._face_mesh is not None:
            self._face_mesh.close()
            self._face_mesh = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ── Private ────────────────────────────────────────────────────────────────

    def _hysteresis(self, smooth: float) -> HeadDirection:
        """히스테리시스 + 최소 유지 프레임을 적용한 방향 판정."""
        self._hold += 1
        prev = self._last_dir

        if prev == "LEFT":
            # LEFT 탈출 조건: hold 충분히 & offset이 EXIT 경계 안쪽으로 복귀
            new = "CENTER" if (self._hold >= _MIN_HOLD and smooth > -_EXIT) else "LEFT"
        elif prev == "RIGHT":
            new = "CENTER" if (self._hold >= _MIN_HOLD and smooth < _EXIT) else "RIGHT"
        else:  # CENTER
            if smooth < -_ENTER:
                new = "LEFT"
            elif smooth > _ENTER:
                new = "RIGHT"
            else:
                new = "CENTER"

        if new != prev:
            self._hold = 0
        self._last_dir = new
        return new  # type: ignore[return-value]

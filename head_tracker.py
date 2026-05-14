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

# Hysteresis thresholds (face-width-normalised offset, [-1 … 1])
# 얼굴 폭 대비 코 offset.  selfie-flipped 이미지에서:
#   좌로 고개 → offset < 0 → "LEFT",  우로 고개 → offset > 0 → "RIGHT"
_ENTER = 0.11   # 이 값을 넘으면 L/R 진입
_EXIT  = 0.04   # 이 값 이내로 돌아와야 CENTER 복귀 (히스테리시스)
_MIN_HOLD = 5   # 방향 유지 최소 프레임 수 (1인칭 진동 방지)


class HeadTracker:
    """
    MediaPipe Face Mesh 기반 머리 방향(좌/우/중앙) 추적기.

    개선 사항:
    - 얼굴 폭 정규화 offset 사용 → 카메라 위치와 무관
    - EMA + 히스테리시스 이중 스무딩 → 좌→중앙→우 순간 오감지 방지
    - 최소 유지 프레임(_MIN_HOLD) → 빠른 jitter 억제
    """

    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.6,
        min_tracking_confidence: float = 0.6,
        refine_landmarks: bool = False,
        ema_alpha: float = 0.40,
        smooth_window: int = 3,
        draw_mesh: bool = False,
    ) -> None:
        self._face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=max_num_faces,
            refine_landmarks=refine_landmarks,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.ema_alpha   = float(np.clip(ema_alpha, 0.01, 1.0))
        self.draw_mesh   = draw_mesh

        self._ema_offset: Optional[float]    = None
        self._history:    Deque[float]        = deque(maxlen=max(1, smooth_window))

        # 히스테리시스 상태
        self._last_dir:   str = "CENTER"
        self._hold:       int = 0

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
        annotated = frame.copy()
        img_rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results   = self._face_mesh.process(img_rgb)

        if not results.multi_face_landmarks:
            return annotated, self._last_dir  # 이전 방향 유지

        lm = results.multi_face_landmarks[0].landmark

        if self.draw_mesh:
            mp_drawing.draw_landmarks(
                image=annotated,
                landmark_list=results.multi_face_landmarks[0],
                connections=mp_face_mesh.FACEMESH_CONTOURS,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_styles.get_default_face_mesh_contours_style(),
            )

        # ── 얼굴 폭 정규화 offset 계산 ────────────────────────────────────────
        nose_x   = float(np.clip(lm[_NOSE_TIP].x,    0.0, 1.0))
        nose_y   = float(np.clip(lm[_NOSE_TIP].y,    0.0, 1.0))
        left_x   = float(np.clip(lm[_LEFT_CHEEK].x,  0.0, 1.0))
        right_x  = float(np.clip(lm[_RIGHT_CHEEK].x, 0.0, 1.0))

        face_cx  = (left_x + right_x) * 0.5
        face_w   = max(abs(right_x - left_x), 0.01)
        raw_off  = (nose_x - face_cx) / face_w

        # EMA 스무딩
        if self._ema_offset is None:
            self._ema_offset = raw_off
        else:
            a = self.ema_alpha
            self._ema_offset = a * raw_off + (1.0 - a) * self._ema_offset

        self._history.append(self._ema_offset)
        smooth = sum(self._history) / len(self._history)

        # ── 히스테리시스 상태 머신 ─────────────────────────────────────────────
        head_dir = self._hysteresis(smooth)

        # ── 디버그 오버레이 ────────────────────────────────────────────────────
        px  = int(nose_x * w)
        py  = int(nose_y * h)
        fcx = int(face_cx * w)

        cv2.circle(annotated, (px, py), 6, (0, 255, 255), -1)
        cv2.line(annotated, (fcx, 0), (fcx, h), (200, 200, 0), 1)

        # offset bar
        bar_x = int((face_cx + smooth * face_w) * w)
        cv2.line(annotated, (bar_x, 0), (bar_x, h), (255, 100, 0), 2)

        # enter/exit threshold lines
        cv2.line(annotated, (int((face_cx - _ENTER * face_w) * w), 0),
                 (int((face_cx - _ENTER * face_w) * w), h), (0, 200, 0), 1)
        cv2.line(annotated, (int((face_cx + _ENTER * face_w) * w), 0),
                 (int((face_cx + _ENTER * face_w) * w), h), (0, 200, 0), 1)

        cv2.putText(
            annotated,
            f"HEAD: {head_dir}  off={smooth:+.3f}",
            (16, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return annotated, head_dir

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

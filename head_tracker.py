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

# 코끝 절대 위치 기반 감지 임계값 (정규화된 화면 좌표 [0,1] 기준)
# selfie-flipped 이미지에서:
#   코끝이 중심보다 왼쪽 → offset < 0 → "LEFT"
#   코끝이 중심보다 오른쪽 → offset > 0 → "RIGHT"
_ENTER = 0.045   # 화면폭의 4.5% 이탈 시 방향 진입
_EXIT  = 0.018   # 화면폭의 1.8% 이내 복귀 시 CENTER 복귀 (히스테리시스)
_MIN_HOLD = 3    # 방향 유지 최소 프레임 수 (진동 방지)

_CENTER_EMA_ALPHA = 0.012  # 적응형 중심 보정 속도 (CENTER 상태일 때만 갱신)
_NO_FACE_HOLD     = 20    # 얼굴 미감지 시 방향 유지 최대 프레임 수
_EMA_FAST  = 0.55         # 빠르게 움직일 때 EMA 알파
_EMA_SLOW  = 0.28         # 안정적일 때 EMA 알파
_VEL_THRESH = 0.004       # 속도 임계 (정규화 좌표)


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
        min_detection_confidence: float = 0.55,
        min_tracking_confidence: float = 0.50,
        refine_landmarks: bool = False,
        smooth_window: int = 5,
        draw_mesh: bool = False,
    ) -> None:
        self._face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=max_num_faces,
            refine_landmarks=refine_landmarks,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.draw_mesh = draw_mesh

        self._ema_offset: Optional[float]  = None
        self._prev_offset: Optional[float] = None
        self._history:     Deque[float]    = deque(maxlen=max(1, smooth_window))

        # 히스테리시스 상태
        self._last_dir:       str = "CENTER"
        self._hold:           int = 0
        self._no_face_frames: int = 0

        # 코끝 적응형 중심 + 얼굴 폭 참고값
        self._nose_cx:   float = 0.5
        self._face_width: float = 0.30  # 초기 추정값

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
            self._no_face_frames += 1
            if self._no_face_frames > _NO_FACE_HOLD:
                self._last_dir = "CENTER"
                self._ema_offset = None
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

        # ── 코끝 위치 + 얼굴 폭 추출 ───────────────────────────────────────
        nose_x  = float(np.clip(lm[_NOSE_TIP].x, 0.0, 1.0))
        nose_y  = float(np.clip(lm[_NOSE_TIP].y, 0.0, 1.0))
        left_x  = float(np.clip(lm[_LEFT_CHEEK].x,  0.0, 1.0))
        right_x = float(np.clip(lm[_RIGHT_CHEEK].x, 0.0, 1.0))
        face_w  = abs(right_x - left_x)
        if face_w > 0.05:  # 유효한 얼굴 폭일 때만 갱신
            self._face_width = 0.95 * self._face_width + 0.05 * face_w

        # 적응형 중심: CENTER 상태일 때만 천천히 보정
        if self._last_dir == "CENTER":
            self._nose_cx = (1.0 - _CENTER_EMA_ALPHA) * self._nose_cx + _CENTER_EMA_ALPHA * nose_x

        # 중심 대비 상대 편차 (양수 = 오른쪽)
        raw_off  = nose_x - self._nose_cx

        # 속도 기반 적응형 EMA 알파 선택
        vel = abs(raw_off - self._prev_offset) if self._prev_offset is not None else 0.0
        ema_a = _EMA_FAST if vel > _VEL_THRESH else _EMA_SLOW
        self._prev_offset = raw_off

        if self._ema_offset is None:
            self._ema_offset = raw_off
        else:
            self._ema_offset = ema_a * raw_off + (1.0 - ema_a) * self._ema_offset

        self._history.append(self._ema_offset)
        smooth = sum(self._history) / len(self._history)

        # ── 히스테리시스 상태 머신 ─────────────────────────────────────────────
        head_dir = self._hysteresis(smooth)

        # ── 디버그 오버레이 ────────────────────────────────────────────────────
        px  = int(nose_x * w)
        py  = int(nose_y * h)
        ncx = int(self._nose_cx * w)  # 적응형 중심

        cv2.circle(annotated, (px, py), 9, (0, 255, 255), -1)   # 코끝 마크 (밝은 파랑)
        cv2.line(annotated, (ncx, 0), (ncx, h), (0, 220, 0), 1)  # 보정 중심 (녹색)

        # 현재 offset 위치 바
        bar_x = int((self._nose_cx + smooth) * w)
        cv2.line(annotated, (bar_x, 0), (bar_x, h), (255, 100, 0), 2)

        # ENTER 임계 라인 (±ENTER)
        cv2.line(annotated, (int((self._nose_cx - _ENTER) * w), 0),
                 (int((self._nose_cx - _ENTER) * w), h), (0, 180, 0), 1)
        cv2.line(annotated, (int((self._nose_cx + _ENTER) * w), 0),
                 (int((self._nose_cx + _ENTER) * w), h), (0, 180, 0), 1)

        cv2.putText(annotated, f"HEAD: {head_dir}  off={smooth:+.3f}  fw={self._face_width:.2f}",
                    (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2, cv2.LINE_AA)
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

from __future__ import annotations

from collections import deque
from typing import Deque, Literal, Optional, Tuple, List

import cv2
import numpy as np
import mediapipe as mp

try:
    from mediapipe.solutions import face_mesh as mp_face_mesh
    from mediapipe.solutions import drawing_utils as mp_drawing
    from mediapipe.solutions import drawing_styles as mp_styles
except Exception:
    try:
        from mediapipe.python.solutions import face_mesh as mp_face_mesh
        from mediapipe.python.solutions import drawing_utils as mp_drawing
        from mediapipe.python.solutions import drawing_styles as mp_styles
    except Exception as e:
        raise ImportError(
            "Mediapip 패키지가 필요합니다.\n"
            "pip install mediapipe로 설치해주세요"
        ) from e

point = Tuple[int, int]
HeadDirection = Literal["LEFT", "RIGHT", "CENTER"]

# MediaPipe Face Mesh landmark indices used for head direction
_NOSE_TIP   = 4    # tip of nose
_LEFT_CHEEK = 234  # outer left cheek
_RIGHT_CHEEK = 454 # outer right cheek
_OFFSET_THRESHOLD = 0.10  # 10% of face width triggers L/R


class HeadTracker:
    """
    MediaPipe Face Mesh 기반 머리 방향(좌/우/중앙) 추적기.

    개선된 방식:
    - 코 끝(4) + 왼쪽/오른쪽 볼(234, 454)을 사용해 얼굴 폭 대비 코의 상대 위치를 계산
    - offset = (nose_x - face_center_x) / face_width 로 절대 위치에 무관하게 판정
    - EMA 스무딩으로 빠른 반응 + jitter 억제
    """
    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.6,
        min_tracking_confidence: float = 0.6,
        refine_landmarks: bool = False,
        offset_threshold: float = _OFFSET_THRESHOLD,
        ema_alpha: float = 0.45,
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
        self.offset_threshold = offset_threshold
        self.ema_alpha = ema_alpha
        self.draw_mesh = draw_mesh
        self._ema_offset: Optional[float] = None
        self._offset_history: Deque[float] = deque(maxlen=max(1, smooth_window))

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, Optional[HeadDirection]]:
        """
        BGR 프레임을 입력받아 (주석된 프레임, 머리 방향 or None)을 반환.
        얼굴 폭 대비 코의 상대 offset으로 좌우를 판정합니다.
        """
        if frame is None or frame.size == 0:
            return frame, None

        h, w = frame.shape[:2]
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._face_mesh.process(img_rgb)

        annotated = frame.copy()
        head_dir: Optional[HeadDirection] = None

        if results.multi_face_landmarks:
            face_landmarks = results.multi_face_landmarks[0]

            if self.draw_mesh:
                mp_drawing.draw_landmarks(
                    image=annotated,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_CONTOURS,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=mp_styles.get_default_face_mesh_contours_style(),
                )

            # 얼굴 폭 기준 정규화된 코 offset 계산
            nose_x  = float(np.clip(face_landmarks.landmark[_NOSE_TIP].x,    0.0, 1.0))
            nose_y  = float(np.clip(face_landmarks.landmark[_NOSE_TIP].y,    0.0, 1.0))
            left_x  = float(np.clip(face_landmarks.landmark[_LEFT_CHEEK].x,  0.0, 1.0))
            right_x = float(np.clip(face_landmarks.landmark[_RIGHT_CHEEK].x, 0.0, 1.0))

            face_center_x = (left_x + right_x) * 0.5
            face_width    = max(abs(right_x - left_x), 0.01)
            raw_offset    = (nose_x - face_center_x) / face_width

            # EMA 스무딩 (빠른 반응 + jitter 억제)
            if self._ema_offset is None:
                self._ema_offset = raw_offset
            else:
                self._ema_offset = self._ema_offset * (1.0 - self.ema_alpha) + raw_offset * self.ema_alpha

            self._offset_history.append(self._ema_offset)
            smoothed_offset = sum(self._offset_history) / len(self._offset_history)

            if smoothed_offset < -self.offset_threshold:
                head_dir = "LEFT"
            elif smoothed_offset > self.offset_threshold:
                head_dir = "RIGHT"
            else:
                head_dir = "CENTER"

            # 디버그 오버레이
            px  = int(nose_x * w)
            py  = int(nose_y * h)
            fcx = int(face_center_x * w)
            cv2.circle(annotated, (px, py), 6, (0, 255, 255), -1)
            cv2.line(annotated, (fcx, 0), (fcx, h), (255, 200, 0), 1)
            # offset bar (center + offset * face_width)
            bar_x = int((face_center_x + smoothed_offset * face_width) * w)
            cv2.line(annotated, (bar_x, 0), (bar_x, h), (255, 100, 0), 2)

            cv2.putText(
                annotated,
                f"HEAD: {head_dir}  off={smoothed_offset:.2f}",
                (20, 40),
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
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
            "pip install mediapipe로 설치해주세요"
        ) from e

Point = Tuple[int, int]
HeadDirection = Literal["LEFT", "RIGHT", "CENTER"]


class HeadTracker:
    """
    MediaPipe Face Mesh 기반 머리 방향(좌/우/중앙) 추적기.

    개선점:
    - 코 끝 1점만 보지 않고, 양쪽 눈 중심 대비 코의 상대 위치를 사용
    - 최근 프레임 비율을 평균내서 jitter 완화
    - HandTracker처럼 구조를 단순하게 유지
    """

    NOSE_TIP = 1
    LEFT_EYE = 33
    RIGHT_EYE = 263

    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.6,
        min_tracking_confidence: float = 0.6,
        refine_landmarks: bool = True,
        left_threshold_ratio: float = -0.08,
        right_threshold_ratio: float = 0.08,
        smooth_window: int = 7,
        draw_mesh: bool = False,
    ) -> None:
        self._face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=max_num_faces,
            refine_landmarks=refine_landmarks,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.left_threshold_ratio = left_threshold_ratio
        self.right_threshold_ratio = right_threshold_ratio
        self.draw_mesh = draw_mesh
        self._yaw_history: Deque[float] = deque(maxlen=max(1, smooth_window))

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, Optional[HeadDirection]]:
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

            nose = face_landmarks.landmark[self.NOSE_TIP]
            left_eye = face_landmarks.landmark[self.LEFT_EYE]
            right_eye = face_landmarks.landmark[self.RIGHT_EYE]

            nose_x = float(np.clip(nose.x, 0.0, 1.0))
            nose_y = float(np.clip(nose.y, 0.0, 1.0))
            left_eye_x = float(np.clip(left_eye.x, 0.0, 1.0))
            right_eye_x = float(np.clip(right_eye.x, 0.0, 1.0))

            eye_center_x = (left_eye_x + right_eye_x) / 2.0
            eye_span = max(abs(right_eye_x - left_eye_x), 1e-6)

            yaw_ratio = (nose_x - eye_center_x) / eye_span
            self._yaw_history.append(yaw_ratio)
            smoothed_yaw = sum(self._yaw_history) / len(self._yaw_history)

            if smoothed_yaw < self.left_threshold_ratio:
                head_dir = "LEFT"
            elif smoothed_yaw > self.right_threshold_ratio:
                head_dir = "RIGHT"
            else:
                head_dir = "CENTER"

            px = int(np.clip(nose_x * w, 0, w - 1))
            py = int(np.clip(nose_y * h, 0, h - 1))
            eye_px = int(np.clip(eye_center_x * w, 0, w - 1))

            cv2.circle(annotated, (px, py), 5, (0, 255, 255), -1)
            cv2.circle(annotated, (eye_px, py), 4, (255, 0, 255), -1)
            cv2.line(annotated, (eye_px, 0), (eye_px, h), (255, 0, 255), 2)
            cv2.putText(
                annotated,
                f"HEAD: {head_dir}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                annotated,
                f"yaw={smoothed_yaw:.3f}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 0),
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
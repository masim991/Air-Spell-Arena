from __future__ import annotations

from collections import deque
from typing import Deque, Literal, Optional, Tuple

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

class HeadTracker:
    """
    MediaPipe Face Mesh 기반 머리 방향(좌/우/중앙) 추적기.

    간단한 방식:
    - 얼굴 랜드마크 중 코 끝 근처 점을 사용
    - 화면 중심 대비 코 위치가 일정 비율 이상 좌/우로 벗어나면 방향 판정
    - 최근 몇 프레임을 평균 내어 jitter를 줄임
    """
    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        refine_landmarks: bool = True,
        left_threshold_ratio: float = 0.42,
        right_threshold_ratio: float = 0.58,
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
        self.left_threshold_ratio = left_threshold_ratio
        self.right_threshold_ratio = right_threshold_ratio
        self.draw_mesh = draw_mesh
        self._nose_history: Deque[float] = deque(maxlen=max(1, smooth_window))

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, Optional[HeadDirection]]:
        """
        BGR 프레임을 입력받아 (주석된 프레임, 머리 방향 or None)을 반환.
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

            # MediaPipe Face Mesh에서 코 끝 근처로 자주 쓰는 랜드마크 인덱스 1
            nose = face_landmarks.landmark[1]
            nose_x = float(np.clip(nose.x, 0.0, 1.0))
            nose_y = float(np.clip(nose.y, 0.0, 1.0))

            self._nose_history.append(nose_x)
            smoothed_x = sum(self._nose_history) / len(self._nose_history)

            if smoothed_x < self.left_threshold_ratio:
                head_dir = "LEFT"
            elif smoothed_x > self.right_threshold_ratio:
                head_dir = "RIGHT"
            else:
                head_dir = "CENTER"

            px = int(nose_x * w)
            py = int(nose_y * h)
            spx = int(smoothed_x * w)

            cv2.circle(annotated, (px, py), 5, (0, 255, 255), -1)
            cv2.line(annotated, (spx, 0), (spx, h), (255, 255, 0), 2)
            cv2.line(annotated, (int(self.left_threshold_ratio * w), 0), (int(self.left_threshold_ratio * w), h), (0, 255, 0), 1)
            cv2.line(annotated, (int(self.right_threshold_ratio * w), 0), (int(self.right_threshold_ratio * w), h), (0, 255, 0), 1)

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
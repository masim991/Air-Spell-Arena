from __future__ import annotations

from typing import Literal, Optional, Tuple

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
    MediaPipe Face Mesh 기반 고정밀 Head Tracker
    - 다중 랜드마크 기반 pose 추정
    - yaw / pitch / roll 계산
    - EMA smoothing
    - 기존 반환형 유지: (annotated_frame, head_dir)
    """

    NOSE_TIP = 1
    CHIN = 199
    LEFT_EYE_OUTER = 33
    RIGHT_EYE_OUTER = 263
    LEFT_MOUTH = 61
    RIGHT_MOUTH = 291
    LEFT_EYE_INNER = 133
    RIGHT_EYE_INNER = 362

    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.7,
        refine_landmarks: bool = True,
        left_threshold_deg: float = -12.0,
        right_threshold_deg: float = 12.0,
        ema_alpha: float = 0.35,
        draw_mesh: bool = False,
        draw_axes: bool = True,
        use_ransac: bool = True,
    ) -> None:
        self._face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=max_num_faces,
            refine_landmarks=refine_landmarks,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

        self.left_threshold_deg = left_threshold_deg
        self.right_threshold_deg = right_threshold_deg
        self.ema_alpha = float(np.clip(ema_alpha, 0.01, 1.0))
        self.draw_mesh = draw_mesh
        self.draw_axes = draw_axes
        self.use_ransac = use_ransac

        self._prev_rvec: Optional[np.ndarray] = None
        self._prev_tvec: Optional[np.ndarray] = None

        self._yaw_ema: Optional[float] = None
        self._pitch_ema: Optional[float] = None
        self._roll_ema: Optional[float] = None

        self.last_yaw: float = 0.0
        self.last_pitch: float = 0.0
        self.last_roll: float = 0.0
        self.last_reprojection_error: float = 0.0

        self._model_points = np.array(
            [
                (0.0, 0.0, 0.0),          # nose tip
                (0.0, -330.0, -65.0),     # chin
                (-225.0, 170.0, -135.0),  # left eye outer
                (225.0, 170.0, -135.0),   # right eye outer
                (-150.0, -150.0, -125.0), # left mouth
                (150.0, -150.0, -125.0),  # right mouth
                (-75.0, 170.0, -135.0),   # left eye inner
                (75.0, 170.0, -135.0),    # right eye inner
            ],
            dtype=np.float64,
        )

    def _ema(self, prev: Optional[float], value: float) -> float:
        if prev is None:
            return value
        a = self.ema_alpha
        return a * value + (1.0 - a) * prev

    def _landmark_to_pixel(self, landmark, w: int, h: int) -> tuple[float, float]:
        x = float(np.clip(landmark.x, 0.0, 1.0) * w)
        y = float(np.clip(landmark.y, 0.0, 1.0) * h)
        return x, y

    def _get_image_points(self, face_landmarks, w: int, h: int) -> np.ndarray:
        indices = [
            self.NOSE_TIP,
            self.CHIN,
            self.LEFT_EYE_OUTER,
            self.RIGHT_EYE_OUTER,
            self.LEFT_MOUTH,
            self.RIGHT_MOUTH,
            self.LEFT_EYE_INNER,
            self.RIGHT_EYE_INNER,
        ]
        points = [self._landmark_to_pixel(face_landmarks.landmark[i], w, h) for i in indices]
        return np.array(points, dtype=np.float64)

    def _camera_matrix(self, w: int, h: int) -> np.ndarray:
        focal_length = float(w)
        center = (w / 2.0, h / 2.0)
        return np.array(
            [
                [focal_length, 0, center[0]],
                [0, focal_length, center[1]],
                [0, 0, 1],
            ],
            dtype=np.float64,
        )

    def _rotation_matrix_to_euler(self, R: np.ndarray) -> tuple[float, float, float]:
        sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
        singular = sy < 1e-6

        if not singular:
            x = np.arctan2(R[2, 1], R[2, 2])
            y = np.arctan2(-R[2, 0], sy)
            z = np.arctan2(R[1, 0], R[0, 0])
        else:
            x = np.arctan2(-R[1, 2], R[1, 1])
            y = np.arctan2(-R[2, 0], sy)
            z = 0.0

        pitch = float(np.degrees(x))
        yaw = float(np.degrees(y))
        roll = float(np.degrees(z))
        return yaw, pitch, roll

    def _classify_direction(self, yaw: float) -> HeadDirection:
        if yaw < self.left_threshold_deg:
            return "LEFT"
        elif yaw > self.right_threshold_deg:
            return "RIGHT"
        return "CENTER"

    def _draw_axes(
        self,
        image: np.ndarray,
        rvec: np.ndarray,
        tvec: np.ndarray,
        camera_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
        origin: Point,
        axis_len: float = 80.0,
    ) -> None:
        axes = np.float32([
            [axis_len, 0, 0],
            [0, axis_len, 0],
            [0, 0, axis_len],
        ]).reshape(-1, 3)

        imgpts, _ = cv2.projectPoints(axes, rvec, tvec, camera_matrix, dist_coeffs)
        imgpts = imgpts.reshape(-1, 2).astype(int)

        ox, oy = origin
        cv2.line(image, (ox, oy), tuple(imgpts[0]), (0, 0, 255), 2)
        cv2.line(image, (ox, oy), tuple(imgpts[1]), (0, 255, 0), 2)
        cv2.line(image, (ox, oy), tuple(imgpts[2]), (255, 0, 0), 2)

    def _reprojection_error(
        self,
        object_points: np.ndarray,
        image_points: np.ndarray,
        rvec: np.ndarray,
        tvec: np.ndarray,
        camera_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
    ) -> float:
        projected, _ = cv2.projectPoints(object_points, rvec, tvec, camera_matrix, dist_coeffs)
        projected = projected.reshape(-1, 2)
        return float(np.mean(np.linalg.norm(projected - image_points, axis=1)))

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, Optional[HeadDirection]]:
        if frame is None or frame.size == 0:
            return frame, None

        h, w = frame.shape[:2]
        annotated = frame.copy()

        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._face_mesh.process(img_rgb)

        if not results.multi_face_landmarks:
            return annotated, None

        face_landmarks = results.multi_face_landmarks[0]

        if self.draw_mesh:
            mp_drawing.draw_landmarks(
                image=annotated,
                landmark_list=face_landmarks,
                connections=mp_face_mesh.FACEMESH_CONTOURS,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_styles.get_default_face_mesh_contours_style(),
            )

        image_points = self._get_image_points(face_landmarks, w, h)
        camera_matrix = self._camera_matrix(w, h)
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        success = False
        rvec = None
        tvec = None

        if self.use_ransac:
            success, rvec, tvec, _ = cv2.solvePnPRansac(
                self._model_points,
                image_points,
                camera_matrix,
                dist_coeffs,
                rvec=self._prev_rvec,
                tvec=self._prev_tvec,
                useExtrinsicGuess=(self._prev_rvec is not None and self._prev_tvec is not None),
                iterationsCount=100,
                reprojectionError=4.0,
                confidence=0.99,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
        else:
            success, rvec, tvec = cv2.solvePnP(
                self._model_points,
                image_points,
                camera_matrix,
                dist_coeffs,
                rvec=self._prev_rvec,
                tvec=self._prev_tvec,
                useExtrinsicGuess=(self._prev_rvec is not None and self._prev_tvec is not None),
                flags=cv2.SOLVEPNP_ITERATIVE,
            )

        if not success or rvec is None or tvec is None:
            return annotated, None

        self._prev_rvec = rvec
        self._prev_tvec = tvec

        rotation_matrix, _ = cv2.Rodrigues(rvec)
        yaw, pitch, roll = self._rotation_matrix_to_euler(rotation_matrix)

        self._yaw_ema = self._ema(self._yaw_ema, yaw)
        self._pitch_ema = self._ema(self._pitch_ema, pitch)
        self._roll_ema = self._ema(self._roll_ema, roll)

        self.last_yaw = self._yaw_ema
        self.last_pitch = self._pitch_ema
        self.last_roll = self._roll_ema

        head_dir = self._classify_direction(self.last_yaw)

        reproj_error = self._reprojection_error(
            self._model_points,
            image_points,
            rvec,
            tvec,
            camera_matrix,
            dist_coeffs,
        )
        self.last_reprojection_error = reproj_error

        nose_x, nose_y = image_points[0]
        nose_pt = (
            int(np.clip(nose_x, 0, w - 1)),
            int(np.clip(nose_y, 0, h - 1)),
        )

        for p in image_points.astype(int):
            cv2.circle(annotated, tuple(p), 2, (255, 180, 0), -1)

        cv2.circle(annotated, nose_pt, 5, (0, 255, 255), -1)

        if self.draw_axes:
            self._draw_axes(
                annotated,
                rvec,
                tvec,
                camera_matrix,
                dist_coeffs,
                nose_pt,
            )

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
            f"yaw={self.last_yaw:+.1f} pitch={self.last_pitch:+.1f} roll={self.last_roll:+.1f}",
            (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"err={self.last_reprojection_error:.2f}px",
            (20, 102),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (180, 255, 180),
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
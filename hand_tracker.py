from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

import cv2
import numpy as np

try:
    from mediapipe.solutions import hands as mp_hands
    from mediapipe.solutions import drawing_utils as mp_drawing
    from mediapipe.solutions import drawing_styles as mp_styles
except Exception:
    try:
        from mediapipe.python.solutions import hands as mp_hands  # type: ignore
        from mediapipe.python.solutions import drawing_utils as mp_drawing  # type: ignore
        from mediapipe.python.solutions import drawing_styles as mp_styles  # type: ignore
    except Exception as e:
        raise ImportError(
            "mediapipe 패키지가 필요합니다.\n"
            "pip install mediapipe로 설치해주세요"
        ) from e


Point = Tuple[int, int]
HandLabel = Literal["Left", "Right"]


@dataclass
class HandState:
    label: Optional[HandLabel]
    score: float
    wrist: Point
    palm_center: Point
    index_tip: Point
    middle_tip: Point
    thumb_tip: Point
    pinch: bool
    pinch_strength: float
    pointing_vector: Tuple[float, float]
    hand_size_px: float
    landmarks_px: List[Point]


class _AdaptiveEMA:
    """Velocity-aware EMA: fast alpha when hand moves quickly, slow alpha when stable."""

    def __init__(
        self,
        alpha_fast: float = 0.60,
        alpha_slow: float = 0.28,
        vel_threshold: float = 6.0,
    ) -> None:
        self.alpha_fast    = float(np.clip(alpha_fast, 0.01, 1.0))
        self.alpha_slow    = float(np.clip(alpha_slow, 0.01, 1.0))
        self.vel_threshold = vel_threshold
        self.prev: Optional[np.ndarray] = None

    def update(self, pts: np.ndarray) -> np.ndarray:
        if self.prev is None:
            self.prev = pts.copy()
            return self.prev.copy()
        vel = float(np.mean(np.linalg.norm(pts - self.prev, axis=1)))
        alpha = self.alpha_fast if vel > self.vel_threshold else self.alpha_slow
        self.prev = alpha * pts + (1.0 - alpha) * self.prev
        return self.prev.copy()

    def reset(self) -> None:
        self.prev = None


class HandTracker:
    """
    MediaPipe Hands 기반 정밀 Hand Tracker

    특징:
    - 21개 랜드마크 전체 추적
    - EMA smoothing
    - 손 크기 기반 정규화
    - pinch / pointing 계산
    - 게임 입력용 상태 제공
    """

    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4

    INDEX_MCP = 5
    INDEX_PIP = 6
    INDEX_DIP = 7
    INDEX_TIP = 8

    MIDDLE_MCP = 9
    MIDDLE_PIP = 10
    MIDDLE_DIP = 11
    MIDDLE_TIP = 12

    RING_MCP = 13
    RING_PIP = 14
    RING_DIP = 15
    RING_TIP = 16

    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20

    _NO_DETECT_HOLD = 12  # frames to hold last state when hand temporarily lost

    def __init__(
        self,
        max_num_hands: int = 1,
        min_detection_confidence: float = 0.65,
        min_tracking_confidence: float = 0.50,
        model_complexity: int = 1,
        ema_alpha_fast: float = 0.60,
        ema_alpha_slow: float = 0.28,
        pinch_threshold_ratio: float = 0.30,
        draw_landmarks: bool = True,
        draw_info: bool = True,
    ) -> None:
        self._hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

        self.draw_landmarks = draw_landmarks
        self.draw_info = draw_info
        self.pinch_threshold_ratio = pinch_threshold_ratio
        self._ema = _AdaptiveEMA(alpha_fast=ema_alpha_fast, alpha_slow=ema_alpha_slow)
        self.last_state: Optional[HandState] = None
        self._no_detect_frames: int = 0

    def _norm_to_px(self, lm, w: int, h: int) -> tuple[float, float]:
        x = float(np.clip(lm.x, 0.0, 1.0) * w)
        y = float(np.clip(lm.y, 0.0, 1.0) * h)
        return x, y

    def _extract_landmarks_px(self, hand_landmarks, w: int, h: int) -> np.ndarray:
        pts = [self._norm_to_px(lm, w, h) for lm in hand_landmarks.landmark]
        return np.array(pts, dtype=np.float32)

    def _hand_size(self, pts: np.ndarray) -> float:
        wrist = pts[self.WRIST]
        index_mcp = pts[self.INDEX_MCP]
        pinky_mcp = pts[self.PINKY_MCP]
        middle_mcp = pts[self.MIDDLE_MCP]

        palm_width = np.linalg.norm(index_mcp - pinky_mcp)
        palm_height = np.linalg.norm(wrist - middle_mcp)
        return float(max((palm_width + palm_height) * 0.5, 1.0))

    def _palm_center(self, pts: np.ndarray) -> np.ndarray:
        key_ids = [self.WRIST, self.INDEX_MCP, self.MIDDLE_MCP, self.RING_MCP, self.PINKY_MCP]
        return np.mean(pts[key_ids], axis=0)

    def _pointing_vector(self, pts: np.ndarray) -> tuple[float, float]:
        base = pts[self.INDEX_MCP]
        tip = pts[self.INDEX_TIP]
        vec = tip - base
        norm = float(np.linalg.norm(vec))
        if norm < 1e-6:
            return (0.0, 0.0)
        unit = vec / norm
        return (float(unit[0]), float(unit[1]))

    def _pinch_strength(self, pts: np.ndarray, hand_size: float) -> float:
        thumb_tip  = pts[self.THUMB_TIP]
        index_tip  = pts[self.INDEX_TIP]
        middle_tip = pts[self.MIDDLE_TIP]
        d_index  = float(np.linalg.norm(thumb_tip - index_tip))
        d_middle = float(np.linalg.norm(thumb_tip - middle_tip))
        dist  = d_index * 0.70 + d_middle * 0.30
        ratio = dist / max(hand_size, 1.0)
        return float(1.0 - np.clip(ratio / self.pinch_threshold_ratio, 0.0, 1.0))

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, Optional[HandState]]:
        if frame is None or frame.size == 0:
            return frame, None

        h, w = frame.shape[:2]
        annotated = frame.copy()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb)

        if not results.multi_hand_landmarks:
            self._no_detect_frames += 1
            if self._no_detect_frames > self._NO_DETECT_HOLD:
                self.last_state = None
                self._ema.reset()
            return annotated, self.last_state

        self._no_detect_frames = 0
        hand_landmarks = results.multi_hand_landmarks[0]
        handedness = None
        score = 0.0

        if results.multi_handedness and len(results.multi_handedness) > 0:
            cls = results.multi_handedness[0].classification[0]
            handedness = cls.label
            score = float(cls.score)

        pts = self._extract_landmarks_px(hand_landmarks, w, h)
        pts = self._ema.update(pts)

        hand_size = self._hand_size(pts)
        palm_center = self._palm_center(pts)
        pinch_strength = self._pinch_strength(pts, hand_size)
        pinch = pinch_strength > 0.5
        pointing_vector = self._pointing_vector(pts)

        wrist = tuple(pts[self.WRIST].astype(int))
        palm_pt = tuple(palm_center.astype(int))
        index_tip = tuple(pts[self.INDEX_TIP].astype(int))
        middle_tip = tuple(pts[self.MIDDLE_TIP].astype(int))
        thumb_tip = tuple(pts[self.THUMB_TIP].astype(int))
        lm_points = [tuple(p.astype(int)) for p in pts]

        state = HandState(
            label=handedness,  # type: ignore
            score=score,
            wrist=wrist,
            palm_center=palm_pt,
            index_tip=index_tip,
            middle_tip=middle_tip,
            thumb_tip=thumb_tip,
            pinch=pinch,
            pinch_strength=pinch_strength,
            pointing_vector=pointing_vector,
            hand_size_px=hand_size,
            landmarks_px=lm_points,
        )
        self.last_state = state

        if self.draw_landmarks:
            mp_drawing.draw_landmarks(
                annotated,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS,
                mp_styles.get_default_hand_landmarks_style(),
                mp_styles.get_default_hand_connections_style(),
            )

            for p in lm_points:
                cv2.circle(annotated, p, 2, (255, 220, 0), -1)

            cv2.circle(annotated, wrist, 5, (0, 255, 255), -1)
            cv2.circle(annotated, palm_pt, 6, (255, 0, 255), -1)
            cv2.circle(annotated, index_tip, 6, (0, 255, 0), -1)
            cv2.circle(annotated, thumb_tip, 6, (0, 180, 255), -1)

            cv2.line(annotated, thumb_tip, index_tip, (0, 200, 255), 2)
            cv2.line(annotated, tuple(pts[self.INDEX_MCP].astype(int)), index_tip, (0, 255, 0), 2)

        if self.draw_info:
            cv2.putText(
                annotated,
                f"HAND: {handedness or 'Unknown'} ({score:.2f})",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                annotated,
                f"pinch={'ON' if pinch else 'OFF'} strength={pinch_strength:.2f}",
                (20, 65),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                annotated,
                f"point=({pointing_vector[0]:+.2f}, {pointing_vector[1]:+.2f}) size={hand_size:.1f}",
                (20, 95),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (180, 255, 180),
                2,
                cv2.LINE_AA,
            )

        return annotated, state

    def close(self) -> None:
        if hasattr(self, "_hands") and self._hands is not None:
            self._hands.close()
            self._hands = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
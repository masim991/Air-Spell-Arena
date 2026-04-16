"""
air_canvas.py – HSV marker-tracking input module for Air Spell Arena.

Typical game-loop usage::

    from air_canvas import AirCanvas, FrameData, COLOR_NAMES

    canvas = AirCanvas()
    while True:
        data = canvas.update()
        if data is None:
            break                               # 'q' pressed or camera lost
        if data.stroke_complete and data.last_stroke:
            spell = gesture_analyzer.classify(data.last_stroke)
            game.trigger(spell)
        cv2.imshow("Tracking", data.frame)
        cv2.imshow("Paint",    data.paint)
    canvas.release()
"""

from __future__ import annotations

import dataclasses
from collections import deque
from typing import Optional

import cv2
import numpy as np


# ── Palette & layout constants ─────────────────────────────────────────────────

# BGR drawing colours
COLORS: list[tuple[int, int, int]] = [
    (255,   0,   0),   # 0 – Blue
    (  0, 255,   0),   # 1 – Green
    (  0,   0, 255),   # 2 – Red
    (  0, 255, 255),   # 3 – Yellow
]

COLOR_NAMES: list[str] = ["BLUE", "GREEN", "RED", "YELLOW"]

_BTN_Y    = 65          # button bar bottom edge (px)
_CANVAS_H = 471
_CANVAS_W = 636
_MAX_PTS  = 1024
_KERNEL   = np.ones((5, 5), np.uint8)

# (x0, x1) pixel ranges per button
_BTN_X: list[tuple[int, int]] = [
    ( 40, 140),   # CLEAR
    (160, 255),   # BLUE
    (275, 370),   # GREEN
    (390, 485),   # RED
    (505, 600),   # YELLOW
]
_BTN_LABELS = ["CLEAR ALL", "BLUE", "GREEN", "RED", "YELLOW"]
_BTN_TEXT_X = [49, 185, 298, 420, 520]


# ── Data packet ────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class FrameData:
    """Snapshot returned by AirCanvas.update() on every frame."""

    frame:           np.ndarray                 # annotated webcam frame (BGR, uint8)
    paint:           np.ndarray                 # accumulated paint canvas (BGR, uint8)
    mask:            np.ndarray                 # binary HSV colour mask
    center:          Optional[tuple[int, int]]  # detected marker centroid, or None
    stroke_complete: bool                       # True on the first frame the marker is lost
    last_stroke:     list[tuple[int, int]]      # ordered point list of the finished stroke


# ── AirCanvas ─────────────────────────────────────────────────────────────────

class AirCanvas:
    """
    Webcam-based air-drawing input module.

    Call ``update()`` once per game frame.  When ``FrameData.stroke_complete``
    is True, ``FrameData.last_stroke`` holds the full ordered trajectory ready
    for a GestureAnalyzer.
    """

    def __init__(
        self,
        camera_index: int = 0,
        show_trackbars: bool = True,
        hsv_lower: tuple[int, int, int] = (64, 72, 49),
        hsv_upper: tuple[int, int, int] = (153, 255, 255),
    ) -> None:
        self._color_idx      = 0
        self._show_trackbars = show_trackbars
        self._hsv_lower      = np.array(hsv_lower, dtype=np.uint8)
        self._hsv_upper      = np.array(hsv_upper, dtype=np.uint8)

        # Per-colour stroke storage: list-of-deques, one deque per pen-down segment
        self._pts:     list[list[deque]] = [[deque(maxlen=_MAX_PTS)] for _ in COLORS]
        self._indices: list[int]         = [0] * len(COLORS)

        # Live stroke buffer – accumulates points between pen-down and pen-up
        self._active:      list[tuple[int, int]] = []
        self._had_center = False

        self._paint = _build_paint_canvas()
        self._cap   = cv2.VideoCapture(camera_index)

        if show_trackbars:
            _create_trackbars(self._hsv_lower, self._hsv_upper)

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def color_index(self) -> int:
        """Currently active drawing colour index (0-3)."""
        return self._color_idx

    def set_color(self, idx: int) -> None:
        """Select drawing colour by index (0=Blue, 1=Green, 2=Red, 3=Yellow)."""
        self._color_idx = idx % len(COLORS)

    def clear(self) -> None:
        """Erase all strokes and reset stroke storage."""
        self._pts     = [[deque(maxlen=_MAX_PTS)] for _ in COLORS]
        self._indices = [0] * len(COLORS)
        self._active.clear()
        self._paint[_BTN_Y + 2:, :, :] = 255  # 버튼 바 아래 영역만 흰색으로 초기화

    def update(self) -> Optional[FrameData]:
        """
        Process one webcam frame and return a FrameData packet.
        Returns ``None`` when the user presses ``q`` or the camera fails.
        """
        ret, frame = self._cap.read()
        if not ret:
            return None

        frame = cv2.flip(frame, 1)
        hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask  = self._build_mask(hsv)

        _draw_ui(frame, on_frame=True)

        center            = self._find_center(mask, frame)
        done, last_stroke = self._record(center)
        self._render_strokes(frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            return None

        return FrameData(
            frame=frame,
            paint=self._paint.copy(),
            mask=mask,
            center=center,
            stroke_complete=done,
            last_stroke=last_stroke,
        )

    def release(self) -> None:
        """Release the webcam and destroy all OpenCV windows."""
        self._cap.release()
        cv2.destroyAllWindows()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_mask(self, hsv: np.ndarray) -> np.ndarray:
        lo, hi = (_read_trackbars() if self._show_trackbars
                  else (self._hsv_lower, self._hsv_upper))
        m = cv2.inRange(hsv, lo, hi)
        m = cv2.erode(m, _KERNEL, iterations=1)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, _KERNEL)
        m = cv2.dilate(m, _KERNEL, iterations=1)
        return m

    def _find_center(
        self, mask: np.ndarray, frame: np.ndarray
    ) -> Optional[tuple[int, int]]:
        cnts, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return None
        cnt = max(cnts, key=cv2.contourArea)
        (cx, cy), radius = cv2.minEnclosingCircle(cnt)
        cv2.circle(frame, (int(cx), int(cy)), int(radius), (0, 255, 255), 2)
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            return None
        return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

    def _record(
        self, center: Optional[tuple[int, int]]
    ) -> tuple[bool, list[tuple[int, int]]]:
        """Append center to the active stroke; detect pen-up (stroke complete)."""
        done: bool = False
        last: list[tuple[int, int]] = []

        if center is not None:
            x, y = center
            if y <= _BTN_Y:
                self._on_button(x)
            else:
                bucket = self._pts[self._color_idx][self._indices[self._color_idx]]
                bucket.appendleft(center)
                self._active.append(center)
            self._had_center = True
        else:
            if self._had_center and self._active:
                # 마커가 사라진 첫 번째 프레임 → 스트로크 완성
                done, last = True, list(self._active)
                self._active = []
            # 새 선분 세그먼트 시작 (펜 들기)
            for i in range(len(COLORS)):
                self._pts[i].append(deque(maxlen=_MAX_PTS))
                self._indices[i] += 1
            self._had_center = False

        return done, last

    def _on_button(self, cx: int) -> None:
        x0, x1 = _BTN_X[0]
        if x0 <= cx <= x1:
            self.clear()
            return
        for i, (x0, x1) in enumerate(_BTN_X[1:]):
            if x0 <= cx <= x1:
                self.set_color(i)
                return

    def _render_strokes(self, frame: np.ndarray) -> None:
        for ci, pt_list in enumerate(self._pts):
            color = COLORS[ci]
            for deq in pt_list:
                pts = list(deq)
                for k in range(1, len(pts)):
                    if pts[k - 1] is None or pts[k] is None:
                        continue
                    cv2.line(frame,       pts[k - 1], pts[k], color, 2)
                    cv2.line(self._paint, pts[k - 1], pts[k], color, 2)


# ── Module-level helpers ───────────────────────────────────────────────────────

def _create_trackbars(lower: np.ndarray, upper: np.ndarray) -> None:
    cv2.namedWindow("Color detectors")
    specs = [
        ("Upper Hue",        int(upper[0]), 180),
        ("Upper Saturation", int(upper[1]), 255),
        ("Upper Value",      int(upper[2]), 255),
        ("Lower Hue",        int(lower[0]), 180),
        ("Lower Saturation", int(lower[1]), 255),
        ("Lower Value",      int(lower[2]), 255),
    ]
    for name, val, max_ in specs:
        cv2.createTrackbar(name, "Color detectors", val, max_, lambda x: None)


def _read_trackbars() -> tuple[np.ndarray, np.ndarray]:
    upper = np.array(
        [cv2.getTrackbarPos(n, "Color detectors")
         for n in ("Upper Hue", "Upper Saturation", "Upper Value")],
        dtype=np.uint8,
    )
    lower = np.array(
        [cv2.getTrackbarPos(n, "Color detectors")
         for n in ("Lower Hue", "Lower Saturation", "Lower Value")],
        dtype=np.uint8,
    )
    return lower, upper


def _draw_ui(frame: np.ndarray, on_frame: bool = True) -> None:
    """Draw the colour-selector button bar onto *frame* in-place."""
    # CLEAR 버튼: 프레임에선 회색 채움 / 캔버스에선 검정 테두리만
    clear_bg   = (122, 122, 122) if on_frame else (0, 0, 0)
    clear_fill = -1               if on_frame else 2
    cv2.rectangle(frame, (_BTN_X[0][0], 1), (_BTN_X[0][1], _BTN_Y), clear_bg, clear_fill)

    for i, (x0, x1) in enumerate(_BTN_X[1:]):
        cv2.rectangle(frame, (x0, 1), (x1, _BTN_Y), COLORS[i], -1)

    labels      = _BTN_LABELS if on_frame else ["CLEAR"] + _BTN_LABELS[1:]
    text_colors = [(255,255,255),(255,255,255),(255,255,255),(255,255,255),(150,150,150)]
    if not on_frame:
        text_colors[0] = (0, 0, 0)

    for lbl, tx, tc in zip(labels, _BTN_TEXT_X, text_colors):
        cv2.putText(frame, lbl, (tx, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.5, tc, 2, cv2.LINE_AA)


def _build_paint_canvas() -> np.ndarray:
    canvas = np.full((_CANVAS_H, _CANVAS_W, 3), 255, dtype=np.uint8)
    _draw_ui(canvas, on_frame=False)
    return canvas


# ── Standalone demo ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    canvas = AirCanvas()
    print("Air Canvas – press 'q' to quit.")
    while True:
        data = canvas.update()
        if data is None:
            break
        if data.stroke_complete and data.last_stroke:
            print(
                f"[stroke] {len(data.last_stroke)} pts | "
                f"color={COLOR_NAMES[canvas.color_index]}"
            )
        cv2.imshow("Tracking", data.frame)
        cv2.imshow("Paint",    data.paint)
        cv2.imshow("Mask",     data.mask)
    canvas.release()

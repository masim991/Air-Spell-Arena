"""
canvas.py – Air Spell Arena 공중 드로잉 입력 모듈.

외부 모듈(게임 루프, 제스처 인식기 등)에서 임포트하거나
단독 실행(python canvas.py)으로 동작을 확인할 수 있습니다.
"""
from __future__ import annotations

import dataclasses
from collections import deque

import cv2
import numpy as np

from gesture import GestureAnalyzer
from trajectory import TrajectoryBuffer


# ── 설정 데이터클래스 ──────────────────────────────────────────────────────────

@dataclasses.dataclass
class CanvasConfig:
    """HSV 감지 범위 및 드로잉 관련 설정값을 담는 불변 설정 객체."""

    upper_hue: int = 153   # 색조 상한값
    upper_sat: int = 255   # 채도 상한값
    upper_val: int = 255   # 명도 상한값
    lower_hue: int = 64    # 색조 하한값
    lower_sat: int = 72    # 채도 하한값
    lower_val: int = 49    # 명도 하한값
    max_points: int = 1024 # 색상별 덱(deque)에 저장할 최대 좌표 수


# ── AirCanvas 클래스 ───────────────────────────────────────────────────────────

class AirCanvas:
    """
    HSV 마커 추적 기반 공중 드로잉 입력 클래스.

    전역 변수 없이 모든 상태를 인스턴스 속성으로 관리하며,
    run() 메서드로 메인 루프를 실행합니다.
    나중에 게임 루프나 제스처 인식기와 연동할 수 있도록
    현재 중심점과 스트로크를 항상 최신 상태로 유지합니다.
    """

    # BGR 색상 팔레트 (파랑, 초록, 빨강, 노랑)
    COLORS: list[tuple[int, int, int]] = [
        (255,   0,   0),
        (  0, 255,   0),
        (  0,   0, 255),
        (  0, 255, 255),
    ]
    COLOR_NAMES: list[str] = ["BLUE", "GREEN", "RED", "YELLOW"]

    # 상단 버튼 바 레이아웃 상수
    _BTN_CLEAR  = ( 40, 140)                              # CLEAR 버튼 x 범위
    _BTN_COLORS = [(160, 255), (275, 370), (390, 485), (505, 600)]  # 색상 버튼 x 범위
    _BTN_Y      = 65                                      # 버튼 바 하단 y 좌표

    def __init__(
        self,
        camera_index: int = 0,
        config: CanvasConfig | None = None,
    ) -> None:
        """
        AirCanvas를 초기화합니다.

        Args:
            camera_index: 사용할 카메라 인덱스 (기본값 0).
            config: HSV 범위 및 드로잉 설정 객체.
                    None이면 CanvasConfig 기본값을 사용합니다.
        """
        self._cfg       = config or CanvasConfig()
        self._kernel    = np.ones((5, 5), np.uint8)
        self._color_idx = 0  # 현재 선택된 색상 인덱스

        # 색상별 스트로크 저장: 리스트[색상] → 리스트[세그먼트] → deque[좌표]
        n = self._cfg.max_points
        self._pts:     list[list[deque]] = [[deque(maxlen=n)] for _ in self.COLORS]
        self._indices: list[int]         = [0] * len(self.COLORS)

        # 외부 연동용: 현재 프레임 중심점과 진행 중인 스트로크
        self._current_center: tuple[int, int] | None = None
        self._current_stroke: list[tuple[int, int]]  = []

        self._paint = self._make_paint_window()
        self._cap   = cv2.VideoCapture(camera_index)
        self._trajectory_buffer = TrajectoryBuffer()
        self._init_windows()

    # ── 공개 메서드 ──────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        메인 루프를 실행합니다.

        매 프레임마다 웹캠을 읽고, HSV 마스킹으로 마커를 추적하며,
        Tracking / Paint / mask 창에 결과를 표시합니다.
        'q' 키를 누르거나 카메라 읽기에 실패하면 루프를 종료하고
        자원을 해제합니다.
        """
        while True:
            ret, frame = self._cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask  = self._build_mask(hsv)

            self._draw_ui_overlay(frame)
            self._update_center(mask, frame)
            self._trajectory_buffer.update(self._current_center)
            self._update_strokes()
            self._draw_strokes(frame)

            cv2.imshow("Tracking", frame)
            cv2.imshow("Paint",    self._paint)
            cv2.imshow("mask",     mask)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        self.release()

    def get_current_center(self) -> tuple[int, int] | None:
        """
        현재 프레임에서 감지된 마커의 중심 좌표를 반환합니다.

        Returns:
            (x, y) 픽셀 좌표, 마커가 없으면 None.
        """
        return self._current_center

    def get_current_stroke(self) -> list[tuple[int, int]]:
        """
        현재 펜-다운 중인 스트로크의 좌표 목록을 반환합니다.

        마커가 화면에서 사라지면 목록이 초기화됩니다.
        나중에 제스처 인식기에 전달할 궤적으로 사용합니다.

        Returns:
            현재 스트로크 좌표 리스트의 복사본.
        """
        return list(self._current_stroke)

    def get_last_trajectory(self) -> list[tuple[int, int]]:
        """
        현재 색상의 마지막 완성된 스트로크 세그먼트를 반환합니다.

        Returns:
            가장 최근 덱 세그먼트의 좌표 리스트.
        """
        idx = self._indices[self._color_idx]
        return list(self._pts[self._color_idx][idx])

    def poll_spell(self, gesture_analyzer: GestureAnalyzer) -> str | None:
        """완료된 새 궤적이 있으면 1회성으로 분류 결과(주문명)를 반환합니다."""
        traj = self._trajectory_buffer.poll_last_closed()
        if not traj:
            return None
        return gesture_analyzer.classify(traj)

    def release(self) -> None:
        """카메라 자원을 해제하고 모든 OpenCV 창을 닫습니다."""
        self._cap.release()
        cv2.destroyAllWindows()

    # ── 비공개 메서드 ────────────────────────────────────────────────────────

    def _init_windows(self) -> None:
        """HSV 트랙바 창과 Paint 창을 초기화합니다."""
        c = self._cfg
        cv2.namedWindow("Color detectors")
        for name, val, max_ in [
            ("Upper Hue",        c.upper_hue, 180),
            ("Upper Saturation", c.upper_sat, 255),
            ("Upper Value",      c.upper_val, 255),
            ("Lower Hue",        c.lower_hue, 180),
            ("Lower Saturation", c.lower_sat, 255),
            ("Lower Value",      c.lower_val, 255),
        ]:
            cv2.createTrackbar(name, "Color detectors", val, max_, lambda x: None)
        cv2.namedWindow("Paint", cv2.WINDOW_AUTOSIZE)

    def _get_hsv_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """트랙바에서 현재 HSV 상·하한 배열을 읽어 반환합니다."""
        g = lambda n: cv2.getTrackbarPos(n, "Color detectors")
        upper = np.array([g("Upper Hue"), g("Upper Saturation"), g("Upper Value")])
        lower = np.array([g("Lower Hue"), g("Lower Saturation"), g("Lower Value")])
        return lower, upper

    def _build_mask(self, hsv: np.ndarray) -> np.ndarray:
        """HSV 범위로 색상 마스크를 생성하고 노이즈를 제거합니다."""
        lower, upper = self._get_hsv_bounds()
        m = cv2.inRange(hsv, lower, upper)
        m = cv2.erode(m, self._kernel, iterations=1)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, self._kernel)
        m = cv2.dilate(m, self._kernel, iterations=1)
        return m

    def _update_center(self, mask: np.ndarray, frame: np.ndarray) -> None:
        """마스크에서 가장 큰 컨투어를 찾아 _current_center를 갱신합니다."""
        cnts, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            self._current_center = None
            return
        cnt = sorted(cnts, key=cv2.contourArea, reverse=True)[0]
        ((x, y), radius) = cv2.minEnclosingCircle(cnt)
        cv2.circle(frame, (int(x), int(y)), int(radius), (0, 255, 255), 2)
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            self._current_center = None
            return
        self._current_center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

    def _update_strokes(self) -> None:
        """
        _current_center를 기반으로 스트로크 덱을 업데이트합니다.

        - 버튼 영역(y <= BTN_Y): 버튼 동작 처리
        - 드로잉 영역: 현재 색상 덱에 좌표 추가
        - 마커 없음: 새 세그먼트 시작 (펜 들기)
        """
        center = self._current_center
        n = self._cfg.max_points
        if center is not None:
            cx, cy = center
            if cy <= self._BTN_Y:
                self._handle_button(cx)
            else:
                self._pts[self._color_idx][self._indices[self._color_idx]].appendleft(center)
                self._current_stroke.append(center)
        else:
            self._current_stroke = []
            for i in range(len(self.COLORS)):
                self._pts[i].append(deque(maxlen=n))
                self._indices[i] += 1

    def _handle_button(self, cx: int) -> None:
        """x 좌표를 기준으로 CLEAR 또는 색상 선택 버튼 동작을 처리합니다."""
        x0, x1 = self._BTN_CLEAR
        if x0 <= cx <= x1:
            n = self._cfg.max_points
            self._pts     = [[deque(maxlen=n)] for _ in self.COLORS]
            self._indices = [0] * len(self.COLORS)
            self._current_stroke = []
            self._trajectory_buffer = TrajectoryBuffer()
            self._paint[self._BTN_Y + 2:, :, :] = 255
            return
        for idx, (x0, x1) in enumerate(self._BTN_COLORS):
            if x0 <= cx <= x1:
                self._color_idx = idx
                return

    def _draw_strokes(self, frame: np.ndarray) -> None:
        """저장된 모든 스트로크를 프레임과 페인트 캔버스에 그립니다."""
        for ci, pt_list in enumerate(self._pts):
            color = self.COLORS[ci]
            for deq in pt_list:
                pts = list(deq)
                for k in range(1, len(pts)):
                    if pts[k - 1] is None or pts[k] is None:
                        continue
                    cv2.line(frame,       pts[k - 1], pts[k], color, 2)
                    cv2.line(self._paint, pts[k - 1], pts[k], color, 2)

    def _draw_ui_overlay(self, frame: np.ndarray) -> None:
        """프레임 상단에 CLEAR / 색상 선택 버튼 바를 오버레이합니다."""
        cv2.rectangle(frame, (self._BTN_CLEAR[0], 1), (self._BTN_CLEAR[1], self._BTN_Y), (122, 122, 122), -1)
        for i, (x0, x1) in enumerate(self._BTN_COLORS):
            cv2.rectangle(frame, (x0, 1), (x1, self._BTN_Y), self.COLORS[i], -1)
        for lbl, tx, tc in zip(
            ["CLEAR ALL", "BLUE", "GREEN", "RED", "YELLOW"],
            [49, 185, 298, 420, 520],
            [(255, 255, 255), (255, 255, 255), (255, 255, 255), (255, 255, 255), (150, 150, 150)],
        ):
            cv2.putText(frame, lbl, (tx, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.5, tc, 2, cv2.LINE_AA)

    @staticmethod
    def _make_paint_window() -> np.ndarray:
        """흰색 배경의 페인트 캔버스를 생성하고 버튼 바를 그려 반환합니다."""
        canvas = np.zeros((471, 636, 3)) + 255
        colors = AirCanvas.COLORS
        cv2.rectangle(canvas, ( 40, 1), (140, 65), (0, 0, 0),  2)
        cv2.rectangle(canvas, (160, 1), (255, 65), colors[0], -1)
        cv2.rectangle(canvas, (275, 1), (370, 65), colors[1], -1)
        cv2.rectangle(canvas, (390, 1), (485, 65), colors[2], -1)
        cv2.rectangle(canvas, (505, 1), (600, 65), colors[3], -1)
        cv2.putText(canvas, "CLEAR",  ( 49, 33), cv2.FONT_HERSHEY_DUPLEX, 0.5, (  0,   0,   0), 2, cv2.LINE_AA)
        cv2.putText(canvas, "BLUE",   (185, 33), cv2.FONT_ITALIC,         0.5, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "GREEN",  (298, 33), cv2.FONT_ITALIC,         0.5, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "RED",    (420, 33), cv2.FONT_ITALIC,         0.5, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "YELLOW", (520, 33), cv2.FONT_ITALIC,         0.5, (150, 150, 150), 2, cv2.LINE_AA)
        return canvas


# ── 단독 실행 진입점 ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    AirCanvas().run()
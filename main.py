from __future__ import annotations
"""
main.py – 비전 입력(VisionPipeline / AirCanvas) + 제스처 + Pygame(SpellGame) 조율.

게임 루프는 비전 워커 스레드와 분리되어, 카메라·MediaPipe 지연에 묶이지 않는다.
- 손 추적 경로(USE_HAND_TRACKING=True): VisionPipeline 이 별도 스레드에서 캡처·추론,
  메인 루프는 최신 결과(poll_result)와 주문 이벤트(drain_spells)만 소비한다.
- HSV 마커 경로(False): AirCanvas.update() 를 메인 루프에서 직접 호출한다.

종료 조건:
- Pygame 창 닫힘 / ESC → SpellGame.run_one_frame() 이 False 반환
- 디버그 창에서 'q'
- 비전 파이프라인 연속 실패(graceful)
"""

import logging
from typing import Optional

import cv2

from air_canvas import AirCanvas
from gesture import GestureAnalyzer
from game import SpellGame
from spell_combo import SpellComboEngine
from trajectory import TrajectoryBuffer, TrajectoryConfig
from vision_loop import VisionPipeline


# ── 실행 옵션 ────────────────────────────────────────────────────────────────
SHOW_DEBUG_WINDOWS = True    # 웹캠 디버그 창(Tracking/Mask/Paint) 표시
CAMERA_INDEX = 0
SHOW_TRACKBARS = False       # HSV 경로 트랙바
USE_HAND_TRACKING = True     # True: MediaPipe 손가락 추적, False: HSV 마커 추적

log = logging.getLogger("air_spell_arena.main")


def _now_s() -> float:
    """단조 증가 초 단위 타임스탬프(콤보 윈도 계산용)."""
    return cv2.getTickCount() / cv2.getTickFrequency()


def _run_hand_tracking(game: SpellGame, combo_engine: SpellComboEngine) -> None:
    """VisionPipeline(워커 스레드) 기반 메인 루프.

    카메라/MediaPipe 초기화가 실패해도 게임을 종료하지 않는다 — 메뉴는 계속 뜨고,
    타이틀 화면의 "PLAY WITHOUT CAMERA" 버튼이나 인게임 키보드 폴백으로 계속 진행할 수 있다.
    """
    pipeline: Optional[VisionPipeline] = VisionPipeline(CAMERA_INDEX, show_debug=SHOW_DEBUG_WINDOWS)
    pipeline.start()
    if pipeline.failed:
        log.warning("비전 파이프라인 시작 실패 — 카메라 없이 키보드 폴백으로 진행합니다.")
        pipeline.close()
        pipeline = None

    last_head_dir: Optional[str] = None
    running = True
    try:
        while running:
            if pipeline is not None and pipeline.failed:
                log.warning("비전 파이프라인이 중단되었습니다 — 키보드 폴백으로 전환합니다.")
                pipeline.close()
                pipeline = None
                last_head_dir = None

            spell_name: Optional[str] = None
            if pipeline is not None:
                # 1) 주문 이벤트 소비: 포즈/궤적 모두 콤보 엔진 경유(최신 결과 채택)
                for _, name in pipeline.drain_spells():
                    spell_name = combo_engine.push_basic_spell(name, _now_s())

                # 2) 최신 비전 결과 소비(연속 신호: head_dir, 디버그 프레임)
                res = pipeline.poll_result()
                if res is not None:
                    last_head_dir = res.head_dir
                    game.set_gesture_feedback(res.trail, res.drawing)
                    if SHOW_DEBUG_WINDOWS and res.annotated is not None:
                        cv2.imshow("Tracking", res.annotated)
                        if res.mask is not None:
                            cv2.imshow("Mask", res.mask)
                        if res.paint is not None:
                            cv2.imshow("Paint", res.paint)
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord("q"):
                            break
                        if key == ord("c"):          # 'c' → 머리 방향 정면 재보정
                            pipeline.recenter_head()
                            log.info("머리 방향 기준점 재보정")

            # 3) 게임 1프레임(내부에서 clock.tick(60) — 유일한 프레임 리미터)
            running = game.run_one_frame(spell_name, head_dir=last_head_dir)

            # 4) 타이틀 화면에서 "PLAY WITHOUT CAMERA"를 누르면 카메라를 해제한다
            if game.consume_no_camera_request() and pipeline is not None:
                pipeline.close()
                pipeline = None
                last_head_dir = None
                cv2.destroyAllWindows()
    except KeyboardInterrupt:
        pass
    finally:
        if pipeline is not None:
            pipeline.close()


def _run_hsv_tracking(game: SpellGame, combo_engine: SpellComboEngine) -> None:
    """AirCanvas(HSV 마커) 기반 메인 루프 — 단일 스레드.

    카메라를 열 수 없어도 종료하지 않고 키보드 폴백으로 계속 진행한다.
    """
    canvas: Optional[AirCanvas] = AirCanvas(camera_index=CAMERA_INDEX, show_trackbars=SHOW_TRACKBARS)
    if not canvas.opened:
        log.warning("카메라를 열 수 없습니다 — 키보드 폴백으로 진행합니다.")
        canvas.release()
        canvas = None
    traj_buffer = TrajectoryBuffer(TrajectoryConfig())
    analyzer = GestureAnalyzer()
    running = True
    try:
        while running:
            spell_name: Optional[str] = None
            if canvas is not None:
                data = canvas.update()
                if data is None:
                    break  # 'q' 또는 카메라 오류

                traj_buffer.update(data.center)
                traj = traj_buffer.poll_last_closed()
                if traj is not None:
                    basic = analyzer.classify(traj)
                    if basic != "UNKNOWN":
                        spell_name = combo_engine.push_basic_spell(basic, _now_s())

                if SHOW_DEBUG_WINDOWS:
                    cv2.imshow("Tracking", data.frame)
                    cv2.imshow("Paint", data.paint)
                    cv2.imshow("Mask", data.mask)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

            running = game.run_one_frame(spell_name, head_dir=None)

            if game.consume_no_camera_request() and canvas is not None:
                canvas.release()
                canvas = None
    except KeyboardInterrupt:
        pass
    finally:
        if canvas is not None:
            canvas.release()


def run() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    combo_engine = SpellComboEngine(combo_window=1.2)
    game = SpellGame()
    try:
        if USE_HAND_TRACKING:
            _run_hand_tracking(game, combo_engine)
        else:
            _run_hsv_tracking(game, combo_engine)
    finally:
        game.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())


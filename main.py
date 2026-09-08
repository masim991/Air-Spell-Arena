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

_now_s = lambda: cv2.getTickCount() / cv2.getTickFrequency()  # noqa: E731


def _run_hand_tracking(game: SpellGame, combo_engine: SpellComboEngine) -> None:
    """VisionPipeline(워커 스레드) 기반 메인 루프."""
    pipeline = VisionPipeline(CAMERA_INDEX, show_debug=SHOW_DEBUG_WINDOWS)
    pipeline.start()
    if pipeline.failed:
        log.error("비전 파이프라인 시작 실패 — 종료합니다.")
        return

    last_head_dir: Optional[str] = None
    running = True
    try:
        while running:
            if pipeline.failed:
                log.error("비전 파이프라인이 중단되었습니다 — 게임을 종료합니다.")
                break

            # 1) 주문 이벤트 소비: 포즈 우선, 없으면 궤적(콤보 경유)
            spell_name: Optional[str] = None
            for kind, name in pipeline.drain_spells():
                if kind == "pose":
                    spell_name = name
                elif kind == "traj" and spell_name is None:
                    spell_name = combo_engine.push_basic_spell(name, _now_s())

            # 2) 최신 비전 결과 소비(연속 신호: head_dir, 디버그 프레임)
            res = pipeline.poll_result()
            if res is not None:
                last_head_dir = res.head_dir
                if SHOW_DEBUG_WINDOWS and res.annotated is not None:
                    cv2.imshow("Tracking", res.annotated)
                    if res.mask is not None:
                        cv2.imshow("Mask", res.mask)
                    if res.paint is not None:
                        cv2.imshow("Paint", res.paint)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

            # 3) 게임 1프레임(내부에서 clock.tick(60) — 유일한 프레임 리미터)
            running = game.run_one_frame(spell_name, head_dir=last_head_dir)
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.close()


def _run_hsv_tracking(game: SpellGame, combo_engine: SpellComboEngine) -> None:
    """AirCanvas(HSV 마커) 기반 메인 루프 — 단일 스레드."""
    canvas = AirCanvas(camera_index=CAMERA_INDEX, show_trackbars=SHOW_TRACKBARS)
    traj_buffer = TrajectoryBuffer(TrajectoryConfig())
    analyzer = GestureAnalyzer()
    running = True
    try:
        while running:
            data = canvas.update()
            if data is None:
                break  # 'q' 또는 카메라 오류

            traj_buffer.update(data.center)
            spell_name: Optional[str] = None
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
    except KeyboardInterrupt:
        pass
    finally:
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

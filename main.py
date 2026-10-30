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

import save_data
from air_canvas import AirCanvas
from gesture import GestureAnalyzer
from game import SpellGame
from spell_combo import SpellComboEngine
from trajectory import TrajectoryBuffer, TrajectoryConfig
from vision_loop import VisionPipeline


# ── 실행 옵션 ────────────────────────────────────────────────────────────────
# 카메라/추적 방식은 게임 내 메뉴(C/H 키)에서 바꿀 수 있으며 save_data.json에
# 저장되어 다음 실행부터 적용된다(핫스왑이 아니라 재시작 시 적용).
_saved = save_data.load()
SHOW_DEBUG_WINDOWS = bool(_saved.get("show_debug_windows", True))  # 웹캠 디버그 창(Tracking/Mask/Paint) 표시
CAMERA_INDEX = int(_saved.get("camera_index", 0))
SHOW_TRACKBARS = False       # HSV 경로 트랙바
USE_HAND_TRACKING = bool(_saved.get("use_hand_tracking", True))  # True: MediaPipe 손가락 추적, False: HSV 마커 추적

log = logging.getLogger("air_spell_arena.main")


def _now_s() -> float:
    """단조 증가 초 단위 타임스탬프(콤보 윈도 계산용)."""
    return cv2.getTickCount() / cv2.getTickFrequency()


def _open_pipeline(game: SpellGame) -> Optional[VisionPipeline]:
    """비전 파이프라인을 새로 띄운다. 실패하면 None 을 돌려주고 게임은 계속 돈다.

    카메라 인덱스는 매번 세이브에서 다시 읽는다 — 메뉴에서 N 키로 인덱스를 바꾼
    뒤 곧바로 재연결할 수 있어야 하기 때문이다.
    """
    saved = save_data.load()
    idx = int(saved.get("camera_index", CAMERA_INDEX))
    pipeline = VisionPipeline(idx, show_debug=SHOW_DEBUG_WINDOWS,
                              seated=bool(saved.get("seated_mode", False)))
    pipeline.start()
    if pipeline.failed:
        log.warning("카메라 #%d 를 열 수 없습니다 — 키보드 모드로 진행합니다.", idx)
        pipeline.close()
        game.set_camera_active(False)
        game.notify_camera_error(idx)
        return None
    log.info("카메라 #%d 연결됨", idx)
    game.set_camera_active(True)
    return pipeline


def _close_pipeline(pipeline: Optional[VisionPipeline], game: SpellGame) -> None:
    """파이프라인을 정리하고 게임에 상태를 통보한다(디버그 창도 함께 닫는다)."""
    if pipeline is not None:
        pipeline.close()
    game.set_camera_active(False)
    try:
        cv2.destroyAllWindows()
    except cv2.error:
        pass


def _run_hand_tracking(game: SpellGame, combo_engine: SpellComboEngine) -> None:
    """VisionPipeline(워커 스레드) 기반 메인 루프.

    카메라는 런타임에 자유롭게 켜고 끌 수 있다 — 게임이 "on"/"off" 를 요청하면
    여기서 파이프라인을 새로 띄우거나 정리하고, 실제 상태를 게임에 되돌려준다.
    초기화가 실패해도 게임은 종료되지 않고 키보드 모드로 계속 진행한다.
    """
    pipeline: Optional[VisionPipeline] = _open_pipeline(game)

    last_head_dir: Optional[str] = None
    running = True
    try:
        while running:
            # ── 파이프라인이 도중에 죽었으면 키보드 모드로 내려앉는다 ──
            if pipeline is not None and pipeline.failed:
                log.warning("비전 파이프라인이 중단되었습니다 — 키보드 모드로 전환합니다.")
                _close_pipeline(pipeline, game)
                pipeline = None
                last_head_dir = None

            spell_name: Optional[str] = None
            fallback_spell: Optional[str] = None
            cast_mode = "single"
            if pipeline is not None:
                # 1) 주문 이벤트 소비
                #    - ("pose"/"traj", name): 한 손 시전 → 시간축 콤보 엔진 경유
                #    - ("amplify"/"fusion", name): 양손 시전. 이미 최종 주문이므로
                #      콤보 엔진에 넣지 않는다(넣으면 직전 주문과 또 엮여버린다).
                for kind, name in pipeline.drain_spells():
                    if kind in ("amplify", "fusion"):
                        spell_name, cast_mode = name, kind
                        fallback_spell = None
                        combo_engine.clear()
                    else:
                        spell_name = combo_engine.push_basic_spell(name, _now_s())
                        fallback_spell = name if spell_name != name else None
                        cast_mode = "single"

                # 2) 최신 비전 결과 소비(연속 신호: head_dir, 미러 프레임, 디버그 창)
                res = pipeline.poll_result()
                if res is not None:
                    last_head_dir = res.head_dir
                    game.set_gesture_feedback(res.trail, res.drawing)
                    game.set_vision_feedback(
                        mirror=res.mirror,
                        dual_progress=res.dual_progress,
                        hands_seen=res.hands_seen,
                        pose_label=res.pose_label,
                        pose_progress=res.pose_progress,
                    )
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
            running = game.run_one_frame(spell_name, head_dir=last_head_dir,
                                         cast_mode=cast_mode, fallback_spell=fallback_spell)

            # 4) 카메라 켜기/끄기 요청 처리 — 양방향이다.
            req = game.consume_camera_request()
            if req == "off" and pipeline is not None:
                _close_pipeline(pipeline, game)
                pipeline = None
                last_head_dir = None
            elif req == "on":
                # 이미 떠 있으면(인덱스 변경 등) 먼저 정리하고 새로 연다.
                if pipeline is not None:
                    _close_pipeline(pipeline, game)
                    pipeline = None
                pipeline = _open_pipeline(game)
                last_head_dir = None
    except KeyboardInterrupt:
        pass
    finally:
        if pipeline is not None:
            pipeline.close()


def _run_hsv_tracking(game: SpellGame, combo_engine: SpellComboEngine) -> None:
    """AirCanvas(HSV 마커) 기반 메인 루프 — 단일 스레드.

    카메라를 열 수 없어도 종료하지 않고 키보드 폴백으로 계속 진행한다.
    """
    def _open_canvas() -> Optional[AirCanvas]:
        idx = int(save_data.load().get("camera_index", CAMERA_INDEX))
        c = AirCanvas(camera_index=idx, show_trackbars=SHOW_TRACKBARS)
        if not c.opened:
            log.warning("카메라 #%d 를 열 수 없습니다 — 키보드 모드로 진행합니다.", idx)
            c.release()
            game.set_camera_active(False)
            game.notify_camera_error(idx)
            return None
        game.set_camera_active(True)
        return c

    canvas: Optional[AirCanvas] = _open_canvas()
    traj_buffer = TrajectoryBuffer(TrajectoryConfig())
    analyzer = GestureAnalyzer()
    running = True
    try:
        while running:
            spell_name: Optional[str] = None
            fallback_spell: Optional[str] = None
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
                        fallback_spell = basic if spell_name != basic else None

                if SHOW_DEBUG_WINDOWS:
                    cv2.imshow("Tracking", data.frame)
                    cv2.imshow("Paint", data.paint)
                    cv2.imshow("Mask", data.mask)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

            running = game.run_one_frame(spell_name, head_dir=None, fallback_spell=fallback_spell)

            req = game.consume_camera_request()
            if req == "off" and canvas is not None:
                canvas.release()
                canvas = None
                game.set_camera_active(False)
            elif req == "on":
                if canvas is not None:
                    canvas.release()
                canvas = _open_canvas()
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


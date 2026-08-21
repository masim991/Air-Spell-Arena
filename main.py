from __future__ import annotations
"""
main.py – OpenCV(air_canvas) + TrajectoryBuffer + GestureAnalyzer + Pygame(SpellGame)
하나의 메인 루프에서 프레임 단위로 모두 조율합니다.

종료 조건:
- Pygame 창 닫힘 / ESC → SpellGame.run_one_frame() 이 False 반환
- OpenCV 창에서 'q' → AirCanvas.update() 가 None 반환

디버그:
- show_debug_windows = True 이면 Tracking/Paint/Mask를 함께 표시(나중에 False로 끌 수 있음)
- 필요 시 process_every_nth_frame 조절로 카메라 처리 주기를 낮출 수 있음(기본 1)
"""

import time
from typing import Optional, Tuple

import cv2

from air_canvas import AirCanvas
from gesture import GestureAnalyzer
from game import SpellGame
from spell_combo import SpellComboEngine
from trajectory import TrajectoryBuffer, TrajectoryConfig
from vision_loop import run_vision_loop


# ── 실행 옵션 ────────────────────────────────────────────────────────────────
SHOW_DEBUG_WINDOWS = True
PROCESS_EVERY_NTH_FRAME = 1  # 성능이 낮으면 2~3 이상으로 올려보세요.
CAMERA_INDEX = 0
SHOW_TRACKBARS = True        # 추후 False로 끄면 트랙바 없이 고정 HSV로 동작
USE_HAND_TRACKING = True     # True면 MediaPipe 기반 손가락 추적 경로 사용


def run() -> int:
    # 모듈 초기화
    traj_buffer = TrajectoryBuffer(TrajectoryConfig())
    analyzer = GestureAnalyzer()
    combo_engine = SpellComboEngine(combo_window=1.2)
    game = SpellGame()

    canvas = None
    cap = None

    if USE_HAND_TRACKING:
        cap = cv2.VideoCapture(CAMERA_INDEX)
    else:
        canvas = AirCanvas(camera_index=CAMERA_INDEX, show_trackbars=SHOW_TRACKBARS)

    frame_idx = 0
    running = True

    try:
        while running:
            # 1) 카메라 1프레임 처리
            if USE_HAND_TRACKING:
                try:
                    if not run_vision_loop(cap, traj_buffer,
                                           gesture_analyzer=analyzer,
                                           show_debug=SHOW_DEBUG_WINDOWS):
                        break
                except KeyboardInterrupt:
                    break
                except Exception as _vl_err:
                    print(f"[vision] 프레임 처리 오류 (건너뜀): {_vl_err}")
            else:
                data = canvas.update()
                if data is None:
                    break  # 'q' 또는 카메라 오류
                # HSV 경로에서는 center를 data에서 공급
                traj_buffer.update(data.center)

            # 3a) 포즈 기반 주문 (FIRE/WATER/EARTH/WIND) — run_vision_loop에서 포스팅
            basic_spell: Optional[str] = None
            if USE_HAND_TRACKING:
                pose_spell = getattr(run_vision_loop, "_last_pose_spell", None)
                if pose_spell:
                    basic_spell = pose_spell
                    setattr(run_vision_loop, "_last_pose_spell", None)

            # 3b) 트래젝토리 기반 주문 (LIGHT/DARK/CIRCLE/ZIGZAG)
            traj = traj_buffer.poll_last_closed()
            if traj and basic_spell is None:
                classified = analyzer.classify(traj)
                if classified != "UNKNOWN":
                    basic_spell = classified

            # 3c) 포즈/궤적 주문 모두 콤보 엔진을 통과시켜 상위 주문으로 승격
            #     (전투 중이 아닐 때는 버퍼를 비워, 메뉴에서 취한 포즈가 전투 시작 직후
            #      엉뚱한 콤보로 이어지지 않게 합니다.)
            now_s = time.perf_counter()
            spell_name: Optional[str] = None
            combo_hint: Optional[Tuple[str, float]] = None
            if game.is_playing:
                if basic_spell:
                    spell_name = combo_engine.push_basic_spell(basic_spell, now_s)
                combo_hint = combo_engine.pending(now_s)
            else:
                combo_engine.clear()

            # 4) 게임 1프레임 진행(이벤트 처리 + 주문 적용 + 렌더)
            head_dir = getattr(run_vision_loop, "_last_head_dir", None) if USE_HAND_TRACKING else None
            running = game.run_one_frame(spell_name, head_dir=head_dir, combo_hint=combo_hint)

            # 5) 디버그 창 표시(HSV 경로만 별도 표시, Hand 경로는 run_vision_loop가 표시)
            if not USE_HAND_TRACKING and SHOW_DEBUG_WINDOWS and data is not None:
                cv2.imshow("Tracking", data.frame)
                cv2.imshow("Paint", data.paint)
                cv2.imshow("Mask", data.mask)

            # 6) FPS/성능 조절(필요 시 N프레임마다만 처리하도록 확장 가능)
            frame_idx += 1
            # if frame_idx % PROCESS_EVERY_NTH_FRAME != 0:
            #     pass  # 여기서 샘플링 전략을 바꾸고 싶다면 적용

    finally:
        game.close()
        if cap is not None:
            cap.release()
            cv2.destroyAllWindows()
        if canvas is not None:
            canvas.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(run())

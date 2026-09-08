from __future__ import annotations

"""
vision_loop.py – HSV 기반 대신 MediaPipe Hands 기반으로 center(검지 끝)만 산출하는 비전 루프 예시.
기존 TrajectoryBuffer/GestureAnalyzer/SpellGame 통합은 그대로 두고,
이 루프에서 TrajectoryBuffer.update(center)를 호출하도록 설계.

향후 main.py에서 이 함수를 import 하여 사용하거나, 코드 일부를 통합하세요.
"""

from typing import Optional

import cv2
import numpy as np

# MediaPipe Hands 직접 임포트(robust)
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
            "mediapipe Hands 모듈이 필요합니다.\n"
            "pip install mediapipe 로 설치해 주세요."
        ) from e
from head_tracker import HeadTracker as FaceHeadTracker, HeadDirection
from trajectory import TrajectoryBuffer


def run_vision_loop(
    cap: cv2.VideoCapture,
    trajectory_buffer: TrajectoryBuffer,
    gesture_analyzer=None,
    show_debug: bool = True,
) -> bool:
    """카메라에서 1프레임을 읽어 MediaPipe Hands로 center를 계산하고 버퍼에 공급.

    - 프레임을 먼저 좌우 반전(selfie view)하여 사용/표시를 일치시킵니다.
    - 'Mask' 창은 검지 끝 위치를 흰 점으로 표시한 합성 마스크입니다.
    - 'Paint' 창은 이전 center와 현재 center를 선으로 연결해 그립니다.

    Returns:
        True: 계속 실행, False: 종료 요청 또는 카메라 실패
    """
    ret, frame = cap.read()
    if not ret:
        return False

    # 1) 셀피 뷰 일관성: 표시/계산 모두 동일하게 좌우 반전 적용
    frame = cv2.flip(frame, 1)

    # 2) MediaPipe Hands / HeadTracker 한 번만 생성하여 재사용
    hands = getattr(run_vision_loop, "_hands", None)
    if hands is None:
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )
        setattr(run_vision_loop, "_hands", hands)

    htracker = getattr(run_vision_loop, "_head_tracker", None)
    if htracker is None:
        htracker = FaceHeadTracker(draw_mesh=False)
        setattr(run_vision_loop, "_head_tracker", htracker)

    # 손가락 중심 계산 + 주석 프레임 생성
    h0, w0 = frame.shape[:2]
    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    annotated = frame.copy()
    center = None
    hand_lm = None
    if results.multi_hand_landmarks:
        hand_landmarks = results.multi_hand_landmarks[0]
        hand_lm = hand_landmarks.landmark
        try:
            mp_drawing.draw_landmarks(
                annotated,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS,
                mp_styles.get_default_hand_landmarks_style(),
                mp_styles.get_default_hand_connections_style(),
            )
        except Exception:
            pass
        tip = hand_lm[mp_hands.HandLandmark.INDEX_FINGER_TIP]
        x = int(np.clip(tip.x * w0, 0, w0 - 1))
        y = int(np.clip(tip.y * h0, 0, h0 - 1))
        center = (x, y)
        cv2.circle(annotated, center, 8, (0, 255, 255), 2)

    # 포즈 인식 (FIRE/WATER/EARTH/WIND)
    if gesture_analyzer is not None:
        pose_spell = gesture_analyzer.update_pose(hand_lm)
        if pose_spell:
            setattr(run_vision_loop, "_last_pose_spell", pose_spell)

        # 디버그 오버레이: 현재 포즈 + 진행 바
        _pose_colors = {
            "FIRE": (30, 140, 255), "WATER": (255, 150, 50),
            "EARTH": (80, 180, 80), "WIND": (200, 200, 200),
        }
        cur_pose = gesture_analyzer._current_pose
        progress = gesture_analyzer.pose_progress
        if cur_pose:
            col = _pose_colors.get(cur_pose, (200, 200, 200))
            label = f"POSE: {cur_pose}  {int(progress*100)}%"
            cv2.putText(annotated, label, (16, 72),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, col, 2, cv2.LINE_AA)
            bar_full = int(w0 * 0.35)
            bar_fill = int(bar_full * progress)
            cv2.rectangle(annotated, (16, 82), (16 + bar_full, 94), (50, 50, 50), -1)
            if bar_fill > 0:
                cv2.rectangle(annotated, (16, 82), (16 + bar_fill, 94), col, -1)
            cv2.rectangle(annotated, (16, 82), (16 + bar_full, 94), col, 1)
    # 손가락 좌표 EMA(지수 이동 평균)로 떨림 감소 + 최소 이동 임계치 적용
    ema = getattr(run_vision_loop, "_ema_center", None)
    prev_center = getattr(run_vision_loop, "_prev_center", None)
    smoothed = None
    if center is not None:
        cx, cy = center
        if ema is None:
            ex, ey = float(cx), float(cy)
        else:
            ex, ey = ema
            alpha = 0.35
            ex = ex * (1.0 - alpha) + cx * alpha
            ey = ey * (1.0 - alpha) + cy * alpha
        cand = (int(round(ex)), int(round(ey)))
        # 최소 이동 임계치(픽셀) 아래는 이전 값 유지
        if prev_center is not None:
            dx = cand[0] - prev_center[0]
            dy = cand[1] - prev_center[1]
            if (dx * dx + dy * dy) < 4:  # < 2px
                cand = prev_center
        smoothed = cand
        setattr(run_vision_loop, "_ema_center", (ex, ey))
    else:
        smoothed = None
    # Head direction (LEFT/RIGHT/CENTER)
    _, head_dir = htracker.process_frame(frame)
    setattr(run_vision_loop, "_last_head_dir", head_dir)

    # 3) TrajectoryBuffer 갱신(스무딩된 center 사용)
    trajectory_buffer.update(smoothed)

    if not show_debug:
        return True

    # 4) 손가락 마스크(합성): 검지 끝 주위 원을 흰색으로
    h, w = annotated.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    if smoothed is not None:
        cv2.circle(mask, smoothed, 12, 255, -1)

    # 5) 페인트 캔버스: 이전 center와 현재 center를 선으로 연결
    # 메모리 최적화: 주기적으로 캔버스 초기화 (300프레임마다)
    paint = getattr(run_vision_loop, "_paint", None)
    prev_center = getattr(run_vision_loop, "_prev_center", None)
    paint_frame_count = getattr(run_vision_loop, "_paint_frame_count", 0)
    
    if paint is None or paint.shape[:2] != (h, w) or paint_frame_count >= 300:
        paint = np.full((h, w, 3), 255, dtype=np.uint8)
        paint_frame_count = 0
    
    if prev_center is not None and smoothed is not None:
        cv2.line(paint, prev_center, smoothed, (255, 0, 0), 2)
    
    setattr(run_vision_loop, "_paint", paint)
    setattr(run_vision_loop, "_paint_frame_count", paint_frame_count + 1)
    setattr(run_vision_loop, "_prev_center", smoothed)

    # 6) 디버그 창 표시 및 종료 키
    if head_dir is not None:
        cv2.putText(annotated, f"HEAD: {head_dir}", (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2, cv2.LINE_AA)
    cv2.imshow("Tracking", annotated)
    cv2.imshow("Mask", mask)
    cv2.imshow("Paint", paint)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        return False

    return True


def cleanup_vision_loop() -> None:
    """vision_loop에서 사용한 MediaPipe 및 OpenCV 리소스를 정리합니다."""
    hands = getattr(run_vision_loop, "_hands", None)
    if hands is not None:
        try:
            hands.close()
        except Exception:
            pass
        setattr(run_vision_loop, "_hands", None)
    
    htracker = getattr(run_vision_loop, "_head_tracker", None)
    if htracker is not None:
        try:
            htracker.close()
        except Exception:
            pass
        setattr(run_vision_loop, "_head_tracker", None)
    
    # 전역 상태 초기화
    setattr(run_vision_loop, "_ema_center", None)
    setattr(run_vision_loop, "_prev_center", None)
    setattr(run_vision_loop, "_paint", None)
    setattr(run_vision_loop, "_paint_frame_count", 0)
    setattr(run_vision_loop, "_last_pose_spell", None)
    setattr(run_vision_loop, "_last_head_dir", None)

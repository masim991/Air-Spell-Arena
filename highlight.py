from __future__ import annotations
"""
highlight.py — 직전 15초를 항상 들고 있다가, 결정적 순간에 영상으로 떨어뜨린다.

왜 필요한가
-----------
결과 카드(share_card.py)는 정지 이미지다. 그런데 이 장르에서 실제로 퍼지는 건
"사람이 손을 휘두르다가 보스를 터뜨리는" 15~30초짜리 영상이다. 플레이어가
녹화 소프트웨어를 따로 켜게 만들면 그 마찰에서 대부분이 이탈한다.

그래서 게임이 항상 직전 N초를 들고 있다가, 보스를 쓰러뜨리는 순간 알아서
저장한다. 플레이어는 아무것도 누르지 않는다.

메모리 설계
-----------
원본 프레임(1280×720×3 = 2.7MB)을 300장 들고 있으면 800MB다. 대신:

1. 캡처 전에 Surface 단계에서 축소한다(파이썬이 아니라 SDL 이 하는 일이라 싸다).
2. 축소한 프레임을 **JPEG 로 인코딩해서** 들고 있는다 — 640×360 품질 72 기준
   장당 약 25KB, 300장이면 **약 7.5MB**.
3. 저장할 때만 디코딩해서 한 번에 mp4 로 굽는다.

초당 60프레임을 전부 담을 이유도 없다. 목표 fps(기본 20)에 맞춰 솎아낸다.

스레드 설계
-----------
JPEG 인코딩은 프레임당 약 5ms 로, 60fps 예산(16.7ms) 안에서 게임 루프가
직접 물기엔 너무 비싸다(실측 p95 24ms → 프레임 드랍). 그래서 게임 스레드는
**축소와 픽셀 복사까지만** 하고(약 2ms), 인코딩은 워커 스레드로 넘긴다.

큐가 밀리면 기다리지 않고 그 프레임을 버린다 — 하이라이트 한 장을 지키려고
게임을 끊는 건 교환 비율이 맞지 않는다.
"""

import logging
import os
import queue
import threading
from collections import deque
from typing import Deque, Optional, Tuple

import numpy as np
import pygame

log = logging.getLogger("air_spell_arena.highlight")

OUTPUT_DIR = "clips"

# 링버퍼 기본값 — 15초 × 20fps = 300장.
DEFAULT_SECONDS = 15
DEFAULT_FPS = 20
DEFAULT_WIDTH = 640
JPEG_QUALITY = 72


class HighlightRecorder:
    """최근 N초를 유지하는 링버퍼 레코더.

    사용법:
        rec = HighlightRecorder()
        rec.capture(screen)          # 매 프레임(내부에서 알아서 솎아낸다)
        rec.save("clips/kill.mp4")   # 결정적 순간에 한 번
    """

    def __init__(
        self,
        seconds: int = DEFAULT_SECONDS,
        fps: int = DEFAULT_FPS,
        width: int = DEFAULT_WIDTH,
        enabled: bool = True,
    ) -> None:
        self.fps = max(1, fps)
        self.seconds = max(1, seconds)
        self.width = max(160, width)
        self._state_lock = threading.RLock()
        self._generation = 0
        self._enabled = enabled
        self._frames: Deque[bytes] = deque(maxlen=self.seconds * self.fps)
        self._size: Optional[tuple] = None      # (w, h) — 첫 캡처에서 확정
        self._accum_ms = 0.0
        self._interval_ms = 1000.0 / self.fps
        self._scaled: Optional[pygame.Surface] = None   # 축소 버퍼 재사용

        # 인코딩 워커 — 큐가 차면 프레임을 버린다(게임 루프는 절대 블록하지 않는다).
        self._raw_q: "queue.Queue[Optional[Tuple[int, bytes, int, int]]]" = queue.Queue(maxsize=3)
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._encode_loop,
                                        name="highlight-encoder", daemon=True)
        self._worker.start()
        self.dropped = 0                 # 큐가 밀려 버린 프레임 수(진단용)

    # ── 상태 ────────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        with self._state_lock:
            return self._enabled

    def set_enabled(self, value: bool) -> None:
        with self._state_lock:
            self._enabled = bool(value)
            if not self._enabled:
                self.clear()

    def toggle(self) -> bool:
        with self._state_lock:
            self.set_enabled(not self._enabled)
            return self._enabled

    def __len__(self) -> int:
        with self._state_lock:
            return len(self._frames)

    @property
    def buffered_seconds(self) -> float:
        return len(self) / float(self.fps)

    def clear(self) -> None:
        with self._state_lock:
            self._generation += 1
            self._frames.clear()
            self._accum_ms = 0.0

    # ── 캡처 ────────────────────────────────────────────────────────────
    def capture(self, surface: pygame.Surface, dt_ms: int = 16, force: bool = False,
                mask: Optional[Tuple[int, int, int]] = None) -> bool:
        """한 프레임을 링버퍼에 넣는다(목표 fps 에 맞춰 솎아낸다).

        Returns:
            실제로 한 장 담았으면 True.
            force: 솎아내기를 건너뛰고 반드시 담는다(처치 장면처럼 놓치면 안 되는 프레임).
            mask: (cx, cy, r) 화면 좌표의 원 영역을 가린 채 담는다(웹캠 얼굴이 클립에 남지 않게).
        """
        with self._state_lock:
            if not self._enabled:
                return False
            generation = self._generation
            if not force:
                self._accum_ms += dt_ms
                if self._accum_ms < self._interval_ms:
                    return False
                # 프레임이 밀려도 따라잡으려 몰아 담지 않는다 — 한 번에 한 장만.
                self._accum_ms = min(self._accum_ms - self._interval_ms, self._interval_ms)

        try:
            raw = self._grab(surface, mask)
        except Exception:                    # noqa: BLE001 — 녹화가 게임을 죽이지 않는다
            log.debug("하이라이트 프레임 캡처 실패(건너뜀)", exc_info=True)
            return False
        if raw is None:
            return False
        item = (generation, *raw)
        try:
            if force:
                self._raw_q.put(item, timeout=0.5)   # 결정적 프레임은 잠깐 기다려서라도 담는다
            else:
                self._raw_q.put_nowait(item)
        except queue.Full:
            self.dropped += 1                # 워커가 밀렸다 — 기다리지 않고 버린다
            return False
        return True

    def _grab(self, surface: pygame.Surface, mask: Optional[Tuple[int, int, int]] = None) -> Optional[Tuple[bytes, int, int]]:
        """Surface → 축소 → 원시 RGB 바이트. 게임 스레드가 하는 일은 여기까지다."""
        sw, sh = surface.get_size()
        if sw <= 0 or sh <= 0:
            return None
        tw = min(self.width, sw)
        th = max(2, int(round(sh * (tw / float(sw)))))
        tw = tw - (tw % 2)                   # 일부 인코더는 짝수 치수를 요구한다
        th = th - (th % 2)
        if tw < 2 or th < 2:
            return None

        # 축소는 SDL 쪽에서 처리 — 파이썬으로 큰 배열을 만지는 것보다 훨씬 싸다.
        if self._scaled is None or self._scaled.get_size() != (tw, th):
            self._scaled = pygame.Surface((tw, th))
        pygame.transform.scale(surface, (tw, th), self._scaled)
        if mask is not None:
            # 원본 해상도에서 얼굴이 흐려져 남지 않도록 축소본 위에 불투명하게 덮는다.
            k = tw / float(sw)
            cx, cy, r = int(mask[0] * k), int(mask[1] * k), int(mask[2] * k) + 2
            pygame.draw.circle(self._scaled, (16, 12, 30), (cx, cy), r)
            pygame.draw.circle(self._scaled, (110, 110, 130), (cx, cy), max(1, int(r * 0.42)), 1)
        self._size = (tw, th)
        # tobytes 는 이미 (행 우선, RGB) 순서라 워커에서 reshape 만 하면 된다.
        return (pygame.image.tobytes(self._scaled, "RGB"), tw, th)

    def _encode_loop(self) -> None:
        """워커 스레드 — 원시 프레임을 JPEG 로 눌러 링버퍼에 쌓는다.

        RGB→BGR 채널 스왑은 여기서도 하지 않는다. 저장은 한 번뿐이므로
        그 비용은 save() 로 미루고, 여기서는 인코딩만 한다.
        """
        import cv2

        while not self._stop.is_set():
            try:
                item = self._raw_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                self._raw_q.task_done()
                break
            generation, raw, w, h = item
            try:
                with self._state_lock:
                    if generation != self._generation or not self._enabled:
                        continue
                arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
                ok, buf = cv2.imencode(".jpg", arr,
                                       [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
                if ok:
                    with self._state_lock:
                        if generation == self._generation and self._enabled:
                            self._frames.append(buf.tobytes())
            except Exception:                # noqa: BLE001
                log.debug("하이라이트 인코딩 실패(건너뜀)", exc_info=True)
            finally:
                self._raw_q.task_done()

    def close(self) -> None:
        """워커를 정리한다(게임 종료 시)."""
        self._stop.set()
        try:
            self._raw_q.put_nowait(None)
        except queue.Full:
            pass
        if self._worker.is_alive():
            self._worker.join(timeout=1.0)

    def flush(self, timeout_s: float = 1.0) -> None:
        """저장 직전에 큐에 남은 프레임이 링버퍼에 들어갈 시간을 준다."""
        import time as _t
        deadline = _t.perf_counter() + timeout_s
        # empty() 만 보면 워커가 마지막 프레임을 인코딩 중일 때 놓친다 — 처리 완료까지 본다.
        while self._raw_q.unfinished_tasks and _t.perf_counter() < deadline:
            _t.sleep(0.01)

    # ── 저장 ────────────────────────────────────────────────────────────
    def save(self, path: str, min_frames: int = 12) -> Optional[str]:
        """링버퍼를 영상 파일로 굽는다. 실패하면 None(게임은 계속 진행).

        Args:
            min_frames: 이보다 짧으면 저장하지 않는다 — 1초도 안 되는 클립은
                공유 가치가 없고 파일만 늘린다.
        """
        import cv2

        self.flush()                         # 워커가 아직 물고 있는 프레임까지 담는다
        with self._state_lock:
            if not self._enabled or self._size is None or len(self._frames) < min_frames:
                return None
            frames = list(self._frames)
        w, h = self._size
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        except OSError:
            log.warning("하이라이트 저장 경로를 만들 수 없습니다: %s", path)
            return None

        # mp4(H.264 계열)가 공유에 가장 무난하지만, 코덱이 없는 환경도 있다.
        # 그럴 땐 조용히 실패하지 말고 MJPG/AVI 로 떨어뜨린다.
        attempts = ((path, "mp4v"), (os.path.splitext(path)[0] + ".avi", "MJPG"))
        for out_path, fourcc_name in attempts:
            writer = None
            try:
                fourcc = cv2.VideoWriter_fourcc(*fourcc_name)  # type: ignore[attr-defined]
                writer = cv2.VideoWriter(out_path, fourcc, float(self.fps), (w, h))
                if not writer.isOpened():
                    continue
                for raw in frames:
                    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        # capture() 가 미뤄둔 채널 스왑을 여기서 한 번에 갚는다.
                        writer.write(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
                writer.release()
                writer = None
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    log.info("하이라이트 저장: %s (%d프레임, %.1f초)",
                             out_path, len(frames), len(frames) / float(self.fps))
                    return out_path
            except Exception:                # noqa: BLE001
                log.debug("%s 인코딩 실패", fourcc_name, exc_info=True)
            finally:
                if writer is not None:
                    writer.release()

        log.warning("하이라이트 저장 실패 — 사용 가능한 비디오 코덱이 없습니다.")
        return None

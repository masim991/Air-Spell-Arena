from __future__ import annotations
"""
webcam_overlay.py — 웹캠 영상을 게임 화면 안의 "점술 수정구(Scrying Orb)"로 합성.

왜 필요한가
-----------
이 장르(웹캠 모션 게임)의 구매 전환은 트레일러가 아니라 *플레이어가 팔을
휘두르는 클립*에서 일어난다. 그런데 기존 빌드는 웹캠을 OpenCV 의 별도
`Tracking` 창으로만 띄웠다 — 게임 화면을 녹화하면 사람이 프레임 밖에 있다.
즉, 이 게임의 가장 큰 차별점이 공유 가능한 형태로 존재하지 않았다.

이 모듈은 웹캠 프레임을 게임 화면 안으로 끌어들여, 한 장의 스크린샷만으로도
"저 사람이 손으로 마법을 쓰고 있다"가 읽히게 만든다.

설계 원칙
---------
- **주 스레드 비용 최소화**: 무거운 리사이즈/크롭은 비전 워커가 이미 끝낸
  작은 프레임(기본 200px 정사각)만 받는다. 여기서는 색보정과 blit 만 한다.
- **원본 그대로 보여주지 않는다**: 대비를 올리고 원소 색으로 틴트해서
  "웹캠 화면"이 아니라 "마법 매체"로 읽히게 한다.
- **실패해도 게임은 돈다**: 프레임이 없으면 오브만 비워 두고 조용히 넘어간다.
"""

import math
from typing import Optional, Tuple

import numpy as np
import pygame


# 워커가 보내오는 미러 프레임의 한 변 길이(정사각). 이 값만 바꾸면 전체가 따라온다.
MIRROR_SRC_SIZE = 200

Color = Tuple[int, int, int]


def prepare_mirror_frame(frame_bgr: np.ndarray, size: int = MIRROR_SRC_SIZE) -> np.ndarray:
    """카메라 BGR 프레임 → 미러용 작은 정사각 RGB 배열.

    비전 워커 스레드에서 호출한다(주 스레드에서 하면 프레임 드랍이 생긴다).
    중앙을 정사각으로 크롭한 뒤 `size` 로 축소하고 RGB 로 변환한다.
    """
    import cv2  # 워커 컨텍스트에서만 필요 — 임포트 비용을 여기로 가둔다

    h, w = frame_bgr.shape[:2]
    side = min(h, w)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    square = frame_bgr[y0:y0 + side, x0:x0 + side]
    small = cv2.resize(square, (size, size), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2RGB)


class ScryingOrb:
    """게임 화면 모서리에 떠 있는 원형 웹캠 오브.

    사용법:
        orb = ScryingOrb(radius=104)
        orb.set_frame(vision_result.mirror)      # 매 프레임(없으면 생략)
        orb.render(screen, center, tick, accent=(255, 100, 50))
    """

    def __init__(self, radius: int = 104) -> None:
        self.radius = radius
        self._surface: Optional[pygame.Surface] = None      # 색보정된 원형 영상
        self._mask: Optional[pygame.Surface] = None         # 알파 원형 마스크(캐시)
        self._last_shape: Optional[Tuple[int, int]] = None
        self._pulse: float = 0.0                            # 0~1, 시전 시 1로 튀고 감쇠
        self._enabled: bool = True

    # ── 상태 ────────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return self._enabled

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def has_frame(self) -> bool:
        return self._surface is not None

    def pulse(self, strength: float = 1.0) -> None:
        """주문 시전 순간 오브가 확 밝아지게 한다."""
        self._pulse = max(self._pulse, min(1.0, strength))

    def portrait(self) -> Optional[pygame.Surface]:
        """마지막으로 받은 영상(원형 마스크 전). 결과 카드가 이걸 그대로 쓴다."""
        return self._surface

    def clear(self) -> None:
        """카메라가 해제됐을 때 — 마지막 프레임이 남아 있지 않게 한다."""
        self._surface = None

    # ── 프레임 수신 ─────────────────────────────────────────────────────
    def set_frame(self, rgb: Optional[np.ndarray], tint: Optional[Color] = None) -> None:
        """워커가 만든 작은 RGB 배열을 받아 색보정 후 Surface 로 캐시한다."""
        if rgb is None or rgb.ndim != 3 or rgb.shape[2] != 3:
            return

        graded = self._grade(rgb, tint)
        # pygame.surfarray 는 (w, h, 3) 축 순서를 기대한다.
        arr = np.transpose(graded, (1, 0, 2))
        surf = pygame.surfarray.make_surface(arr)

        d = self.radius * 2
        if surf.get_width() != d:
            surf = pygame.transform.smoothscale(surf, (d, d))
        self._surface = surf.convert_alpha() if pygame.display.get_init() else surf

    def _grade(self, rgb: np.ndarray, tint: Optional[Color]) -> np.ndarray:
        """대비 + 틴트 + 비네트 — "웹캠"이 아니라 "마법 매체"로 보이게 만든다."""
        f = rgb.astype(np.float32) / 255.0

        # 1) S자 대비: 어두운 곳은 더 어둡게, 밝은 곳은 더 밝게 → 실루엣이 선다
        f = np.clip((f - 0.5) * 1.28 + 0.46, 0.0, 1.0)

        # 2) 원소 틴트 — 밝은 영역일수록 강하게 물들여 발광하는 느낌을 준다
        if tint is not None:
            t = np.array(tint, dtype=np.float32) / 255.0
            lum = f.mean(axis=2, keepdims=True)
            f = f * 0.66 + (t[None, None, :] * (0.35 + 0.65 * lum)) * 0.34

        # 3) 원형 비네트 — 가장자리를 어둡게 해 오브 경계와 자연스럽게 섞는다
        n = f.shape[0]
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        c = (n - 1) / 2.0
        r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
        vig = np.clip(1.15 - 0.85 * np.clip(r, 0.0, 1.0) ** 2.2, 0.0, 1.0)
        f *= vig[:, :, None]

        return (np.clip(f, 0.0, 1.0) * 255.0).astype(np.uint8)

    # ── 렌더 ────────────────────────────────────────────────────────────
    def _circle_mask(self) -> pygame.Surface:
        """반지름이 바뀔 때만 다시 만드는 알파 원형 마스크."""
        d = self.radius * 2
        if self._mask is not None and self._last_shape == (d, d):
            return self._mask
        mask = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (self.radius, self.radius), self.radius)
        # 가장자리 몇 px 를 서서히 투명하게 — 계단 현상 완화
        for i, a in enumerate((190, 120, 60)):
            pygame.draw.circle(mask, (255, 255, 255, a), (self.radius, self.radius),
                               self.radius - i, 1)
        self._mask = mask
        self._last_shape = (d, d)
        return mask

    def update(self, dt_ms: int) -> None:
        if self._pulse > 0.0:
            self._pulse = max(0.0, self._pulse - dt_ms / 420.0)

    def render(
        self,
        screen: pygame.Surface,
        center: Tuple[int, int],
        tick: int,
        accent: Color = (150, 120, 255),
        label: str = "",
    ) -> None:
        """오브를 그린다. 프레임이 없으면 빈 오브(대기 상태)를 그린다."""
        if not self._enabled:
            return

        cx, cy = center
        r = self.radius
        pulse = self._pulse

        # ── 외곽 글로우 (시전 시 강해짐) ──
        glow_r = int(r * (1.14 + 0.10 * pulse))
        glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        for i in range(6):
            t = i / 6.0
            rad = int(glow_r * (1.0 - t * 0.28))
            a = int((26 + 74 * pulse) * (1.0 - t))
            pygame.draw.circle(glow, (accent[0], accent[1], accent[2], a), (glow_r, glow_r), rad)
        screen.blit(glow, (cx - glow_r, cy - glow_r), special_flags=pygame.BLEND_RGBA_ADD)

        # ── 영상 본체 (원형 마스크 적용) ──
        if self._surface is not None:
            framed = self._surface.copy()
            framed.blit(self._circle_mask(), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            screen.blit(framed, (cx - r, cy - r))
        else:
            # 카메라 없음 — 어두운 오브 + 희미한 내부 링
            pygame.draw.circle(screen, (16, 12, 30), (cx, cy), r)
            pygame.draw.circle(screen, (110, 110, 130), (cx, cy), int(r * 0.42), 1)

        # ── 시전 플래시 (영상 위에 가산 합성) ──
        if pulse > 0.01:
            flash = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(flash, (accent[0], accent[1], accent[2], int(90 * pulse)), (r, r), r)
            screen.blit(flash, (cx - r, cy - r), special_flags=pygame.BLEND_RGBA_ADD)

        # ── 장식 링: 이중 테두리 + 회전하는 룬 눈금 ──
        pygame.draw.circle(screen, accent, (cx, cy), r + 1, 2)
        dim = (int(accent[0] * 0.5), int(accent[1] * 0.5), int(accent[2] * 0.5))
        pygame.draw.circle(screen, dim, (cx, cy), r + 5, 1)

        spin = tick * 0.012
        ticks = 12
        for i in range(ticks):
            ang = spin + i * (2 * math.pi / ticks)
            long_tick = (i % 3 == 0)
            r0 = r + 6
            r1 = r + (14 if long_tick else 9)
            a = (0.45 + 0.55 * pulse) if long_tick else (0.30 + 0.40 * pulse)
            col = (int(accent[0] * a), int(accent[1] * a), int(accent[2] * a))
            pygame.draw.line(
                screen, col,
                (cx + math.cos(ang) * r0, cy + math.sin(ang) * r0),
                (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
                2 if long_tick else 1,
            )

        # ── 라벨 ──
        if label and pygame.font.get_init():
            font = pygame.font.SysFont(None, 18)
            txt = font.render(label, True, accent)
            screen.blit(txt, (cx - txt.get_width() // 2, cy + r + 18))

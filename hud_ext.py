from __future__ import annotations
"""
hud_ext.py — 이번 업그레이드에서 새로 추가된 HUD 요소들.

fp_renderer.py 는 이미 2,600줄을 넘겼다. 마나 게이지·룬 칩·듀얼 캐스팅
게이지·룬 선택 화면을 거기에 더 밀어 넣는 대신 여기로 분리한다.
모두 순수 그리기 함수라 화면 Surface 와 좌표만 받으면 단독으로 테스트된다.

색은 game.py 의 네온 팔레트와 톤을 맞춘다.
"""

import math
import os
from typing import List, Optional, Sequence, Tuple

import pygame



# ── 한글 폰트 ───────────────────────────────────────────────────────────────
_KOR_FONT_CACHE: dict = {}

# 기본 SysFont(None) 에는 한글 글리프가 없어 설명문이 두부(□)로 깨진다.
# 윈도우 기본 한국어 폰트를 파일 경로로 직접 로드하는 쪽이 SysFont 이름
# 매칭보다 안정적이다.
_KOR_FONT_PATHS = (
    "C:/Windows/Fonts/malgunbd.ttf",   # 맑은 고딕 Bold
    "C:/Windows/Fonts/malgun.ttf",     # 맑은 고딕
    "C:/Windows/Fonts/gulim.ttc",      # 굴림
    "C:/Windows/Fonts/dotum.ttc",      # 돋움
    "C:/Windows/Fonts/batang.ttc",     # 바탕
)
_KOR_FONT_NAMES = ("malgungothic", "malgun gothic", "gulim", "dotum", "batang")


def reset_font_cache() -> None:
    """pygame.quit() 뒤에는 캐시된 Font 가 무효가 된다(재초기화 시 'Text has zero width')."""
    _KOR_FONT_CACHE.clear()


def korean_font(size: int) -> pygame.font.Font:
    """한글을 렌더할 수 있는 폰트(크기별 캐시). 전부 실패하면 기본 폰트로 떨어진다."""
    cached = _KOR_FONT_CACHE.get(size)
    if cached is not None:
        return cached

    font: Optional[pygame.font.Font] = None
    for path in _KOR_FONT_PATHS:
        if os.path.exists(path):
            try:
                font = pygame.font.Font(path, size)
                break
            except Exception:
                pass
    if font is None:
        for name in _KOR_FONT_NAMES:
            try:
                font = pygame.font.SysFont(name, size)
                break
            except Exception:
                pass
    if font is None:
        font = pygame.font.SysFont(None, size)

    _KOR_FONT_CACHE[size] = font
    return font


Color = Tuple[int, int, int]

MANA_FULL = (90, 170, 255)
MANA_LOW = (255, 120, 90)
MANA_EXHAUST = (255, 70, 100)
PANEL_BG = (14, 10, 26)
PANEL_EDGE = (90, 80, 140)


def _lerp_color(a: Color, b: Color, t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


# ── 마나 게이지 ─────────────────────────────────────────────────────────────
def draw_mana_bar(
    screen: pygame.Surface,
    font: pygame.font.Font,
    rect: pygame.Rect,
    ratio: float,
    exhausted: bool,
    tick: int,
    cost_preview: float = 0.0,
) -> None:
    """플레이어 마나 게이지.

    Args:
        ratio: 0.0~1.0 현재 마나 비율.
        exhausted: 완전 고갈 직후의 탈진 상태(회복이 멈춘 동안 True).
        cost_preview: 0.0~1.0 — 다음 시전에 빠져나갈 몫. 게이지 끝에 어둡게 표시해
            "지금 쓰면 얼마나 남는지"를 눈으로 가늠하게 한다.
    """
    ratio = max(0.0, min(1.0, ratio))

    # 바탕
    pygame.draw.rect(screen, (18, 14, 32), rect, border_radius=4)

    # 채움 — 낮을수록 붉어지고, 탈진 중에는 맥동한다
    fill_col = _lerp_color(MANA_LOW, MANA_FULL, min(1.0, ratio / 0.55))
    if exhausted:
        beat = 0.5 + 0.5 * math.sin(tick * 0.35)
        fill_col = _lerp_color(MANA_EXHAUST, (120, 30, 50), beat)

    fw = int(rect.w * ratio)
    if fw > 0:
        fill = pygame.Rect(rect.x, rect.y, fw, rect.h)
        pygame.draw.rect(screen, fill_col, fill, border_radius=4)
        # 상단 하이라이트 — 유리질 느낌
        hi = pygame.Rect(rect.x + 1, rect.y + 1, max(0, fw - 2), max(1, rect.h // 3))
        pygame.draw.rect(screen, _lerp_color(fill_col, (255, 255, 255), 0.35), hi,
                         border_radius=3)

    # 다음 시전 비용 미리보기 — 채움의 오른쪽 끝에서 왼쪽으로 어둡게 깎아 보여준다
    if cost_preview > 0.0 and fw > 0:
        cw = min(fw, int(rect.w * cost_preview))
        if cw > 0:
            prev = pygame.Surface((cw, rect.h), pygame.SRCALPHA)
            prev.fill((0, 0, 0, 110))
            screen.blit(prev, (rect.x + fw - cw, rect.y))
            pygame.draw.line(screen, (255, 255, 255),
                             (rect.x + fw - cw, rect.y),
                             (rect.x + fw - cw, rect.y + rect.h - 1), 1)

    pygame.draw.rect(screen, PANEL_EDGE, rect, 1, border_radius=4)

    label = "EXHAUSTED" if exhausted else "MANA"
    txt = font.render(label, True, (210, 220, 255) if not exhausted else MANA_EXHAUST)
    screen.blit(txt, (rect.x, rect.y - txt.get_height() - 2))


# ── 듀얼 캐스팅 게이지 ──────────────────────────────────────────────────────
def draw_dual_gauge(
    screen: pygame.Surface,
    font: pygame.font.Font,
    center: Tuple[int, int],
    progress: float,
    poses: Optional[Tuple[str, str]] = None,
) -> None:
    """양손이 모이는 중일 때 화면 하단에 차오르는 원호.

    홀드 대기시간을 "기다리는 시간"이 아니라 "차오르는 연출"로 바꾼다.
    """
    if progress <= 0.0:
        return
    cx, cy = center
    r = 34
    p = max(0.0, min(1.0, progress))

    pygame.draw.circle(screen, (40, 32, 70), (cx, cy), r, 3)
    # 진행 원호 — 12시 방향에서 시계방향
    steps = max(2, int(48 * p))
    pts: List[Tuple[float, float]] = []
    for i in range(steps + 1):
        ang = -math.pi / 2 + (2 * math.pi) * (i / 48.0)
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    if len(pts) >= 2:
        col = _lerp_color((140, 110, 255), (255, 240, 160), p)
        pygame.draw.lines(screen, col, False, pts, 4)

    if poses is not None:
        a, b = poses
        kind = "AMPLIFY" if a == b else "FUSION"
        txt = font.render(kind, True, (255, 240, 160) if p >= 1.0 else (180, 170, 230))
        screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))
        sub = font.render(f"{a}+{b}", True, (150, 145, 190))
        screen.blit(sub, (cx - sub.get_width() // 2, cy + r + 6))


# ── 획득 룬 칩 ──────────────────────────────────────────────────────────────
def draw_rune_chips(
    screen: pygame.Surface,
    font: pygame.font.Font,
    x: int,
    y: int,
    summary: Sequence[Tuple[str, int]],
    colors: Optional[Sequence[Color]] = None,
    max_width: int = 420,
) -> None:
    """획득한 룬을 작은 칩으로 나열한다(이름 + 스택 수)."""
    if not summary:
        return
    cx = x
    cy = y
    for i, (name, stacks) in enumerate(summary):
        col = colors[i] if colors is not None and i < len(colors) else (170, 160, 220)
        label = name if stacks <= 1 else f"{name} x{stacks}"
        txt = font.render(label, True, col)
        w = txt.get_width() + 14
        if cx - x + w > max_width:          # 폭을 넘으면 다음 줄로
            cx = x
            cy += txt.get_height() + 6
        chip = pygame.Rect(cx, cy, w, txt.get_height() + 6)
        bg = pygame.Surface((chip.w, chip.h), pygame.SRCALPHA)
        bg.fill((col[0] // 6, col[1] // 6, col[2] // 6, 190))
        screen.blit(bg, (chip.x, chip.y))
        pygame.draw.rect(screen, col, chip, 1, border_radius=3)
        screen.blit(txt, (chip.x + 7, chip.y + 3))
        cx += w + 6


# ── 룬 선택 화면 ────────────────────────────────────────────────────────────
def render_rune_select(
    screen: pygame.Surface,
    font: pygame.font.Font,
    font_big: pygame.font.Font,
    offers: Sequence,          # Sequence[runes.Rune]
    tick: int,
    stage_cleared: int,
    next_boss_name: str = "",
) -> List[Tuple[pygame.Rect, str]]:
    """스테이지 클리어 후 3택 1 룬 선택 화면.

    Returns:
        [(카드 Rect, rune_id), ...] — 게임 루프가 클릭 판정에 쓴다.
    """
    W, H = screen.get_size()

    # 어두운 배경 + 은은한 방사 그라데이션
    screen.fill((8, 5, 18))
    for i in range(8):
        t = i / 8.0
        rad = int(min(W, H) * (0.75 - t * 0.55))
        a = int(16 * (1.0 - t))
        ov = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
        pygame.draw.circle(ov, (90, 70, 180, a), (rad, rad), rad)
        screen.blit(ov, (W // 2 - rad, H // 2 - rad), special_flags=pygame.BLEND_RGBA_ADD)

    # 제목
    title = font_big.render(f"STAGE {stage_cleared} CLEAR", True, (255, 230, 120))
    screen.blit(title, (W // 2 - title.get_width() // 2, 54))
    kf = korean_font(17)
    sub = kf.render("룬 하나를 골라 이번 런을 강화하세요  —  1 / 2 / 3 키 또는 클릭",
                    True, (190, 185, 225))
    screen.blit(sub, (W // 2 - sub.get_width() // 2, 54 + title.get_height() + 10))

    if next_boss_name:
        nxt = font.render(f"NEXT:  {next_boss_name}", True, (255, 120, 140))
        screen.blit(nxt, (W // 2 - nxt.get_width() // 2, H - 44))

    # 카드
    clickables: List[Tuple[pygame.Rect, str]] = []
    n = len(offers)
    if n == 0:
        none_txt = korean_font(18).render("더 고를 룬이 없습니다 — 아무 키나 눌러 계속",
                                          True, (200, 200, 220))
        screen.blit(none_txt, (W // 2 - none_txt.get_width() // 2, H // 2))
        return clickables

    cw, ch = 236, 300
    gap = 28
    total = n * cw + (n - 1) * gap
    x0 = W // 2 - total // 2
    y0 = H // 2 - ch // 2 + 16

    for i, rune in enumerate(offers):
        rect = pygame.Rect(x0 + i * (cw + gap), y0, cw, ch)
        col: Color = rune.color

        # 카드가 살짝 위아래로 떠다니게 — 정적인 화면이 되지 않도록
        bob = int(math.sin(tick * 0.045 + i * 1.1) * 4)
        rect.y += bob

        panel = pygame.Surface((cw, ch), pygame.SRCALPHA)
        panel.fill((col[0] // 9, col[1] // 9, col[2] // 9, 232))
        screen.blit(panel, rect.topleft)
        pygame.draw.rect(screen, col, rect, 2, border_radius=8)

        # 상단 룬 문양(간이 마법진)
        ccx, ccy = rect.centerx, rect.y + 86
        for ring, rr in enumerate((40, 30, 20)):
            a = 0.35 + 0.25 * math.sin(tick * 0.06 + ring)
            rc = (int(col[0] * a), int(col[1] * a), int(col[2] * a))
            pygame.draw.circle(screen, rc, (ccx, ccy), rr, 1)
        spokes = 6
        for k in range(spokes):
            ang = tick * 0.02 + k * (2 * math.pi / spokes)
            pygame.draw.line(
                screen, col,
                (ccx + math.cos(ang) * 20, ccy + math.sin(ang) * 20),
                (ccx + math.cos(ang) * 40, ccy + math.sin(ang) * 40), 1,
            )

        # 번호 뱃지
        badge = font_big.render(str(i + 1), True, col)
        screen.blit(badge, (rect.x + 12, rect.y + 10))

        # 이름
        name = font_big.render(rune.name, True, (245, 245, 255))
        screen.blit(name, (rect.centerx - name.get_width() // 2, rect.y + 146))

        # 설명 — 카드 폭에 맞춰 단어 단위 줄바꿈
        for li, line in enumerate(_wrap(rune.desc, kf, cw - 28)):
            d = kf.render(line, True, (205, 205, 225))
            screen.blit(d, (rect.centerx - d.get_width() // 2, rect.y + 190 + li * 20))

        clickables.append((rect, rune.id))

    return clickables


def _wrap(text: str, font: pygame.font.Font, max_w: int) -> List[str]:
    """단어 단위 줄바꿈. 한 단어가 폭을 넘으면 그대로 한 줄로 둔다."""
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if font.size(trial)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ── 캘리브레이션 온보딩 ─────────────────────────────────────────────────────
# 경쟁작 리뷰에서 이탈 사유 1순위가 "인식이 안 된다"였다. 첫 실행에서 4가지
# 포즈가 *실제로 내 카메라에서* 잡히는지 눈으로 확인시키고 나면, 같은 인식률
# 이라도 체감 품질이 완전히 달라진다 — 안 되는 게 내 탓인지 게임 탓인지를
# 플레이어가 알 수 있기 때문이다.

CALIBRATION_STEPS = [
    ("FIRE",  "palm",      "손바닥을 펴서 다섯 손가락을 벌리세요"),
    ("WATER", "fist",      "주먹을 쥐세요"),
    ("WIND",  "index",     "검지만 펴세요"),
    ("EARTH", "thumb",     "엄지만 위로 세우세요"),
    ("DUAL",  "dual_same", "이제 양손을 함께 화면에 올려보세요"),
]

_STEP_COLORS = {
    "FIRE": (255, 100, 50), "WATER": (60, 180, 255), "WIND": (120, 255, 180),
    "EARTH": (200, 160, 100), "DUAL": (255, 215, 50),
}


def render_calibration(
    screen: pygame.Surface,
    font: pygame.font.Font,
    font_big: pygame.font.Font,
    step_index: int,
    hold_ratio: float,
    detected: Optional[str],
    camera_on: bool,
    tick: int,
    orb=None,
    orb_center: Optional[Tuple[int, int]] = None,
    draw_icon=None,
) -> List[Tuple[pygame.Rect, str]]:
    """포즈 확인 온보딩 화면.

    Args:
        step_index: 현재 단계(len(CALIBRATION_STEPS) 이면 완료 화면).
        hold_ratio: 현재 단계의 유지 진행률 0~1.
        detected: 지금 인식 중인 포즈 이름(없으면 None).
        draw_icon: (cx, cy, icon, color, tick) 시그니처의 아이콘 그리기 함수.

    Returns:
        [(Rect, action), ...] — action: "skip" | "done" | "retry"
    """
    W, H = screen.get_size()
    kf = korean_font(19)
    kf_small = korean_font(15)
    screen.fill((9, 6, 20))

    steps = CALIBRATION_STEPS
    done = step_index >= len(steps)
    accent = (120, 235, 180) if done else _STEP_COLORS.get(steps[step_index][0],
                                                           (180, 170, 230))
    clickables: List[Tuple[pygame.Rect, str]] = []

    # ── 헤더 ────────────────────────────────────────────────────────────
    title = font_big.render("CALIBRATION" if not done else "READY", True, accent)
    screen.blit(title, (W // 2 - title.get_width() // 2, 38))
    sub = kf_small.render(
        "카메라가 내 손을 제대로 보는지 먼저 확인합니다  —  약 30초"
        if not done else "모든 포즈가 인식되었습니다",
        True, (175, 170, 205))
    screen.blit(sub, (W // 2 - sub.get_width() // 2, 38 + title.get_height() + 8))

    # ── 본문: 수정구(내 모습) + 현재 단계 안내 ───────────────────────────
    main_y = 322
    orb_pos = (W // 2 - 270, main_y)
    if orb is not None:
        orb.render(screen, orb_pos, tick, accent=accent)
    else:
        pygame.draw.circle(screen, (22, 16, 38), orb_pos, 96)
        pygame.draw.circle(screen, (100, 92, 130), orb_pos, 96, 2)
        msg = kf_small.render("카메라 꺼짐" if not camera_on else "대기 중",
                              True, (150, 145, 175))
        screen.blit(msg, (orb_pos[0] - msg.get_width() // 2,
                          orb_pos[1] - msg.get_height() // 2))

    panel_x = W // 2 - 110

    if done:
        msg = kf.render("이제 시작할 준비가 되었습니다.", True, (230, 230, 245))
        screen.blit(msg, (panel_x, main_y - 40))
        hint = kf_small.render("인식이 잘 안 되면 언제든 메뉴에서 다시 확인할 수 있습니다.",
                               True, (150, 145, 180))
        screen.blit(hint, (panel_x, main_y + 2))
        btn = pygame.Rect(panel_x, main_y + 44, 210, 50)
        _button(screen, btn, "START", font_big, (120, 235, 180))
        clickables.append((btn, "done"))
        btn2 = pygame.Rect(panel_x + 224, main_y + 44, 150, 50)
        _button(screen, btn2, "RETRY", font, (130, 125, 160))
        clickables.append((btn2, "retry"))
    else:
        label, icon, instruction = steps[step_index]
        if draw_icon is not None:
            draw_icon(panel_x + 44, main_y - 34, icon, accent, tick, 2.4)

        name = font_big.render(label if label != "DUAL" else "BOTH HANDS", True, accent)
        screen.blit(name, (panel_x + 98, main_y - 56))
        for i, line in enumerate(_wrap(instruction, kf, 380)):
            t = kf.render(line, True, (224, 224, 240))
            screen.blit(t, (panel_x + 98, main_y - 20 + i * 26))

        # 유지 게이지
        bar = pygame.Rect(panel_x, main_y + 48, 400, 16)
        pygame.draw.rect(screen, (26, 20, 44), bar, border_radius=8)
        fw = int(bar.w * max(0.0, min(1.0, hold_ratio)))
        if fw > 0:
            pygame.draw.rect(screen, accent, pygame.Rect(bar.x, bar.y, fw, bar.h),
                             border_radius=8)
        pygame.draw.rect(screen, (95, 88, 130), bar, 1, border_radius=8)

        # 실시간 인식 상태 — 왜 안 되는지를 플레이어가 알 수 있어야 한다
        if not camera_on:
            state_txt, col = "카메라가 꺼져 있습니다 — C 키로 켜세요", (255, 120, 140)
        elif detected:
            ok = detected == label or label == "DUAL"
            state_txt = f"좋습니다 — {detected}" if ok else f"지금은 {detected} 로 인식 중"
            col = (120, 235, 180) if ok else (255, 190, 90)
        else:
            state_txt, col = "손이 보이지 않습니다 — 화면 안으로 손을 올려주세요", (255, 150, 110)
        st = kf_small.render(state_txt, True, col)
        screen.blit(st, (panel_x, bar.bottom + 12))

    # ── 단계 스트립 — 남은 과정을 한눈에(중간 이탈 방지) ────────────────
    strip_y = H - 186
    cell = 150
    x0 = W // 2 - (len(steps) * cell) // 2
    for i, (lbl, icon, _desc) in enumerate(steps):
        cx = x0 + i * cell + cell // 2
        passed, current = i < step_index, i == step_index
        col = ((120, 235, 180) if passed
               else _STEP_COLORS.get(lbl, (170, 160, 210)) if current
               else (78, 72, 100))
        box = pygame.Rect(cx - cell // 2 + 8, strip_y, cell - 16, 78)
        if current:
            bg = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
            bg.fill((col[0] // 7, col[1] // 7, col[2] // 7, 210))
            screen.blit(bg, box.topleft)
        pygame.draw.rect(screen, col, box, 2 if current else 1, border_radius=5)
        if draw_icon is not None:
            draw_icon(cx, strip_y + 28, icon, col, tick, 0.95)
        name = font.render(lbl if lbl != "DUAL" else "BOTH", True, col)
        screen.blit(name, (cx - name.get_width() // 2, strip_y + 52))
        if passed:
            chk = font.render("DONE", True, (120, 235, 180))
            screen.blit(chk, (box.right - chk.get_width() - 6, box.y + 4))

    # ── 하단: 자세 팁 + 건너뛰기 ─────────────────────────────────────────
    tip = kf_small.render(
        "팔을 쭉 뻗지 마세요. 팔꿈치를 몸에 붙인 채 손만 올리면 충분합니다.",
        True, (135, 130, 165))
    screen.blit(tip, (W // 2 - tip.get_width() // 2, H - 88))

    if not done:
        btn = pygame.Rect(W // 2 - 90, H - 60, 180, 34)
        _button(screen, btn, "SKIP  (ESC)", font, (130, 125, 160))
        clickables.append((btn, "skip"))
    return clickables


def _button(screen: pygame.Surface, rect: pygame.Rect, label: str,
            font: pygame.font.Font, color: Color) -> None:
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill((color[0] // 8, color[1] // 8, color[2] // 8, 220))
    screen.blit(bg, rect.topleft)
    pygame.draw.rect(screen, color, rect, 1, border_radius=5)
    t = font.render(label, True, color)
    screen.blit(t, t.get_rect(center=rect.center))

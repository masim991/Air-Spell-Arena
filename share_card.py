from __future__ import annotations
"""
share_card.py — 런이 끝나면 공유용 결과 카드(PNG)를 자동 저장한다.

왜 필요한가
-----------
이 게임의 판매 포인트는 "웹캠으로 마법을 쓴다"인데, 그걸 남에게 보여줄
방법이 스크린샷 수동 촬영밖에 없었다. 런이 끝날 때마다 *플레이어의 얼굴이
박힌* 카드가 자동으로 떨어지면, 공유 행위의 마찰이 0에 가까워진다.

카드 규격은 1200×630 — 대부분의 SNS 링크 미리보기(OG 이미지)와 같은 비율이라
업로드했을 때 잘리지 않는다.
"""

import datetime as _dt
import logging
import math
import os
from typing import Dict, Optional, Sequence, Tuple

import pygame

import hud_ext

log = logging.getLogger("air_spell_arena.share")

CARD_W, CARD_H = 1200, 630
OUTPUT_DIR = "clips"

Color = Tuple[int, int, int]

_BG = (10, 7, 20)
_GOLD = (255, 215, 60)
_RED = (255, 80, 110)
_TEXT = (238, 238, 248)
_DIM = (150, 148, 178)


def _fonts():
    """카드에서 쓰는 폰트 묶음. 숫자/영문은 기본, 한글은 한글 폰트."""
    return {
        "huge": pygame.font.SysFont(None, 92),
        "big": pygame.font.SysFont(None, 52),
        "mid": pygame.font.SysFont(None, 32),
        "small": pygame.font.SysFont(None, 24),
        "kor": hud_ext.korean_font(22),
        "kor_small": hud_ext.korean_font(18),
    }


def build_card(
    won: bool,
    score: int,
    boss_name: str,
    stats: Dict[str, int],
    stage_index: int,
    stage_count: int,
    difficulty: str,
    rune_summary: Sequence[Tuple[str, int]] = (),
    rune_colors: Sequence[Color] = (),
    portrait: Optional[pygame.Surface] = None,
    is_record: bool = False,
    daily_label: str = "",
) -> pygame.Surface:
    """결과 카드 Surface 를 그린다(저장은 `save_card` 가 한다).

    Args:
        portrait: 수정구에 찍힌 플레이어 영상(없으면 마법진만 그린다).
    """
    card = pygame.Surface((CARD_W, CARD_H))
    card.fill(_BG)
    f = _fonts()
    accent = _GOLD if won else _RED

    # ── 배경: 비스듬한 광선 + 외곽 테두리 ──
    for i in range(26):
        x = int(-200 + i * 78)
        a = 8 if i % 2 else 5
        ray = pygame.Surface((46, CARD_H), pygame.SRCALPHA)
        ray.fill((accent[0], accent[1], accent[2], a))
        card.blit(ray, (x + i * 6, 0))
    pygame.draw.rect(card, accent, (0, 0, CARD_W, CARD_H), 3)
    pygame.draw.rect(card, (accent[0] // 3, accent[1] // 3, accent[2] // 3),
                     (12, 12, CARD_W - 24, CARD_H - 24), 1)

    # ── 좌측: 초상(수정구) ──
    orb_cx, orb_cy, orb_r = 236, CARD_H // 2 + 10, 158
    if portrait is not None:
        p = pygame.transform.smoothscale(portrait, (orb_r * 2, orb_r * 2))
        mask = pygame.Surface((orb_r * 2, orb_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (orb_r, orb_r), orb_r)
        p = p.convert_alpha()
        p.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        card.blit(p, (orb_cx - orb_r, orb_cy - orb_r))
    else:
        pygame.draw.circle(card, (18, 13, 32), (orb_cx, orb_cy), orb_r)

    pygame.draw.circle(card, accent, (orb_cx, orb_cy), orb_r + 2, 3)
    for k in range(16):                          # 장식 룬 눈금
        ang = k * (2 * math.pi / 16)
        r0, r1 = orb_r + 8, orb_r + (18 if k % 4 == 0 else 12)
        pygame.draw.line(
            card, accent,
            (orb_cx + math.cos(ang) * r0, orb_cy + math.sin(ang) * r0),
            (orb_cx + math.cos(ang) * r1, orb_cy + math.sin(ang) * r1),
            2 if k % 4 == 0 else 1,
        )

    # ── 우측: 결과 텍스트 ──
    x = 486
    verdict = "VICTORY" if won else "DEFEAT"
    v = f["huge"].render(verdict, True, accent)
    card.blit(v, (x, 74))

    sub = f["mid"].render(f"{boss_name}   ·   STAGE {stage_index}/{stage_count}"
                          f"   ·   {difficulty.upper()}", True, _DIM)
    card.blit(sub, (x + 4, 74 + v.get_height() + 6))

    # 일일 챌린지 표식 — 시드가 찍혀 있어야 "같은 판"인지 대조가 된다.
    if daily_label:
        dl = f["small"].render(daily_label, True, _GOLD)
        pad_x, pad_y = 9, 5
        box = pygame.Rect(x + 2, 74 + v.get_height() + 6 + sub.get_height() + 8,
                          dl.get_width() + pad_x * 2, dl.get_height() + pad_y * 2)
        pygame.draw.rect(card, (_GOLD[0] // 7, _GOLD[1] // 7, _GOLD[2] // 7), box)
        pygame.draw.rect(card, _GOLD, box, 1)
        card.blit(dl, (box.x + pad_x, box.y + pad_y))

    # 점수
    sl = f["small"].render("SCORE", True, _DIM)
    card.blit(sl, (x + 4, 222))
    sc = f["huge"].render(f"{score:,}", True, _TEXT)
    card.blit(sc, (x, 242))
    if is_record:
        rec = f["mid"].render("NEW RECORD", True, _GOLD)
        card.blit(rec, (x + sc.get_width() + 20, 268))

    # 통계 4칸
    cells = (
        ("DAMAGE DEALT", stats.get("dmg_dealt", 0)),
        ("DAMAGE TAKEN", stats.get("dmg_taken", 0)),
        ("SPELLS CAST", stats.get("spells_cast", 0)),
        ("TIME", f"{stats.get('time_ms', 0) // 1000}s"),
    )
    cy = 356
    for i, (label, value) in enumerate(cells):
        cx = x + (i % 2) * 234
        row = cy + (i // 2) * 74
        lbl = f["small"].render(label, True, _DIM)
        card.blit(lbl, (cx + 2, row))
        val = f["big"].render(str(value), True, _TEXT)
        card.blit(val, (cx, row + 20))

    # 룬 칩
    if rune_summary:
        rl = f["small"].render("RUNES", True, _DIM)
        card.blit(rl, (x + 2, 516))
        hud_ext.draw_rune_chips(card, f["small"], x, 538, rune_summary,
                                rune_colors, max_width=CARD_W - x - 40)

    # 워터마크
    pad = 44
    wm = f["mid"].render("AIR SPELL ARENA", True, (90, 86, 120))
    card.blit(wm, (CARD_W - wm.get_width() - pad, CARD_H - wm.get_height() - 28))
    tag = f["kor_small"].render("웹캠으로 시전하는 마법 대전", True, (74, 70, 100))
    card.blit(tag, (CARD_W - tag.get_width() - pad, CARD_H - wm.get_height() - 48))

    return card


def save_card(card: pygame.Surface, out_dir: str = OUTPUT_DIR) -> Optional[str]:
    """카드를 PNG 로 저장하고 경로를 돌려준다. 실패해도 게임은 멈추지 않는다."""
    try:
        os.makedirs(out_dir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(out_dir, f"airspell_{stamp}.png")
        pygame.image.save(card, path)
        log.info("결과 카드 저장: %s", path)
        return path
    except Exception:                      # noqa: BLE001 — 저장 실패로 런을 망치지 않는다
        log.warning("결과 카드 저장 실패", exc_info=True)
        return None

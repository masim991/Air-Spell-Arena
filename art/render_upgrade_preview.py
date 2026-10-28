"""Generate a local, simulated review of the combat animation states."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from fp_renderer import FPRenderer  # noqa: E402

pygame.init()
screen = pygame.display.set_mode((1280, 720))
font = pygame.font.Font(None, 25)
renderer = FPRenderer(screen, font, font)
images = []
for i in range(70):
    effects = []
    shield = 0
    offset = 0
    if 10 <= i < 20:
        effects = [{"type": "telegraph", "elapsed": (i - 10) * 50, "dur": 500}]
    if 20 <= i < 27:
        effects = [{"type": "proj", "origin": "boss", "elapsed": (i - 20) * 50,
                    "dur": 900, "color": (240, 70, 40), "style": "fire", "r": 8}]
    if 30 <= i < 39:
        effects = [{"type": "player_motion", "style": "fire", "elapsed": (i - 30) * 50, "dur": 450},
                   {"type": "proj", "origin": "player", "elapsed": (i - 30) * 50,
                    "dur": 900, "color": (255, 90, 40), "style": "fire", "r": 8}]
    if 40 <= i < 55:
        shield = 1600
    if 52 <= i < 61:
        effects = [{"type": "boss_guard", "elapsed": (i - 52) * 50, "dur": 450}]
        offset = -65
    renderer.render_frame(100, 100, shield, 0, "", 0, (255, 255, 255), effects,
                          boss_offset_x=offset, stage_count=3, dt_ms=50)
    images.append(Image.frombytes("RGB", (1280, 720), pygame.image.tobytes(screen, "RGB"))
                  .resize((640, 360)))
pygame.quit()
images[0].save(ROOT / "art/upgrade_motion_preview.gif", save_all=True,
               append_images=images[1:], duration=50, loop=0, optimize=False)
sheet = Image.new("RGB", (1280, 1140), (10, 10, 10))
draw = ImageDraw.Draw(sheet)
for n, (frame, label) in enumerate(zip((1, 16, 22, 34, 46, 56),
                                       ("IDLE", "BOSS WINDUP", "BOSS ATTACK",
                                        "PLAYER CAST", "PLAYER GUARD", "BOSS DODGE"))):
    x, y = (n % 2) * 640, (n // 2) * 380
    sheet.paste(images[frame], (x, y + 20))
    draw.text((x + 8, y + 2), label, fill="white")
sheet.save(ROOT / "art/upgrade_combat_sheet.png")
print("PREVIEW_RESULT", len(images), "frames")

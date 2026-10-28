"""Pack Blender's rendered 320px frames into runtime atlases."""
from pathlib import Path

from PIL import Image

root = Path(__file__).resolve().parents[2]
for variant in ("arcane", "frost", "void"):
    sheet = Image.new("RGBA", (3840, 960))
    for i in range(36):
        with Image.open(root / "build" / "boss_motion" / f"{variant}_{i:02}.png") as frame:
            if frame.size != (320, 320):
                raise ValueError(f"Unexpected frame size: {variant} {i}: {frame.size}")
            bounds = frame.getchannel("A").getbbox()
            if not bounds or bounds[0] == 0 or bounds[1] == 0 or bounds[2] == 320 or bounds[3] == 320:
                raise ValueError(f"Clipped or empty pose: {variant} {i}: {bounds}")
            sheet.paste(frame, ((i % 12) * 320, (i // 12) * 320))
    sheet.save(root / "assets" / f"boss_{variant}_motion.png", optimize=True)
    print(f"Packed {variant}: 36 poses")

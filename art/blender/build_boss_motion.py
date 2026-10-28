"""Create editable boss motion, 36-frame sheets, and hand attachment points.

Blender 5.2: blender -b art/blender/air_spell_arena_art.blend --factory-startup
  --python-exit-code 1 -P art/blender/build_boss_motion.py
Each row contains 12 frames: idle, attack, and defense. Timing is in game code.
"""
import json
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "build" / "boss_motion"
TMP.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
boss = bpy.data.collections["02_Boss"]


def control(name, position, parent=None):
    obj = bpy.data.objects.new(name, None)
    boss.objects.link(obj)
    obj.location = position
    obj.parent = parent
    return obj


def attach(obj, parent):
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = world


root = control("motion root", (0, 0, 0))
arms = {}
wings = {}
for side in (-1, 1):
    arms[side] = control(f"motion arm {side}", (side * .64, 0, 2.29), root)
    wings[side] = control(f"motion wing {side}", (side * .48, .1, 2.44), root)
bpy.context.view_layer.update()
for obj in list(boss.objects):
    if obj.type != "MESH":
        continue
    target = root
    for side in (-1, 1):
        arm_names = (f"shoulder {side}", f"upper arm {side}", f"forearm {side}",
                     f"claw palm {side}", f"claw {side} ", f"pauldron spike {side}")
        wing_names = (f"wing membrane {side}", f"wing spar {side} ",
                      f"frost wing shard {side}", f"void tendril {side}")
        if any(obj.name.startswith(name) for name in arm_names):
            target = arms[side]
        if any(obj.name.startswith(name) for name in wing_names):
            target = wings[side]
    attach(obj, target)

# Readable beats at 24 fps: idle sway, anticipation / release / recovery,
# and arms raised / guard hold / settle. Hold is intentional for gameplay cues.
beats = {
    1:  (0, 0, 0, .02, .02), 5: (0, .025, 0, .09, -.08),
    9:  (0, -.025, 0, -.06, .08), 13: (0, 0, 0, .02, .02),
    21: (0, 0, 0, .02, .02), 25: (-.10, -.06, .25, -.35, -.10),
    29: (.12, .06, -1.05, .25, .18), 33: (.03, 0, -.40, .15, .05),
    41: (0, 0, 0, .02, .02), 45: (-.07, 0, -.20, 1.12, -.18),
    49: (-.07, 0, -.20, 1.12, -.18), 53: (0, 0, 0, .02, .02),
}
for frame, (lean, twist, arm_x, arm_y, wing) in beats.items():
    root.rotation_euler = (lean, 0, twist)
    root.keyframe_insert(data_path="rotation_euler", frame=frame)
    for side in (-1, 1):
        arms[side].rotation_euler = (arm_x, side * arm_y, 0)
        wings[side].rotation_euler = (0, side * wing, side * wing * .3)
        arms[side].keyframe_insert(data_path="rotation_euler", frame=frame)
        wings[side].keyframe_insert(data_path="rotation_euler", frame=frame)

for c in ("01_Arena", "02_Boss", "03_Player", "04_FirstPersonWand"):
    bpy.data.collections[c].hide_render = c != "02_Boss"
scene.camera = bpy.data.objects["Character orthographic"]
scene.camera.data.ortho_scale = 5.8  # Leave room for the widest defensive wings.
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = scene.render.resolution_y = 320
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 53
scene.frame_set(1)
out_blend = ROOT / "art" / "blender" / "air_spell_arena_motion.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))

palettes = {
    "arcane": ("violet cloth", "charred wing", "arcane boss core", "arcane boss eye"),
    "frost": ("frost robe", "frost wing", "frost core", "frost eye"),
    "void": ("void robe", "void wing", "void core", "void eye"),
}
arcane = palettes["arcane"]
slots = []
for obj in boss.objects:
    if obj.type == "MESH":
        for i, material in enumerate(obj.data.materials):
            if material and material.name in arcane:
                slots.append((obj, i, arcane.index(material.name)))

sample_frames = ([1 + i for i in range(12)]
                 + [21 + 12 * i / 11 for i in range(12)]
                 + [41 + 12 * i / 11 for i in range(12)])
for variant, palette in palettes.items():
    for obj in boss.objects:
        if obj.type == "MESH" and (obj.name.startswith("frost ") or obj.name.startswith("void ")):
            obj.hide_render = not obj.name.startswith(variant + " ")
    for obj, i, index in slots:
        obj.data.materials[i] = bpy.data.materials[palette[index]]
    hands = []
    for n, frame in enumerate(sample_frames):
        scene.frame_set(int(frame), subframe=frame % 1)
        bpy.context.view_layer.update()
        pose_hands = {}
        for side in (-1, 1):
            p = world_to_camera_view(scene, scene.camera,
                                     bpy.data.objects[f"claw palm {side}"].matrix_world.translation)
            pose_hands[str(side)] = [round(p.x, 6), round(1 - p.y, 6)]
        hands.append(pose_hands)
        scene.render.filepath = str(TMP / f"{variant}_{n:02}.png")
        bpy.ops.render.render(write_still=True)
    (ROOT / "assets" / f"boss_{variant}_hands.json").write_text(
        json.dumps(hands, separators=(",", ":")), encoding="utf-8")
print("MOTION_RESULT", {"blend": str(out_blend), "frames": 108, "beats": list(beats)})

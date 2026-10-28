"""Build Air Spell Arena's original low-poly art in Blender 5.2.

Run with: blender -b --factory-startup --python-exit-code 1 -P art/blender/build_assets.py
The .blend is the editable source; PNGs in assets/ are the 1280x720 game renders.
"""
from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets"
SRC = ROOT / "art" / "blender"
OUT.mkdir(exist_ok=True)
SRC.mkdir(exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for coll in list(bpy.data.collections):
    if coll.name != "Collection":
        bpy.data.collections.remove(coll)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.render.resolution_percentage = 100
scene.render.image_settings.color_depth = "8"
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.world.color = (0.015, 0.015, 0.02)
scene.render.engine = "BLENDER_EEVEE"


def collection(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


ARENA = collection("01_Arena")
BOSS = collection("02_Boss")
PLAYER = collection("03_Player")
WAND = collection("04_FirstPersonWand")
LIGHTS = collection("05_LightsAndCameras")


def move(obj, coll):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def mat(name, color, metal=0.0, rough=0.65, emit=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    p.inputs["Emission Color"].default_value = (*color, 1)
    p.inputs["Emission Strength"].default_value = emit
    return m


stone = mat("cold basalt", (0.06, 0.067, 0.075), rough=0.92)
stone_edge = mat("worn edge", (0.16, 0.17, 0.18), rough=0.82)
floor_stone = mat("dark floor", (0.015, 0.018, 0.025), rough=0.96)
floor_edge = mat("floor inlay", (0.055, 0.058, 0.075), rough=0.88)
floor_glow = mat("low energy rune", (0.08, 0.065, 0.10), rough=0.65, emit=0.09)
recess = mat("recessed stone", (0.025, 0.031, 0.042), rough=0.94)
dark = mat("deep robe", (0.035, 0.023, 0.048), rough=0.82)
robe = mat("violet cloth", (0.105, 0.055, 0.16), rough=0.78)
trim = mat("aged silver", (0.38, 0.34, 0.31), metal=0.65, rough=0.34)
bone = mat("ivory bone", (0.55, 0.49, 0.39), rough=0.72)
wood = mat("blackened oak", (0.13, 0.075, 0.042), rough=0.72)
gem = mat("arcane core", (0.67, 0.20, 0.33), rough=0.25, emit=1.4)
glow = mat("floor rune", (0.33, 0.25, 0.38), rough=0.45, emit=0.45)
eye = mat("eye ember", (0.9, 0.24, 0.10), rough=0.3, emit=1.7)
wingmat = mat("charred wing", (0.035, 0.025, 0.045), rough=0.92)
void_detail = mat("void horn metal", (0.18, 0.075, 0.27), metal=0.25, rough=0.65)


def assign(obj, material, name, coll):
    obj.name = name
    move(obj, coll)
    obj.data.materials.append(material)
    return obj


def cube(name, loc, scale, material, coll, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = assign(bpy.context.object, material, name, coll)
    o.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = o.modifiers.new("soft stone edges", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        o.modifiers.new("weighted face normals", "WEIGHTED_NORMAL")
    return o


def sphere(name, loc, scale, material, coll, ico=False):
    if ico:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1, location=loc)
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=1, location=loc)
    o = assign(bpy.context.object, material, name, coll)
    o.scale = scale
    for p in o.data.polygons:
        p.use_smooth = not ico
    return o


def cone(name, loc, radius1, radius2, depth, material, coll, vertices=12):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1, radius2=radius2,
                                    depth=depth, location=loc)
    return assign(bpy.context.object, material, name, coll)


def rod(name, a, b, radius, material, coll, vertices=12):
    a, b = Vector(a), Vector(b)
    mid = (a+b)/2
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                        depth=(b-a).length, location=mid)
    o = assign(bpy.context.object, material, name, coll)
    o.rotation_euler = (b-a).to_track_quat("Z", "Y").to_euler()
    return o


def ring(name, loc, major, minor, material, coll, vertical=False):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=64, minor_segments=8, location=loc)
    o = assign(bpy.context.object, material, name, coll)
    if vertical:
        o.rotation_euler.x = math.pi/2
    return o


def mesh(name, vertices, faces, material, coll):
    me = bpy.data.meshes.new(name)
    me.from_pydata(vertices, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    me.materials.append(material)
    return o


def aim(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat("-Z", "Y").to_euler()


def camera(name, loc, target, ortho=None, lens=42):
    data = bpy.data.cameras.new(name)
    o = bpy.data.objects.new(name, data)
    LIGHTS.objects.link(o)
    o.location = loc
    aim(o, target)
    if ortho:
        data.type = "ORTHO"
        data.ortho_scale = ortho
    else:
        data.lens = lens
    return o


def area_light(name, loc, color, power, size, target):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.color = color
    data.shape = "DISK"
    data.size = size
    o = bpy.data.objects.new(name, data)
    LIGHTS.objects.link(o)
    o.location = loc
    aim(o, target)


# Arena: a neutral, low-value ruined hall. Center stays quiet for the boss.
cube("arena floor", (0, 4, -0.14), (18, 23, 0.25), floor_stone, ARENA, 0.08)
cube("distant wall", (0, 10, 3.0), (18, 0.45, 7), stone, ARENA, 0.04)
for side in (-1, 1):
    x = side * 5.5
    cube(f"arch pier {side}", (x, 7.5, 2.3), (1.15, 1.25, 4.6), stone, ARENA, 0.08)
    cube(f"pier foot {side}", (x, 7.5, 0.22), (1.7, 1.7, 0.44), stone_edge, ARENA, 0.05)
    cube(f"pier cap {side}", (x, 7.5, 4.55), (1.55, 1.6, 0.42), stone_edge, ARENA, 0.05)
    for z in (1.05, 2.25, 3.45):
        cube(f"pier scar {side} {z}", (x-side*0.59, 6.85, z), (0.07, 0.08, 0.55), stone_edge, ARENA)
    cube(f"raised buttress {side}", (side*8.3, 4.0, 1.65), (1.0, 5.4, 3.3), stone, ARENA, 0.05)
    for j in range(4):
        cube(f"floor slab {side} {j}", (side*(1.7+j*1.2), 2.0, -0.005),
             (0.035, 10, 0.009), floor_edge, ARENA)
cube("upper lintel", (0, 8, 5.0), (12.3, 1.6, 0.65), stone, ARENA, 0.08)
# Receding side frames create depth while leaving the centre quiet for combat.
for side in (-1, 1):
    for depth, scale in ((2.9, 1.0), (5.2, 0.80)):
        x = side * (7.1 - depth * 0.12)
        cube(f"receding pier {side} {depth}", (x, depth, 2.15),
             (0.50 * scale, 0.75, 4.3), recess, ARENA, 0.045)
        cube(f"pier highlight {side} {depth}", (x-side*0.27, depth-0.4, 2.30),
             (0.05, 0.07, 3.20), stone_edge, ARENA)
    # Unequal fragments make the place feel worn without filling the aim area.
    for j, (depth, height) in enumerate(((4.2, 0.32), (6.0, 0.46), (7.0, 0.22))):
        x = side * (4.55 + j * 0.4)
        chunk = cube(f"fallen masonry {side} {j}", (x, depth, height/2),
                     (0.65+0.18*j, 0.54, height), stone, ARENA, 0.035)
        chunk.rotation_euler.z = side * (0.14 + 0.11*j)
for side in (-1, 1):
    cube(f"rear arch side {side}", (side*3.25, 9.64, 2.25),
         (0.22, 0.18, 4.35), stone_edge, ARENA, 0.025)
    rod(f"rear arch slope {side}", (side*3.25, 9.64, 4.30),
        (side*1.65, 9.64, 5.20), 0.11, stone_edge, ARENA, 8)
    sphere(f"sconce {side}", (side*4.5, 7.2, 2.95),
           (0.12, 0.12, 0.18), glow, ARENA, True)
ring("distant sigil outer", (0, 9.70, 2.36), 1.35, 0.022, glow, ARENA, True)
ring("distant sigil inner", (0, 9.66, 2.36), 0.83, 0.013, glow, ARENA, True)
for i in range(12):
    a = math.tau*i/12
    x, z = 1.12*math.sin(a), 2.36+1.12*math.cos(a)
    cube(f"wall rune {i}", (x, 9.62, z), (0.12, 0.025, 0.04), glow, ARENA)
for r in (1.8, 3.3, 5.6):
    ring(f"floor inscription {r}", (0, 3.1, 0.015), r, 0.010, floor_glow, ARENA)
for i in range(16):
    a = math.tau*i/16
    rod(f"floor ray {i}", (1.85*math.sin(a), 3.1+1.85*math.cos(a), 0.016),
        (3.1*math.sin(a), 3.1+3.1*math.cos(a), 0.016), 0.012, floor_glow, ARENA, 6)
for y in (0.8, 2.8, 5.0):
    cube(f"horizontal floor joint {y}", (0, y, -0.005), (15, 0.035, 0.01), floor_edge, ARENA)


# Boss: a floating horned wraith with a winged, readable silhouette.
cone("tattered lower robe", (0, 0, 0.75), 0.78, 0.38, 1.55, dark, BOSS, 12)
sphere("armoured chest", (0, -0.02, 1.95), (0.64, 0.42, 0.8), robe, BOSS, True)
cone("collar", (0, -0.11, 2.38), 0.65, 0.32, 0.58, dark, BOSS, 10)
sphere("skull", (0, -0.28, 2.88), (0.44, 0.37, 0.45), bone, BOSS, True)
sphere("face mask", (0, -0.56, 2.91), (0.36, 0.14, 0.30), dark, BOSS, True)
cone("jaw", (0, -0.55, 2.61), 0.28, 0.12, 0.34, bone, BOSS, 8)
for side in (-1, 1):
    cone(f"main horn {side}", (side*0.39, -0.27, 3.42), 0.18, 0.0, 0.92, bone, BOSS, 8).rotation_euler.y = side*0.45
    sphere(f"eye socket {side}", (side*0.17, -0.66, 2.98), (0.12, 0.055, 0.10), eye, BOSS, True)
    sphere(f"shoulder {side}", (side*0.64, -0.02, 2.29), (0.36, 0.43, 0.32), stone_edge, BOSS, True)
    rod(f"upper arm {side}", (side*0.72, -0.06, 2.15), (side*1.02, -0.22, 1.59), 0.17, robe, BOSS)
    rod(f"forearm {side}", (side*1.02, -0.22, 1.59), (side*0.98, -0.66, 1.29), 0.14, dark, BOSS)
    sphere(f"claw palm {side}", (side*0.98, -0.68, 1.27), (0.18, 0.14, 0.19), bone, BOSS, True)
    for finger in (-1, 0, 1):
        rod(f"claw {side} {finger}", (side*0.98+finger*0.09, -0.72, 1.20),
            (side*0.98+finger*0.12, -0.86, 0.94), 0.035, bone, BOSS, 6)
    # Five-point wing membrane, stitched from a root to three scalloped tips.
    wing = [(side*0.48, 0.10, 2.44), (side*1.26, 0.16, 3.07),
            (side*2.15, 0.27, 3.29), (side*1.83, 0.20, 2.48),
            (side*2.38, 0.34, 2.15), (side*1.49, 0.16, 1.80),
            (side*1.95, 0.30, 1.44), (side*0.50, 0.07, 1.78)]
    mesh(f"wing membrane {side}", wing,
         [(0, 1, 2, 3), (0, 3, 4, 5), (0, 5, 6, 7)], wingmat, BOSS)
    for j, tip in enumerate((wing[2], wing[4], wing[6])):
        rod(f"wing spar {side} {j}", wing[0], tip, 0.036, stone_edge, BOSS, 6)
    cone(f"pauldron spike {side}", (side*0.83, -0.06, 2.65), 0.14, 0, 0.60, bone, BOSS, 8).rotation_euler.y = side*0.30
sphere("heart crystal", (0, -0.48, 1.96), (0.22, 0.13, 0.31), gem, BOSS, True)
for side in (-1, 1):
    rod(f"angry brow {side}", (side*0.04, -0.73, 3.11),
        (side*0.30, -0.70, 3.19), 0.055, bone, BOSS, 6)
    cone(f"skull fang {side}", (side*0.14, -0.65, 2.54), 0.065, 0.0, 0.19, bone, BOSS, 6).rotation_euler.y = math.pi
ring("boss halo", (0, 0.17, 2.40), 1.56, 0.017, gem, BOSS, True)
for i in range(8):
    a = math.tau*i/8
    sphere(f"halo bead {i}", (1.56*math.sin(a), 0.16, 2.40+1.56*math.cos(a)),
           (0.045, 0.045, 0.045), gem, BOSS, True)

# Visible-only variant meshes preserve a shared identity but change the silhouette.
variant_objects = {"arcane": [], "frost": [], "void": []}
for side in (-1, 1):
    shard = cone(f"frost crown {side}", (side*0.54, 0.02, 3.47), 0.14, 0, 1.22, bone, BOSS, 5)
    shard.rotation_euler.y = side * 0.18
    variant_objects["frost"].append(shard)
    shard = cone(f"frost wing shard {side}", (side*1.78, 0.18, 2.75), 0.18, 0, 1.38, bone, BOSS, 5)
    shard.rotation_euler.y = side * 0.65
    variant_objects["frost"].append(shard)
    # A wide broken crown and swept tendrils give the void boss a heavier outline.
    for j, (x, z, angle) in enumerate(((0.53, 3.35, 0.78), (0.83, 3.08, 1.04))):
        horn = cone(f"void crown {side} {j}", (side*x, 0.0, z), 0.19, 0, 0.95, void_detail, BOSS, 7)
        horn.rotation_euler.y = side * angle
        variant_objects["void"].append(horn)
    tendril = rod(f"void tendril {side}", (side*1.32, 0.18, 1.92),
                  (side*2.50, 0.15, 1.18), 0.09, void_detail, BOSS, 7)
    variant_objects["void"].append(tendril)
for objects in variant_objects.values():
    for obj in objects:
        obj.hide_render = True

# Keep all three editable palettes in the .blend, even when not active.
boss_palettes = {
    "arcane": (robe, wingmat, mat("arcane boss core", (0.82, 0.25, 0.15), rough=0.25, emit=1.4),
               mat("arcane boss eye", (0.82, 0.25, 0.15), rough=0.3, emit=1.7)),
    "frost": (mat("frost robe", (0.055, 0.15, 0.22)),
              mat("frost wing", (0.09, 0.22, 0.30)),
              mat("frost core", (0.23, 0.65, 1.0), rough=0.25, emit=1.4),
              mat("frost eye", (0.23, 0.65, 1.0), rough=0.3, emit=1.7)),
    "void": (mat("void robe", (0.085, 0.025, 0.13)),
             mat("void wing", (0.085, 0.025, 0.11)),
             mat("void core", (0.69, 0.19, 0.92), rough=0.25, emit=1.4),
             mat("void eye", (0.69, 0.19, 0.92), rough=0.3, emit=1.7)),
}
for pair in boss_palettes.values():
    for material in pair:
        material.use_fake_user = True
palette_slots = []
for obj in BOSS.objects:
    if obj.type == "MESH":
        for index, material in enumerate(obj.data.materials):
            if material == robe:
                palette_slots.append((obj, index, 0))
            elif material == wingmat:
                palette_slots.append((obj, index, 1))
            elif material == gem:
                palette_slots.append((obj, index, 2))
            elif material == eye:
                palette_slots.append((obj, index, 3))
for obj, index, palette_index in palette_slots:
    obj.data.materials[index] = boss_palettes["arcane"][palette_index]


# Player: full mage model for the asset library and menu illustration.
cone("mage robe", (0, 0, 0.94), 0.83, 0.43, 1.85, robe, PLAYER, 12)
sphere("mage torso", (0, -0.02, 2.03), (0.57, 0.37, 0.61), dark, PLAYER, True)
sphere("hood outer", (0, -0.07, 2.84), (0.55, 0.43, 0.64), robe, PLAYER, True)
sphere("hood void", (0, -0.43, 2.78), (0.38, 0.13, 0.42), dark, PLAYER, True)
for side in (-1, 1):
    sphere(f"mage eye {side}", (side*0.15, -0.55, 2.78), (0.075, 0.045, 0.035), gem, PLAYER, True)
    sphere(f"mage shoulder {side}", (side*0.51, 0, 2.23), (0.28, 0.32, 0.32), robe, PLAYER, True)
    rod(f"mage arm {side}", (side*0.54, -0.06, 2.17), (side*0.78, -0.42, 1.55), 0.18, robe, PLAYER)
    sphere(f"mage glove {side}", (side*0.78, -0.47, 1.51), (0.17, 0.12, 0.17), trim, PLAYER, True)
    rod(f"robe piping {side}", (side*0.34, -0.39, 1.9), (side*0.58, -0.36, 0.35), 0.025, trim, PLAYER, 8)
rod("mage staff", (0.76, -0.43, 1.45), (0.91, -0.67, 3.25), 0.052, wood, PLAYER, 10)
sphere("mage staff crystal", (0.92, -0.69, 3.34), (0.22, 0.20, 0.31), gem, PLAYER, True)
ring("mage staff collar", (0.91, -0.67, 3.05), 0.11, 0.025, trim, PLAYER)


# First-person prop: on its own camera, right forearm and wand directed up-left.
rod("fp sleeve", (1.62, 0.10, 0.46), (0.55, -0.15, 1.23), 0.30, robe, WAND, 12)
rod("fp cuff", (0.72, -0.12, 1.12), (0.47, -0.17, 1.37), 0.32, trim, WAND, 12)
sphere("fp glove", (0.42, -0.18, 1.39), (0.31, 0.28, 0.23), dark, WAND, True)
rod("fp wand", (1.10, -0.15, 0.22), (-0.35, -0.20, 2.52), 0.072, wood, WAND, 10)
for i in range(3):
    t = 0.38+i*0.20
    x = 1.10+(-1.45)*t
    z = 0.22+2.30*t
    sphere(f"fp silver ferrule {i}", (x, -0.20, z), (0.09, 0.08, 0.10), trim, WAND, True)
sphere("fp tip setting", (-0.35, -0.20, 2.56), (0.20, 0.17, 0.26), trim, WAND, True)
sphere("fp crystal", (-0.35, -0.22, 2.69), (0.16, 0.15, 0.22), gem, WAND, True)


area_light("warm key", (-4, -4, 7), (1.0, 0.72, 0.58), 1550, 5, (0, 0, 1.7))
area_light("cool fill", (4, -2, 5), (0.48, 0.65, 1.0), 1000, 6, (0, 0, 1.7))
area_light("back rim", (1, 5, 6), (0.54, 0.39, 0.79), 1600, 4, (0, 0, 2))

arena_cam = camera("Arena 16x9", (0, -9, 2.5), (0, 5, 1.80), lens=41)
sprite_cam = camera("Character orthographic", (4.0, -10, 3.7), (0, 0, 2.03), ortho=5.2)
wand_cam = camera("Wand orthographic", (0.0, -8, 2.3), (0.63, 0, 1.22), ortho=3.85)


def visibility(show):
    for c in (ARENA, BOSS, PLAYER, WAND):
        c.hide_render = c.name not in show


def render(name, cam, size, shown, transparent=True):
    visibility(shown)
    scene.camera = cam
    scene.render.film_transparent = transparent
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.filepath = str(OUT/name)
    bpy.ops.render.render(write_still=True)


# Save an editable source with the full set visible in the Outliner.
visibility({ARENA.name, BOSS.name})
scene.camera = arena_cam
scene.render.resolution_x, scene.render.resolution_y = (1280, 720)
scene.render.film_transparent = False
bpy.ops.wm.save_as_mainfile(filepath=str(SRC/"air_spell_arena_art.blend"))

render("arena_background.png", arena_cam, (1280, 720), {ARENA.name}, False)
render("player_mage.png", sprite_cam, (640, 640), {PLAYER.name})
render("player_wand.png", wand_cam, (512, 512), {WAND.name})

for key in ("arcane", "frost", "void"):
    for name, objects in variant_objects.items():
        for obj in objects:
            obj.hide_render = name != key
    for obj, index, palette_index in palette_slots:
        obj.data.materials[index] = boss_palettes[key][palette_index]
    render(f"boss_{key}.png", sprite_cam, (640, 640), {BOSS.name})

print("ASSET_RESULT", {"blend": str(SRC/"air_spell_arena_art.blend"),
                       "renders": sorted(p.name for p in OUT.glob("*.png")),
                       "meshes": sum(o.type == "MESH" for o in bpy.data.objects)})

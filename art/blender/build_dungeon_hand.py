"""Render a ruined circular dungeon and a connected first-person glove."""
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector

root = Path(__file__).resolve().parents[2]
scene = bpy.context.scene
arena = bpy.data.collections["01_Arena"]
wand = bpy.data.collections["04_FirstPersonWand"]
for obj in list(arena.objects):
    bpy.data.objects.remove(obj, do_unlink=True)


def assign(obj, name, material, collection):
    obj.name = name
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection.objects.link(obj)
    obj.data.materials.clear()
    obj.data.materials.append(material)
    return obj


def cube(name, loc, size, mat, angle=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = assign(bpy.context.object, name, mat, arena)
    obj.dimensions = size
    obj.rotation_euler.z = angle
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = obj.modifiers.new("worn corners", "BEVEL")
    bevel.width = .045
    bevel.segments = 2
    return obj


def rod(name, a, b, radius, mat, collection):
    a, b = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius, depth=(b-a).length,
                                        location=(a+b)/2)
    obj = assign(bpy.context.object, name, mat, collection)
    obj.rotation_euler = (b-a).to_track_quat("Z", "Y").to_euler()
    return obj


def ruined_wall(name, loc, width, depth, left_height, right_height, mat, angle):
    # Uneven upper edge breaks the clean rectangular silhouette.
    w, d = width / 2, depth / 2
    vertices = [(-w, -d, 0), (w, -d, 0), (w, d, 0), (-w, d, 0),
                (-w, -d, left_height), (w, -d, right_height),
                (w, d, right_height + .12), (-w, d, left_height + .12)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5),
                                   (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    arena.objects.link(obj)
    obj.location = loc
    obj.rotation_euler.z = angle
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("chipped edges", "BEVEL")
    bevel.width = .055
    bevel.segments = 2
    return obj


stone = bpy.data.materials["cold basalt"]
edge = bpy.data.materials["worn edge"]
floor = bpy.data.materials["dark floor"]
rune = bpy.data.materials["low energy rune"]
robe = bpy.data.materials["violet cloth"]
glove = bpy.data.materials["deep robe"]
trim = bpy.data.materials["aged silver"]
# Subtle mineral variation on the broken masonry, without obscuring silhouettes.
stone_nodes = stone.node_tree.nodes
stone_links = stone.node_tree.links
stone_shader = next(n for n in stone_nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
noise = stone_nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 5.0
noise.inputs["Detail"].default_value = 3.0
ramp = stone_nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (.025, .022, .026, 1)
ramp.color_ramp.elements[1].color = (.095, .082, .075, 1)
stone_links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
stone_links.new(ramp.outputs["Color"], stone_shader.inputs["Base Color"])
glow = bpy.data.materials.new("embers in ash")
glow.diffuse_color = (.45, .075, .018, 1)
glow.use_nodes = True
principled = next(n for n in glow.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
principled.inputs["Base Color"].default_value = (.3, .045, .008, 1)
principled.inputs["Emission Color"].default_value = (.65, .09, .015, 1)
principled.inputs["Emission Strength"].default_value = 2.0
random.seed(781)

# Round stone arena, interrupted masonry, and a broken circular crown.
bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=8.4, depth=.25, location=(0, 2, -.15))
assign(bpy.context.object, "circular arena floor", floor, arena)
for radius in (2.0, 4.2, 7.5):
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=.025,
                                     major_segments=96, minor_segments=6, location=(0, 2, .012))
    assign(bpy.context.object, f"floor ring {radius}", rune, arena)
for i in range(20):
    a = math.tau * i / 20
    rod(f"radial floor seam {i}", (2 * math.sin(a), 2 + 2 * math.cos(a), .016),
        (7.4 * math.sin(a), 2 + 7.4 * math.cos(a), .016), .012, rune, arena)
for i in range(22):
    a = math.tau * i / 22
    x, y = 8.0 * math.sin(a), 2 + 8.0 * math.cos(a)
    if y < -3.1:  # Camera entrance.
        continue
    if i in (2, 8, 14, 19):
        continue
    height = (2.2, 3.6, 2.9, 4.2, 3.1)[i % 5]
    ruined_wall(f"broken wall {i}", (x, y, 0), 2.1, .70, height,
                max(1.5, height - (i % 3 + 1) * .35), stone, -a)
    if i % 3 == 0:
        cube(f"stone pier {i}", (x*.96, 2+(y-2)*.96, 2.1), (.50, .7, 4.2), edge, -a)
    if i % 2 == 0:
        # Broken beam rests on the surviving part of the wall.
        tangent = Vector((math.cos(a), -math.sin(a), 0))
        midpoint = Vector((x, y, height - .12))
        rod(f"broken crown {i}", midpoint - tangent*.65,
            midpoint + tangent*.65, .12, edge, arena)
    if y > 2 and i % 3 == 1:
        tangent = Vector((math.cos(a), -math.sin(a), 0))
        midpoint = Vector((x, y-.39, height*.58))
        rod(f"wall fracture {i}", midpoint - tangent*.34,
            midpoint + tangent*.25 + Vector((0, 0, .16)), .025, rune, arena)
    if i % 4 == 1:
        # Exposed broken rebar leaning above the damaged wall.
        rod(f"exposed rebar {i}", (x, y, height-.25),
            (x+.25, y-.12, height+.60), .035, edge, arena)
for i in range(18):
    a = random.uniform(-1.9, 1.9)
    radius = random.uniform(5.3, 7.1)
    height = random.uniform(.15, .5)
    cube(f"fallen masonry {i}", (radius*math.sin(a), 2+radius*math.cos(a), height/2),
         (random.uniform(.35, .85), random.uniform(.4, .9), height), edge, random.uniform(-1, 1))
for i in range(18):
    a = random.uniform(-1.8, 1.8)
    radius = random.uniform(5.2, 7.8)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=random.uniform(.025, .075),
                                          location=(radius*math.sin(a), 2+radius*math.cos(a), .08))
    assign(bpy.context.object, f"ember {i}", glow, arena)

scene.world.use_nodes = True
world_bg = scene.world.node_tree.nodes.get("Background")
world_bg.inputs["Color"].default_value = (.035, .017, .014, 1)
world_bg.inputs["Strength"].default_value = .28
for light in bpy.data.objects:
    if light.type == "LIGHT" and light.name == "warm key":
        light.data.color = (1.0, .46, .28)
        light.data.energy = 900

camera = bpy.data.objects["Arena 16x9"]
camera.location = (0, -10.6, 3.4)
camera.rotation_euler = (Vector((0, 2.2, 1.65)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.lens = 37

# Extend the sleeve beyond the screen edge; sculpt individual gloved fingers
# around the existing wand while retaining its exact crystal position.
old_sleeve = bpy.data.objects.get("fp sleeve")
if old_sleeve:
    bpy.data.objects.remove(old_sleeve, do_unlink=True)
rod("connected sleeve", (2.45, .10, -.35), (.55, -.15, 1.23), .30, robe, wand)
for i in range(4):
    x = .30 + i * .095
    rod(f"gripping finger {i}", (x, -.43, 1.48), (x+.045, -.47, 1.28), .067, glove, wand)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=.068, location=(x+.045, -.47, 1.28))
    assign(bpy.context.object, f"finger joint {i}", glove, wand)
rod("gloved thumb", (.22, -.37, 1.50), (.40, -.49, 1.58), .088, glove, wand)
rod("wrist stitch", (.76, -.25, 1.00), (.89, -.25, .90), .025, trim, wand)

for name in ("01_Arena", "02_Boss", "03_Player", "04_FirstPersonWand"):
    bpy.data.collections[name].hide_render = name != "01_Arena"
scene.camera = camera
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
scene.render.film_transparent = False
bpy.ops.wm.save_as_mainfile(filepath=str(root / "art/blender/apocalypse_dungeon_hand.blend"))
scene.render.filepath = str(root / "assets/arena_background.png")
bpy.ops.render.render(write_still=True)
arena.hide_render = True
wand.hide_render = False
scene.camera = bpy.data.objects["Wand orthographic"]
scene.render.resolution_x = scene.render.resolution_y = 512
scene.render.film_transparent = True
scene.render.filepath = str(root / "assets/player_wand.png")
bpy.ops.render.render(write_still=True)
print("DUNGEON_RESULT", {"meshes": sum(o.type == "MESH" for o in arena.objects), "wand": len(wand.objects)})

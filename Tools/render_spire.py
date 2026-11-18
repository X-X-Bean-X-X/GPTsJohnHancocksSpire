"""Render the actual V1 mesh against transparency for the preview artwork."""

import sys
from pathlib import Path

import bpy
from mathutils import Vector


root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "Tools"))
from build_spire import ASSET, LENS, SWATCHES

output = Path(sys.argv[sys.argv.index("--") + 1])
output.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
mast = bpy.data.objects[ASSET]
surface = mast.active_material.node_tree.nodes.get("Principled BSDF")
graph = mast.active_material.node_tree
coords = graph.nodes.new("ShaderNodeTexCoord")
uv_channels = graph.nodes.new("ShaderNodeSeparateXYZ")
graph.links.new(coords.outputs["UV"], uv_channels.inputs[0])
lens = graph.nodes.new("ShaderNodeMath")
lens.operation = "GREATER_THAN"
graph.links.new(uv_channels.outputs["X"], lens.inputs[0])
lens.inputs[1].default_value = LENS / len(SWATCHES)
glow = graph.nodes.new("ShaderNodeMath")
glow.operation = "MULTIPLY"
graph.links.new(lens.outputs[0], glow.inputs[0])
glow.inputs[1].default_value = 3.0
graph.links.new(glow.outputs[0], surface.inputs["Emission Strength"])
surface.inputs["Emission Color"].default_value = (1.0, 0.023, 0.026, 1.0)

camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(camera)
scene.camera = camera
camera.data.type = "ORTHO"
camera.data.clip_end = 300


def light(name, position, energy, tint, radius, aim):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = tint
    data.shape = "DISK"
    data.size = radius
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (Vector(aim) - obj.location).to_track_quat("-Z", "Y").to_euler()


def render(name, center, view, vertical_span, width, height):
    target = Vector((0, 0, center))
    camera.location = target + Vector(view)
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = vertical_span * max(1, width / height)
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.filepath = str(output / f"{name}.png")
    bpy.ops.render.render(write_still=True)


scene.world = bpy.data.worlds.new("Sky fill")
scene.world.use_nodes = True
scene.world.node_tree.nodes.get("Background").inputs[0].default_value = (0.19, 0.28, 0.48, 1)
scene.world.node_tree.nodes.get("Background").inputs[1].default_value = 0.29
scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.cycles.use_denoising = True
scene.render.threads_mode = "FIXED"
scene.render.threads = 8
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "AgX"
light("Cool rim", (-6, 11, 33), 34000, (0.51, 0.69, 1.0), 44, (0, 0, 30))
light("Key", (13, -15, 40), 65000, (1.0, 0.91, 0.78), 36, (0, 0, 30))
light("Mount fill", (3, -5, 6), 1400, (0.72, 0.84, 1.0), 6, (0, 0, 2))
light("Beacon fill", (2, -4, 61), 700, (0.83, 0.89, 1.0), 6, (0, 0, 58))
render("full", 30, (9, -32, 2.8), 66, 320, 940)
render("mount", 3.75, (3, -11, 1.7), 8.32, 248, 325)
render("tip", 58.67, (3, -11, 0.1), 3.55, 248, 325)

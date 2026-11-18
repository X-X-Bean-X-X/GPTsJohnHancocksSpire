"""Build the standalone mesh, native-import FBXs, and texture atlas in Blender."""

import json
from math import cos, pi, sin, sqrt
from pathlib import Path
import struct
import zlib

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
IMPORT = ROOT / "Import"
ASSET = "XBeanXJohnHancocksSpireV1"
HEIGHT = 60.0
DONOR_BASE = 343.7
FACTOR = HEIGHT / (456.9 - DONOR_BASE)

# One material at every LOD. MaskMap is metallic, occlusion, detail, smoothness.
PAINT, BLACK, STEEL, ZINC, RED, BRASS, LENS = range(7)
SWATCHES = (
    ((219, 224, 224), (35, 255, 0, 106)),
    ((30, 34, 39), (42, 255, 0, 73)),
    ((69, 77, 85), (165, 255, 0, 100)),
    ((129, 141, 146), (148, 255, 0, 112)),
    ((163, 16, 24), (25, 255, 0, 144)),
    ((196, 147, 44), (165, 255, 0, 168)),
    ((225, 23, 30), (0, 255, 0, 184)),
)
# CS2's native packager creates 512 px virtual texture tiles. Every map must
# meet that minimum or the package may contain an empty MidMips cache.
TEX_SIZE = 512
TIERS = (
    (348.5, 378.0, 1.35, 1.23, (350, 356, 362, 368, 374)),
    (378.0, 411.0, 1.00, 0.92, (380, 386, 392, 398, 404, 410)),
    (411.0, 438.0, 0.65, 0.59, (416, 422, 428, 434)),
    (438.0, 452.9, 0.30, 0.24, (440, 446)),
)
TRUNK_FACE = -120 * pi / 180
FEED_FACE = -37 * pi / 180


def mount(radial, across, height, spin):
    return (radial * cos(spin) - across * sin(spin),
            radial * sin(spin) + across * cos(spin), height)


def shaft_radius(height):
    original = height / FACTOR + DONOR_BASE
    for bottom, top, wide, narrow, _ in TIERS:
        if original <= top:
            return (wide + (narrow - wide) * max(0, original - bottom) / (top - bottom)) * FACTOR
    return TIERS[-1][3] * FACTOR


def png(path, colors):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    texels = bytes(value for index in range(TEX_SIZE)
                   for value in colors[index * len(colors) // TEX_SIZE])
    pixels = (b"\0" + texels) * TEX_SIZE
    header = struct.pack(">IIBBBBB", TEX_SIZE, TEX_SIZE, 8, {3: 2, 4: 6}[len(colors[0])], 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class Parts:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.swatches = []
        self.smooth = []

    def add_face(self, indices, swatch, smooth=False):
        self.faces.append(indices)
        self.swatches.append(swatch)
        self.smooth.append(smooth)

    def profile(self, rings, sides, swatch, center=(0, 0), spin=0.0, smooth=True):
        start = len(self.vertices)
        for z, radius in rings:
            self.vertices.extend(
                (center[0] + radius * cos(spin + 2 * pi * i / sides),
                 center[1] + radius * sin(spin + 2 * pi * i / sides), z)
                for i in range(sides)
            )
        self.add_face(tuple(reversed(range(start, start + sides))), swatch)
        for index in range(len(rings) - 1):
            near = start + index * sides
            far = near + sides
            for face in range(sides):
                following = (face + 1) % sides
                self.add_face((near + face, near + following, far + following, far + face), swatch, smooth)
        last = start + (len(rings) - 1) * sides
        self.add_face(tuple(range(last, last + sides)), swatch)

    def box(self, center, dims, swatch, spin):
        x, y, z = center
        depth, width, height = (d / 2 for d in dims)
        start = len(self.vertices)
        for vertical in (-height, height):
            for radial, across in ((-depth, -width), (depth, -width), (depth, width), (-depth, width)):
                a, b, c = mount(radial, across, vertical, spin)
                self.vertices.append((x + a, y + b, z + c))
        for face in ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.add_face(tuple(start + i for i in face), swatch)

    def tube(self, points, radius, sides, swatch, spin):
        points = [Vector(p) for p in points]
        axis = Vector((-sin(spin), cos(spin), 0))
        start = len(self.vertices)
        for index, point in enumerate(points):
            before = points[max(0, index - 1)]
            after = points[min(len(points) - 1, index + 1)]
            tangent = (after - before).normalized()
            primary = (axis - tangent * tangent.dot(axis)).normalized()
            secondary = tangent.cross(primary)
            for side in range(sides):
                angle = 2 * pi * side / sides
                self.vertices.append(tuple(point + radius * (primary * cos(angle) + secondary * sin(angle))))
        self.add_face(tuple(reversed(range(start, start + sides))), swatch)
        for ring in range(len(points) - 1):
            near = start + ring * sides
            for side in range(sides):
                following = (side + 1) % sides
                self.add_face((near + side, near + following, near + sides + following, near + sides + side),
                              swatch, True)
        end = start + (len(points) - 1) * sides
        self.add_face(tuple(range(end, end + sides)), swatch)

    def pedestal(self, lod):
        outline = [(0, 1.44), (0.06, 1.50), (1.36, 1.50), (1.42, 1.44)]
        self.profile([(z, half * sqrt(2)) for z, half in outline],
                     4, BLACK, spin=pi / 4, smooth=False)
        self.profile([(1.41, 1.41 * sqrt(2)), (1.50, 1.36 * sqrt(2))],
                     4, STEEL, spin=pi / 4, smooth=False)
        self.profile([(1.49, 1.07), (1.67, 1.07), (1.78, 0.81), (2.56, 0.77)],
                     (16, 10, 6)[lod], BLACK)
        if lod == 0:
            for x in (-1.12, 1.12):
                for y in (-1.12, 1.12):
                    self.profile([(1.48, 0.17), (1.53, 0.17)], 8, STEEL, center=(x, y))
                    self.profile([(1.52, 0.125), (1.67, 0.125), (1.71, 0.091)],
                                 6, ZINC, center=(x, y), smooth=False)
            for spin in (0, pi / 2, pi, 3 * pi / 2):
                start = len(self.vertices)
                self.vertices.extend(mount(radial, across, z, spin)
                                     for across in (-0.071, 0.071)
                                     for radial, z in ((0.73, 1.57), (1.23, 1.57), (0.73, 2.17)))
                for face in ((0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)):
                    self.add_face(tuple(start + i for i in face), STEEL)

    def mast(self, lod):
        sides = (16, 8, 6)[lod]
        # The four tier breaks and collar spacing are measured from Hancock V002.
        for bottom, top, wide, narrow, collars in TIERS:
            low = (bottom - DONOR_BASE) * FACTOR
            high = (top - DONOR_BASE) * FACTOR
            self.profile([(low - 0.025, wide * FACTOR), (high, narrow * FACTOR)], sides, PAINT)
            if lod == 1:
                collars = collars[::2]
            elif lod == 2:
                collars = collars[:1]
            for band in collars:
                z = (band - DONOR_BASE) * FACTOR
                radius = (wide + (narrow - wide) * (band - bottom) / (top - bottom)) * FACTOR
                edge = radius + max(0.024, 0.14 * radius)
                shape = [(z, radius), (z + 0.05, edge), (z + 0.22, edge), (z + 0.28, radius)]
                if lod == 2:
                    shape = [(z, edge), (z + 0.30, edge)]
                self.profile(shape, (12, 8, 6)[lod], BLACK)
                if lod == 0:
                    size = max(0.10, min(0.22, 0.36 * edge))
                    self.box(mount(edge, 0.075, z + 0.14, TRUNK_FACE), (size, 0.24, 0.21), BLACK, TRUNK_FACE)
                    self.box(mount(edge + size * 0.48, 0.136, z + 0.14, TRUNK_FACE),
                             (0.052, 0.084, 0.090), STEEL, TRUNK_FACE)

        if lod == 0:
            lower = [(57.83, 0.18), (57.88, 0.26), (57.94, 0.30), (58.00, 0.30),
                     (58.035, 0.267), (58.065, 0.303), (58.12, 0.303), (58.16, 0.271)]
            upper = [(58.60, 0.282), (58.66, 0.303), (58.72, 0.303), (58.75, 0.271),
                     (58.78, 0.292), (58.87, 0.292), (58.96, 0.238), (59.04, 0.145)]
        else:
            lower = [(57.83, 0.18), (57.90, 0.30), (58.16, 0.271)]
            upper = [(58.60, 0.282), (58.72, 0.303), (59.04, 0.145)]
        beacon_sides = (12, 8, 6)[lod]
        self.profile(lower, beacon_sides, RED)
        self.profile([(58.14, 0.267), (58.23, 0.302), (58.53, 0.31), (58.63, 0.277)], beacon_sides, LENS)
        self.profile(upper, beacon_sides, RED)
        self.profile([(59.01, 0.091), (59.80, 0.090)], beacon_sides, PAINT)
        self.profile([(59.67, 0.102), (59.71, 0.128), (59.96, 0.128), (HEIGHT, 0.100)], beacon_sides, BRASS)

    def mechanical(self, lod):
        if lod == 2:
            return
        heights = (2.42, 3.11, 17.98, 18.18, 19.02, 35.5, 35.68, 36.52, 49.89, 50.16, 50.81, 56.7)
        rail = [mount(shaft_radius(z) + 0.089, -0.027, z, TRUNK_FACE) for z in heights]
        self.tube(rail, 0.055, 6 if lod == 0 else 4, ZINC, TRUNK_FACE)
        if lod == 0:
            aux = [mount(shaft_radius(z) + 0.079, -0.163, z, TRUNK_FACE)
                   for z in (2.41, 3.04, 17.98, 18.18, 19.02, 30.0)]
            self.tube(aux, 0.025, 5, STEEL, TRUNK_FACE)
            for z in (3.9, 5.48, 8.8, 11.2, 14.7, 17.1, 19.6, 22.0, 24.6, 27.2, 31.0,
                      33.5, 37.0, 39.4, 42.0, 44.6, 47.5, 51.8, 54.9):
                radius = shaft_radius(z)
                self.box(mount(radius + 0.045, -0.025, z, TRUNK_FACE),
                         (0.18, 0.21, 0.103), STEEL, TRUNK_FACE)
            for side in (-0.09, 0.09):
                bends = ((-0.31, 2.43), (-0.34, 3.03), (-0.34, 13.15), (-0.31, 13.40),
                         (-0.23, 13.65), (-0.02, 13.87), (0.10, 14.11), (0.12, 14.4), (0.12, 15.73))
                feed = [mount(shaft_radius(z) + 0.075, across + side, z, FEED_FACE) for across, z in bends]
                self.tube(feed, 0.043, 6, ZINC, FEED_FACE)
            for z in (3.1, 6.8, 9.4, 12.25, 14.72):
                y = -0.34 if z < 13 else 0.12
                self.box(mount(shaft_radius(z) + 0.043, y, z, FEED_FACE),
                         (0.151, 0.346, 0.138), STEEL, FEED_FACE)
            self.box(mount(shaft_radius(10.7) + 0.015, -0.05, 10.7, FEED_FACE),
                     (0.06, 0.39, 0.78), ZINC, FEED_FACE)
        for z, spin, across, width, height in (
                (6.1, TRUNK_FACE, 0.14, 0.44, 1.32),
                (16.28, FEED_FACE, 0.12, 0.43, 1.22),
                (20.71, TRUNK_FACE, 0.03, 0.36, 0.99)):
            radius = shaft_radius(z)
            self.box(mount(radius + 0.063, across, z, spin),
                     (0.153, width + 0.06, height + 0.12), STEEL, spin)
            self.box(mount(radius + 0.166, across, z, spin),
                     (0.133, width, height), ZINC, spin)
            if lod == 0:
                for side in (-1, 1):
                    for level in (-1, 1):
                        self.box(mount(radius + 0.234, across + side * (width / 2 - 0.06),
                                       z + level * (height / 2 - 0.10), spin),
                                 (0.031, 0.057, 0.056), STEEL, spin)

    def make_mesh(self, name, material):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        if mesh.validate(verbose=True):
            raise ValueError(f"Invalid input mesh {name}")
        mesh.materials.append(material)
        uv = mesh.uv_layers.new(name="UVMap")
        for face, swatch, smooth in zip(mesh.polygons, self.swatches, self.smooth):
            face.use_smooth = smooth
            u = (swatch + 0.5) / len(SWATCHES)
            for corner, loop in enumerate(face.loop_indices):
                angle = corner * 2 * pi / face.loop_total
                uv.data[loop].uv = (u + 0.31 / len(SWATCHES) * cos(angle), 0.5 + 0.26 * sin(angle))
        mesh.calc_loop_triangles()
        return mesh


def make_material():
    material = bpy.data.materials.new(ASSET)
    material.use_nodes = True
    graph = material.node_tree
    surface = graph.nodes.get("Principled BSDF")
    image = graph.nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(str(IMPORT / f"{ASSET}_BaseColor.png"))
    image.image.pack()
    graph.links.new(image.outputs["Color"], surface.inputs["Base Color"])
    mask = graph.nodes.new("ShaderNodeTexImage")
    mask.image = bpy.data.images.load(str(IMPORT / f"{ASSET}_MaskMap.png"))
    mask.image.colorspace_settings.name = "Non-Color"
    mask.image.pack()
    split = graph.nodes.new("ShaderNodeSeparateColor")
    graph.links.new(mask.outputs["Color"], split.inputs["Color"])
    graph.links.new(split.outputs["Red"], surface.inputs["Metallic"])
    roughness = graph.nodes.new("ShaderNodeMath")
    roughness.operation = "SUBTRACT"
    roughness.inputs[0].default_value = 1.0
    graph.links.new(mask.outputs["Alpha"], roughness.inputs[1])
    graph.links.new(roughness.outputs[0], surface.inputs["Roughness"])
    return material


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    material = None
    records = []
    for lod in range(3):
        name = ASSET if lod == 0 else f"{ASSET}_LOD{lod}"
        png(IMPORT / f"{name}_BaseColor.png", [entry[0] for entry in SWATCHES])
        png(IMPORT / f"{name}_MaskMap.png", [entry[1] for entry in SWATCHES])
        png(IMPORT / f"{name}_Normal.png", [(128, 128, 255)])
        png(IMPORT / f"{name}_ControlMask.png", [(0, 0, 0, 0)])
        png(IMPORT / f"{name}_Emissive.png",
            [(255, 29, 34) if i == LENS else (0, 0, 0) for i in range(len(SWATCHES))])
        if material is None:
            material = make_material()
        parts = Parts()
        parts.pedestal(lod)
        parts.mast(lod)
        parts.mechanical(lod)
        mesh = parts.make_mesh(name, material)
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.export_scene.fbx(
            filepath=str(IMPORT / f"{name}.fbx"), use_selection=True, object_types={"MESH"},
            axis_forward="-Z", axis_up="Y", bake_space_transform=True, apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_NONE", mesh_smooth_type="FACE", use_tspace=True,
            use_triangles=True, bake_anim=False, add_leaf_bones=False,
        )
        if lod:
            obj.hide_set(True)
            obj.hide_render = True
        coords = [vertex.co for vertex in mesh.vertices]
        bounds = [[round(float(f(coord[i] for coord in coords)), 4) for i in range(3)]
                  for f in (min, max)]
        assert bounds == [[-1.5, -1.5, 0.0], [1.5, 1.5, HEIGHT]], bounds
        assert tuple(obj.location) == (0.0, 0.0, 0.0)
        records.append(dict(lod=lod, name=name, boundsMeters=bounds,
                            vertices=len(mesh.vertices), triangles=len(mesh.loop_triangles)))
    assert records[0]["triangles"] > records[1]["triangles"] > records[2]["triangles"]
    main = bpy.data.objects[ASSET]
    bpy.context.view_layer.objects.active = main
    main.select_set(True)
    bpy.context.preferences.filepaths.save_version = 0
    scene["author"] = "X_Bean_X"
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "Source" / "Hancock Spire V1.blend"))
    (ROOT / "Validation" / "Mesh audit.json").write_text(
        json.dumps(dict(heightMeters=HEIGHT, baseMeters=[3, 3], pivot="bottom center",
                        donorScale=FACTOR, lods=records), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()

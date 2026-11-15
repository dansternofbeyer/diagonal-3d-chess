"""
build_pieces.py — builds every Diagonal 3D Chess piece in Blender and exports them.

What it does:
  1. Builds each piece (king, queen, bishop, rook, knight, and the two pawn parts)
     from simple octagonal shapes, matching the faceted look of the 2006 pieces.
  2. Lays them out side by side in a "ChessPieces" collection so you can edit them.
  3. Exports each piece as a .glb into ../models/

Afterwards, from the project folder, run:
    python3 tools/bundle_models.py
That packs every .glb into models/pieces.js so the web pages can load the models
from a double-clicked file (no server needed).

How to run it:
  Blender > Scripting tab > open this file > Run Script.
  To keep hand edits you made in Blender and only re-export, set REBUILD = False.

Conventions every piece follows:
  - One chess cell is 1 x 1 x 1 Blender unit. Pieces are centred on the origin and
    fit inside roughly 0.8 x 0.8 x 0.9 so they sit inside one cell.
  - Blender's Z is "up". The glTF exporter converts it to three.js's Y-up.
  - Each mesh uses two materials: "Body" (recoloured red or black by the game)
    and "Trim" (the light silver accents).
  - Most pieces are vertically symmetric on purpose: the board is tilted 45
    degrees, so pieces read the same from above and below.

The script only uses bpy, bmesh and mathutils (no file access of its own), so it
also runs through the Blender MCP server in safe mode.

Open source under the MIT License (see ../LICENSE).
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

# ===== Settings =====

REBUILD = True  # False = keep the pieces already in the file, only export them

PROJECT_FOLDER = "/Users/garyschmid/Desktop/Claude Work/Diagonal 3D Chess"
MODELS_FOLDER = PROJECT_FOLDER + "/models"
COLLECTION_NAME = "ChessPieces"

# Names here become file names (models/king.glb) and keys in models/pieces.js.
PIECE_NAMES = ["king", "queen", "bishop", "rook", "knight", "pawn_body", "pawn_cap"]

BODY = 0  # material slot index for the main colour
TRIM = 1  # material slot index for the accents

OCTAGON = 8  # every round part is an octagon, like the original models


# ===== Materials =====

def get_material(name, color):
    """Return a material with this name, creating it with a base colour if needed."""
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        material.use_nodes = True
    shader = None
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            shader = node
    if shader is not None:
        shader.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
        shader.inputs["Roughness"].default_value = 0.35
    return material


# ===== Mesh-building helpers =====
# Every helper adds faces to one shared bmesh and tags its new faces with a material.

def tag_new_faces(mesh_data, faces_before, material_index):
    """Give every face created since `faces_before` was taken the given material slot."""
    for face in mesh_data.faces:
        if face not in faces_before:
            face.material_index = material_index


def placement(center, rotation):
    """A transform matrix: move to `center`, then turn by `rotation` (or not at all)."""
    matrix = Matrix.Translation(center)
    if rotation is not None:
        matrix = matrix @ rotation
    return matrix


def add_octagon_cylinder(mesh_data, radius, height, center=(0, 0, 0),
                         top_radius=None, rotation=None, material_index=BODY):
    """An octagonal prism, or a tapered one when top_radius differs from radius."""
    if top_radius is None:
        top_radius = radius
    # A small turn so a flat face points forward, like the old models.
    matrix = placement(center, rotation) @ Matrix.Rotation(math.pi / OCTAGON, 4, "Z")
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cone(mesh_data, cap_ends=True, cap_tris=False, segments=OCTAGON,
                          radius1=radius, radius2=top_radius, depth=height, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material_index)


def add_box(mesh_data, size, center=(0, 0, 0), rotation=None, material_index=BODY):
    """A box with the given (x, y, z) size."""
    matrix = placement(center, rotation) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cube(mesh_data, size=1.0, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material_index)


def add_octagon_ball(mesh_data, radius, stretch=1.0, center=(0, 0, 0), material_index=BODY):
    """A low-poly faceted ball (8 sides around), optionally stretched tall."""
    matrix = Matrix.Translation(center) @ Matrix.Diagonal((1, 1, stretch, 1))
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_uvsphere(mesh_data, u_segments=OCTAGON, v_segments=6,
                              radius=radius, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material_index)


def add_octagon_ring(mesh_data, ring_radius, thickness, width, center=(0, 0, 0),
                     rotation=None, material_index=BODY):
    """A flat octagonal ring (a washer). `thickness` is across the band,
    `width` is along the ring's axis."""
    matrix = placement(center, rotation)
    inner = ring_radius - thickness / 2
    outer = ring_radius + thickness / 2
    faces_before = set(mesh_data.faces)

    # Four loops of 8 vertices: outer-top, outer-bottom, inner-bottom, inner-top.
    loops = []
    for radius, z in ((outer, width / 2), (outer, -width / 2),
                      (inner, -width / 2), (inner, width / 2)):
        loop = []
        for step in range(OCTAGON):
            angle = (step + 0.5) * 2 * math.pi / OCTAGON
            point = Vector((radius * math.cos(angle), radius * math.sin(angle), z))
            loop.append(mesh_data.verts.new(matrix @ point))
        loops.append(loop)
    for loop_index in range(4):
        loop_a = loops[loop_index]
        loop_b = loops[(loop_index + 1) % 4]
        for step in range(OCTAGON):
            next_step = (step + 1) % OCTAGON
            mesh_data.faces.new((loop_a[step], loop_a[next_step],
                                 loop_b[next_step], loop_b[step]))
    tag_new_faces(mesh_data, faces_before, material_index)


def add_horn(mesh_data, base_radius, length, bend_degrees, center,
             flip=False, material_index=BODY):
    """A curved, pointed horn (the knight's 'horse heads').

    Rings of vertices are placed along an arc that curls toward +X and shrink
    to a point, so the tip hooks over like the old knight model.
    `flip` turns it upside down and mirrors it, for the lower horn.
    """
    faces_before = set(mesh_data.faces)
    ring_count = 7
    sides = 4  # a squarish cross-section reads as the sharp 'beak' of the old model
    bend = math.radians(bend_degrees)
    arc_radius = length / bend
    loops = []
    for ring_index in range(ring_count):
        along = ring_index / (ring_count - 1)   # 0 at the base, 1 at the tip
        radius = base_radius * (1 - along) ** 0.8 + 0.004
        angle = bend * along
        spine = Vector((arc_radius * (1 - math.cos(angle)), 0, arc_radius * math.sin(angle)))
        loop = []
        for side in range(sides):
            side_angle = side * 2 * math.pi / sides
            offset = Vector((radius * math.cos(side_angle), radius * 1.6 * math.sin(side_angle), 0))
            offset.rotate(Matrix.Rotation(-angle, 3, "Y"))  # keep each ring square to the curve
            point = spine + offset
            if flip:
                point = Vector((-point.x, point.y, -point.z))
            loop.append(mesh_data.verts.new(Vector(center) + point))
        loops.append(loop)
    for ring_index in range(ring_count - 1):
        for side in range(sides):
            corner_a = loops[ring_index][side]
            corner_b = loops[ring_index][(side + 1) % sides]
            corner_c = loops[ring_index + 1][(side + 1) % sides]
            corner_d = loops[ring_index + 1][side]
            mesh_data.faces.new((corner_a, corner_b, corner_c, corner_d))
    mesh_data.faces.new(list(reversed(loops[0])))   # close the base
    mesh_data.faces.new(loops[-1])                   # close the tip
    tag_new_faces(mesh_data, faces_before, material_index)


def rotation_x(degrees):
    return Matrix.Rotation(math.radians(degrees), 4, "X")


def rotation_y(degrees):
    return Matrix.Rotation(math.radians(degrees), 4, "Y")


# ===== The pieces =====
# Each function fills a bmesh. Sizes are in cells (1.0 = one cube of the board).

def build_king(mesh_data):
    """Gyroscope-like: an upright octagonal ring around an octagonal core,
    cross bars, and a small diamond cube above and below."""
    add_octagon_ball(mesh_data, 0.19, stretch=1.1)
    add_octagon_ring(mesh_data, 0.33, 0.07, 0.07, rotation=rotation_x(90))
    add_box(mesh_data, (0.74, 0.06, 0.06))           # horizontal bar
    add_box(mesh_data, (0.52, 0.11, 0.11))           # stepped centre of the bar
    add_box(mesh_data, (0.06, 0.06, 0.78))           # vertical spine
    for z in (0.43, -0.43):
        add_box(mesh_data, (0.08, 0.08, 0.08), center=(0, 0, z * 0.95),
                rotation=rotation_y(45) @ rotation_x(35), material_index=TRIM)


def build_queen(mesh_data):
    """A tall faceted barrel pierced by a rod, with discs and small cubes at both ends."""
    add_octagon_ball(mesh_data, 0.2, stretch=1.45)
    for z in (0.11, -0.11):
        add_octagon_cylinder(mesh_data, 0.215, 0.035, center=(0, 0, z), material_index=TRIM)
    add_octagon_cylinder(mesh_data, 0.025, 0.72, rotation=rotation_y(90))   # through-rod
    for x in (0.36, -0.36):
        add_octagon_cylinder(mesh_data, 0.045, 0.03, center=(x, 0, 0), rotation=rotation_y(90))
    for disc_z, cube_z in ((0.33, 0.41), (-0.33, -0.41)):
        add_octagon_cylinder(mesh_data, 0.09, 0.025, center=(0, 0, disc_z))
        add_box(mesh_data, (0.1, 0.1, 0.1), center=(0, 0, cube_z), material_index=TRIM)


def build_bishop(mesh_data):
    """A bullet-shaped spire over two tilted octagonal halos, tapering to a point below."""
    add_octagon_cylinder(mesh_data, 0.1, 0.24, center=(0, 0, 0.14))
    add_octagon_cylinder(mesh_data, 0.1, 0.16, center=(0, 0, 0.34), top_radius=0.02)
    add_octagon_cylinder(mesh_data, 0.135, 0.06, material_index=TRIM)
    add_octagon_ring(mesh_data, 0.28, 0.04, 0.04, center=(0, 0, -0.02), rotation=rotation_x(14))
    add_octagon_ring(mesh_data, 0.24, 0.04, 0.04, center=(0, 0, -0.09), rotation=rotation_x(14))
    add_octagon_cylinder(mesh_data, 0.02, 0.4, center=(0, 0, -0.24), top_radius=0.1)


def build_rook(mesh_data):
    """A stacked tower: an octagonal block with side pegs, floating caps above and below."""
    add_octagon_cylinder(mesh_data, 0.17, 0.42)
    add_box(mesh_data, (0.62, 0.05, 0.05))
    for x in (0.31, -0.31):
        add_box(mesh_data, (0.05, 0.09, 0.09), center=(x, 0, 0))
    for z in (0.37, -0.37):
        add_octagon_cylinder(mesh_data, 0.2, 0.1, center=(0, 0, z))
    for z in (0.43, -0.43):
        add_octagon_cylinder(mesh_data, 0.205, 0.025, center=(0, 0, z), material_index=TRIM)


def build_knight(mesh_data):
    """Two curling horse-head horns, one up and one down, on a double octagonal nut."""
    add_octagon_cylinder(mesh_data, 0.26, 0.09, center=(0, 0, 0.05))
    add_octagon_cylinder(mesh_data, 0.24, 0.09, center=(0, 0, -0.06))
    add_octagon_ring(mesh_data, 0.13, 0.04, 0.03, center=(0, 0, 0.105), material_index=TRIM)
    add_horn(mesh_data, 0.15, 0.42, 120, center=(-0.08, 0, 0.09))
    add_horn(mesh_data, 0.15, 0.42, 120, center=(0.08, 0, -0.1), flip=True)


def build_pawn_body(mesh_data):
    """One unit-tall flat slab. The game stretches it to the length of the pawn's
    diagonal row of cells, then puts a pawn_cap on each end."""
    add_box(mesh_data, (0.3, 0.1, 1.0))
    add_box(mesh_data, (0.16, 0.13, 0.98))   # raised centre strip


def build_pawn_cap(mesh_data):
    """The crown on the end of a pawn: a notched plate with a little ring.
    Its origin is its bottom edge, so the game can stack it on the body."""
    add_box(mesh_data, (0.34, 0.12, 0.06), center=(0, 0, 0.03))
    for x, height in ((-0.12, 0.08), (0.0, 0.11), (0.12, 0.08)):
        add_box(mesh_data, (0.08, 0.12, height), center=(x, 0, 0.06 + height / 2))
    add_octagon_ring(mesh_data, 0.045, 0.025, 0.02, center=(0, 0.075, -0.07),
                     rotation=rotation_x(90), material_index=TRIM)


def build_piece_shape(name, mesh_data):
    """Fill `mesh_data` with the shape of the named piece."""
    if name == "king":
        build_king(mesh_data)
    elif name == "queen":
        build_queen(mesh_data)
    elif name == "bishop":
        build_bishop(mesh_data)
    elif name == "rook":
        build_rook(mesh_data)
    elif name == "knight":
        build_knight(mesh_data)
    elif name == "pawn_body":
        build_pawn_body(mesh_data)
    elif name == "pawn_cap":
        build_pawn_cap(mesh_data)


# ===== Scene setup =====

def get_collection():
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    return collection


def build_piece_object(name, body_material, trim_material, collection):
    """Create (or replace) one piece object."""
    old_object = bpy.data.objects.get(name)
    if old_object is not None:
        old_mesh = old_object.data
        bpy.data.objects.remove(old_object, do_unlink=True)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    mesh_data = bmesh.new()
    build_piece_shape(name, mesh_data)
    bmesh.ops.remove_doubles(mesh_data, verts=mesh_data.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(mesh_data, faces=mesh_data.faces)

    mesh = bpy.data.meshes.new(name)
    mesh_data.to_mesh(mesh)
    mesh_data.free()
    mesh.materials.append(body_material)
    mesh.materials.append(trim_material)

    piece_object = bpy.data.objects.new(name, mesh)
    collection.objects.link(piece_object)
    return piece_object


def build_all():
    body_material = get_material("Body", (0.8, 0.05, 0.03))
    trim_material = get_material("Trim", (0.85, 0.87, 0.9))
    collection = get_collection()
    for index, name in enumerate(PIECE_NAMES):
        piece_object = build_piece_object(name, body_material, trim_material, collection)
        # Side by side for editing, in a row away from the world origin.
        piece_object.location = (index * 1.2, -3, 0)


# ===== Export =====

def export_piece(piece_object, file_path):
    """Export one object as a .glb, centred on the origin (its layout offset removed)."""
    saved_location = piece_object.location.copy()
    piece_object.location = (0, 0, 0)
    bpy.ops.object.select_all(action="DESELECT")
    piece_object.select_set(True)
    bpy.context.view_layer.objects.active = piece_object
    bpy.ops.export_scene.gltf(
        filepath=file_path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
    )
    piece_object.location = saved_location


def export_all():
    """Write models/<piece>.glb for every piece."""
    collection = get_collection()
    for name in PIECE_NAMES:
        piece_object = collection.objects.get(name)
        if piece_object is None:
            print("Missing piece object:", name)
        else:
            export_piece(piece_object, MODELS_FOLDER + "/" + name + ".glb")
            print("Exported", name)
    print("Now run: python3 tools/bundle_models.py")


# ===== Run =====

if REBUILD:
    build_all()
export_all()

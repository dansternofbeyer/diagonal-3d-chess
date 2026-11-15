"""
build_classic_pieces.py — classic-style versions of the Diagonal 3D Chess pieces.

The 2026 pieces mix classic Staunton chess pieces and architectural moldings
(torus, scotia, fillet, collar, baluster stem) with the faceted look of the
2006 originals. Each piece is like two classic pieces joined at their bases:
a wide molded plinth in the middle and the piece's head at BOTH ends, so it
reads the same from above and below on the tilted board. The knight works
like a playing card: one horse head up, one down, facing opposite ways.

Every piece is built in three styles from the same design:
  faceted  8 sides, curves cut into a few flat facets (closest to 2006)
  deco     16 sides, curves turned into sharp chevrons, fluted stems
  classic  32 smooth sides, fully curved moldings

How it works: each piece's outline (from the middle up to the tip) is a list of
points made with molding helpers below. The outline is mirrored to make the
bottom half and spun around the vertical axis (a lathe). Extra parts that are
not round (crosses, crown points, battlements, horse heads) are added on top.

Exports models/<piece>-<style>.glb, e.g. models/king-deco.glb. The original
2006-style pieces (blender/build_pieces.py, models/king.glb ...) are untouched.
Afterwards run, from the project folder:
    python3 tools/bundle_models.py

Same conventions as build_pieces.py: one cell = 1 Blender unit, Z up, materials
"Body" (slot 0, recoloured per side) and "Trim" (slot 1, a lighter shade).
Safe-mode friendly: only bpy, bmesh, mathutils; no file access, no callbacks.

Open source under the MIT License (see ../LICENSE).
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

# ===== Settings =====

PROJECT_FOLDER = "/Users/garyschmid/Desktop/Claude Work/Diagonal 3D Chess"
MODELS_FOLDER = PROJECT_FOLDER + "/models"
COLLECTION_NAME = "ClassicChessPieces"

PIECES = ["king", "queen", "bishop", "rook", "knight", "pawn_body", "pawn_cap"]
STYLES = ["faceted", "deco", "classic"]

BODY = 0
TRIM = 1

# The pieces are designed a little large, then shrunk to sit inside one cell
# with room between the tips of pieces stacked on the tilted board.
PIECE_SCALE = 0.86


# ===== Styles =====

def style_sides(style):
    """How many sides every round part has."""
    if style == "faceted":
        return 8
    if style == "deco":
        return 16
    return 32


def style_flute_depth(style):
    """Deco stems are fluted: every other vertex pulled in by this fraction."""
    if style == "deco":
        return 0.13
    return 0.0


def style_is_smooth(style):
    return style == "classic"


# ===== Outline (profile) helpers =====
# A profile is a list of points [radius, height, material, fluted], starting
# in the middle of the piece and climbing to its tip. Each helper adds points
# from wherever the profile currently ends.

def start_profile(radius, height=0.0):
    return [[radius, height, BODY, False]]


def line_to(profile, radius, height, material=BODY, fluted=False):
    profile.append([radius, height, material, fluted])


def curve_to(profile, style, radius, height, bulge, material=BODY, fluted=False):
    """A curved step to (radius, height). `bulge` pushes the middle of the curve
    outward (+, like a torus) or inward (-, like a scotia), in cells.

    faceted: a few flat facets. deco: one sharp chevron. classic: a smooth curve.
    """
    start_radius, start_height = profile[-1][0], profile[-1][1]
    middle_radius = (start_radius + radius) / 2 + bulge
    middle_height = (start_height + height) / 2
    if style == "deco":
        # A chevron through the curve's halfway point.
        profile.append([(start_radius + radius) / 2 + bulge * 0.5, middle_height, material, fluted])
        profile.append([radius, height, material, fluted])
        return
    samples = 3 if style == "faceted" else 8
    for sample in range(1, samples + 1):
        t = sample / samples
        # Quadratic Bezier with the bulged middle as its control point.
        along_radius = (1 - t) ** 2 * start_radius + 2 * (1 - t) * t * middle_radius + t ** 2 * radius
        along_height = (1 - t) ** 2 * start_height + 2 * (1 - t) * t * middle_height + t ** 2 * height
        profile.append([along_radius, along_height, material, fluted])


def current(profile):
    return profile[-1][0], profile[-1][1]


def fillet(profile, height, material=BODY):
    """A short straight band (a fillet in molding terms)."""
    radius, at = current(profile)
    line_to(profile, radius, at + height, material)


def ledge(profile, radius, material=BODY):
    """A flat step in or out to a new radius."""
    _, at = current(profile)
    line_to(profile, radius, at, material)


def torus(profile, style, height, bulge, material=BODY):
    """A rounded convex band (torus molding)."""
    radius, at = current(profile)
    curve_to(profile, style, radius, at + height, bulge, material)


def scotia(profile, style, height, depth, material=BODY):
    """A concave cove (scotia molding)."""
    radius, at = current(profile)
    curve_to(profile, style, radius, at + height, -depth, material)


def plinth(profile, style, radius):
    """The molded base in the middle of every piece, from height 0 up:
    a band, a big torus, a scotia, a trim fillet and a small torus."""
    fillet(profile, 0.025)
    torus(profile, style, 0.05, 0.025)
    ledge(profile, radius - 0.04)
    scotia(profile, style, 0.035, 0.02)
    ledge(profile, radius - 0.03)
    fillet(profile, 0.014, TRIM)
    ledge(profile, radius - 0.06)
    torus(profile, style, 0.028, 0.012)


def collar(profile, style, radius):
    """The ring below a piece's head: trim fillet, bead, fillet."""
    ledge(profile, radius)
    fillet(profile, 0.015, TRIM)
    ledge(profile, radius - 0.015)
    torus(profile, style, 0.024, 0.01)
    ledge(profile, radius - 0.03)
    fillet(profile, 0.01)


# ===== Mesh helpers =====

def tag_new_faces(mesh_data, faces_before, material_index):
    for face in mesh_data.faces:
        if face not in faces_before:
            face.material_index = material_index


def mirrored_profile(profile):
    """Bottom-to-top list of (radius, height, material, fluted, depth) for the
    whole piece: the profile mirrored below the middle, then the profile itself.
    `depth` is how far a point is from the middle, used to pick segment materials."""
    points = []
    for depth in range(len(profile) - 1, 0, -1):
        radius, height, material, fluted = profile[depth]
        points.append((radius, -height, material, fluted, depth))
    for depth in range(len(profile)):
        radius, height, material, fluted = profile[depth]
        points.append((radius, height, material, fluted, depth))
    return points


def single_profile(profile):
    """Like mirrored_profile, for one-ended parts (the pawn cap)."""
    return [(p[0], p[1], p[2], p[3], depth) for depth, p in enumerate(profile)]


def revolve(mesh_data, points, style):
    """Spin a bottom-to-top list of outline points around the Z axis.
    A point on the axis (radius 0) becomes a single tip vertex."""
    sides = style_sides(style)
    flute = style_flute_depth(style)
    rings = []
    for radius, height, material, fluted, depth in points:
        if radius < 1e-6:
            rings.append([mesh_data.verts.new((0.0, 0.0, height))])
            continue
        ring = []
        for side in range(sides):
            angle = (side + 0.5) * 2 * math.pi / sides
            side_radius = radius
            if fluted and flute > 0 and side % 2 == 1:
                side_radius = radius * (1 - flute)
            ring.append(mesh_data.verts.new((side_radius * math.cos(angle),
                                             side_radius * math.sin(angle), height)))
        rings.append(ring)

    for index in range(len(points) - 1):
        lower, upper = rings[index], rings[index + 1]
        # A segment takes the material of its outer end (further from the middle).
        if points[index][4] > points[index + 1][4]:
            material = points[index][2]
        else:
            material = points[index + 1][2]
        new_faces = []
        if len(lower) == 1 and len(upper) == 1:
            continue
        if len(lower) == 1:
            for side in range(sides):
                new_faces.append(mesh_data.faces.new((lower[0], upper[side], upper[(side + 1) % sides])))
        elif len(upper) == 1:
            for side in range(sides):
                new_faces.append(mesh_data.faces.new((lower[side], upper[0], lower[(side + 1) % sides])))
        else:
            for side in range(sides):
                next_side = (side + 1) % sides
                new_faces.append(mesh_data.faces.new((lower[side], lower[next_side],
                                                      upper[next_side], upper[side])))
        for face in new_faces:
            face.material_index = material

    # Close open ends (only happens if an outline does not end on the axis).
    if len(rings[0]) > 1:
        face = mesh_data.faces.new(list(reversed(rings[0])))
        face.material_index = points[0][2]
    if len(rings[-1]) > 1:
        face = mesh_data.faces.new(rings[-1])
        face.material_index = points[-1][2]


def add_ball(mesh_data, style, radius, center, material=TRIM):
    sides = style_sides(style)
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_uvsphere(mesh_data, u_segments=max(8, sides // 2 if style == "classic" else sides),
                              v_segments=6 if style == "faceted" else 10,
                              radius=radius, matrix=Matrix.Translation(center))
    tag_new_faces(mesh_data, faces_before, material)


def add_box(mesh_data, size, center, rotation=None, material=BODY):
    matrix = Matrix.Translation(center)
    if rotation is not None:
        matrix = matrix @ rotation
    matrix = matrix @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cube(mesh_data, size=1.0, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material)


def add_cone(mesh_data, style, radius, height, center, flip, material=TRIM):
    """A small pointed cone (a crown point). `flip` points it down."""
    matrix = Matrix.Translation(center)
    if flip:
        matrix = matrix @ Matrix.Rotation(math.pi, 4, "X")
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cone(mesh_data, cap_ends=True, cap_tris=False,
                          segments=6 if style == "faceted" else 10,
                          radius1=radius, radius2=0.0, depth=height,
                          matrix=matrix @ Matrix.Translation((0, 0, height / 2)))
    tag_new_faces(mesh_data, faces_before, material)


def add_disc(mesh_data, style, radius, thickness, center, tilt_degrees, material=TRIM):
    """A thin tilted disc (the bishop's mitre band)."""
    matrix = Matrix.Translation(center) @ Matrix.Rotation(math.radians(tilt_degrees), 4, "X")
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cone(mesh_data, cap_ends=True, cap_tris=False, segments=style_sides(style),
                          radius1=radius, radius2=radius, depth=thickness, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material)


def smooth_polygon(points, rounds):
    """Chaikin corner cutting: rounds the corners of a closed outline."""
    for _ in range(rounds):
        rounded = []
        for index in range(len(points)):
            first = points[index]
            second = points[(index + 1) % len(points)]
            rounded.append((first[0] * 0.75 + second[0] * 0.25, first[1] * 0.75 + second[1] * 0.25))
            rounded.append((first[0] * 0.25 + second[0] * 0.75, first[1] * 0.25 + second[1] * 0.75))
        points = rounded
    return points


def add_extruded_outline(mesh_data, outline, thickness, chamfer, flip, material=BODY):
    """Turn a flat (x, z) outline into a solid slab `thickness` deep along Y,
    with chamfered edges. `flip` turns it 180 degrees about Y (playing-card style)."""
    center_x = sum(point[0] for point in outline) / len(outline)
    center_z = sum(point[1] for point in outline) / len(outline)
    half = thickness / 2
    layers = []
    for y, shrink in ((-half, chamfer), (-half * 0.55, 0.0), (half * 0.55, 0.0), (half, chamfer)):
        layer = []
        for x, z in outline:
            px = x + (center_x - x) * shrink
            pz = z + (center_z - z) * shrink
            if flip:
                px, pz = -px, -pz
            layer.append(mesh_data.verts.new((px, y, pz)))
        layers.append(layer)
    faces_before = set(mesh_data.faces)
    count = len(outline)
    for layer_index in range(3):
        near, far = layers[layer_index], layers[layer_index + 1]
        for index in range(count):
            following = (index + 1) % count
            mesh_data.faces.new((near[index], near[following], far[following], far[index]))
    mesh_data.faces.new(list(reversed(layers[0])))
    mesh_data.faces.new(layers[3])
    tag_new_faces(mesh_data, faces_before, material)


# ===== The pieces =====
# Profiles climb from the middle (height 0) to the tip. Sizes in cells, before PIECE_SCALE.

def build_king(mesh_data, style):
    profile = start_profile(0.28)
    plinth(profile, style, 0.28)
    ledge(profile, 0.16)
    curve_to(profile, style, 0.085, 0.33, -0.03, fluted=True)   # the tall baluster stem
    collar(profile, style, 0.135)
    ledge(profile, 0.085)
    curve_to(profile, style, 0.15, 0.46, -0.025)                 # the crown flares out
    fillet(profile, 0.012, TRIM)
    curve_to(profile, style, 0.05, 0.5, 0.025)                   # domed top
    line_to(profile, 0.0, 0.5)
    revolve(mesh_data, mirrored_profile(profile), style)
    for sign in (1, -1):
        add_ball(mesh_data, style, 0.034, (0, 0, sign * 0.53))
        # The cross: an upright bar and a crossbar; deco adds a stepped back plate.
        add_box(mesh_data, (0.03, 0.03, 0.11), (0, 0, sign * 0.61), material=TRIM)
        add_box(mesh_data, (0.09, 0.03, 0.03), (0, 0, sign * 0.625), material=TRIM)
        if style == "deco":
            add_box(mesh_data, (0.05, 0.045, 0.05), (0, 0, sign * 0.625), material=TRIM)
        if style == "classic":
            for end_x in (-0.045, 0.045):
                add_ball(mesh_data, style, 0.018, (end_x, 0, sign * 0.625))
            add_ball(mesh_data, style, 0.018, (0, 0, sign * 0.665))


def build_queen(mesh_data, style):
    profile = start_profile(0.275)
    plinth(profile, style, 0.275)
    ledge(profile, 0.155)
    curve_to(profile, style, 0.08, 0.32, -0.03, fluted=True)
    collar(profile, style, 0.13)
    ledge(profile, 0.08)
    curve_to(profile, style, 0.16, 0.45, -0.03)                  # the coronet cup
    fillet(profile, 0.012, TRIM)
    ledge(profile, 0.125)
    curve_to(profile, style, 0.05, 0.48, 0.02)
    line_to(profile, 0.0, 0.48)
    revolve(mesh_data, mirrored_profile(profile), style)
    point_count = 8 if style != "classic" else 10
    for sign in (1, -1):
        for point_index in range(point_count):
            angle = (point_index + 0.5) * 2 * math.pi / point_count
            center = (0.145 * math.cos(angle), 0.145 * math.sin(angle), sign * 0.462)
            add_cone(mesh_data, style, 0.022, 0.05, center, flip=sign < 0)
        add_ball(mesh_data, style, 0.045, (0, 0, sign * 0.52))


def build_bishop(mesh_data, style):
    profile = start_profile(0.255)
    plinth(profile, style, 0.255)
    ledge(profile, 0.145)
    curve_to(profile, style, 0.075, 0.29, -0.028, fluted=True)
    collar(profile, style, 0.12)
    ledge(profile, 0.07)
    curve_to(profile, style, 0.115, 0.41, 0.02)                  # the mitre swells
    curve_to(profile, style, 0.0, 0.53, 0.06)                    # and comes to a point
    revolve(mesh_data, mirrored_profile(profile), style)
    for sign in (1, -1):
        # The mitre's slit, as a tilted trim band.
        add_disc(mesh_data, style, 0.118, 0.014, (0, 0, sign * 0.44), sign * 32)
        add_ball(mesh_data, style, 0.026, (0, 0, sign * 0.55))


def build_rook(mesh_data, style):
    profile = start_profile(0.27)
    plinth(profile, style, 0.27)
    ledge(profile, 0.2)
    curve_to(profile, style, 0.155, 0.35, -0.012, fluted=True)   # the tower walls
    ledge(profile, 0.19)
    fillet(profile, 0.018, TRIM)
    ledge(profile, 0.18)
    fillet(profile, 0.07)                                        # the turret
    ledge(profile, 0.13)                                         # top rim, then the hollow
    line_to(profile, 0.13, 0.405)
    line_to(profile, 0.0, 0.405)
    revolve(mesh_data, mirrored_profile(profile), style)
    merlon_count = 6
    for sign in (1, -1):
        for merlon in range(merlon_count):
            angle = merlon * 2 * math.pi / merlon_count
            rotation = Matrix.Rotation(angle, 4, "Z")
            center = (0.155 * math.cos(angle), 0.155 * math.sin(angle), sign * 0.462)
            add_box(mesh_data, (0.05, 0.07, 0.045), center, rotation=rotation, material=TRIM)


# The knight's horse head, facing +X, standing on the plinth (x, z in cells).
HORSE_OUTLINE = [
    (-0.13, 0.2), (-0.15, 0.28), (-0.15, 0.36), (-0.12, 0.44), (-0.07, 0.5),
    (-0.05, 0.565), (-0.02, 0.52), (0.05, 0.5), (0.12, 0.45), (0.19, 0.39),
    (0.215, 0.355), (0.205, 0.328), (0.16, 0.318), (0.15, 0.3), (0.09, 0.3),
    (0.04, 0.27), (0.06, 0.23), (0.1, 0.2),
]

# Deco: the mane is cut into steps, like the carved manes of classic knights.
DECO_HORSE_OUTLINE = [
    (-0.13, 0.2), (-0.15, 0.25), (-0.17, 0.25), (-0.15, 0.31), (-0.17, 0.31),
    (-0.15, 0.37), (-0.16, 0.38), (-0.12, 0.44), (-0.13, 0.45), (-0.07, 0.5),
    (-0.05, 0.565), (-0.02, 0.52), (0.05, 0.5), (0.19, 0.39), (0.215, 0.355),
    (0.215, 0.325), (0.15, 0.318), (0.15, 0.3), (0.09, 0.3), (0.04, 0.27),
    (0.06, 0.23), (0.1, 0.2),
]


def build_knight(mesh_data, style):
    profile = start_profile(0.26)
    plinth(profile, style, 0.26)
    ledge(profile, 0.17)
    curve_to(profile, style, 0.15, 0.2, -0.01)
    fillet(profile, 0.014, TRIM)
    line_to(profile, 0.0, 0.214)
    revolve(mesh_data, mirrored_profile(profile), style)

    if style == "deco":
        outline = DECO_HORSE_OUTLINE
    elif style == "classic":
        outline = smooth_polygon(HORSE_OUTLINE, 2)
    else:
        outline = HORSE_OUTLINE
    for flip in (False, True):
        add_extruded_outline(mesh_data, outline, 0.15, 0.08, flip)
        for side_y in (-0.074, 0.074):
            eye = (0.07, side_y, 0.44)
            if flip:
                eye = (-0.07, side_y, -0.44)
            add_ball(mesh_data, style, 0.017, eye)


def build_pawn_body(mesh_data, style):
    """One unit tall; the game stretches it along the pawn's row. A fluted column shaft."""
    profile = [[0.0, -0.5, BODY, False], [0.11, -0.5, BODY, True],
               [0.11, 0.5, BODY, True], [0.0, 0.5, BODY, False]]
    points = single_profile(profile)
    if style != "deco":
        points = [(p[0], p[1], p[2], False, p[4]) for p in points]
    revolve(mesh_data, points, style)
    if style == "classic":
        # Classical columns have flutes: add them as fine raised reeds.
        for reed in range(12):
            angle = reed * 2 * math.pi / 12
            add_box(mesh_data, (0.018, 0.018, 0.98), (0.108 * math.cos(angle), 0.108 * math.sin(angle), 0),
                    rotation=Matrix.Rotation(angle, 4, "Z"))


def build_pawn_cap(mesh_data, style):
    """The classic pawn head on each end of the column. Origin at its bottom."""
    profile = start_profile(0.0)
    ledge(profile, 0.16)
    torus(profile, style, 0.035, 0.015)
    ledge(profile, 0.13)
    scotia(profile, style, 0.02, 0.012)
    ledge(profile, 0.1)
    curve_to(profile, style, 0.06, 0.1, -0.015)                  # neck
    collar(profile, style, 0.13)
    ledge(profile, 0.06)
    curve_to(profile, style, 0.08, 0.17, 0.03, TRIM)             # the ball head
    curve_to(profile, style, 0.0, 0.245, 0.045, TRIM)
    revolve(mesh_data, single_profile(profile), style)


def build_piece_shape(name, style, mesh_data):
    if name == "king":
        build_king(mesh_data, style)
    elif name == "queen":
        build_queen(mesh_data, style)
    elif name == "bishop":
        build_bishop(mesh_data, style)
    elif name == "rook":
        build_rook(mesh_data, style)
    elif name == "knight":
        build_knight(mesh_data, style)
    elif name == "pawn_body":
        build_pawn_body(mesh_data, style)
    elif name == "pawn_cap":
        build_pawn_cap(mesh_data, style)


# ===== Scene setup =====

def get_material(name, color):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        for node in material.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                node.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    return material


def get_collection():
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    return collection


def finish_shading(mesh_data, style):
    """Classic pieces are smooth-shaded with crisp edges kept sharp; the others stay faceted."""
    smooth = style_is_smooth(style)
    for face in mesh_data.faces:
        face.smooth = smooth
    if smooth:
        for edge in mesh_data.edges:
            if len(edge.link_faces) == 2:
                angle = edge.link_faces[0].normal.angle(edge.link_faces[1].normal, 0.0)
                edge.smooth = angle < math.radians(38)


def build_piece_object(name, style, body_material, trim_material, collection):
    object_name = name + "-" + style
    old_object = bpy.data.objects.get(object_name)
    if old_object is not None:
        old_mesh = old_object.data
        bpy.data.objects.remove(old_object, do_unlink=True)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    mesh_data = bmesh.new()
    build_piece_shape(name, style, mesh_data)
    bmesh.ops.remove_doubles(mesh_data, verts=mesh_data.verts, dist=0.0001)
    # The pawn body must stay exactly 1 tall: the game stretches it to the row's length.
    height_scale = 1.0 if name == "pawn_body" else PIECE_SCALE
    bmesh.ops.scale(mesh_data, vec=(PIECE_SCALE, PIECE_SCALE, height_scale), verts=mesh_data.verts)
    bmesh.ops.recalc_face_normals(mesh_data, faces=mesh_data.faces)
    finish_shading(mesh_data, style)

    mesh = bpy.data.meshes.new(object_name)
    mesh_data.to_mesh(mesh)
    mesh_data.free()
    mesh.materials.append(body_material)
    mesh.materials.append(trim_material)

    piece_object = bpy.data.objects.new(object_name, mesh)
    collection.objects.link(piece_object)
    return piece_object


def build_all():
    body_material = get_material("Body", (0.8, 0.05, 0.03))
    trim_material = get_material("Trim", (0.85, 0.87, 0.9))
    collection = get_collection()
    for style_index, style in enumerate(STYLES):
        for piece_index, name in enumerate(PIECES):
            piece_object = build_piece_object(name, style, body_material, trim_material, collection)
            # A grid away from everything else: one row per style.
            piece_object.location = (piece_index * 1.0, -6 - style_index * 1.6, 0)


# ===== Export =====

def export_piece(piece_object, file_path):
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
    collection = get_collection()
    for style in STYLES:
        for name in PIECES:
            piece_object = collection.objects.get(name + "-" + style)
            if piece_object is not None:
                export_piece(piece_object, MODELS_FOLDER + "/" + name + "-" + style + ".glb")
    print("Exported", len(STYLES) * len(PIECES), "pieces. Now run: python3 tools/bundle_models.py")


# ===== Run =====

build_all()
export_all()

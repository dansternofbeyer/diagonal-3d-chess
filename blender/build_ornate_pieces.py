"""
build_ornate_pieces.py — the "ornate" version of the Diagonal 3D Chess pieces.

The original 2006-style pieces (blender/build_pieces.py) exactly as they are,
dressed with architectural "greebles" taken from wood moldings and mantels
(from reference photos of moldings, kept locally and not published):
  - molded bands with real profiles: ogee, cove, quarter-round, bead, stepped crown
  - dentil courses: rows of small rectangular teeth
  - fluting: raised reeds on the faces of the octagonal blocks, like a pilaster
  - cornice caps and plinths on the little cubes

Every original part is rebuilt first (same sizes and places), then the details
are added around it, so the silhouette stays the one you know.

Exports models/<piece>-ornate.glb. The knight swaps the original horns for a raven. Afterwards, from the project folder:
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
COLLECTION_NAME = "OrnateChessPieces"
VERSION = "ornate"

PIECES = ["king", "queen", "bishop", "rook", "knight", "pawn_body", "pawn_cap"]

BODY = 0
TRIM = 1
OCTAGON = 8


# ===== Basic shapes (the same as build_pieces.py) =====

def tag_new_faces(mesh_data, faces_before, material_index):
    for face in mesh_data.faces:
        if face not in faces_before:
            face.material_index = material_index


def placement(center, rotation):
    matrix = Matrix.Translation(center)
    if rotation is not None:
        matrix = matrix @ rotation
    return matrix


def rotation_x(degrees):
    return Matrix.Rotation(math.radians(degrees), 4, "X")


def rotation_y(degrees):
    return Matrix.Rotation(math.radians(degrees), 4, "Y")


def add_octagon_cylinder(mesh_data, radius, height, center=(0, 0, 0),
                         top_radius=None, rotation=None, material_index=BODY):
    if top_radius is None:
        top_radius = radius
    matrix = placement(center, rotation) @ Matrix.Rotation(math.pi / OCTAGON, 4, "Z")
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cone(mesh_data, cap_ends=True, cap_tris=False, segments=OCTAGON,
                          radius1=radius, radius2=top_radius, depth=height, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material_index)


def add_box(mesh_data, size, center=(0, 0, 0), rotation=None, material_index=BODY):
    matrix = placement(center, rotation) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cube(mesh_data, size=1.0, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material_index)


def add_octagon_ball(mesh_data, radius, stretch=1.0, center=(0, 0, 0), material_index=BODY):
    matrix = Matrix.Translation(center) @ Matrix.Diagonal((1, 1, stretch, 1))
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_uvsphere(mesh_data, u_segments=OCTAGON, v_segments=6,
                              radius=radius, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material_index)


def add_octagon_ring(mesh_data, ring_radius, thickness, width, center=(0, 0, 0),
                     rotation=None, material_index=BODY):
    matrix = placement(center, rotation)
    inner = ring_radius - thickness / 2
    outer = ring_radius + thickness / 2
    faces_before = set(mesh_data.faces)
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


# ===== Molding greebles =====

def molding_outline(shape):
    """The cross-section of a molded band as a closed outline of (u, v) points:
    u runs from the band's inner radius (0) to its outer radius (1), v from its
    bottom (0) to its top (1). The outer side carries the profile."""
    outline = [(0.0, 0.0), (1.0, 0.0)]
    if shape == "ogee":
        # A fillet, then an S-curve stepping in: concave below, convex above.
        outline.append((1.0, 0.12))
        for sample in range(1, 6):
            t = sample / 5
            outline.append((1.0 - 0.6 * (3 * t * t - 2 * t * t * t), 0.12 + 0.88 * t))
    elif shape == "cove":
        # A fillet, then a concave quarter circle.
        outline.append((1.0, 0.15))
        for sample in range(0, 5):
            angle = (sample / 4) * math.pi / 2
            outline.append((1.0 - 0.6 * math.sin(angle), 1.0 - 0.6 * math.cos(angle) * 0.85 - 0.0))
    elif shape == "quarter":
        # A convex quarter-round.
        for sample in range(1, 5):
            angle = (sample / 4) * math.pi / 2
            outline.append((0.4 + 0.6 * math.cos(angle), 0.75 * math.sin(angle)))
        outline.append((0.4, 1.0))
    elif shape == "bead":
        # A half-round bead.
        outline[1] = (0.4, 0.0)
        for sample in range(1, 6):
            angle = (sample / 6) * math.pi
            outline.append((0.4 + 0.6 * math.sin(angle), 0.5 - 0.5 * math.cos(angle)))
        outline.append((0.4, 1.0))
    else:  # "step": a stepped crown
        outline += [(1.0, 0.25), (0.75, 0.25), (0.75, 0.55), (0.5, 0.55), (0.5, 0.8), (0.3, 0.8), (0.3, 1.0)]
    outline.append((0.0, 1.0))
    return outline


def add_molded_band(mesh_data, shape, inner_radius, outer_radius, height,
                    center=(0, 0, 0), rotation=None, flip=False, material_index=BODY):
    """An octagonal ring whose cross-section is a molding profile.
    `flip` turns the profile upside down (wide end on top)."""
    matrix = placement(center, rotation)
    if flip:
        matrix = matrix @ rotation_x(180)
    faces_before = set(mesh_data.faces)
    loops = []
    for u, v in molding_outline(shape):
        radius = inner_radius + (outer_radius - inner_radius) * u
        z = (v - 0.5) * height
        loop = []
        for step in range(OCTAGON):
            angle = (step + 0.5) * 2 * math.pi / OCTAGON
            loop.append(mesh_data.verts.new(matrix @ Vector((radius * math.cos(angle),
                                                             radius * math.sin(angle), z))))
        loops.append(loop)
    for index in range(len(loops)):
        loop_a = loops[index]
        loop_b = loops[(index + 1) % len(loops)]
        for step in range(OCTAGON):
            next_step = (step + 1) % OCTAGON
            mesh_data.faces.new((loop_a[step], loop_a[next_step], loop_b[next_step], loop_b[step]))
    tag_new_faces(mesh_data, faces_before, material_index)


def add_dentil_ring(mesh_data, radius, count, tooth, center=(0, 0, 0), rotation=None,
                    material_index=TRIM):
    """A dentil course: `count` small blocks around a circle of `radius`.
    tooth = (depth outward, width along the ring, height)."""
    base = placement(center, rotation)
    for index in range(count):
        angle = (index + 0.5) * 2 * math.pi / count
        matrix = (base @ Matrix.Rotation(angle, 4, "Z") @ Matrix.Translation((radius, 0, 0))
                  @ Matrix.Diagonal((tooth[0], tooth[1], tooth[2], 1.0)))
        faces_before = set(mesh_data.faces)
        bmesh.ops.create_cube(mesh_data, size=1.0, matrix=matrix)
        tag_new_faces(mesh_data, faces_before, material_index)


def add_reeds(mesh_data, radius, height, per_face, reed, center=(0, 0, 0), material_index=BODY):
    """Fluting on an octagonal prism: thin raised reeds running up each of its
    eight faces, like a fluted pilaster."""
    apothem = radius * math.cos(math.pi / OCTAGON)
    face_width = 2 * radius * math.sin(math.pi / OCTAGON)
    for face in range(OCTAGON):
        angle = face * 2 * math.pi / OCTAGON
        for index in range(per_face):
            offset = (index - (per_face - 1) / 2) * face_width / (per_face + 0.6)
            matrix = (Matrix.Translation(center) @ Matrix.Rotation(angle, 4, "Z")
                      @ Matrix.Translation((apothem + reed * 0.3, offset, 0))
                      @ Matrix.Diagonal((reed, reed, height, 1.0)))
            faces_before = set(mesh_data.faces)
            bmesh.ops.create_cube(mesh_data, size=1.0, matrix=matrix)
            tag_new_faces(mesh_data, faces_before, material_index)


# ===== The raven (the ornate knight's head) =====
# Modelled from a photo of a raven in profile: a domed head on a thick,
# feathered neck, a heavy beak as long as the head that hooks down at the tip,
# a bead eye, and shaggy hackle feathers hanging under the throat. It is lofted
# from cross-sections like the classic knight's horse, but kept to 8 sides with
# flat facets to match the ornate set. The head faces +X; the game turns the
# knight to face the opponent. The lower raven is a mirror image (z -> -z), so
# both heads face the same way.

# (x, z) of the spine, half width over the top, half width underneath, depth
# above the spine (crown / nape) and below it (throat / lower beak).
RAVEN_SECTIONS = [
    (-0.010, 0.090, 0.100, 0.100, 0.100, 0.100),   # 0 neck base, inside the nut's collar
    (-0.020, 0.150, 0.100, 0.104, 0.100, 0.104),   # 1 breast: a short, thick neck
    (-0.015, 0.210, 0.100, 0.104, 0.100, 0.110),   # 2 throat feathers puff out
    (0.010, 0.270, 0.100, 0.098, 0.100, 0.098),    # 3 back of the big, round head
    (0.050, 0.310, 0.095, 0.085, 0.090, 0.075),    # 4 domed crown, eye
    (0.095, 0.325, 0.075, 0.062, 0.070, 0.050),    # 5 forehead
    (0.135, 0.322, 0.052, 0.044, 0.050, 0.036),    # 6 beak base (from here on: beak)
    (0.185, 0.312, 0.040, 0.034, 0.038, 0.028),    # 7 heavy beak
    (0.235, 0.296, 0.029, 0.024, 0.027, 0.020),    # 8
    (0.280, 0.272, 0.018, 0.015, 0.018, 0.012),    # 9 curving down
    (0.310, 0.245, 0.008, 0.007, 0.009, 0.006),    # 10 the hook
]
RAVEN_SIDES = 8
RAVEN_BEAK_FROM = 6   # sections from here on are beak (trim colour)


def raven_frames():
    """Spine point, forward direction and 'up' direction for each section."""
    frames = []
    count = len(RAVEN_SECTIONS)
    for index in range(count):
        before = RAVEN_SECTIONS[max(0, index - 1)]
        after = RAVEN_SECTIONS[min(count - 1, index + 1)]
        forward = Vector((after[0] - before[0], 0, after[1] - before[1])).normalized()
        up = forward.cross(Vector((0, 1, 0))).normalized()
        section = RAVEN_SECTIONS[index]
        frames.append((Vector((section[0], 0, section[1])), forward, up))
    return frames


def raven_half_width(section, height):
    """Half width at a height (-1 underneath .. 1 on top), blended smoothly."""
    blend = (height + 1) / 2
    blend = blend * blend * (3 - 2 * blend)
    return section[3] + (section[2] - section[3]) * blend


def raven_point(frames, along, side, height):
    """A point on the raven's surface: `along` is a section number (fractions
    allowed), `side` -1..1 across, `height` -1 (throat) .. 1 (crown)."""
    lower = min(int(along), len(RAVEN_SECTIONS) - 2)
    mix = along - lower
    spine = frames[lower][0].lerp(frames[lower + 1][0], mix)
    forward = frames[lower][1].lerp(frames[lower + 1][1], mix).normalized()
    up = frames[lower][2].lerp(frames[lower + 1][2], mix).normalized()
    section = [near + (far - near) * mix for near, far in zip(RAVEN_SECTIONS[lower], RAVEN_SECTIONS[lower + 1])]
    depth = section[4] if height > 0 else section[5]
    return spine + Vector((0, 1, 0)) * (raven_half_width(section, height) * side) + up * (depth * height), forward, up


def along_frame(forward, up):
    """A rotation whose X axis follows `forward`, Z follows `up`."""
    across = up.cross(forward).normalized()
    return Matrix((
        (forward.x, across.x, up.x, 0),
        (forward.y, across.y, up.y, 0),
        (forward.z, across.z, up.z, 0),
        (0, 0, 0, 1),
    ))


def add_feather(mesh_data, matrix, radius, length, material=BODY):
    """One pointed feather: a 4-sided cone along the matrix's Z axis."""
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cone(mesh_data, cap_ends=True, cap_tris=False, segments=4,
                          radius1=radius, radius2=0.0015, depth=length,
                          matrix=matrix @ Matrix.Translation((0, 0, length / 2)))
    tag_new_faces(mesh_data, faces_before, material)


def add_raven_head(mesh_data, mirror):
    flip = Matrix.Diagonal((1, 1, -1, 1)) if mirror else Matrix.Identity(4)
    frames = raven_frames()

    # The head, neck and beak, lofted from the sections.
    rings = []
    for (spine, forward, up), section in zip(frames, RAVEN_SECTIONS):
        ring = []
        for step in range(RAVEN_SIDES):
            angle = (step + 0.5) * 2 * math.pi / RAVEN_SIDES
            across = math.sin(angle)
            upward = math.cos(angle)
            depth = section[4] if upward > 0 else section[5]
            point = spine + Vector((0, raven_half_width(section, upward) * across, 0)) + up * (depth * upward)
            ring.append(mesh_data.verts.new(flip @ point))
        rings.append(ring)
    for index in range(len(rings) - 1):
        material = TRIM if index >= RAVEN_BEAK_FROM else BODY
        for step in range(RAVEN_SIDES):
            following = (step + 1) % RAVEN_SIDES
            face = mesh_data.faces.new((rings[index][step], rings[index][following],
                                        rings[index + 1][following], rings[index + 1][step]))
            face.material_index = material
    mesh_data.faces.new(list(reversed(rings[0]))).material_index = BODY
    tip_spine, tip_forward, tip_up = frames[-1]
    tip = mesh_data.verts.new(flip @ (tip_spine + tip_forward * 0.014 - tip_up * 0.012))   # hooked tip
    for step in range(RAVEN_SIDES):
        following = (step + 1) % RAVEN_SIDES
        mesh_data.faces.new((rings[-1][step], rings[-1][following], tip)).material_index = TRIM

    # The gape: a dark line along the beak where it opens.
    point, forward, up = raven_point(frames, 7.4, 0, -0.15)
    matrix = flip @ Matrix.Translation(point) @ along_frame(forward, up) @ Matrix.Diagonal((0.13, 0.07, 0.004, 1))
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cube(mesh_data, size=1.0, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, BODY)

    # Eyes: small glossy beads.
    for side in (1, -1):
        point, forward, up = raven_point(frames, 4.4, side * 0.94, 0.3)
        matrix = (flip @ Matrix.Translation(point) @ along_frame(forward, up)
                  @ Matrix.Diagonal((0.014, 0.009, 0.014, 1)))
        faces_before = set(mesh_data.faces)
        bmesh.ops.create_uvsphere(mesh_data, u_segments=8, v_segments=6, radius=1.0, matrix=matrix)
        tag_new_faces(mesh_data, faces_before, TRIM)

    # Hackles: shaggy feathers hanging under the throat.
    # They grow from the throat just under the beak and hang down and back.
    hackles = ((4.6, -0.4), (4.6, 0.4), (4.2, -0.6), (4.2, 0.0), (4.2, 0.6),
               (3.8, -0.45), (3.8, 0.45), (3.4, 0.0))
    for along, side in hackles:
        point, forward, up = raven_point(frames, along, side, -0.9)
        matrix = (flip @ Matrix.Translation(point) @ Matrix.Rotation(math.radians(192), 4, "Y")
                  @ Matrix.Rotation(math.radians(side * 14), 4, "X") @ Matrix.Diagonal((1, 0.55, 1, 1)))
        add_feather(mesh_data, matrix, 0.016, 0.055)

    # A few ruffled crown feathers, swept back.
    for along, side in ((3.4, 0.0), (3.9, -0.3), (3.9, 0.3)):
        point, forward, up = raven_point(frames, along, side, 0.95)
        matrix = flip @ Matrix.Translation(point) @ Matrix.Rotation(math.radians(-70), 4, "Y")
        add_feather(mesh_data, matrix, 0.012, 0.035)

    # A ring of feather tips where the neck rises from the nut.
    for index in range(14):
        angle = index * 2 * math.pi / 14
        matrix = (flip @ Matrix.Rotation(angle, 4, "Z") @ Matrix.Translation((0.092, 0, 0.112))
                  @ Matrix.Rotation(math.radians(58), 4, "Y"))
        add_feather(mesh_data, matrix, 0.02, 0.05, TRIM)


# ===== The pieces: the original parts first, then the ornament =====

# ===== Shapes for the king's and queen's tips =====

def add_tesseract_net(mesh_data, cube_size, base_height, pointing_up, material_index=TRIM):
    """An unfolded 4D cube (a tesseract net, the 'Dali cross'): eight small cubes,
    a column of four with four more around the second from the end. The long leg
    starts at `base_height` and points toward the middle of the piece; the cross
    arms sit near the tip. Turned 45 degrees so the arms read from every side."""
    direction = 1 if pointing_up else -1
    turn = Matrix.Rotation(math.radians(45), 4, "Z")
    cells = [(0, 0, level) for level in range(4)]                     # the column
    cells += [(1, 0, 2), (-1, 0, 2), (0, 1, 2), (0, -1, 2)]           # the cross arms
    for across, along, level in cells:
        center = Vector((across * cube_size, along * cube_size,
                         direction * (base_height + (level + 0.5) * cube_size)))
        matrix = (turn @ Matrix.Translation(center)
                  @ Matrix.Diagonal((cube_size, cube_size, cube_size, 1.0)))
        faces_before = set(mesh_data.faces)
        bmesh.ops.create_cube(mesh_data, size=0.94, matrix=matrix)   # small gaps show each cube
        tag_new_faces(mesh_data, faces_before, material_index)


def add_dodecahedron(mesh_data, inner_radius, center, material_index=TRIM):
    """A regular dodecahedron (twelve pentagon faces) sitting flat on a face.
    `inner_radius`: from its centre to the middle of a face."""
    golden = (1 + math.sqrt(5)) / 2
    points = [Vector((x, y, z)) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    for a in (-1, 1):
        for b in (-1, 1):
            points += [Vector((0, a / golden, b * golden)),
                       Vector((a / golden, b * golden, 0)),
                       Vector((a * golden, 0, b / golden))]
    # In these units a face is 1.376 from the centre; the face around (0, 1, golden)
    # is tipped up to face straight up, so the shape sits flat.
    scale = inner_radius / 1.3764
    tilt = Matrix.Rotation(math.atan(1 / golden), 4, "X")
    verts = [mesh_data.verts.new(Vector(center) + (tilt @ point) * scale) for point in points]
    faces_before = set(mesh_data.faces)
    hull = bmesh.ops.convex_hull(mesh_data, input=verts)
    hull_faces = [item for item in hull["geom"] if isinstance(item, bmesh.types.BMFace)]
    # The hull is made of triangles: merge each flat group into one pentagon.
    bmesh.ops.dissolve_limit(mesh_data, angle_limit=math.radians(1), verts=verts,
                             edges=list({edge for face in hull_faces for edge in face.edges}))
    tag_new_faces(mesh_data, faces_before, material_index)


def build_king(mesh_data):
    # Original: core ball, upright ring, bars, spine, tesseract nets.
    add_octagon_ball(mesh_data, 0.19, stretch=1.1)
    add_octagon_ring(mesh_data, 0.33, 0.07, 0.07, rotation=rotation_x(90))
    add_box(mesh_data, (0.74, 0.06, 0.06))
    add_box(mesh_data, (0.52, 0.11, 0.11))
    add_box(mesh_data, (0.06, 0.06, 0.78))
    # At each end: an unfolded 4D cube (tesseract net), see add_tesseract_net.
    for pointing_up in (True, False):
        add_tesseract_net(mesh_data, 0.03, 0.375, pointing_up)

    # Ornament.
    add_molded_band(mesh_data, "bead", 0.17, 0.21, 0.05, material_index=TRIM)          # equator bead
    for z in (0.1, -0.1):
        add_molded_band(mesh_data, "cove", 0.13, 0.17, 0.03, center=(0, 0, z), flip=z < 0)
    ring = rotation_x(90)
    add_dentil_ring(mesh_data, 0.372, 32, (0.018, 0.024, 0.05), rotation=ring)        # dentils round the ring
    add_molded_band(mesh_data, "bead", 0.27, 0.298, 0.03, rotation=ring, material_index=TRIM)
    for x in (0.36, -0.36):                                                            # molded bar ends
        add_molded_band(mesh_data, "step", 0.01, 0.06, 0.04, center=(x, 0, 0),
                        rotation=rotation_y(90 if x > 0 else -90))
        add_octagon_cylinder(mesh_data, 0.028, 0.03, center=(x * 1.1, 0, 0),
                             rotation=rotation_y(90), material_index=TRIM)
    for x in (0.26, -0.26):
        add_molded_band(mesh_data, "cove", 0.05, 0.085, 0.025, center=(x, 0, 0),
                        rotation=rotation_y(90 if x > 0 else -90))
    for z in (0.25, -0.25):                                                            # spine collars
        add_molded_band(mesh_data, "bead", 0.03, 0.056, 0.025, center=(0, 0, z), material_index=TRIM)
    for z in (0.355, -0.355):
        add_molded_band(mesh_data, "step", 0.03, 0.062, 0.03, center=(0, 0, z), flip=z > 0)
    for z in (0.385, -0.385):
        add_octagon_cylinder(mesh_data, 0.045, 0.012, center=(0, 0, z), material_index=TRIM)


def build_queen(mesh_data):
    # Original: barrel, trim discs, through-rod, end discs and dodecahedra.
    add_octagon_ball(mesh_data, 0.2, stretch=1.45)
    for z in (0.11, -0.11):
        add_octagon_cylinder(mesh_data, 0.215, 0.035, center=(0, 0, z), material_index=TRIM)
    add_octagon_cylinder(mesh_data, 0.025, 0.72, rotation=rotation_y(90))
    for x in (0.36, -0.36):
        add_octagon_cylinder(mesh_data, 0.045, 0.03, center=(x, 0, 0), rotation=rotation_y(90))
    for disc_z, cube_z in ((0.33, 0.41), (-0.33, -0.41)):
        add_octagon_cylinder(mesh_data, 0.09, 0.025, center=(0, 0, disc_z))
        add_dodecahedron(mesh_data, 0.056, (0, 0, cube_z * 0.99))

    # Ornament.
    add_molded_band(mesh_data, "bead", 0.185, 0.215, 0.03, material_index=TRIM)        # equator bead
    for z in (0.145, -0.145):                                                          # dentils by the trim discs
        add_dentil_ring(mesh_data, 0.178, 20, (0.016, 0.018, 0.022), center=(0, 0, z), material_index=BODY)
    for z in (0.075, -0.075):
        add_molded_band(mesh_data, "cove", 0.18, 0.205, 0.025, center=(0, 0, z), flip=z < 0)
    for x in (0.325, -0.325):                                                          # molded rod ends
        add_molded_band(mesh_data, "quarter", 0.02, 0.05, 0.03, center=(x, 0, 0),
                        rotation=rotation_y(-90 if x > 0 else 90))
        add_octagon_ball(mesh_data, 0.028, center=(x * 1.22, 0, 0), material_index=TRIM)
    for z in (0.3, -0.3):                                                              # ogee brackets under the discs
        add_molded_band(mesh_data, "ogee", 0.03, 0.085, 0.035, center=(0, 0, z), flip=z > 0)
    for z in (0.33, -0.33):
        add_dentil_ring(mesh_data, 0.096, 16, (0.012, 0.016, 0.02), center=(0, 0, z))
    for z in (0.348, -0.348):                                                          # bead seat under each dodecahedron
        add_molded_band(mesh_data, "bead", 0.03, 0.062, 0.014, center=(0, 0, z), material_index=TRIM)


def build_bishop(mesh_data):
    # Original: spire, tip cone, trim disc, two tilted halos, lower point.
    add_octagon_cylinder(mesh_data, 0.1, 0.24, center=(0, 0, 0.14))
    add_octagon_cylinder(mesh_data, 0.1, 0.16, center=(0, 0, 0.34), top_radius=0.02)
    add_octagon_cylinder(mesh_data, 0.135, 0.06, material_index=TRIM)
    add_octagon_ring(mesh_data, 0.28, 0.04, 0.04, center=(0, 0, -0.02), rotation=rotation_x(14))
    add_octagon_ring(mesh_data, 0.24, 0.04, 0.04, center=(0, 0, -0.09), rotation=rotation_x(14))
    add_octagon_cylinder(mesh_data, 0.02, 0.4, center=(0, 0, -0.24), top_radius=0.1)

    # Ornament.
    add_reeds(mesh_data, 0.1, 0.19, 2, 0.012, center=(0, 0, 0.145))                    # fluted spire
    add_molded_band(mesh_data, "bead", 0.08, 0.116, 0.02, center=(0, 0, 0.262), material_index=TRIM)
    add_molded_band(mesh_data, "step", 0.09, 0.13, 0.03, center=(0, 0, 0.045))
    add_molded_band(mesh_data, "bead", 0.06, 0.088, 0.015, center=(0, 0, 0.3), material_index=TRIM)
    add_molded_band(mesh_data, "bead", 0.035, 0.058, 0.012, center=(0, 0, 0.36), material_index=TRIM)
    add_dentil_ring(mesh_data, 0.142, 16, (0.015, 0.02, 0.04), material_index=BODY)
    add_molded_band(mesh_data, "ogee", 0.08, 0.14, 0.03, center=(0, 0, -0.045))
    add_dentil_ring(mesh_data, 0.308, 30, (0.016, 0.02, 0.03), center=(0, 0, -0.02), rotation=rotation_x(14))
    add_dentil_ring(mesh_data, 0.268, 26, (0.016, 0.02, 0.03), center=(0, 0, -0.09), rotation=rotation_x(14))
    for z, inner, outer in ((-0.13, 0.06, 0.09), (-0.22, 0.042, 0.066), (-0.32, 0.024, 0.046)):
        add_molded_band(mesh_data, "bead", inner, outer, 0.015, center=(0, 0, z), material_index=TRIM)


def build_rook(mesh_data):
    # Original: the block, side bar and pegs, floating caps, trim discs.
    add_octagon_cylinder(mesh_data, 0.17, 0.42)
    add_box(mesh_data, (0.62, 0.05, 0.05))
    for x in (0.31, -0.31):
        add_box(mesh_data, (0.05, 0.09, 0.09), center=(x, 0, 0))
    for z in (0.37, -0.37):
        add_octagon_cylinder(mesh_data, 0.2, 0.1, center=(0, 0, z))
    for z in (0.43, -0.43):
        add_octagon_cylinder(mesh_data, 0.205, 0.025, center=(0, 0, z), material_index=TRIM)

    # Ornament.
    add_reeds(mesh_data, 0.17, 0.28, 2, 0.014)                                         # fluted pilaster faces
    for z in (0.19, -0.19):                                                            # crown and base moldings
        add_molded_band(mesh_data, "cove", 0.15, 0.2, 0.04, center=(0, 0, z), flip=z < 0)
    for z in (0.16, -0.16):
        add_dentil_ring(mesh_data, 0.177, 24, (0.015, 0.016, 0.025), center=(0, 0, z))
    for x in (0.345, -0.345):                                                          # molded peg caps
        add_molded_band(mesh_data, "quarter", 0.01, 0.05, 0.02, center=(x, 0, 0),
                        rotation=rotation_y(-90 if x > 0 else 90))
    for z in (0.37, -0.37):                                                            # dentils round the caps
        add_dentil_ring(mesh_data, 0.206, 24, (0.012, 0.018, 0.03), center=(0, 0, z))
    for z in (0.312, -0.312):
        add_molded_band(mesh_data, "bead", 0.12, 0.19, 0.02, center=(0, 0, z), material_index=TRIM)
    for z in (0.457, -0.457):                                                          # small boss on each end
        add_molded_band(mesh_data, "step", 0.006, 0.08, 0.03, center=(0, 0, z), flip=z < 0)


def build_knight(mesh_data):
    # Original: double octagonal nut and trim ring. The original's curling horns
    # are replaced here by a raven's head, up and down (owner's request).
    add_octagon_cylinder(mesh_data, 0.26, 0.09, center=(0, 0, 0.05))
    add_octagon_cylinder(mesh_data, 0.24, 0.09, center=(0, 0, -0.06))
    add_octagon_ring(mesh_data, 0.13, 0.04, 0.03, center=(0, 0, 0.105), material_index=TRIM)
    add_raven_head(mesh_data, mirror=False)
    add_raven_head(mesh_data, mirror=True)

    # Ornament.
    add_dentil_ring(mesh_data, 0.266, 28, (0.014, 0.022, 0.05), center=(0, 0, 0.05))
    add_dentil_ring(mesh_data, 0.246, 26, (0.014, 0.022, 0.05), center=(0, 0, -0.06))
    add_molded_band(mesh_data, "bead", 0.2, 0.262, 0.016, center=(0, 0, 0.097), material_index=TRIM)
    add_molded_band(mesh_data, "bead", 0.18, 0.242, 0.016, center=(0, 0, -0.107), material_index=TRIM)


def build_pawn_body(mesh_data):
    """One unit tall (the game stretches it along the row). The slab and raised
    strip of the original, fluted like a pilaster with beaded edges."""
    add_box(mesh_data, (0.3, 0.1, 1.0))
    add_box(mesh_data, (0.16, 0.13, 0.98))
    for side_y in (0.056, -0.056):
        for x in (0.1, 0.128, -0.1, -0.128):
            add_box(mesh_data, (0.012, 0.012, 0.98), center=(x, side_y, 0))
        add_box(mesh_data, (0.02, 0.01, 0.98), center=(0, side_y * 1.2, 0), material_index=TRIM)
    for x in (0.15, -0.15):
        add_octagon_cylinder(mesh_data, 0.014, 1.0, center=(x, 0, 0), material_index=TRIM)


def build_pawn_cap(mesh_data):
    """The original notched crown with a cornice lip, dentils and capped teeth.
    Its origin is its bottom edge, so the game can stack it on the body."""
    add_box(mesh_data, (0.34, 0.12, 0.06), center=(0, 0, 0.03))
    for x, height in ((-0.12, 0.08), (0.0, 0.11), (0.12, 0.08)):
        add_box(mesh_data, (0.08, 0.12, height), center=(x, 0, 0.06 + height / 2))
        add_box(mesh_data, (0.096, 0.136, 0.014), center=(x, 0, 0.06 + height + 0.007), material_index=TRIM)
    add_octagon_ring(mesh_data, 0.045, 0.025, 0.02, center=(0, 0.075, -0.07),
                     rotation=rotation_x(90), material_index=TRIM)

    add_box(mesh_data, (0.37, 0.145, 0.014), center=(0, 0, 0.007), material_index=TRIM)  # cornice lip
    for side_y in (0.064, -0.064):                                                       # dentils
        for step in range(8):
            x = -0.14 + step * 0.04
            add_box(mesh_data, (0.02, 0.012, 0.024), center=(x, side_y, 0.032))


def build_piece_shape(name, mesh_data):
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


def build_piece_object(name, body_material, trim_material, collection):
    object_name = name + "-" + VERSION
    old_object = bpy.data.objects.get(object_name)
    if old_object is not None:
        old_mesh = old_object.data
        bpy.data.objects.remove(old_object, do_unlink=True)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    mesh_data = bmesh.new()
    build_piece_shape(name, mesh_data)
    bmesh.ops.remove_doubles(mesh_data, verts=mesh_data.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(mesh_data, faces=mesh_data.faces)

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
    for index, name in enumerate(PIECES):
        piece_object = build_piece_object(name, body_material, trim_material, collection)
        piece_object.location = (index * 1.2, -11, 0)


# ===== Export =====

def export_all():
    collection = get_collection()
    for name in PIECES:
        piece_object = collection.objects.get(name + "-" + VERSION)
        if piece_object is None:
            continue
        saved_location = piece_object.location.copy()
        piece_object.location = (0, 0, 0)
        bpy.ops.object.select_all(action="DESELECT")
        piece_object.select_set(True)
        bpy.context.view_layer.objects.active = piece_object
        bpy.ops.export_scene.gltf(filepath=MODELS_FOLDER + "/" + piece_object.name + ".glb",
                                  export_format="GLB", use_selection=True, export_apply=True,
                                  export_yup=True, export_materials="EXPORT")
        piece_object.location = saved_location
    print("Exported the ornate pieces. Now run: python3 tools/bundle_models.py")


# ===== Run =====

build_all()
export_all()

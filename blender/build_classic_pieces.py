"""
build_classic_pieces.py — classic-style versions of the Diagonal 3D Chess pieces.

The 2026 pieces mix classic Staunton chess pieces and architectural moldings
(torus, scotia, fillet, collar, baluster stem) with the faceted look of the
2006 originals. Each piece is like two classic pieces joined at their bases:
a wide molded plinth in the middle and the piece's head at BOTH ends, so it
reads the same from above and below on the tilted board. The knight has a
3D horse head at both ends, mirrored so both heads face the same way.

The pieces are built in the "classic" style: 32 smooth sides, fully curved
moldings. (The style switches still know "faceted" and "deco", which were
tried and retired; remove_retired_pieces() clears them from the .blend.)

How it works: each piece's outline (from the middle up to the tip) is a list of
points made with molding helpers below. The outline is mirrored to make the
bottom half and spun around the vertical axis (a lathe). Extra parts that are
not round (crosses, crown points, battlements, horse heads) are added on top.

Exports models/<piece>-classic.glb, e.g. models/king-classic.glb. The original
2006-style pieces (blender/build_pieces.py, models/king.glb ...) are untouched.
Afterwards run, from the project folder:
    python3 tools/bundle_models.py

Same conventions as build_pieces.py: one cell = 1 Blender unit, Z up, materials
"Body" (slot 0, recoloured per side) and "Trim" (slot 1, a lighter shade).
Safe-mode friendly: only bpy, bmesh, mathutils; no file access, no callbacks.
It also runs headless from the project folder:
    /Applications/Blender.app/Contents/MacOS/Blender -b blender/pieces.blend \
        --python blender/build_classic_pieces.py --python-expr "import bpy; bpy.ops.wm.save_mainfile()"

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
# Only "classic" is used now. "faceted" and "deco" were tried and retired
# (2026-11-15); the style switches below still describe them.
STYLES = ["classic"]
RETIRED_STYLES = ["faceted", "deco"]

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


# ===== The knight's horse head =====
# Modelled on a carved wooden Staunton knight seen side on (the reference photo
# docs/wooden-chess-piece-knight-horse-head-png.webp, which is not in the repo):
#   - a broad, rounded chest that rises from the collar and swells forward
#   - a neck that curves in under the jaw (the throat)
#   - a head turned forward and down: flat forehead, a long face, a rounded
#     muzzle with a nostril, a mouth line and a soft chin
#   - a big round jowl behind the mouth, a small carved almond eye under a brow
#   - two upright pointed ears at the poll and a forelock between them
#   - a tall mane down the back of the neck, carved in slanting strands
#
# The body is built from horizontal slices stacked from the collar to the poll,
# like a carver's contour lines. Each slice is a rounded loop running from the
# front of the silhouette to the back, with its own width at the front, the
# middle and the back. Outlines were traced from the photo in its own pixels
# (a 680 x 920 close-up of the head): HORSE_UNIT turns them into Blender units.
# The head faces +X; the game turns the knight so it faces the opponent.

HORSE_UNIT = 0.0005             # Blender units per traced pixel
HORSE_CENTER_PIXEL = 340        # the traced x that sits over the piece's axis
HORSE_BASE_PIXEL = 890          # the traced y of the collar (bottom of the neck)
HORSE_BASE_HEIGHT = 0.205       # where the collar is on the piece
HORSE_LOOP_POINTS = 28          # points around each slice

# Traced pixel y of the slice, pixel x of its front and back edge, then the half
# widths (Blender units) at its front, middle and back.
HORSE_SLICES = [
    (920, 108, 605, 0.085, 0.100, 0.080),   # buried in the collar
    (890, 105, 605, 0.085, 0.100, 0.080),   # base of the neck
    (850, 90, 605, 0.082, 0.098, 0.075),
    (800, 85, 605, 0.080, 0.095, 0.070),    # the chest, swelling forward
    (750, 88, 600, 0.075, 0.090, 0.064),
    (700, 100, 595, 0.068, 0.084, 0.058),
    (650, 130, 590, 0.060, 0.078, 0.052),
    (600, 170, 595, 0.054, 0.074, 0.048),
    (560, 200, 600, 0.050, 0.071, 0.044),
    (520, 225, 605, 0.046, 0.070, 0.040),   # the throat, under the jaw
    (500, 205, 610, 0.040, 0.070, 0.037),
    (490, 165, 612, 0.036, 0.071, 0.036),   # underside of the jaw, rising to the chin
    (480, 115, 615, 0.034, 0.072, 0.035),
    (465, 75, 617, 0.034, 0.073, 0.034),    # lower lip
    (450, 60, 618, 0.035, 0.073, 0.033),    # mouth
    (430, 50, 618, 0.036, 0.072, 0.032),
    (410, 42, 617, 0.038, 0.071, 0.031),
    (390, 38, 616, 0.039, 0.070, 0.030),    # nostril, front of the nose
    (370, 42, 614, 0.039, 0.069, 0.030),
    (350, 55, 612, 0.039, 0.068, 0.029),
    (320, 78, 608, 0.040, 0.066, 0.028),    # bridge of the nose
    (290, 100, 604, 0.041, 0.064, 0.027),
    (260, 125, 595, 0.042, 0.062, 0.026),
    (230, 150, 582, 0.043, 0.059, 0.025),   # eye level
    (200, 175, 565, 0.044, 0.056, 0.025),
    (170, 200, 545, 0.045, 0.052, 0.024),   # forehead
    (140, 228, 520, 0.044, 0.048, 0.023),
    (110, 255, 490, 0.041, 0.044, 0.022),
    (85, 275, 455, 0.036, 0.039, 0.020),    # the poll, between the ears
    (68, 295, 420, 0.026, 0.029, 0.016),
    (60, 320, 390, 0.014, 0.016, 0.010),
]


def horse_height(pixel_y):
    return HORSE_BASE_HEIGHT + (HORSE_BASE_PIXEL - pixel_y) * HORSE_UNIT


def horse_x(pixel_x):
    return (HORSE_CENTER_PIXEL - pixel_x) * HORSE_UNIT


def slice_at(pixel_y):
    """The slice at any height, blended from the two traced slices around it."""
    for upper, lower in zip(HORSE_SLICES[1:], HORSE_SLICES):
        if upper[0] <= pixel_y <= lower[0]:
            mix = (lower[0] - pixel_y) / (lower[0] - upper[0])
            return [near + (far - near) * mix for near, far in zip(lower, upper)]
    return list(HORSE_SLICES[0] if pixel_y > HORSE_SLICES[0][0] else HORSE_SLICES[-1])


def slice_half_width(horse_slice, along):
    """Half width at `along` (0 = front edge, 1 = back edge): a smooth blend of
    the front, middle and back widths."""
    front, middle, back = horse_slice[3], horse_slice[4], horse_slice[5]
    if along < 0.5:
        blend = along * 2
        blend = blend * blend * (3 - 2 * blend)
        return front + (middle - front) * blend
    blend = (along - 0.5) * 2
    blend = blend * blend * (3 - 2 * blend)
    return middle + (back - middle) * blend


def loop_point(horse_slice, angle):
    """A point on a slice's rounded loop. angle 0 = front edge, pi = back edge;
    0..pi is the +Y side, pi..2pi the -Y side."""
    along = (1 - math.cos(angle)) / 2
    across = math.sin(angle)
    half_width = slice_half_width(horse_slice, along)
    x = horse_x(horse_slice[1] + (horse_slice[2] - horse_slice[1]) * along)
    # A square-ish loop (power 0.5): flat cheeks and sides, rounded edges.
    y = half_width * math.copysign(abs(across) ** 0.5, across)
    return Vector((x, y, horse_height(horse_slice[0])))


def surface_point(pixel_x, pixel_y, side, sink=0.0):
    """The point on the horse's side at a traced pixel (side +1 or -1),
    pushed `sink` units into the wood."""
    horse_slice = slice_at(pixel_y)
    along = (pixel_x - horse_slice[1]) / (horse_slice[2] - horse_slice[1])
    along = min(0.999, max(0.001, along))
    point = loop_point(horse_slice, math.acos(1 - 2 * along))
    return Vector((point.x, side * (abs(point.y) - sink), point.z))


def add_ellipsoid(mesh_data, center, rotation, radii, flip, material=BODY, segments=12):
    """A squashed ball, turned by `rotation`, for jowls, eyes, nostrils, locks."""
    matrix = (flip @ Matrix.Translation(center) @ rotation
              @ Matrix.Diagonal((radii[0], radii[1], radii[2], 1)))
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_uvsphere(mesh_data, u_segments=segments, v_segments=max(6, segments // 2),
                              radius=1.0, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, material)


def add_horse_body(mesh_data, flip):
    """Stack the slices into one closed, rounded body."""
    faces_before = set(mesh_data.faces)
    rings = []
    for horse_slice in HORSE_SLICES:
        ring = []
        for step in range(HORSE_LOOP_POINTS):
            angle = step * 2 * math.pi / HORSE_LOOP_POINTS
            ring.append(mesh_data.verts.new(flip @ loop_point(horse_slice, angle)))
        rings.append(ring)
    for index in range(len(rings) - 1):
        for step in range(HORSE_LOOP_POINTS):
            following = (step + 1) % HORSE_LOOP_POINTS
            mesh_data.faces.new((rings[index][step], rings[index][following],
                                 rings[index + 1][following], rings[index + 1][step]))
    mesh_data.faces.new(rings[0])
    # The top of the head closes to a soft ridge between the ears.
    top_slice = HORSE_SLICES[-1]
    top = mesh_data.verts.new(flip @ Vector((horse_x((top_slice[1] + top_slice[2]) / 2), 0,
                                             horse_height(top_slice[0] - 6))))
    for step in range(HORSE_LOOP_POINTS):
        following = (step + 1) % HORSE_LOOP_POINTS
        mesh_data.faces.new((rings[-1][step], rings[-1][following], top))
    tag_new_faces(mesh_data, faces_before, BODY)


def turn_in_side_plane(degrees):
    """A rotation in the side (XZ) plane: tilts a feature's long axis up or down."""
    return Matrix.Rotation(math.radians(-degrees), 4, "Y")


def add_carved_line(mesh_data, pixel_points, side, flip, height=0.0035):
    """A carved ridge along the horse's side, through traced pixel points: a
    chain of long, thin ovals that stand `height` proud of the surface."""
    for start, end in zip(pixel_points, pixel_points[1:]):
        steps = 4
        for step in range(steps):
            mix_a = step / steps
            mix_b = (step + 1) / steps
            point_a = surface_point(start[0] + (end[0] - start[0]) * mix_a,
                                    start[1] + (end[1] - start[1]) * mix_a, side, 0.0)
            point_b = surface_point(start[0] + (end[0] - start[0]) * mix_b,
                                    start[1] + (end[1] - start[1]) * mix_b, side, 0.0)
            middle = (point_a + point_b) / 2
            length = (point_b - point_a).length
            tilt = math.degrees(math.atan2(point_b.z - point_a.z, point_b.x - point_a.x))
            add_ellipsoid(mesh_data, middle - Vector((0, side * 0.004, 0)), turn_in_side_plane(tilt),
                          (length * 1.1, 0.004 + height, 0.004), flip, segments=8)


def add_horse_head(mesh_data, mirror):
    """The whole carved horse: body, then features on both sides. `mirror`
    reflects it below the middle (z -> -z), so the lower head faces the same way."""
    flip = Matrix.Diagonal((1, 1, -1, 1)) if mirror else Matrix.Identity(4)
    add_horse_body(mesh_data, flip)

    for side in (1, -1):
        # The jowl: the round of the jaw, carved as a raised edge like the photo,
        # from under the eye, around the back of the jaw, to the throat.
        add_carved_line(mesh_data, [(300, 285), (365, 300), (405, 345), (412, 405),
                                    (385, 455), (320, 482)], side, flip)
        # The cheek bone, from below the eye down the face toward the nose.
        add_carved_line(mesh_data, [(255, 270), (200, 310), (140, 350)], side, flip)
        # Eye: a small carved almond under a heavy lid.
        add_ellipsoid(mesh_data, surface_point(285, 245, side, 0.003), turn_in_side_plane(-12),
                      (0.017, 0.005, 0.0075), flip, TRIM, 12)
        add_ellipsoid(mesh_data, surface_point(282, 229, side, 0.004), turn_in_side_plane(-12),
                      (0.025, 0.007, 0.006), flip, segments=10)

        # Nostril: a dark oval set into a flared rim at the front of the nose.
        add_ellipsoid(mesh_data, surface_point(78, 392, side, 0.006), turn_in_side_plane(-60),
                      (0.017, 0.012, 0.014), flip, segments=12)
        add_ellipsoid(mesh_data, surface_point(70, 392, side, -0.004), turn_in_side_plane(-60),
                      (0.009, 0.004, 0.006), flip, TRIM, 10)

        # Ears: upright and pointed, the near one a little ahead of the far one.
        ear_base = surface_point(305, 82, side, 0.014)
        ear_tilt = (Matrix.Rotation(math.radians(8), 4, "Y")
                    @ Matrix.Rotation(math.radians(side * -12), 4, "X"))
        add_ellipsoid(mesh_data, ear_base, ear_tilt @ Matrix.Translation((0, 0, 0.026)),
                      (0.016, 0.009, 0.036), flip, segments=12)

        # Chest muscles: the carved line where the neck meets the chest.
        add_carved_line(mesh_data, [(250, 545), (200, 610), (170, 690), (175, 770), (205, 840)], side, flip)
        # The mane: slanting carved strands down the back of the neck, from the
        # poll to the shoulders, each sweeping forward and down from the crest.
        for strand in range(15):
            pixel_y = 120 + strand * 34
            back_edge = slice_at(pixel_y)[2]
            add_ellipsoid(mesh_data, surface_point(back_edge - 38, pixel_y + 10, side, 0.004),
                          turn_in_side_plane(-55), (0.03, 0.006, 0.0055), flip, segments=10)
        # The front edge of the mane: a ridge where it lies on the neck.
        for step in range(9):
            pixel_y = 150 + step * 55
            back_edge = slice_at(pixel_y)[2]
            add_ellipsoid(mesh_data, surface_point(back_edge - 85, pixel_y, side, 0.006),
                          turn_in_side_plane(-80), (0.034, 0.008, 0.006), flip, segments=10)

    # The mouth: a fine line where the lips meet, through the muzzle.
    mouth = Vector((horse_x(102), 0, horse_height(452)))
    matrix = flip @ Matrix.Translation(mouth) @ turn_in_side_plane(-8) @ Matrix.Diagonal((0.026, 0.074, 0.003, 1))
    faces_before = set(mesh_data.faces)
    bmesh.ops.create_cube(mesh_data, size=1.0, matrix=matrix)
    tag_new_faces(mesh_data, faces_before, TRIM)

    # Chin: the soft round of the lower lip.
    add_ellipsoid(mesh_data, Vector((horse_x(135), 0, horse_height(478))), turn_in_side_plane(-10),
                  (0.022, 0.03, 0.012), flip, segments=12)

    # Forelock: a tuft lying forward over the forehead, between the ears.
    add_ellipsoid(mesh_data, Vector((horse_x(250), 0, horse_height(112))), turn_in_side_plane(-40),
                  (0.042, 0.02, 0.007), flip, segments=12)
    # Crest of the mane: a row of lock tips along the back edge.
    for lock in range(12):
        pixel_y = 100 + lock * 45
        back_edge = slice_at(pixel_y)[2]
        add_ellipsoid(mesh_data, Vector((horse_x(back_edge - 6), 0, horse_height(pixel_y))),
                      turn_in_side_plane(-55), (0.02, 0.012, 0.008), flip, segments=10)


def build_knight(mesh_data, style):
    profile = start_profile(0.26)
    plinth(profile, style, 0.26)
    ledge(profile, 0.17)
    curve_to(profile, style, 0.15, 0.2, -0.01)
    fillet(profile, 0.014, TRIM)
    line_to(profile, 0.0, 0.214)
    revolve(mesh_data, mirrored_profile(profile), style)
    add_horse_head(mesh_data, mirror=False)
    add_horse_head(mesh_data, mirror=True)


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


def remove_retired_pieces():
    """Delete the faceted and deco objects from the Blender file."""
    for style in RETIRED_STYLES:
        for name in PIECES:
            old_object = bpy.data.objects.get(name + "-" + style)
            if old_object is not None:
                old_mesh = old_object.data
                bpy.data.objects.remove(old_object, do_unlink=True)
                if old_mesh.users == 0:
                    bpy.data.meshes.remove(old_mesh)


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

remove_retired_pieces()
build_all()
export_all()

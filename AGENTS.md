# Diagonal 3D Chess — notes for AI agents

Follows the shared rules in `../AGENTS.md`. This file adds project-specific detail.

## What it is

A browser remake of the owner's 2006 Director 3D chess board (senior thesis).
8×8×8 cube tilted 45°, pawns that span a whole upright row and grow as they advance.
Original site for reference: https://thehinge.net/3dchess/ (pages: pieces, pawns,
board, philosophy, how to play). The philosophy matters: the board deliberately
allows "incorrect" moves (Free moves mode, taking pieces off by hand).

## Current state (2026-11-14)

Repository: https://github.com/dansternofbeyer/diagonal-3d-chess (public, branch `main`).
Live site (GitHub Pages, from `main` root, `.nojekyll`): https://dansternofbeyer.github.io/diagonal-3d-chess/
Commits use the GitHub noreply email (set in this repo's git config), not a personal one.
Third-party reference photos in docs/ are git-ignored on purpose (see .gitignore).
The README's "Download and play" section is written for people new to GitHub: keep it
first and keep the ZIP link pointing at archive/refs/heads/main.zip.

Working and tested in Chrome, both over http and from `file://`:
- `index.html`: dark theme; play, orbit/pan/zoom (middle- or right-drag pans),
  classic + free moves, animated moves (knight L, sliding, pawns grow/shrink),
  taken pieces pop up on the rose rail, collapsible side panel, Reset view,
  move styles as checkboxes (glass cubes / glowing dots / cube edges, any mix,
  `state.moveStyle`), optional move lines, castling, Explore Moves toggle (a single
  ON/OFF button; multi-select pieces, red/white/purple), the selected piece outlined
  by its cell edges (`buildCellOutlines`), Delete key takes the selected piece off
  the board (the Selected box was removed), gradient background dome, undo,
  save/load `.txt`, drag-drop load, check warning, pawn promotion dialog (opens
  after the move animation), move log. Header has GAME and ABOUT drop-down menus;
  side-panel boxes are `<details class="section">`, closed by default, open state
  saved in preferences (`openSections`). The game in progress + last 100 undo steps
  autosave to localStorage `diagonal-3d-chess.current-game` on every `refreshAll()`
  and are restored on load (so visiting the Studio doesn't reset the game). Rose cubes and the place-holder markers were
  removed (owner's request): Explore Moves replaced the markers. Marker lines in
  save files still load and save (rules keep `game.markers`) but are not drawn.
  The 2006 preset-view buttons were removed on purpose (owner's request).
- `game-studio.html`: view each piece alone or on the board with moves, board and
  full-set views, edit look settings, preview a replacement `.glb`.

## Key decisions (don't undo without asking)

- **Must open by double-click, offline.** So: classic `<script>` tags, no ES modules,
  no fetch. three.js is **r147** vendored in `lib/` because it is the last version
  with `build/three.min.js` + `examples/js/` (non-module) files. Don't upgrade to a
  module-only version without a plan for file://.
- **Models are bundled as base64** in `models/pieces.js` (`window.CHESS_PIECE_MODELS`)
  because file:// pages can't fetch `.glb`. Regenerate with `python3 tools/bundle_models.py`.
- **Coordinates**: cell (x, y, z) 0–7. Red home edge y=0,z=0; Black y=7,z=7.
  Plane = y+z (0–14), upright after the tilt. Pawn = (file, plane), fills `rowCells`.
- **Pawns start on plane 2 / 12** (3 cubes tall), not 1 / 13. On plane 1 the line
  (x,t,t) through the cube's middle is open and queens/rooks/bishops can capture their
  opposite numbers on move one. Plane 2 contains (x,1,1) and blocks it. Matches the
  2006 start image, where pawns are ~3 cubes tall.
- Pawn rules chosen for the old "open questions": step 1 plane (2 from start) into an
  empty row; capture diagonally forward taking all enemies in the row; promote at the
  far edge (plane 14 / 0), with an option to stay a pawn.
- **Pawns guard the diagonal they stand across** (`stepCrossesPawn` in the rules):
  a flat diagonal step (0, ±1, ±1) that jumps a plane passes through the edge
  between two cells of the row in between; if one pawn fills both, the step is
  blocked for all sliding pieces and kings, both sides. 3D corner diagonals pass
  between files and are not blocked.
- Back row order R N B K Q B N R for both sides (from the 2006 control bar).
- Turns are enforced in classic mode unless "Take turns" is unticked. Check is shown,
  never enforced (no checkmate logic on purpose).
- Look settings: `js/look-settings.js` defaults, overridden by localStorage key
  `diagonal-3d-chess.look` written by the studio, **only if** its `lookVersion`
  matches the defaults. Bump `lookVersion` when defaults change in a way old saved
  edits must not override (it was bumped to 2 for the dark theme). Game
  preferences (incl. `panelCollapsed`) use `diagonal-3d-chess.preferences`.
- Trim is not its own colour: it is the side colour lightened by `trimLighten`
  (HSL lightness). Materials are `red`, `black`, `redTrim`, `blackTrim`.
- Lighting: ACES tone mapping; one strong directional light from above plus dim
  fills; `scene.environment` is a PMREM of a hand-written shader room
  (`STUDIO_FRAGMENT_SHADER`: small bright overhead softbox + thin strip lights).
  Keep env lights small and bright: big ones wash the red out to salmon.
  Pieces are `MeshPhysicalMaterial` with clearcoat and a rim light injected via
  `onBeforeCompile` (`addRimLight`). `material.clone()` drops it, so use
  `ChessScene.clonePieceMaterial`. Avoid GLSL reserved words (`flat` broke it once).
- Animation: the move is applied to the game first and the board redrawn; then
  `animateMove` plays the mover from its old place (`ChessScene.movePath`,
  `setPawnLength`). Any redraw calls `finishAnimations()` first.
- **Wood finish** (`look.pieceFinish` = "wood" default | "lacquer"): procedural grain
  in the piece shader (`WOOD_SHADER_FUNCTIONS`, `addPieceShader` in chess-scene.js),
  from object-space position x4 (models have no UVs, so photos can't be mapped;
  the x4 in `woodColor(vWoodPosition * 4.0)` sets the grain size). Wood
  colours `redWoodLight/Dark`, `blackWoodLight/Dark` are converted sRGB -> linear
  (unconverted they wash out). `addPieceShader` also holds the rim light; clone piece
  materials with `clonePieceMaterial` to keep both.
- Haze: `look.haze` (0..1) sets `THREE.FogExp2` density (`HAZE_AT_FULL` = 0.05 at 1),
  fog colour = backgroundColor; the sky dome ignores fog. `viewer.setHaze(amount, color)`.
- **Castling** (`getCastlingMoves`, `getPlayMoves` = classic + castling; the UI uses
  getPlayMoves, `isInCheck` still uses getClassicMoves so there is no recursion):
  2D rules along the home edge, king at x=3 moves to x=1 (rook 0 -> 2) or x=5
  (rook 7 -> 4). `piece.hasMoved` is set by applyMove/promotePawn and saved as a
  trailing "moved" on king/rook lines. A castling move carries `move.castle =
  { rookId, rookTo }`; the rook hops over the king (`animateHop`).
- Highlights: `style` is `{ cubes, dots, edges }` (old strings "blue"/"dots" still
  accepted by `normalizeMoveStyle`). `buildMoveHighlights(moves, style, look, piece, showLines)` for play
  (clickable hit boxes); `buildAvailableMoves(entries, style, look, showLines)` for
  the look-only multi-piece view. Lines and dots use `toneMapped: false` to keep
  their exact colours. Background is a camera-following shader dome
  (`createSkyDome`); change its colour with `viewer.setBackgroundColor`.
- **Piece versions**: `look.pieceVersions[type]` = "original" | "ornate" | "classic"
  (default all "original" until the owner picks). "faceted" and "deco" were retired
  2026-11-15; saved looks that still name them fall back to "classic" (`versionOf`).
  Knights are modelled facing +X; `KNIGHT_TURN` in chess-scene.js turns every knight
  to face the opponent. "ornate" =
  original geometry + molding greebles (`blender/build_ornate_pieces.py`: molded
  profile bands, dentil rings, reeds/fluting); its knight is a lofted, 8-sided raven
  head (`add_raven_head`) instead of the original horns. Its horn collars sit only at the horn
  bases: the original horn rings are skewed, so collars along the curve looked broken. Model keys are
  `king` (original) or `king-classic` / `king-ornate`; pawns use `pawn_body-<v>` + `pawn_cap-<v>`.
  `ChessScene.pieceModel` falls back to the original. Classic-style pieces are built
  by `blender/build_classic_pieces.py` (profile + lathe system, mirrored top/bottom,
  knight = carved horse traced from the photo `docs/wooden-chess-piece-knight-horse-head-png.webp`
  (git-ignored): `HORSE_SLICES` are horizontal slices in the photo's pixels, turned into
  units by `HORSE_UNIT`; features placed with `surface_point`, carved ridges with
  `add_carved_line`; mirrored so both heads face the same way). It runs
  headless: `Blender -b blender/pieces.blend --python blender/build_classic_pieces.py`
  (see its docstring), no MCP paste needed. The pawn body must stay 1.0
  tall (the game stretches it). All versions are bundled, so `models/pieces.js` is
  ~2.3 MB; once versions are chosen, unused .glb files can be deleted and re-bundled.
  The studio has a "Compare versions" view (click a piece to choose it).
- **Glow lights**: `createGlowLights` keeps a fixed pool of 8 PointLights (never add or
  remove lights at runtime: it recompiles all shaders). The game puts a yellow light in
  each selected piece and clusters move-marker cells (`clusterGlowPoints`) into the rest.
  Highlight builders return `glowPoints` for this.
- Taken pieces stand on the floor ring (`buildRailPiece`, `railPosition`): Red's
  taken pieces at the back row (Black's side), Black's at the front.

## Files

- `js/chess-rules.js` — `window.ChessRules`: board math, moves, apply/undo data, save/load text format.
  Pure logic; can be tested in Node (`global.window = {}; require(...)`).
- `js/chess-scene.js` — `window.ChessScene`: viewer, board, textures (canvas-drawn), piece
  building (pawn = stretched `pawn_body` + two `pawn_cap`), move highlights, markers.
  `CUBE_TO_WORLD` is the 45° tilt; `cellToWorld`/`cellToCubeSpace` convert cells.
- `index.html` — game UI + controller. `window.chessDebug` exposes state for console debugging.
- `game-studio.html` — studio UI. `window.studioDebug` likewise.
- `blender/build_pieces.py` — builds all pieces from bmesh primitives and exports `.glb`.
  Written to run under the Blender MCP **safe mode** (no open/os/exec, no callbacks
  passed as arguments, no dict-of-functions dispatch). Keep it that way.
- `blender/pieces.blend` — saved copy of the built pieces.
- Materials in Blender must be named `Body` (recoloured per side) and `Trim`.

## Testing tips

- If the browser pane is hidden, requestAnimationFrame stops and screenshots go
  stale. Headless Chrome screenshots (below) are more reliable. Headless `--dump-dom`
  runs no animation frames at all: step `chessDebug.animations[i].update(dt)` by
  hand to test animations. A small iframe harness page served next to index.html
  (deleted afterwards) is a handy way to run test steps in headless Chrome.
- Watch the console for shader compile errors after touching the shaders.
- The Claude browser pane renders `file://` pages as static snapshots, and its preview
  server could not read the Desktop folder. Serve with
  `python3 -m http.server 8766 --bind 127.0.0.1` from Bash and open
  `http://127.0.0.1:8766/`. Front the tab (`tabs_select`) or `requestAnimationFrame` stalls.
- Add `?v=N` to the URL to dodge cached HTML.
- To verify file:// really works, use headless Chrome:
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --use-angle=swiftshader --enable-unsafe-swiftshader --virtual-time-budget=6000 --screenshot=out.png file:///…/index.html`

## Known issues / ideas

- No checkmate detection or legal-move filtering (by design, but could be optional).
- Not tested on a real phone yet; layout stacks below 760px.
- Possible additions: en passant, a hand-written puzzle library,
  sharing a game via URL.

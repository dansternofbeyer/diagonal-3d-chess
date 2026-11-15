/*
 * look-settings.js — the default colours and sizes for the pieces and board.
 *
 * game-studio.html can change these. Changes made there are kept in this
 * browser (localStorage) and show up in the game straight away. To make them
 * permanent for everyone, use "Download look-settings.js" in the studio and
 * replace this file with the downloaded one.
 *
 * Open source under the MIT License (see ../LICENSE).
 */
window.CHESS_LOOK_DEFAULTS = {
  // Bumped when the defaults change in a way old saved studio edits should not override.
  lookVersion: 2,

  // Piece colours. The trim is the same colour as the body, just a little lighter.
  redColor: "#d8200f",
  blackColor: "#1b1b1d",
  trimLighten: 0.14,          // how much lighter the trim is (0 = same as the body)
  pieceRoughness: 0.3,
  pieceMetalness: 0.1,
  pieceShine: 0.85,           // the clear glossy coat on top (0 = none, 1 = full)
  rimLight: 0.35,             // the soft glow around a piece's outline

  // Size of each piece inside its cell (1 = as modelled in Blender)
  pieceScale: { king: 1, queen: 1, rook: 1, bishop: 1, knight: 1, pawn: 1 },

  // Which version of each piece to use: "original", "ornate" or "classic"
  // (compare them in the studio's "Compare versions" view).
  pieceVersions: { king: "original", queen: "original", rook: "original",
    bishop: "original", knight: "original", pawn: "original" },

  // Board
  backgroundColor: "#141518",
  frameColor: "#c9d2d8",
  frameOpacity: 0.45,
  floorColor: "#e7b2a2",
  floorOpacity: 0.72,
  haze: 0.3,                  // depth fog: far things fade toward the background (0 = none)

  // Move highlights
  blueCubeColor: "#7fb6cc",
  captureColor: "#ff7a2f",
  dotColor: "#2bb8f0",
  cubeOpacity: 0.4,
  moveLineColor: "#3da5ff",   // the thin "move lines" along each path
  moveEdgeColor: "#4fb3ff",   // "Cube edges": the outline of each cell a piece can move to

  // Available Moves tool: several pieces' moves at once
  redMovesColor: "#ff3b2a",
  blackMovesColor: "#f2f2f2",
  sharedMovesColor: "#b04dff",  // a cell both sides can reach
};

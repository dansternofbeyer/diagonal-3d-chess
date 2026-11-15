/*
 * chess-rules.js — the rules of Diagonal 3D Chess, with no 3D drawing code.
 *
 * Used by index.html (the game) and game-studio.html (the asset viewer).
 * Exposes one global object: window.ChessRules.
 *
 * ===== How the board works =====
 * The board is an 8 x 8 x 8 cube of cells. A cell is written (x, y, z), each 0-7.
 *   x = the "file", left to right across the row of pieces.
 *   y and z = the other two cube directions.
 * The whole cube is tilted 45 degrees, so one edge points at Red and the
 * opposite edge points at Black:
 *   Red's home edge   is y = 0, z = 0  (front, middle height)
 *   Black's home edge is y = 7, z = 7  (back, middle height)
 * A "plane" is a slice of cells where y + z is the same (0 to 14). After the
 * tilt each plane stands upright, facing the players. Plane 0 is Red's edge,
 * plane 14 is Black's edge. Red moves toward higher planes, Black toward lower.
 *
 * ===== Pawns =====
 * A pawn is not one cell. It fills a whole upright row of cells: every cell
 * in its plane that has its file x. So a pawn is written (file, plane), and it
 * "grows" as it walks toward the middle of the board, where the rows are
 * longest, and shrinks again near the far edge.
 *
 * ===== Rules are suggestions =====
 * The original 2006 version let players make "incorrect" moves on purpose (see
 * the Philosophy page). This file gives the classic moves, plus a free mode
 * where any piece may go anywhere.
 *
 * Open source under the MIT License (see LICENSE).
 */
window.ChessRules = (function () {
  "use strict";

  // ===== Board constants =====

  const BOARD_SIZE = 8;
  const LAST_INDEX = BOARD_SIZE - 1;          // 7
  const LAST_PLANE = 2 * LAST_INDEX;          // 14
  const SIDES = ["red", "black"];
  const PIECE_TYPES = ["king", "queen", "rook", "bishop", "knight", "pawn"];

  // The back row, left to right, the same as the 2006 control bar.
  const BACK_ROW = ["rook", "knight", "bishop", "king", "queen", "bishop", "knight", "rook"];

  const PIECE_DESCRIPTIONS = {
    king: "Moves one cube in any of the 26 directions (6 straight, 12 diagonal, 8 corner-to-corner 3D diagonals).",
    queen: "Moves any number of cubes in any of the 26 directions.",
    rook: "Moves any number of cubes in 18 directions: the 6 straight and the 12 flat diagonals. No 3D diagonals.",
    bishop: "Moves any number of cubes along any diagonal, flat or 3D: 20 directions. No straight lines.",
    knight: "Two out and one over, in three dimensions: 24 possible jumps. Jumps over anything in between.",
    pawn: "Fills a whole upright row of cubes and grows as it crosses the board. Steps forward one plane " +
      "(two from its starting plane) when the row ahead is empty. Captures one plane forward and one file " +
      "to either side, taking every enemy in that row. Promotes on reaching the far edge. " +
      "Guards the diagonal it stands across: no piece can move diagonally through a pawn.",
  };

  // ===== Directions =====

  /** All 26 one-step directions, sorted by how many axes they change. */
  function buildDirections() {
    const straight = [];
    const flatDiagonal = [];
    const cornerDiagonal = [];
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (let dz = -1; dz <= 1; dz++) {
          const axesChanged = Math.abs(dx) + Math.abs(dy) + Math.abs(dz);
          const direction = [dx, dy, dz];
          if (axesChanged === 1) straight.push(direction);
          if (axesChanged === 2) flatDiagonal.push(direction);
          if (axesChanged === 3) cornerDiagonal.push(direction);
        }
      }
    }
    return { straight, flatDiagonal, cornerDiagonal };
  }

  /** The 24 knight jumps: every arrangement of (2, 1, 0) with every sign. */
  function buildKnightJumps() {
    const jumps = [];
    const seen = new Set();
    const orders = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
    for (const order of orders) {
      for (const signTwo of [-2, 2]) {
        for (const signOne of [-1, 1]) {
          const jump = [0, 0, 0];
          jump[order[0]] = signTwo;
          jump[order[1]] = signOne;
          const key = jump.join(",");
          if (!seen.has(key)) {
            seen.add(key);
            jumps.push(jump);
          }
        }
      }
    }
    return jumps;
  }

  const DIRECTIONS = buildDirections();
  const KNIGHT_JUMPS = buildKnightJumps();

  /** Which directions each sliding/stepping piece uses. */
  const PIECE_DIRECTIONS = {
    king: [...DIRECTIONS.straight, ...DIRECTIONS.flatDiagonal, ...DIRECTIONS.cornerDiagonal],
    queen: [...DIRECTIONS.straight, ...DIRECTIONS.flatDiagonal, ...DIRECTIONS.cornerDiagonal],
    rook: [...DIRECTIONS.straight, ...DIRECTIONS.flatDiagonal],
    bishop: [...DIRECTIONS.flatDiagonal, ...DIRECTIONS.cornerDiagonal],
  };

  // ===== Cells and planes =====

  function isInsideBoard(x, y, z) {
    return x >= 0 && x <= LAST_INDEX && y >= 0 && y <= LAST_INDEX && z >= 0 && z <= LAST_INDEX;
  }

  function cellKey(x, y, z) {
    return x + "," + y + "," + z;
  }

  /** The cells of one upright row: file x, plane y + z. Listed bottom to top. */
  function rowCells(file, plane) {
    const cells = [];
    for (let y = LAST_INDEX; y >= 0; y--) {
      const z = plane - y;
      if (isInsideBoard(file, y, z)) cells.push({ x: file, y, z });
    }
    return cells;
  }

  /** Every cell in one plane (all files). */
  function planeCells(plane) {
    const cells = [];
    for (let x = 0; x <= LAST_INDEX; x++) cells.push(...rowCells(x, plane));
    return cells;
  }

  /** +1 for Red (toward higher planes), -1 for Black. */
  function forwardDirection(side) {
    return side === "red" ? 1 : -1;
  }

  function otherSide(side) {
    return side === "red" ? "black" : "red";
  }

  /** The plane where this side's pawns promote: the enemy's home edge. */
  function promotionPlane(side) {
    return side === "red" ? LAST_PLANE : 0;
  }

  /**
   * Pawns start on plane 2 (Black: 12), three cubes tall. Plane 2 includes the
   * cell (x, 1, 1), which blocks the line that runs from each back-row piece
   * straight through the middle of the cube to its opposite number. On plane 1
   * that line is open and queens could take queens on the first move.
   */
  function pawnStartPlane(side) {
    return side === "red" ? 2 : LAST_PLANE - 2;
  }

  /** The cells a piece fills: one cell, or a whole row for a pawn. */
  function cellsOfPiece(piece) {
    if (piece.type === "pawn") return rowCells(piece.file, piece.plane);
    return [{ x: piece.x, y: piece.y, z: piece.z }];
  }

  // ===== Positions =====

  let nextPieceNumber = 1;

  function makePiece(side, type, place) {
    const piece = { id: "p" + nextPieceNumber++, side, type };
    if (type === "pawn") {
      piece.file = place.file;
      piece.plane = place.plane;
    } else {
      piece.x = place.x;
      piece.y = place.y;
      piece.z = place.z;
    }
    return piece;
  }

  /** The standard opening: back rows on the two home edges, pawns one plane in. */
  function createStartingPieces() {
    const pieces = [];
    for (let file = 0; file < BOARD_SIZE; file++) {
      pieces.push(makePiece("red", BACK_ROW[file], { x: file, y: 0, z: 0 }));
      pieces.push(makePiece("red", "pawn", { file, plane: pawnStartPlane("red") }));
      pieces.push(makePiece("black", BACK_ROW[file], { x: file, y: LAST_INDEX, z: LAST_INDEX }));
      pieces.push(makePiece("black", "pawn", { file, plane: pawnStartPlane("black") }));
    }
    return pieces;
  }

  function createNewGame() {
    return {
      pieces: createStartingPieces(),
      markers: [],        // { id, color, x, y, z } — the old "place holder" cubes
      captured: [],       // { side, type } of pieces taken off the board
      turn: "red",
      moveLog: [],        // human-readable lines, e.g. "red knight 1,0,0 -> 1,2,1"
    };
  }

  function copyGame(game) {
    return JSON.parse(JSON.stringify(game));
  }

  /** Map of "x,y,z" -> piece, for every cell that has something in it. */
  function buildOccupancy(pieces) {
    const occupancy = new Map();
    for (const piece of pieces) {
      for (const cell of cellsOfPiece(piece)) occupancy.set(cellKey(cell.x, cell.y, cell.z), piece);
    }
    return occupancy;
  }

  // ===== Moves =====
  // A move is { pieceId, to, cells, captureIds }.
  //   to:     { x, y, z } for most pieces, { file, plane } for a pawn
  //   cells:  the cells to highlight for this move (a whole row for pawns)
  //   captureIds: ids of enemy pieces this move takes

  function makeCellMove(piece, x, y, z, capturedPiece) {
    return {
      pieceId: piece.id,
      to: { x, y, z },
      cells: [{ x, y, z }],
      captureIds: capturedPiece ? [capturedPiece.id] : [],
    };
  }

  function makeRowMove(piece, file, plane, captureIds) {
    return { pieceId: piece.id, to: { file, plane }, cells: rowCells(file, plane), captureIds };
  }

  /**
   * Pawns guard the diagonal they stand across. A step like (0, +1, +1) jumps
   * from plane p to plane p+2, passing exactly through the edge where two
   * cells of the row on plane p+1 meet. If one pawn fills both of those cells,
   * the step goes straight through the pawn, so it is blocked (for both sides,
   * and it does not capture the pawn).
   */
  function stepCrossesPawn(fromX, fromY, fromZ, dx, dy, dz, occupancy) {
    if (dx !== 0 || dy === 0 || dy !== dz) return false;
    const besideOne = occupancy.get(cellKey(fromX, fromY + dy, fromZ));
    const besideTwo = occupancy.get(cellKey(fromX, fromY, fromZ + dz));
    return Boolean(besideOne && besideOne === besideTwo && besideOne.type === "pawn");
  }

  /** Moves for king, queen, rook and bishop: walk each direction until blocked. */
  function slidingMoves(piece, occupancy, maximumSteps) {
    const moves = [];
    for (const [dx, dy, dz] of PIECE_DIRECTIONS[piece.type]) {
      for (let step = 1; step <= maximumSteps; step++) {
        const x = piece.x + dx * step;
        const y = piece.y + dy * step;
        const z = piece.z + dz * step;
        if (!isInsideBoard(x, y, z)) break;
        if (stepCrossesPawn(x - dx, y - dy, z - dz, dx, dy, dz, occupancy)) break;
        const occupant = occupancy.get(cellKey(x, y, z));
        if (occupant && occupant.side === piece.side) break;
        moves.push(makeCellMove(piece, x, y, z, occupant));
        if (occupant) break; // captured; cannot slide past it
      }
    }
    return moves;
  }

  function knightMoves(piece, occupancy) {
    const moves = [];
    for (const [dx, dy, dz] of KNIGHT_JUMPS) {
      const x = piece.x + dx;
      const y = piece.y + dy;
      const z = piece.z + dz;
      if (!isInsideBoard(x, y, z)) continue;
      const occupant = occupancy.get(cellKey(x, y, z));
      if (occupant && occupant.side === piece.side) continue;
      moves.push(makeCellMove(piece, x, y, z, occupant));
    }
    return moves;
  }

  /** Everything (other than `ignorePiece`) found in a row, split by side. */
  function piecesInRow(file, plane, occupancy, ignorePiece) {
    const found = new Map();
    for (const cell of rowCells(file, plane)) {
      const occupant = occupancy.get(cellKey(cell.x, cell.y, cell.z));
      if (occupant && occupant !== ignorePiece) found.set(occupant.id, occupant);
    }
    return [...found.values()];
  }

  function pawnMoves(piece, occupancy) {
    const moves = [];
    const forward = forwardDirection(piece.side);

    // Step forward one plane, or two from the starting plane, into empty rows.
    const maximumSteps = piece.plane === pawnStartPlane(piece.side) ? 2 : 1;
    for (let step = 1; step <= maximumSteps; step++) {
      const plane = piece.plane + forward * step;
      if (plane < 0 || plane > LAST_PLANE) break;
      if (piecesInRow(piece.file, plane, occupancy, piece).length > 0) break;
      moves.push(makeRowMove(piece, piece.file, plane, []));
    }

    // Capture one plane forward and one file to the side.
    const capturePlane = piece.plane + forward;
    if (capturePlane >= 0 && capturePlane <= LAST_PLANE) {
      for (const file of [piece.file - 1, piece.file + 1]) {
        if (file < 0 || file > LAST_INDEX) continue;
        const occupants = piecesInRow(file, capturePlane, occupancy, piece);
        const hasFriend = occupants.some((occupant) => occupant.side === piece.side);
        const enemies = occupants.filter((occupant) => occupant.side !== piece.side);
        if (!hasFriend && enemies.length > 0) {
          moves.push(makeRowMove(piece, file, capturePlane, enemies.map((enemy) => enemy.id)));
        }
      }
    }
    return moves;
  }

  /** Classic-rule moves for one piece. */
  function getClassicMoves(piece, pieces) {
    const occupancy = buildOccupancy(pieces);
    switch (piece.type) {
      case "king": return slidingMoves(piece, occupancy, 1);
      case "queen":
      case "rook":
      case "bishop": return slidingMoves(piece, occupancy, LAST_INDEX);
      case "knight": return knightMoves(piece, occupancy);
      case "pawn": return pawnMoves(piece, occupancy);
      default: return [];
    }
  }

  /**
   * Free-mode moves: the piece may go to any spot in the chosen plane that is
   * not blocked by its own side. Anything of the other side there is captured.
   */
  function getFreeMoves(piece, pieces, plane) {
    const occupancy = buildOccupancy(pieces);
    const moves = [];
    if (piece.type === "pawn") {
      for (let file = 0; file <= LAST_INDEX; file++) {
        if (file === piece.file && plane === piece.plane) continue;
        const occupants = piecesInRow(file, plane, occupancy, piece);
        if (occupants.some((occupant) => occupant.side === piece.side)) continue;
        moves.push(makeRowMove(piece, file, plane, occupants.map((occupant) => occupant.id)));
      }
      return moves;
    }
    for (const cell of planeCells(plane)) {
      if (cell.x === piece.x && cell.y === piece.y && cell.z === piece.z) continue;
      const occupant = occupancy.get(cellKey(cell.x, cell.y, cell.z));
      if (occupant && occupant.side === piece.side) continue;
      moves.push(makeCellMove(piece, cell.x, cell.y, cell.z, occupant));
    }
    return moves;
  }

  /** The plane a piece is standing in. */
  function planeOfPiece(piece) {
    return piece.type === "pawn" ? piece.plane : piece.y + piece.z;
  }

  // ===== Making moves =====

  function describePlace(piece) {
    if (piece.type === "pawn") return "file " + piece.file + " plane " + piece.plane;
    return piece.x + "," + piece.y + "," + piece.z;
  }

  /** True if this pawn move lands on the far edge and the pawn should promote. */
  function needsPromotion(piece) {
    return piece.type === "pawn" && piece.plane === promotionPlane(piece.side);
  }

  /**
   * Apply a move to a game (changes it in place) and return a short report.
   * The caller should copy the game first if it wants undo.
   */
  function applyMove(game, move) {
    const piece = game.pieces.find((candidate) => candidate.id === move.pieceId);
    if (!piece) return null;
    const from = describePlace(piece);

    const capturedPieces = game.pieces.filter((candidate) => move.captureIds.includes(candidate.id));
    game.pieces = game.pieces.filter((candidate) => !move.captureIds.includes(candidate.id));
    for (const captured of capturedPieces) game.captured.push({ side: captured.side, type: captured.type });

    if (piece.type === "pawn") {
      piece.file = move.to.file;
      piece.plane = move.to.plane;
    } else {
      piece.x = move.to.x;
      piece.y = move.to.y;
      piece.z = move.to.z;
    }

    let line = piece.side + " " + piece.type + " " + from + " -> " + describePlace(piece);
    if (capturedPieces.length > 0) {
      line += " takes " + capturedPieces.map((captured) => captured.side + " " + captured.type).join(", ");
    }
    game.moveLog.push(line);
    game.turn = otherSide(piece.side);

    const kingTaken = capturedPieces.find((captured) => captured.type === "king");
    return { piece, capturedPieces, kingTaken: kingTaken || null, needsPromotion: needsPromotion(piece) };
  }

  /** Turn a pawn into another piece, standing in the single cell at the end of its row. */
  function promotePawn(game, pawnId, newType) {
    const pawn = game.pieces.find((candidate) => candidate.id === pawnId);
    if (!pawn || pawn.type !== "pawn") return;
    const cell = rowCells(pawn.file, pawn.plane)[0];
    delete pawn.file;
    delete pawn.plane;
    pawn.type = newType;
    pawn.x = cell.x;
    pawn.y = cell.y;
    pawn.z = cell.z;
    game.moveLog.push(pawn.side + " pawn promotes to " + newType);
  }

  /** Take a piece off the board by hand (the old "put it off the board" capture). */
  function removePiece(game, pieceId) {
    const piece = game.pieces.find((candidate) => candidate.id === pieceId);
    if (!piece) return;
    game.pieces = game.pieces.filter((candidate) => candidate !== piece);
    game.captured.push({ side: piece.side, type: piece.type });
    game.moveLog.push(piece.side + " " + piece.type + " at " + describePlace(piece) + " removed from the board");
  }

  /** Is this side's king attacked by any enemy piece right now? */
  function isInCheck(side, pieces) {
    const king = pieces.find((piece) => piece.side === side && piece.type === "king");
    if (!king) return false;
    for (const enemy of pieces) {
      if (enemy.side === side) continue;
      const moves = getClassicMoves(enemy, pieces);
      if (moves.some((move) => move.captureIds.includes(king.id))) return true;
    }
    return false;
  }

  // ===== Saving and loading (.txt) =====

  const SAVE_FORMAT_LINE = "format: diagonal-3d-chess 1";

  function gameToText(game) {
    const lines = [
      "# Diagonal 3D Chess — saved game",
      "# Saved " + new Date().toLocaleString(),
      "#",
      "# You can edit this file by hand to set up puzzles. Lines starting with # are ignored.",
      "# Cells are x y z, each 0-7. x is the file (left to right).",
      "# Red's home edge is y=0 z=0. Black's home edge is y=7 z=7.",
      "# Pawns fill a whole upright row, written as: file <0-7> plane <0-14>  (plane = y + z).",
      "# Piece types: king queen rook bishop knight pawn. Sides: red black.",
      "# Marker colours: " + MARKER_COLORS.join(" "),
      "",
      SAVE_FORMAT_LINE,
      "turn: " + game.turn,
      "",
    ];
    for (const side of SIDES) {
      for (const piece of game.pieces.filter((candidate) => candidate.side === side)) {
        if (piece.type === "pawn") {
          lines.push("piece: " + side + " pawn file " + piece.file + " plane " + piece.plane);
        } else {
          lines.push("piece: " + side + " " + piece.type + " at " + piece.x + " " + piece.y + " " + piece.z);
        }
      }
      lines.push("");
    }
    for (const marker of game.markers) {
      lines.push("marker: " + marker.color + " at " + marker.x + " " + marker.y + " " + marker.z);
    }
    for (const captured of game.captured) {
      lines.push("captured: " + captured.side + " " + captured.type);
    }
    if (game.moveLog.length > 0) {
      lines.push("", "# Moves so far (kept for the record; not needed to load the game)");
      game.moveLog.forEach((line, index) => lines.push("move: " + (index + 1) + ". " + line));
    }
    return lines.join("\n") + "\n";
  }

  function readNumbers(text) {
    return (text.match(/-?\d+/g) || []).map(Number);
  }

  /**
   * Read a saved .txt back into a game. Returns { game, warnings }.
   * Unknown or broken lines are skipped with a warning instead of failing,
   * so hand-written puzzle files are forgiving.
   */
  function textToGame(text) {
    const game = { pieces: [], markers: [], captured: [], turn: "red", moveLog: [] };
    const warnings = [];
    const lines = text.split(/\r?\n/);

    lines.forEach((rawLine, index) => {
      const line = rawLine.trim();
      if (line === "" || line.startsWith("#")) return;
      const colon = line.indexOf(":");
      if (colon === -1) {
        warnings.push("Line " + (index + 1) + " skipped: " + line);
        return;
      }
      const label = line.slice(0, colon).trim().toLowerCase();
      const value = line.slice(colon + 1).trim();
      const words = value.toLowerCase().split(/\s+/);

      if (label === "format") return;
      if (label === "turn") {
        if (SIDES.includes(words[0])) game.turn = words[0];
        return;
      }
      if (label === "move") {
        game.moveLog.push(value.replace(/^\d+\.\s*/, ""));
        return;
      }
      if (label === "captured") {
        if (SIDES.includes(words[0]) && PIECE_TYPES.includes(words[1])) {
          game.captured.push({ side: words[0], type: words[1] });
        }
        return;
      }
      if (label === "marker") {
        const [x, y, z] = readNumbers(value);
        if (MARKER_COLORS.includes(words[0]) && isInsideBoard(x, y, z)) {
          game.markers.push({ id: "m" + nextPieceNumber++, color: words[0], x, y, z });
        } else {
          warnings.push("Line " + (index + 1) + " has a bad marker: " + line);
        }
        return;
      }
      if (label === "piece") {
        const side = words[0];
        const type = words[1];
        const numbers = readNumbers(value);
        if (!SIDES.includes(side) || !PIECE_TYPES.includes(type)) {
          warnings.push("Line " + (index + 1) + " has an unknown piece: " + line);
          return;
        }
        if (type === "pawn") {
          const [file, plane] = numbers;
          if (rowCells(file, plane).length === 0) {
            warnings.push("Line " + (index + 1) + " puts a pawn off the board: " + line);
            return;
          }
          game.pieces.push(makePiece(side, "pawn", { file, plane }));
        } else {
          const [x, y, z] = numbers;
          if (!isInsideBoard(x, y, z)) {
            warnings.push("Line " + (index + 1) + " puts a piece off the board: " + line);
            return;
          }
          game.pieces.push(makePiece(side, type, { x, y, z }));
        }
        return;
      }
      warnings.push("Line " + (index + 1) + " not understood: " + line);
    });

    if (game.pieces.length === 0) warnings.push("No pieces were found in this file.");
    return { game, warnings };
  }

  // ===== Markers =====
  // Six coloured "place holder" cubes, from the 2006 version, to help plan moves.
  const MARKER_COLORS = ["red", "orange", "yellow", "green", "blue", "purple"];

  function toggleMarker(game, color, cell) {
    const existing = game.markers.find((marker) => marker.x === cell.x && marker.y === cell.y && marker.z === cell.z);
    if (existing) {
      game.markers = game.markers.filter((marker) => marker !== existing);
    } else {
      game.markers.push({ id: "m" + nextPieceNumber++, color, x: cell.x, y: cell.y, z: cell.z });
    }
  }

  // ===== Public interface =====

  return {
    BOARD_SIZE,
    LAST_INDEX,
    LAST_PLANE,
    SIDES,
    PIECE_TYPES,
    PIECE_DESCRIPTIONS,
    MARKER_COLORS,
    DIRECTIONS,
    KNIGHT_JUMPS,
    isInsideBoard,
    cellKey,
    rowCells,
    planeCells,
    cellsOfPiece,
    planeOfPiece,
    otherSide,
    makePiece,
    createNewGame,
    copyGame,
    buildOccupancy,
    getClassicMoves,
    getFreeMoves,
    applyMove,
    promotePawn,
    removePiece,
    isInCheck,
    toggleMarker,
    gameToText,
    textToGame,
    describePlace,
  };
})();

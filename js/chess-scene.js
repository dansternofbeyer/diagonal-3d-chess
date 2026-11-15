/*
 * chess-scene.js — the 3D drawing shared by the game and the studio.
 *
 * Builds the tilted glass board, the floor of rose tiles, the pieces (from the
 * Blender models in models/pieces.js), and the move highlights (glass cubes or
 * glowing dots). Needs three.js, OrbitControls and GLTFLoader loaded first
 * (see lib/), plus js/chess-rules.js and js/look-settings.js.
 *
 * Exposes one global object: window.ChessScene.
 *
 * Open source under the MIT License (see LICENSE).
 */
window.ChessScene = (function () {
  "use strict";

  const Rules = window.ChessRules;
  const SQRT2 = Math.SQRT2;
  const HALF_BOARD = Rules.BOARD_SIZE / 2;            // 4
  const LOWEST_POINT = -HALF_BOARD * SQRT2;           // bottom edge of the tilted cube
  const FLOOR_HEIGHT = LOWEST_POINT - 1.3;

  // ===== Look settings (colours, sizes) =====

  const LOOK_STORAGE_KEY = "diagonal-3d-chess.look";

  /** Defaults from look-settings.js, with any studio edits saved in this browser on top. */
  function loadLook() {
    const defaults = JSON.parse(JSON.stringify(window.CHESS_LOOK_DEFAULTS));
    try {
      const saved = JSON.parse(localStorage.getItem(LOOK_STORAGE_KEY) || "null");
      // Edits saved for older defaults (e.g. the white background) are dropped.
      if (saved && saved.lookVersion === defaults.lookVersion) {
        Object.assign(defaults, saved);
        defaults.pieceScale = Object.assign({}, window.CHESS_LOOK_DEFAULTS.pieceScale, saved.pieceScale);
        defaults.pieceVersions = Object.assign({}, window.CHESS_LOOK_DEFAULTS.pieceVersions, saved.pieceVersions);
      }
    } catch (error) {
      // Storage can be blocked (private windows, some file:// setups). Defaults are fine.
    }
    return defaults;
  }

  function saveLook(look) {
    try {
      localStorage.setItem(LOOK_STORAGE_KEY, JSON.stringify(look));
      return true;
    } catch (error) {
      return false;
    }
  }

  function clearSavedLook() {
    try { localStorage.removeItem(LOOK_STORAGE_KEY); } catch (error) { /* nothing to clear */ }
  }

  /** The text of a look-settings.js file holding these settings. */
  function lookToFileText(look) {
    return [
      "/*",
      " * look-settings.js — the default colours and sizes for the pieces and board.",
      " * Downloaded from game-studio.html on " + new Date().toLocaleString() + ".",
      " * Open source under the MIT License (see ../LICENSE).",
      " */",
      "window.CHESS_LOOK_DEFAULTS = " + JSON.stringify(look, null, 2) + ";",
      "",
    ].join("\n");
  }

  // ===== Board geometry =====
  // Cube space: x, y, z centred on the cube (-3.5 .. 3.5). World space: the cube
  // turned 45 degrees so Red's edge faces the viewer (+Z) and Black's faces away.

  /** The rotation from cube space to world space. */
  function createCubeToWorldMatrix() {
    const cubeX = new THREE.Vector3(1, 0, 0);
    const cubeY = new THREE.Vector3(0, -1 / SQRT2, -1 / SQRT2);
    const cubeZ = new THREE.Vector3(0, 1 / SQRT2, -1 / SQRT2);
    return new THREE.Matrix4().makeBasis(cubeX, cubeY, cubeZ);
  }

  const CUBE_TO_WORLD = createCubeToWorldMatrix();

  /** A group whose children are placed in cube space (they come out tilted). */
  function createCubeSpaceGroup() {
    const group = new THREE.Group();
    group.matrixAutoUpdate = false;
    group.matrix.copy(CUBE_TO_WORLD);
    return group;
  }

  function cellToCubeSpace(x, y, z) {
    const offset = HALF_BOARD - 0.5;
    return new THREE.Vector3(x - offset, y - offset, z - offset);
  }

  function cellToWorld(x, y, z) {
    return cellToCubeSpace(x, y, z).applyMatrix4(CUBE_TO_WORLD);
  }

  // ===== Textures =====

  /**
   * An ornamental tile drawn on a canvas, in the spirit of the embossed glass
   * cubes on the 2006 site: a framed square with an eight-petal rosette.
   */
  function makeOrnamentTexture(baseColor, lineColor) {
    const size = 256;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");
    const middle = size / 2;

    context.fillStyle = baseColor;
    context.fillRect(0, 0, size, size);

    // Soft vignette so each face looks a little bevelled.
    const shade = context.createRadialGradient(middle, middle, size * 0.15, middle, middle, size * 0.75);
    shade.addColorStop(0, "rgba(255,255,255,0.35)");
    shade.addColorStop(1, "rgba(0,0,0,0.18)");
    context.fillStyle = shade;
    context.fillRect(0, 0, size, size);

    context.strokeStyle = lineColor;
    context.lineWidth = 6;
    context.strokeRect(10, 10, size - 20, size - 20);
    context.lineWidth = 2;
    context.strokeRect(24, 24, size - 48, size - 48);

    // Rosette: eight petals around a small centre.
    context.lineWidth = 3;
    for (let petal = 0; petal < 8; petal++) {
      const angle = (petal / 8) * Math.PI * 2;
      context.save();
      context.translate(middle, middle);
      context.rotate(angle);
      context.beginPath();
      context.ellipse(0, -size * 0.17, size * 0.06, size * 0.15, 0, 0, Math.PI * 2);
      context.stroke();
      context.restore();
    }
    context.beginPath();
    context.arc(middle, middle, size * 0.06, 0, Math.PI * 2);
    context.stroke();
    context.beginPath();
    context.arc(middle, middle, size * 0.36, 0, Math.PI * 2);
    context.stroke();

    // Little corner diamonds.
    for (const [cornerX, cornerY] of [[44, 44], [size - 44, 44], [44, size - 44], [size - 44, size - 44]]) {
      context.beginPath();
      context.moveTo(cornerX, cornerY - 10);
      context.lineTo(cornerX + 10, cornerY);
      context.lineTo(cornerX, cornerY + 10);
      context.lineTo(cornerX - 10, cornerY);
      context.closePath();
      context.stroke();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.encoding = THREE.sRGBEncoding;
    texture.anisotropy = 4;
    return texture;
  }

  /** A soft round glow, used behind the move dots. */
  function makeGlowTexture() {
    const size = 128;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");
    const glow = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    glow.addColorStop(0, "rgba(255,255,255,1)");
    glow.addColorStop(0.25, "rgba(255,255,255,0.6)");
    glow.addColorStop(1, "rgba(255,255,255,0)");
    context.fillStyle = glow;
    context.fillRect(0, 0, size, size);
    return new THREE.CanvasTexture(canvas);
  }

  function darkerColor(hexColor, amount) {
    const color = new THREE.Color(hexColor);
    color.multiplyScalar(1 - amount);
    return "#" + color.getHexString();
  }

  /** The same colour with its lightness raised by `amount` (0..1). Used for the trim. */
  function lighterColor(hexColor, amount) {
    const color = new THREE.Color(hexColor);
    const hsl = {};
    color.getHSL(hsl);
    color.setHSL(hsl.h, hsl.s, Math.min(1, hsl.l + amount));
    return "#" + color.getHexString();
  }

  // ===== Lighting: a hand-written "photo studio" for reflections =====

  /*
   * The shiny look comes from reflections. Instead of loading a photo of a
   * room, this shader paints one: a dark room with a big bright softbox
   * straight overhead (the main light, above the board), a warm panel in front
   * and a cool one behind. three.js turns it into an environment map that every
   * piece, glass bar and tile reflects.
   */
  const STUDIO_VERTEX_SHADER = `
    varying vec3 vDirection;
    void main() {
      vDirection = normalize(position);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `;

  const STUDIO_FRAGMENT_SHADER = `
    varying vec3 vDirection;

    // A soft-edged round light centred on a direction. Brightness can go above 1
    // so reflections of it really glow.
    float softPanel(vec3 direction, vec3 centre, float size) {
      float closeness = dot(direction, normalize(centre));
      return smoothstep(1.0 - size, 1.0 - size * 0.55, closeness);
    }

    // A tall, thin strip light standing at one compass angle, like a studio
    // strip box. Upright faces of the pieces catch it as a bright line.
    float stripLight(vec3 direction, float angle) {
      vec2 compass = normalize(direction.xz + 1e-5);
      float closeness = dot(compass, vec2(cos(angle), sin(angle)));
      float across = smoothstep(0.9975, 0.9993, closeness);
      float along = 1.0 - smoothstep(0.35, 0.6, abs(direction.y - 0.1));
      return across * along;
    }

    void main() {
      vec3 direction = normalize(vDirection);

      // Dark room: a bit lighter around the horizon so edges catch some light.
      float horizon = 1.0 - abs(direction.y);
      vec3 room = vec3(0.012, 0.012, 0.016) + vec3(0.035, 0.032, 0.03) * pow(horizon, 4.0);

      // The main light: a small, very bright softbox directly above the board.
      // Small and bright gives crisp highlights without washing out the colour.
      vec3 overhead = vec3(1.0, 0.97, 0.92) * 16.0 * softPanel(direction, vec3(0.0, 1.0, 0.0), 0.03);

      // Strip lights around the sides: warm in front, cool behind.
      vec3 strips = vec3(1.0, 0.88, 0.75) * 2.5 * (stripLight(direction, 1.2) + stripLight(direction, 2.4))
                  + vec3(0.7, 0.82, 1.0) * 3.0 * (stripLight(direction, -0.7) + stripLight(direction, -2.5));

      gl_FragColor = vec4(room + overhead + strips, 1.0);
    }
  `;

  /** Paint the studio room once and turn it into an environment map. */
  function createStudioEnvironment(renderer) {
    const roomScene = new THREE.Scene();
    const room = new THREE.Mesh(
      new THREE.SphereGeometry(10, 64, 32),
      new THREE.ShaderMaterial({
        vertexShader: STUDIO_VERTEX_SHADER,
        fragmentShader: STUDIO_FRAGMENT_SHADER,
        side: THREE.BackSide,
        depthWrite: false,
      })
    );
    roomScene.add(room);
    const generator = new THREE.PMREMGenerator(renderer);
    const environment = generator.fromScene(roomScene, 0.01).texture;
    generator.dispose();
    return environment;
  }

  /*
   * Rim light: a small addition to three.js's own material shader. Where a
   * surface turns away from the camera (the outline of a piece) it gets a soft
   * glow, so dark pieces stand out against the dark background.
   */
  /*
   * Wood grain, painted by the shader rather than an image (the models have no
   * texture coordinates to wrap a photo onto). Each piece is treated as if it
   * were turned from a log whose trunk runs up the piece, a little off to one
   * side: the growth rings then show as long, gently wavy stripes, with fine
   * fibres between them, like the grain in docs' wood photos. The colours of
   * the light and dark wood come from the look settings.
   */
  const WOOD_SHADER_FUNCTIONS = `
    uniform vec3 woodLight;
    uniform vec3 woodDark;
    uniform float woodAmount;
    varying vec3 vWoodPosition;

    float woodHash(vec3 p) {
      p = fract(p * 0.3183099 + 0.1);
      p *= 17.0;
      return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
    }

    // Smooth random values in 3D (value noise), for the waviness of the grain.
    float woodNoise(vec3 p) {
      vec3 cell = floor(p);
      vec3 f = fract(p);
      f = f * f * (3.0 - 2.0 * f);
      return mix(
        mix(mix(woodHash(cell), woodHash(cell + vec3(1, 0, 0)), f.x),
            mix(woodHash(cell + vec3(0, 1, 0)), woodHash(cell + vec3(1, 1, 0)), f.x), f.y),
        mix(mix(woodHash(cell + vec3(0, 0, 1)), woodHash(cell + vec3(1, 0, 1)), f.x),
            mix(woodHash(cell + vec3(0, 1, 1)), woodHash(cell + vec3(1, 1, 1)), f.x), f.y),
        f.z);
    }

    vec3 woodColor(vec3 p) {
      // Waviness: the rings bend slowly along the trunk (Y), like real grain.
      vec3 stretched = p * vec3(1.0, 0.3, 1.0);
      float warp = woodNoise(stretched * 2.5) * 0.7 + woodNoise(stretched * 7.0) * 0.3;
      // Distance from the (off-centre) trunk counts the growth rings.
      float rings = length(p.xz + vec2(0.85, 0.3)) * 15.0 + warp * 2.6 + p.y * 0.9;
      float ring = fract(rings);
      // Each ring: pale wood that darkens toward a thin dark line.
      float band = smoothstep(0.0, 0.2, ring) * (1.0 - smoothstep(0.55, 1.0, ring));
      // Fine fibres running along the grain.
      float fibres = woodNoise(vec3(p.x * 110.0, p.y * 5.0, p.z * 110.0));
      float tone = clamp(band * 0.78 + fibres * 0.28, 0.0, 1.0);
      return mix(woodDark, woodLight, tone);
    }
  `;

  /*
   * Additions to three.js's own material shader for the pieces:
   *   - rim light: where a surface turns away from the camera (a piece's
   *     outline) it gets a soft glow, so dark pieces stand out
   *   - wood grain (see above), when the finish is wood
   * `options`: { rimColor, rimStrength, woodLight, woodDark, wood (true/false) }
   */
  function addPieceShader(material, options) {
    material.userData.pieceShaderOptions = options;
    material.userData.pieceUniforms = {
      rimColor: { value: new THREE.Color(options.rimColor) },
      rimStrength: { value: options.rimStrength },
      // Converted to linear light, so the wood shows the colours picked (unconverted,
      // the screen's brightening would bleach the golden wood to pale birch).
      woodLight: { value: new THREE.Color(options.woodLight || "#ffffff").convertSRGBToLinear() },
      woodDark: { value: new THREE.Color(options.woodDark || "#000000").convertSRGBToLinear() },
      woodAmount: { value: options.wood ? 1 : 0 },
    };
    material.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, material.userData.pieceUniforms);
      shader.vertexShader = shader.vertexShader
        .replace("#include <common>", "#include <common>\nvarying vec3 vWoodPosition;")
        .replace("#include <begin_vertex>", "#include <begin_vertex>\nvWoodPosition = position;");
      shader.fragmentShader = shader.fragmentShader
        .replace("#include <common>", "#include <common>\nuniform vec3 rimColor;\nuniform float rimStrength;\n" + WOOD_SHADER_FUNCTIONS)
        .replace("#include <color_fragment>", [
          "#include <color_fragment>",
          "diffuseColor.rgb = mix(diffuseColor.rgb, woodColor(vWoodPosition), woodAmount);",
        ].join("\n"))
        .replace("#include <output_fragment>", [
          "float rimFacing = 1.0 - saturate(dot(normal, normalize(vViewPosition)));",
          "outgoingLight += rimColor * pow(rimFacing, 3.0) * rimStrength;",
          "#include <output_fragment>",
        ].join("\n"));
    };
    material.customProgramCacheKey = () => "piece-shader";
    return material;
  }

  // ===== Haze: depth fog =====

  /*
   * A light haze makes far things fade toward the background colour, so it is
   * easier to tell near pieces from far ones. `amount` 0..1 comes from the look
   * settings (studio "Haze" slider). The background dome ignores fog, so only
   * the board and pieces fade.
   */
  const HAZE_AT_FULL = 0.05;   // fog density when the slider is all the way up

  function setHaze(scene, amount, color) {
    const density = Math.max(0, Number(amount) || 0) * HAZE_AT_FULL;
    if (density <= 0) {
      scene.fog = null;
      return;
    }
    if (!scene.fog) scene.fog = new THREE.FogExp2(color, density);
    scene.fog.color.set(color);
    scene.fog.density = density;
  }

  // ===== Background: a soft gradient dome =====

  /*
   * A huge sphere around the camera, coloured by height: a little lighter
   * above the horizon and a little darker below, around the look setting's
   * background colour. It moves with the camera so it always looks infinitely far.
   */
  const SKY_FRAGMENT_SHADER = `
    uniform vec3 middleColor;
    uniform vec3 topColor;
    uniform vec3 bottomColor;
    varying vec3 vDirection;
    void main() {
      float height = normalize(vDirection).y;
      vec3 color = height > 0.0
        ? mix(middleColor, topColor, smoothstep(0.0, 0.8, height))
        : mix(middleColor, bottomColor, smoothstep(0.0, 0.6, -height));
      gl_FragColor = vec4(color, 1.0);
    }
  `;

  function createSkyDome(backgroundColor) {
    const material = new THREE.ShaderMaterial({
      vertexShader: STUDIO_VERTEX_SHADER,
      fragmentShader: SKY_FRAGMENT_SHADER,
      uniforms: {
        middleColor: { value: new THREE.Color() },
        topColor: { value: new THREE.Color() },
        bottomColor: { value: new THREE.Color() },
      },
      side: THREE.BackSide,
      depthWrite: false,
      toneMapped: false,
    });
    const dome = new THREE.Mesh(new THREE.SphereGeometry(300, 32, 16), material);
    dome.renderOrder = -10;
    dome.frustumCulled = false;
    setSkyColors(dome, backgroundColor);
    return dome;
  }

  function setSkyColors(dome, backgroundColor) {
    const uniforms = dome.material.uniforms;
    uniforms.middleColor.value.set(backgroundColor);
    uniforms.topColor.value.set(lighterColor(backgroundColor, 0.07));
    uniforms.bottomColor.value.set(darkerColor(backgroundColor, 0.45));
  }

  /** Copy a piece material, keeping its shader additions (a plain clone would lose them). */
  function clonePieceMaterial(material) {
    const copy = material.clone();
    const options = material.userData.pieceShaderOptions;
    if (options) addPieceShader(copy, options);
    return copy;
  }

  // ===== Viewer (renderer, camera, controls) =====

  /**
   * Named camera spots. The 2006 version had six preset-view buttons; the free
   * orbit controls replaced them, so only the starting view is left.
   */
  const VIEW_PRESETS = {
    corner: { position: [15, 13, 21], label: "Corner" },
  };

  /**
   * Make a renderer, camera, lights and orbit controls inside `container`.
   * Left-drag spins; right-drag, middle-drag (mouse wheel held down) or two
   * fingers pan; scrolling the wheel or pinching zooms.
   */
  function createViewer(container, look) {
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    // Filmic tone mapping lets bright highlights roll off softly instead of clipping.
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(look.backgroundColor); // shows only if the dome fails
    const skyDome = createSkyDome(look.backgroundColor);
    scene.add(skyDome);
    setHaze(scene, look.haze, look.backgroundColor);
    scene.environment = createStudioEnvironment(renderer);

    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 400);
    camera.position.set(...VIEW_PRESETS.corner.position);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 3;
    controls.maxDistance = 70;
    controls.zoomSpeed = 0.7; // the old zoom was "a little touchy"
    controls.target.set(0, -0.5, 0);
    // Middle-drag pans (like many 3D programs); the wheel still zooms when scrolled.
    controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.PAN };
    // Stop the browser's own middle-click auto-scroll from starting over the board.
    renderer.domElement.addEventListener("mousedown", (event) => {
      if (event.button === 1) event.preventDefault();
    });

    // The global light: straight down from above the board, matching the
    // overhead softbox in the reflections. A dim sky/ground fill keeps shadows soft.
    scene.add(new THREE.HemisphereLight(0xcfdcff, 0x2a1d18, 0.22));
    const overheadLight = new THREE.DirectionalLight(0xfff6ea, 1.5);
    overheadLight.position.set(0.5, 20, 1);
    scene.add(overheadLight);
    const frontFill = new THREE.DirectionalLight(0xffffff, 0.12);
    frontFill.position.set(-6, 4, 14);
    scene.add(frontFill);

    const frameCallbacks = [];
    let cameraFlight = null;

    function resize() {
      const width = container.clientWidth || 1;
      const height = container.clientHeight || 1;
      renderer.setSize(width, height, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }
    new ResizeObserver(resize).observe(container);
    resize();

    /** Glide the camera to a preset view over about half a second. */
    function flyTo(presetName, distanceScale) {
      const preset = VIEW_PRESETS[presetName];
      if (!preset) return;
      const scale = distanceScale || 1;
      cameraFlight = {
        fromPosition: camera.position.clone(),
        toPosition: new THREE.Vector3(...preset.position).multiplyScalar(scale),
        fromTarget: controls.target.clone(),
        toTarget: new THREE.Vector3(0, -0.5, 0),
        progress: 0,
      };
    }

    function updateCameraFlight(deltaSeconds) {
      if (!cameraFlight) return;
      cameraFlight.progress = Math.min(1, cameraFlight.progress + deltaSeconds * 2);
      const eased = 1 - Math.pow(1 - cameraFlight.progress, 3);
      camera.position.lerpVectors(cameraFlight.fromPosition, cameraFlight.toPosition, eased);
      controls.target.lerpVectors(cameraFlight.fromTarget, cameraFlight.toTarget, eased);
      if (cameraFlight.progress >= 1) cameraFlight = null;
    }

    const clock = new THREE.Clock();
    function animate() {
      requestAnimationFrame(animate);
      const deltaSeconds = Math.min(clock.getDelta(), 0.1);
      updateCameraFlight(deltaSeconds);
      controls.update();
      for (const callback of frameCallbacks) callback(deltaSeconds, clock.elapsedTime);
      skyDome.position.copy(camera.position);
      renderer.render(scene, camera);
    }
    animate();

    return {
      renderer,
      scene,
      camera,
      controls,
      flyTo,
      onFrame: (callback) => frameCallbacks.push(callback),
      stopCameraFlight: () => { cameraFlight = null; },
      setBackgroundColor: (color) => {
        scene.background = new THREE.Color(color);
        setSkyColors(skyDome, color);
      },
      setHaze: (amount, color) => setHaze(scene, amount, color),
    };
  }

  // ===== The board =====

  /** The twelve glass bars along the edges of the tilted cube. */
  function buildFrame(look) {
    const group = createCubeSpaceGroup();
    const material = new THREE.MeshStandardMaterial({
      color: look.frameColor,
      transparent: true,
      opacity: look.frameOpacity,
      roughness: 0.15,
      metalness: 0.1,
      depthWrite: false,
    });
    const edgeLength = Rules.BOARD_SIZE + 0.12;
    const barThickness = 0.09;
    for (const axis of [0, 1, 2]) {
      for (const sideA of [-HALF_BOARD, HALF_BOARD]) {
        for (const sideB of [-HALF_BOARD, HALF_BOARD]) {
          const size = [barThickness, barThickness, barThickness];
          size[axis] = edgeLength;
          const bar = new THREE.Mesh(new THREE.BoxGeometry(...size), material);
          const position = [sideA, sideB];
          position.splice(axis, 0, 0);
          bar.position.set(...position);
          group.add(bar);
        }
      }
    }
    // Thin lines over the bars, so the frame edges read clearly.
    const outline = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(Rules.BOARD_SIZE, Rules.BOARD_SIZE, Rules.BOARD_SIZE)),
      new THREE.LineBasicMaterial({ color: look.frameColor, transparent: true, opacity: 0.45 })
    );
    group.add(outline);
    return group;
  }

  /** The square ring of rose glass tiles on the ground, as on the 2006 site. */
  function buildFloorRing(look) {
    const ringHalfWidth = 11;
    const tilePositions = [];
    for (let step = -ringHalfWidth; step < ringHalfWidth; step++) {
      tilePositions.push([step + 0.5, -ringHalfWidth + 0.5]);
      tilePositions.push([step + 0.5, ringHalfWidth - 0.5]);
    }
    for (let step = -ringHalfWidth + 1; step < ringHalfWidth - 1; step++) {
      tilePositions.push([-ringHalfWidth + 0.5, step + 0.5]);
      tilePositions.push([ringHalfWidth - 0.5, step + 0.5]);
    }
    const material = new THREE.MeshStandardMaterial({
      map: makeOrnamentTexture(look.floorColor, darkerColor(look.floorColor, 0.25)),
      transparent: true,
      opacity: look.floorOpacity,
      roughness: 0.4,
      depthWrite: false,
    });
    const tiles = new THREE.InstancedMesh(new THREE.BoxGeometry(0.96, 0.96, 0.96), material, tilePositions.length);
    const placement = new THREE.Matrix4();
    tilePositions.forEach(([x, z], index) => {
      placement.makeTranslation(x, FLOOR_HEIGHT, z);
      tiles.setMatrixAt(index, placement);
    });
    return tiles;
  }

  /** A faint dot at the centre of every one of the 512 cells. */
  function buildCellGrid() {
    const positions = [];
    for (let x = 0; x < Rules.BOARD_SIZE; x++) {
      for (let y = 0; y < Rules.BOARD_SIZE; y++) {
        for (let z = 0; z < Rules.BOARD_SIZE; z++) {
          const point = cellToCubeSpace(x, y, z);
          positions.push(point.x, point.y, point.z);
        }
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    const points = new THREE.Points(geometry, new THREE.PointsMaterial({
      color: 0x8aa3b0, size: 0.07, transparent: true, opacity: 0.6,
    }));
    const group = createCubeSpaceGroup();
    group.add(points);
    return group;
  }

  /** The whole board: frame, floor ring and (hidden until asked) the cell grid. */
  function buildBoard(look) {
    const board = new THREE.Group();
    board.name = "board";
    board.add(buildFrame(look));
    board.add(buildFloorRing(look));
    const grid = buildCellGrid();
    grid.visible = false;
    board.add(grid);
    board.userData.cellGrid = grid;
    return board;
  }

  // ===== Pieces =====

  /** Decode a base64 string into an ArrayBuffer. */
  function base64ToArrayBuffer(base64Text) {
    const binary = atob(base64Text);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
    return bytes.buffer;
  }

  function parseGlb(arrayBuffer) {
    return new Promise((resolve, reject) => {
      new THREE.GLTFLoader().parse(arrayBuffer, "", (gltf) => resolve(gltf.scene), reject);
    });
  }

  /** Load every piece model from models/pieces.js. Resolves to { king: Object3D, ... }. */
  async function loadPieceModels() {
    const bundle = window.CHESS_PIECE_MODELS || {};
    const models = {};
    for (const name of Object.keys(bundle)) {
      models[name] = await parseGlb(base64ToArrayBuffer(bundle[name]));
    }
    return models;
  }

  /**
   * One shiny material: a glossy clear coat over the colour (like lacquer),
   * reflecting the studio environment, plus the rim light.
   */
  /**
   * One piece material: a glossy clear coat (lacquer, or varnish on wood) over
   * the colour, reflecting the studio environment, plus the rim light.
   * `wood`: null for a plain colour, or { light, dark } wood colours.
   */
  function createShinyMaterial(color, look, extraMetalness, wood) {
    const material = new THREE.MeshPhysicalMaterial({
      color,
      roughness: wood ? Math.max(look.pieceRoughness, 0.42) : look.pieceRoughness,
      metalness: wood ? 0 : Math.min(1, look.pieceMetalness + (extraMetalness || 0)),
      clearcoat: look.pieceShine,
      clearcoatRoughness: wood ? 0.12 : 0.06,
    });
    return addPieceShader(material, {
      rimColor: lighterColor(wood ? wood.light : color, 0.35),
      rimStrength: look.rimLight,
      woodLight: wood ? wood.light : null,
      woodDark: wood ? wood.dark : null,
      wood: Boolean(wood),
    });
  }

  /**
   * Body and trim materials for both sides. The trim is the body, a little
   * lighter. With the wood finish, Red is golden wood and Black dark walnut.
   */
  function createPieceMaterials(look) {
    const isWood = look.pieceFinish === "wood";
    const woodFor = (side, lighten) => (isWood ? {
      light: lighterColor(look[side + "WoodLight"], lighten),
      dark: lighterColor(look[side + "WoodDark"], lighten),
    } : null);
    return {
      red: createShinyMaterial(look.redColor, look, 0, woodFor("red", 0)),
      black: createShinyMaterial(look.blackColor, look, 0, woodFor("black", 0)),
      redTrim: createShinyMaterial(lighterColor(look.redColor, look.trimLighten), look, 0.2,
        woodFor("red", look.trimLighten)),
      blackTrim: createShinyMaterial(lighterColor(look.blackColor, look.trimLighten), look, 0.2,
        woodFor("black", look.trimLighten)),
    };
  }

  /** Copy a model and give it this side's colour (Blender "Body") and the trim colour. */
  function cloneModel(template, sideMaterial, trimMaterial) {
    const copy = template.clone(true);
    copy.traverse((child) => {
      if (child.isMesh) {
        const isTrim = child.material && child.material.name === "Trim";
        child.material = isTrim ? trimMaterial : sideMaterial;
      }
    });
    return copy;
  }

  /**
   * Build the 3D object for a pawn: a slab stretched to fill its upright row of
   * cells, with a crown cap on each end.
   */
  // ===== Piece versions =====
  // Each piece comes in several versions (see blender/build_classic_pieces.py):
  // "original" (the 2006-style pieces, models/king.glb) and the classic-styled
  // "ornate" and "classic" (models/king-ornate.glb, models/king-classic.glb). look.pieceVersions
  // says which one each piece uses.

  const PIECE_VERSIONS = [
    { id: "original", label: "Original" },
    { id: "ornate", label: "Ornate" },     // the original shapes with molding details
    { id: "classic", label: "Classic" },
  ];

  /**
   * The model for one part of a piece in a version. `part` is the model's base
   * name: "king", or "pawn_body" / "pawn_cap" for the pawn's two parts.
   * Falls back to the original if that version is missing.
   */
  function pieceModel(models, part, version) {
    if (version && version !== "original" && models[part + "-" + version]) return models[part + "-" + version];
    return models[part];
  }

  function versionOf(type, look) {
    const version = (look.pieceVersions && look.pieceVersions[type]) || "original";
    // "faceted" and "deco" were retired; their closest relative is "classic".
    return PIECE_VERSIONS.some((known) => known.id === version) ? version : "classic";
  }

  function buildPawnObject(cellCount, models, sideMaterial, trimMaterial, scale, version) {
    const group = new THREE.Group();
    const body = cloneModel(pieceModel(models, "pawn_body", version), sideMaterial, trimMaterial);
    const topCap = cloneModel(pieceModel(models, "pawn_cap", version), sideMaterial, trimMaterial);
    const bottomCap = cloneModel(pieceModel(models, "pawn_cap", version), sideMaterial, trimMaterial);
    bottomCap.rotation.z = Math.PI;
    topCap.scale.setScalar(scale);
    bottomCap.scale.setScalar(scale);
    group.add(body, topCap, bottomCap);
    group.userData.pawnParts = { body, topCap, bottomCap, scale };
    setPawnLength(group, cellCount);
    return group;
  }

  /**
   * Stretch a pawn to span `cellCount` cells. The count can be a fraction, so a
   * moving pawn can grow or shrink smoothly between rows.
   */
  function setPawnLength(pawnGroup, cellCount) {
    const parts = pawnGroup.userData.pawnParts;
    const bodyLength = Math.max(0.3, cellCount * SQRT2 - 0.64);
    parts.body.scale.set(parts.scale, bodyLength, parts.scale);
    parts.topCap.position.y = bodyLength / 2;
    parts.bottomCap.position.y = -bodyLength / 2;
  }

  /** How many cells a pawn spans on a plane: 1 at the edges, 8 in the middle. */
  function pawnCellCount(plane) {
    return Rules.rowCells(0, plane).length;
  }

  /** The world position of a piece (for a pawn, the middle of its row). */
  function pieceWorldPosition(piece) {
    const cells = Rules.cellsOfPiece(piece);
    const middle = new THREE.Vector3();
    for (const cell of cells) middle.add(cellToWorld(cell.x, cell.y, cell.z));
    return middle.divideScalar(cells.length);
  }

  /** Just the piece's shape (not yet placed), coloured for its side. */
  /** Turns a knight's +X face toward Black's side of the board (-Z). */
  const KNIGHT_TURN = Math.PI / 2;

  function buildPieceShape(side, type, cellCount, models, materials, look, versionOverride) {
    const sideMaterial = materials[side];
    const trimMaterial = materials[side + "Trim"];
    const scale = look.pieceScale[type] || 1;
    const version = versionOverride || versionOf(type, look);
    if (type === "pawn") return buildPawnObject(cellCount, models, sideMaterial, trimMaterial, scale, version);
    const object = cloneModel(pieceModel(models, type, version), sideMaterial, trimMaterial);
    object.scale.setScalar(scale);
    // Black's pieces face the other way, so the two armies mirror each other.
    // Knights are modelled facing +X (sideways); turn them to face the opponent.
    if (type === "knight") object.rotation.y = KNIGHT_TURN;
    if (side === "black") object.rotation.y += Math.PI;
    return object;
  }

  /** Build the 3D object for one piece, placed on the board. */
  /** `version` (optional) shows a piece in a version other than the look's choice. */
  function buildPieceObject(piece, models, materials, look, version) {
    const cellCount = piece.type === "pawn" ? Rules.cellsOfPiece(piece).length : 1;
    const holder = new THREE.Group();
    holder.add(buildPieceShape(piece.side, piece.type, cellCount, models, materials, look, version));
    holder.position.copy(pieceWorldPosition(piece));
    holder.userData.pieceId = piece.id;
    return holder;
  }

  // ===== Taken pieces, standing on the rose rail =====

  const RAIL_SPACING = 1.2;
  const RAIL_ROW = 10.5;                     // the middle of the tile ring's front and back rows
  const RAIL_TOP = FLOOR_HEIGHT + 0.48;      // the top face of the tiles

  /**
   * Where the nth taken piece of a side stands. A taken piece goes to the
   * other player's side of the rail, beside the player who took it. Each row
   * fills from that player's left.
   */
  function railPosition(takenSide, index) {
    const offset = -9.5 + index * RAIL_SPACING;
    // Red's pieces are taken by Black, who sits at the back (-z) looking forward.
    return takenSide === "red"
      ? new THREE.Vector3(-offset, RAIL_TOP, -RAIL_ROW)
      : new THREE.Vector3(offset, RAIL_TOP, RAIL_ROW);
  }

  /** A taken piece standing on the rail. Pawns are shown two cells tall. */
  function buildRailPiece(taken, index, models, materials, look) {
    const shape = buildPieceShape(taken.side, taken.type, 2, models, materials, look);
    // Lift the shape so its lowest point rests on the tile tops.
    const bounds = new THREE.Box3().setFromObject(shape);
    shape.position.y -= bounds.min.y;
    const holder = new THREE.Group();
    holder.add(shape);
    holder.position.copy(railPosition(taken.side, index));
    holder.userData.railIndex = index;
    return holder;
  }

  // ===== Move paths (for animating moves) =====

  /**
   * The points a piece travels through, in world space. Most pieces slide in a
   * straight line along their move. A knight's jump becomes an "L": first along
   * the long (two-cube) leg, then the short one.
   */
  function movePath(pieceBefore, pieceAfter) {
    const start = pieceWorldPosition(pieceBefore);
    const end = pieceWorldPosition(pieceAfter);
    if (pieceBefore.type !== "knight") return [start, end];

    const change = [pieceAfter.x - pieceBefore.x, pieceAfter.y - pieceBefore.y, pieceAfter.z - pieceBefore.z];
    const sizes = change.map(Math.abs).sort((first, second) => second - first);
    const isKnightJump = sizes[0] === 2 && sizes[1] === 1 && sizes[2] === 0;
    if (!isKnightJump) return [start, end]; // e.g. a free move: just slide

    const longAxis = change.findIndex((amount) => Math.abs(amount) === 2);
    const corner = [pieceBefore.x, pieceBefore.y, pieceBefore.z];
    corner[longAxis] += change[longAxis];
    return [start, cellToWorld(corner[0], corner[1], corner[2]), end];
  }

  /** The point a fraction (0..1) of the way along a path of straight legs. */
  function pointAlongPath(path, fraction) {
    const legLengths = [];
    let total = 0;
    for (let index = 1; index < path.length; index++) {
      const length = path[index].distanceTo(path[index - 1]);
      legLengths.push(length);
      total += length;
    }
    let remaining = fraction * total;
    for (let index = 0; index < legLengths.length; index++) {
      if (remaining <= legLengths[index] || index === legLengths.length - 1) {
        const legFraction = legLengths[index] > 0 ? Math.min(1, remaining / legLengths[index]) : 1;
        return path[index].clone().lerp(path[index + 1], legFraction);
      }
      remaining -= legLengths[index];
    }
    return path[path.length - 1].clone();
  }

  function pathLength(path) {
    let total = 0;
    for (let index = 1; index < path.length; index++) total += path[index].distanceTo(path[index - 1]);
    return total;
  }

  // ===== Move highlights =====

  const CUBE_GEOMETRY = new THREE.BoxGeometry(0.94, 0.94, 0.94);
  const DOT_GEOMETRY = new THREE.SphereGeometry(0.11, 16, 12);
  let glowTexture = null;

  /** A see-through glass cube material with the ornament tile, in one colour. */
  function makeGlassCubeMaterial(color, opacity) {
    return new THREE.MeshStandardMaterial({
      map: makeOrnamentTexture(color, darkerColor(color, 0.3)),
      transparent: true,
      opacity,
      depthWrite: false,
      roughness: 0.2,
    });
  }

  const CELL_EDGES_GEOMETRY = new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1));

  /**
   * How moves are shown: any mix of glass cubes, glowing dots and cube edges.
   * Accepts the old single-style strings too ("blue" = cubes, "dots" = dots).
   */
  function normalizeMoveStyle(style) {
    if (style === "dots") return { cubes: false, dots: true, edges: false };
    if (typeof style === "string") return { cubes: true, dots: false, edges: false };
    return { cubes: Boolean(style.cubes), dots: Boolean(style.dots), edges: Boolean(style.edges) };
  }

  /** Thin outlines of whole cells, in cube space (they come out tilted with the board). */
  function buildCellOutlines(cells, color) {
    const group = createCubeSpaceGroup();
    const material = new THREE.LineBasicMaterial({ color, toneMapped: false });
    for (const cell of cells) {
      const outline = new THREE.LineSegments(CELL_EDGES_GEOMETRY, material);
      outline.position.copy(cellToCubeSpace(cell.x, cell.y, cell.z));
      group.add(outline);
    }
    return group;
  }

  /**
   * Everything drawn for one cell: a glass cube, a dot with a soft glow, and/or
   * the cell's edges, as `style` asks. Returns the visible things, each tagged
   * with userData.kind, so hovering can make them stand out.
   */
  function addCellMarker(group, center, style, color, cubeMaterial, edgeColor) {
    const added = [];
    if (style.cubes) {
      const cube = new THREE.Mesh(CUBE_GEOMETRY, cubeMaterial);
      cube.position.copy(center);
      cube.renderOrder = 1;
      cube.userData.kind = "cube";
      added.push(cube);
    }
    if (style.dots) {
      const dot = new THREE.Mesh(DOT_GEOMETRY, new THREE.MeshBasicMaterial({ color, toneMapped: false }));
      dot.position.copy(center);
      dot.userData.kind = "dot";
      if (!glowTexture) glowTexture = makeGlowTexture();
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTexture, color, transparent: true, opacity: 0.55, depthWrite: false, toneMapped: false,
      }));
      glow.scale.setScalar(0.55);
      glow.position.copy(center);
      glow.userData.kind = "glow";
      added.push(dot, glow);
    }
    if (style.edges) {
      const edges = new THREE.LineSegments(CELL_EDGES_GEOMETRY,
        new THREE.LineBasicMaterial({ color: edgeColor, transparent: true, opacity: 0.9, toneMapped: false }));
      edges.position.copy(center);
      edges.userData.kind = "edges";
      added.push(edges);
    }
    for (const thing of added) group.add(thing);
    return added;
  }

  /**
   * Thin lines along each move's path: from the piece through every cell it
   * crosses to the target (an L for knights). Sliding moves in one direction
   * share one straight line, so the dots or cubes look threaded on it.
   */
  function buildMoveLines(piece, moves, color) {
    const points = [];
    for (const move of moves) {
      const pieceAfter = Object.assign({}, piece, move.to);
      const path = movePath(piece, pieceAfter);
      for (let index = 1; index < path.length; index++) points.push(path[index - 1], path[index]);
    }
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({
      color, transparent: true, opacity: 0.9, toneMapped: false,
    }));
    lines.renderOrder = 2;
    return lines;
  }

  /**
   * Draw the cells a piece can move to, for playing.
   *   style: { cubes, dots, edges } — any mix (see normalizeMoveStyle)
   *   piece + showLines: also draw move lines from the piece
   * Returns { group, hitMeshes, setHovered(move) }. Every hit mesh has
   * userData.move, so a click can be turned back into a move.
   */
  function buildMoveHighlights(moves, moveStyle, look, piece, showLines) {
    const style = normalizeMoveStyle(moveStyle);
    const group = new THREE.Group();
    const cellGroup = createCubeSpaceGroup();
    group.add(cellGroup);
    const hitMeshes = [];
    const meshesByMove = new Map();

    const hitMaterial = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false });
    const normalCubeMaterial = makeGlassCubeMaterial(look.blueCubeColor, look.cubeOpacity);
    const captureCubeMaterial = makeGlassCubeMaterial(look.captureColor, Math.min(0.8, look.cubeOpacity + 0.15));

    const glowPoints = [];
    for (const move of moves) {
      const isCapture = move.captureIds.length > 0;
      const color = isCapture ? look.captureColor : look.dotColor;
      const glowColor = isCapture || !style.cubes ? color : look.blueCubeColor;
      const edgeColor = isCapture ? look.captureColor : look.moveEdgeColor;
      const cubeMaterial = isCapture ? captureCubeMaterial : normalCubeMaterial.clone();
      const visibleMeshes = [];
      for (const cell of move.cells) {
        const center = cellToCubeSpace(cell.x, cell.y, cell.z);
        visibleMeshes.push(...addCellMarker(cellGroup, center, style, color, cubeMaterial, edgeColor));
        glowPoints.push({ position: cellToWorld(cell.x, cell.y, cell.z), color: glowColor });
        // An invisible full-size cube makes small dots easy to click.
        const hitBox = new THREE.Mesh(CUBE_GEOMETRY, hitMaterial);
        hitBox.position.copy(center);
        hitBox.userData.move = move;
        cellGroup.add(hitBox);
        hitMeshes.push(hitBox);
      }
      meshesByMove.set(move, visibleMeshes);
    }
    if (piece && showLines && moves.length > 0) group.add(buildMoveLines(piece, moves, look.moveLineColor));

    let hoveredMove = null;
    /** Make the hovered move's cubes or dots stand out. */
    function setHovered(move) {
      if (move === hoveredMove) return;
      for (const [candidate, meshes] of meshesByMove) {
        const active = candidate === move;
        for (const mesh of meshes) {
          const kind = mesh.userData.kind;
          const baseScale = kind === "glow" ? 0.55 : 1;
          const grow = kind === "glow" ? 1.8 : kind === "dot" ? 1.3 : 1.04;
          mesh.scale.setScalar(active ? baseScale * grow : baseScale);
          if (kind === "cube" && candidate.captureIds.length === 0) {
            mesh.material.opacity = active ? Math.min(0.85, look.cubeOpacity + 0.3) : look.cubeOpacity;
          }
        }
      }
      hoveredMove = move;
    }

    return { group, hitMeshes, setHovered, glowPoints };
  }

  /**
   * Show the moves of several pieces at once (the Available Moves tool).
   *   entries: [{ piece, moves }]
   * Red pieces' moves are red, Black's are white, and a cell both sides can
   * reach is purple. Nothing here is clickable: it is only for looking.
   */
  function buildAvailableMoves(entries, moveStyle, look, showLines) {
    const style = normalizeMoveStyle(moveStyle);
    const group = new THREE.Group();
    const cellGroup = createCubeSpaceGroup();
    group.add(cellGroup);

    // Which sides can reach each cell?
    const sidesByCell = new Map();
    for (const { piece, moves } of entries) {
      for (const move of moves) {
        for (const cell of move.cells) {
          const key = Rules.cellKey(cell.x, cell.y, cell.z);
          if (!sidesByCell.has(key)) sidesByCell.set(key, { cell, sides: new Set() });
          sidesByCell.get(key).sides.add(piece.side);
        }
      }
    }

    const colorFor = { red: look.redMovesColor, black: look.blackMovesColor, both: look.sharedMovesColor };
    const cubeMaterials = {
      red: makeGlassCubeMaterial(colorFor.red, look.cubeOpacity),
      black: makeGlassCubeMaterial(colorFor.black, look.cubeOpacity),
      both: makeGlassCubeMaterial(colorFor.both, Math.min(0.8, look.cubeOpacity + 0.1)),
    };
    const glowPoints = [];
    for (const { cell, sides } of sidesByCell.values()) {
      const which = sides.size > 1 ? "both" : [...sides][0];
      addCellMarker(cellGroup, cellToCubeSpace(cell.x, cell.y, cell.z), style, colorFor[which], cubeMaterials[which],
        colorFor[which]);
      glowPoints.push({ position: cellToWorld(cell.x, cell.y, cell.z), color: colorFor[which] });
    }

    if (showLines) {
      for (const { piece, moves } of entries) {
        if (moves.length > 0) group.add(buildMoveLines(piece, moves, colorFor[piece.side]));
      }
    }
    return { group, hitMeshes: [], setHovered: () => {}, glowPoints };
  }

  // ===== Glow that lights up the pieces around it =====

  /*
   * Glowing things (the selected piece, move dots and cubes) give off real
   * light, so nearby pieces pick up a yellow or blue tint. A fixed pool of
   * small point lights is kept in the scene; unused ones are just switched to
   * zero. (Adding and removing lights would make three.js rebuild every shader.)
   */
  const GLOW_LIGHT_COUNT = 8;
  const GLOW_REACH = 3.6;        // how far (in cells) a glow's light reaches

  function createGlowLights(scene) {
    const lights = [];
    for (let index = 0; index < GLOW_LIGHT_COUNT; index++) {
      const light = new THREE.PointLight(0xffffff, 0, GLOW_REACH, 2);
      scene.add(light);
      lights.push(light);
    }
    /** sources: [{ position, color, strength }]; extra lights are turned off. */
    function setGlowSources(sources) {
      lights.forEach((light, index) => {
        const source = sources[index];
        light.intensity = source ? source.strength : 0;
        if (source) {
          light.position.copy(source.position);
          light.color.set(source.color);
        }
      });
    }
    return { lights, setGlowSources, count: GLOW_LIGHT_COUNT };
  }

  /**
   * Many glowing cells, few lights: group the cells into at most `lightCount`
   * clusters (spread out by picking far-apart seeds) and put one light at the
   * middle of each, coloured like its cells and brighter for bigger clusters.
   */
  function clusterGlowPoints(points, lightCount, strengthPerLight) {
    if (points.length === 0 || lightCount <= 0) return [];
    const seeds = [points[0].position];
    while (seeds.length < Math.min(lightCount, points.length)) {
      let farthest = null;
      let farthestDistance = -1;
      for (const point of points) {
        const nearest = Math.min(...seeds.map((seed) => seed.distanceToSquared(point.position)));
        if (nearest > farthestDistance) { farthestDistance = nearest; farthest = point.position; }
      }
      seeds.push(farthest);
    }
    const clusters = seeds.map(() => ({ position: new THREE.Vector3(), color: new THREE.Color(0, 0, 0), count: 0 }));
    for (const point of points) {
      let best = 0;
      seeds.forEach((seed, index) => {
        if (seed.distanceToSquared(point.position) < seeds[best].distanceToSquared(point.position)) best = index;
      });
      clusters[best].position.add(point.position);
      clusters[best].color.add(new THREE.Color(point.color));
      clusters[best].count++;
    }
    return clusters.filter((cluster) => cluster.count > 0).map((cluster) => ({
      position: cluster.position.divideScalar(cluster.count),
      color: cluster.color.multiplyScalar(1 / cluster.count),
      strength: strengthPerLight * Math.min(1.8, 0.55 + 0.15 * cluster.count),
    }));
  }

  // ===== Public interface =====

  return {
    SQRT2,
    FLOOR_HEIGHT,
    VIEW_PRESETS,
    loadLook,
    saveLook,
    clearSavedLook,
    lookToFileText,
    createCubeSpaceGroup,
    cellToCubeSpace,
    cellToWorld,
    makeOrnamentTexture,
    createViewer,
    buildBoard,
    loadPieceModels,
    parseGlb,
    createPieceMaterials,
    clonePieceMaterial,
    lighterColor,
    cloneModel,
    buildPieceObject,
    PIECE_VERSIONS,
    versionOf,
    setPawnLength,
    pawnCellCount,
    pieceWorldPosition,
    buildRailPiece,
    movePath,
    pointAlongPath,
    pathLength,
    buildMoveHighlights,
    buildAvailableMoves,
    buildCellOutlines,
    createGlowLights,
    clusterGlowPoints,
  };
})();

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

// ─── Globals exposed to window.app ──────────────────────────────
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a0f);
scene.fog = new THREE.FogExp2(0x0a0a0f, 0.035);

// Camera — FOV tuned so Hero framing fits full bounding box with margin
const camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(0, 2.8, 14);

const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
document.getElementById('canvas-container').appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 3;
controls.maxDistance = 18;
controls.target.set(0, 1.2, 0);
controls.maxPolarAngle = Math.PI * 0.48;

// ─── PMREM + RoomEnvironment ──────────────────────────────────────
const pmremGenerator = new THREE.PMREMGenerator(renderer);
pmremGenerator.compileEquirectangularShader();
const envTexture = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environment = envTexture;

// ─── Post-processing: EffectComposer + UnrealBloomPass ──────────
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));

const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  0.45,   // strength
  0.6,    // radius
  0.72    // threshold
);
composer.addPass(bloomPass);
composer.addPass(new OutputPass());

// ─── Procedural CanvasTexture bump/roughness maps ──────────────
function createBumpTexture(size = 256) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let v = Math.random() * 30 + 15;
      const dx = (Math.sin(x * 0.1) * Math.cos(y * 0.08)) * 20;
      const dy = (Math.cos(x * 0.06) * Math.sin(y * 0.12)) * 15;
      v += dx + dy;
      const brightness = Math.floor(Math.max(0, Math.min(255, v)));
      ctx.fillStyle = `rgb(${brightness},${brightness},${brightness})`;
      ctx.fillRect(x, y, 1, 1);
    }
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(2, 2);
  return tex;
}

function createRoughnessMap(size = 128) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const cx = Math.abs(x / size - 0.5) * 2;
      const cy = Math.abs(y / size - 0.5) * 2;
      const dist = Math.sqrt(cx * cx + cy * cy);
      let v = Math.floor(40 + dist * 80 + Math.random() * 15);
      ctx.fillStyle = `rgb(${v},${v},${v})`;
      ctx.fillRect(x, y, 1, 1);
    }
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

const bumpMap = createBumpTexture(256);
const roughnessMap = createRoughnessMap(128);

// ─── Materials ──────────────────────────────────────────────────
function makeMat(color, metalness, roughness, clearcoat = 0) {
  return new THREE.MeshPhysicalMaterial({
    color, metalness, roughness,
    clearcoat, clearcoatRoughness: 0.15,
    bumpMap: bumpMap.clone(),
    bumpScale: 0.02,
    roughnessMap: roughnessMap.clone(),
    envMapIntensity: 1.4,
  });
}

const colorways = {
  midnight: { body: 0x1a1a3e, accent: 0x4a6cf7, glow: 0x3344aa, bg: 0x0a0a0f },
  arctic:   { body: 0xc8dce8, accent: 0x5bb8d9, glow: 0x88ccff, bg: 0xdde4ea },
  sunset:   { body: 0x3e1a1a, accent: 0xe07a4f, glow: 0xff6622, bg: 0x1a0f0a },
};

const matBody = makeMat(0x1a1a3e, 0.85, 0.12);
const matAccent = makeMat(0x4a6cf7, 0.9, 0.08, 1.0);
const matBase = makeMat(0x111122, 0.6, 0.35);
const matGlow = new THREE.MeshPhysicalMaterial({
  color: 0x6688ff, metalness: 0.1, roughness: 0.4,
  emissive: 0x3344aa, emissiveIntensity: 0.6,
  transparent: true, opacity: 0.9,
  envMapIntensity: 1.2,
});

// ─── Centerpiece Group — 16 non-plane meshes ──────────────────────
const centerpiece = new THREE.Group();
centerpiece.position.y = -0.5;
scene.add(centerpiece);

// Mesh 1: Pedestal base disc (CylinderGeometry)
const pedestalBase = new THREE.Mesh(
  new THREE.CylinderGeometry(2.4, 2.6, 0.35, 64),
  matBase
);
pedestalBase.position.y = -0.38;
pedestalBase.receiveShadow = true;
pedestalBase.castShadow = true;
centerpiece.add(pedestalBase);

// Mesh 2: Pedestal rim (TorusGeometry)
const pedestalRim = new THREE.Mesh(
  new THREE.TorusGeometry(2.5, 0.04, 16, 64),
  matAccent.clone()
);
pedestalRim.position.y = -0.2;
pedestalRim.rotation.x = Math.PI / 2;
pedestalRim.castShadow = true;
centerpiece.add(pedestalRim);

// Mesh 3: Main body cylinder (CylinderGeometry)
const mainBody = new THREE.Mesh(
  new THREE.CylinderGeometry(0.85, 1.05, 2.6, 48),
  matBody.clone()
);
mainBody.position.y = 1.3;
mainBody.castShadow = true;
mainBody.receiveShadow = true;
centerpiece.add(mainBody);

// Mesh 4: Top dome (SphereGeometry hemisphere)
const topDome = new THREE.Mesh(
  new THREE.SphereGeometry(0.87, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
  matBody.clone()
);
topDome.position.y = 2.6;
topDome.castShadow = true;
centerpiece.add(topDome);

// Mesh 5: Accent equator ring (TorusGeometry)
const accentRing = new THREE.Mesh(
  new THREE.TorusGeometry(1.1, 0.07, 16, 80),
  matAccent.clone()
);
accentRing.position.y = 1.8;
accentRing.rotation.x = Math.PI / 2;
accentRing.castShadow = true;
centerpiece.add(accentRing);

// Mesh 6: Inner accent ring (smaller torus)
const innerRing = new THREE.Mesh(
  new THREE.TorusGeometry(0.9, 0.04, 12, 64),
  matAccent.clone()
);
innerRing.position.y = 0.8;
innerRing.rotation.x = Math.PI / 2;
centerpiece.add(innerRing);

// Mesh 7: Left wing panel (BoxGeometry)
const leftWing = new THREE.Mesh(
  new THREE.BoxGeometry(0.1, 1.6, 0.8),
  matAccent.clone()
);
leftWing.position.set(-1.45, 1.2, 0);
leftWing.rotation.z = 0.35;
leftWing.castShadow = true;
centerpiece.add(leftWing);

// Mesh 8: Right wing panel (BoxGeometry)
const rightWing = new THREE.Mesh(
  new THREE.BoxGeometry(0.1, 1.6, 0.8),
  matAccent.clone()
);
rightWing.position.set(1.45, 1.2, 0);
rightWing.rotation.z = -0.35;
rightWing.castShadow = true;
centerpiece.add(rightWing);

// Mesh 9: Floating orb (SphereGeometry) — top
const floatingOrb = new THREE.Mesh(
  new THREE.SphereGeometry(0.28, 48, 48),
  matGlow.clone()
);
floatingOrb.position.y = 4.5;
floatingOrb.castShadow = true;
centerpiece.add(floatingOrb);

// Mesh 10: Inner core sphere (SphereGeometry) — inside body
const innerCore = new THREE.Mesh(
  new THREE.SphereGeometry(0.38, 32, 32),
  matGlow.clone()
);
innerCore.position.y = 1.5;
centerpiece.add(innerCore);

// Mesh 11: Outer shell — LatheGeometry (sculpted profile)
const shellPoints = [];
for (let i = 0; i <= 24; i++) {
  const t = i / 24;
  const angle = t * Math.PI;
  let r = Math.sin(angle) * 1.35 + Math.sin(angle * 2) * 0.15;
  if (t < 0.15) r *= t / 0.15; // taper bottom
  const y = -0.2 + t * 4.8;
  shellPoints.push(new THREE.Vector2(r, y));
}
const outerShell = new THREE.Mesh(
  new THREE.LatheGeometry(shellPoints, 48),
  matBody.clone()
);
outerShell.position.y = -0.3;
outerShell.castShadow = true;
centerpiece.add(outerShell);

// Mesh 12: Base plate — ExtrudeGeometry (hexagonal)
const hexShape = new THREE.Shape();
for (let i = 0; i < 6; i++) {
  const angle = (i / 6) * Math.PI * 2 - Math.PI / 2;
  const x = Math.cos(angle) * 1.8;
  const y = Math.sin(angle) * 1.8;
  if (i === 0) hexShape.moveTo(x, y);
  else hexShape.lineTo(x, y);
}
hexShape.closePath();

const extrudeSettings = { depth: 0.06, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.02, bevelSegments: 3 };
const basePlate = new THREE.Mesh(
  new THREE.ExtrudeGeometry(hexShape, extrudeSettings),
  matAccent.clone()
);
basePlate.position.set(0, -0.56, 0);
basePlate.rotation.x = Math.PI / 2; // lay flat
basePlate.receiveShadow = true;
centerpiece.add(basePlate);

// Mesh 13: Spiral accent — TubeGeometry along a helix curve
const spiralCurve = new THREE.Curve();
spiralCurve.getPoint = function(t) {
  const angle = t * Math.PI * 6;
  const r = 0.95 + t * 0.2;
  return new THREE.Vector3(
    Math.cos(angle) * r,
    0.4 + t * 3.8,
    Math.sin(angle) * r
  );
};
const spiralTube = new THREE.Mesh(
  new THREE.TubeGeometry(spiralCurve, 128, 0.025, 8, false),
  matAccent.clone()
);
spiralTube.castShadow = true;
centerpiece.add(spiralTube);

// Mesh 14: Orbital ring — TubeGeometry (large tilted torus-like loop)
const orbitCurve = new THREE.EllipseCurve(0, 0, 2.0, 0.6, 0, Math.PI * 2, false, 0);
const orbitPoints3D = orbitCurve.getPoints(80).map(p => new THREE.Vector3(p.x, p.y + 1.5, 0));
const orbitPath = new THREE.CatmullRomCurve3(orbitPoints3D, true);
const orbitalRing = new THREE.Mesh(
  new THREE.TubeGeometry(orbitPath, 80, 0.02, 8, true),
  matAccent.clone()
);
orbitalRing.rotation.z = Math.PI * 0.15;
centerpiece.add(orbitalRing);

// Mesh 15: Top fin — ExtrudeGeometry (thin diamond shape)
const finShape = new THREE.Shape();
finShape.moveTo(0, 0.6);
finShape.lineTo(-0.2, 0);
finShape.lineTo(0, -0.3);
finShape.lineTo(0.2, 0);
finShape.closePath();

const finExtrudeSettings = { depth: 0.04, bevelEnabled: true, bevelThickness: 0.01, bevelSize: 0.01, bevelSegments: 2 };
const topFin = new THREE.Mesh(
  new THREE.ExtrudeGeometry(finShape, finExtrudeSettings),
  matAccent.clone()
);
topFin.position.set(0, 3.4, -0.5);
topFin.castShadow = true;
centerpiece.add(topFin);

// Mesh 16: Bottom ring — LatheGeometry (thin decorative band)
const bandPoints = [];
for (let i = 0; i <= 12; i++) {
  const t = i / 12;
  const angle = t * Math.PI;
  let r = Math.sin(angle) * 1.08 + 0.06 * Math.cos(angle * 3);
  bandPoints.push(new THREE.Vector2(r, -0.1));
}
const bottomBand = new THREE.Mesh(
  new THREE.LatheGeometry(bandPoints, 48),
  matAccent.clone()
);
bottomBand.position.y = -0.5;
centerpiece.add(bottomBand);

// ─── Studio Floor + Shadow Catcher ──────────────────────────────
const floorGeo = new THREE.CircleGeometry(6, 64);
const floorMat = new THREE.MeshStandardMaterial({
  color: 0x111118, roughness: 0.95, metalness: 0.0,
});
const floor = new THREE.Mesh(floorGeo, floorMat);
floor.rotation.x = -Math.PI / 2;
floor.position.y = -0.56;
floor.receiveShadow = true;
scene.add(floor);

// ─── Lighting (3-point studio rig with shadows) ──────────────
const keyLight = new THREE.SpotLight(0xffeedd, 80, 20, Math.PI / 4, 0.6, 1.5);
keyLight.position.set(4, 7, 4);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(1024, 1024);
keyLight.shadow.bias = -0.0003;
keyLight.shadow.radius = 4;
scene.add(keyLight);

const fillLight = new THREE.PointLight(0x8899cc, 25, 15);
fillLight.position.set(-3, 3, -2);
scene.add(fillLight);

const rimLight = new THREE.SpotLight(0x6677ee, 40, 15, Math.PI / 5, 0.7, 1.5);
rimLight.position.set(-2, 5, -5);
rimLight.castShadow = true;
rimLight.shadow.mapSize.set(512, 512);
scene.add(rimLight);

const ambientLight = new THREE.AmbientLight(0x222233, 0.4);
scene.add(ambientLight);

// ─── Camera Presets (Hero framed to fit full bounding box) ──────
const presets = {
  hero:    { pos: [0, 2.8, 14],   target: [0, 1.2, 0] },
  top:     { pos: [0, 9, 0.01],   target: [0, 1.5, 0] },
  detail:  { pos: [3.5, 2.8, 3.5], target: [0, 2.0, 0] },
};

let currentPreset = 'hero';
const camAnim = {
  active: false,
  startPos: new THREE.Vector3(),
  endPos: new THREE.Vector3(),
  startTarget: new THREE.Vector3(),
  endTarget: new THREE.Vector3(),
  progress: 0,
  duration: 1.2,
};

function setPreset(name) {
  const p = presets[name];
  if (!p) return;
  currentPreset = name;
  camAnim.startPos.copy(camera.position);
  camAnim.endPos.set(...p.pos);
  camAnim.startTarget.copy(controls.target);
  camAnim.endTarget.set(...p.target);
  camAnim.progress = 0;
  camAnim.active = true;

  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`[data-preset="${name}"]`)?.classList.add('active');
}

// ─── Colorways ──────────────────────────────────────────────────
function setColorway(name) {
  const c = colorways[name];
  if (!c) return;
  matBody.color.setHex(c.body);
  matAccent.color.setHex(c.accent);
  matGlow.emissive.setHex(c.glow);
  scene.background.setHex(c.bg);
  scene.fog.color.setHex(c.bg);

  document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`[data-colorway="${name}"]`)?.classList.add('active');
}

// ─── Lighting Modes ──────────────────────────────────────────────
const lightingModes = {
  warm: { key: 0xffeedd, fill: 0x8899cc, rim: 0x6677ee, ambient: 0x222233, exposure: 1.2 },
  cool: { key: 0xddeeff, fill: 0xaabbdd, rim: 0x5566bb, ambient: 0x1a1a2e, exposure: 1.4 },
};

function setLighting(name) {
  const l = lightingModes[name];
  if (!l) return;
  keyLight.color.setHex(l.key);
  fillLight.color.setHex(l.fill);
  rimLight.color.setHex(l.rim);
  ambientLight.color.setHex(l.ambient);
  renderer.toneMappingExposure = l.exposure;

  document.querySelectorAll('.light-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`[data-lighting="${name}"]`)?.classList.add('active');
}

// ─── HUD Event Wiring ────────────────────────────────────────────
document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', () => setPreset(btn.dataset.preset));
});
document.querySelectorAll('.color-btn').forEach(btn => {
  btn.addEventListener('click', () => setColorway(btn.dataset.colorway));
});
document.querySelectorAll('.light-btn').forEach(btn => {
  btn.addEventListener('click', () => setLighting(btn.dataset.lighting));
});

// ─── Animation Loop ──────────────────────────────────────────────
const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();

  // Smooth camera transitions
  if (camAnim.active) {
    camAnim.progress += (1 / 60) / camAnim.duration;
    if (camAnim.progress >= 1) {
      camAnim.progress = 1;
      camAnim.active = false;
    }
    const ease = 1 - Math.pow(1 - camAnim.progress, 3); // ease-out cubic
    camera.position.lerpVectors(camAnim.startPos, camAnim.endPos, ease);
    controls.target.lerpVectors(camAnim.startTarget, camAnim.endTarget, ease);
  }

  // Floating orb bob + pulse
  floatingOrb.position.y = 4.5 + Math.sin(t * 1.5) * 0.3;
  matGlow.emissiveIntensity = 0.6 + Math.sin(t * 2) * 0.35;

  // Inner core subtle rotation
  innerCore.rotation.y = t * 0.4;
  innerCore.rotation.x = Math.sin(t * 0.7) * 0.2;

  // Orbital ring slow spin
  orbitalRing.rotation.z = Math.PI * 0.15 + t * 0.12;

  // Gentle centerpiece idle rotation
  centerpiece.rotation.y = t * 0.06;

  controls.update();
  composer.render();
}

animate();

// ─── Resize Handling ──────────────────────────────────────────────
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
});

// ─── Expose window.app ────────────────────────────────────────────
window.app = { scene, camera, renderer, controls, presets, composer };

// Initialize default state
setPreset('hero');
setColorway('midnight');
setLighting('warm');
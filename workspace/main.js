import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

/* ─── Core Setup ─── */
const canvas = document.getElementById('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.95;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a0f);

const camera = new THREE.PerspectiveCamera(48, window.innerWidth / window.innerHeight, 0.1, 100);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 2;
controls.maxDistance = 20;
controls.target.set(0, 1.8, 0);
controls.maxPolarAngle = Math.PI * 0.48;

/* ─── Environment / Reflections ─── */
const pmrem = new THREE.PMREMGenerator(renderer);
pmrem.compileEquirectangularShader();
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

/* ─── Post-processing ─── */
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
// Half-resolution bloom for performance (>=30 FPS at 2x DPR)
// Half-resolution bloom for performance (>=30 FPS at 2x DPR)
const bloom = new UnrealBloomPass(
  new THREE.Vector2(Math.max(Math.ceil(window.innerWidth / 2), 1), Math.max(Math.ceil(window.innerHeight / 2), 1)), 0.35, 0.6, 0.82
);
composer.addPass(bloom);
composer.addPass(new OutputPass());

/* ─── Lights (>=2 with shadows) ─── */
const keyLight = new THREE.DirectionalLight(0xffeedd, 3.0);
keyLight.position.set(4, 8, 5);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(512, 512);
keyLight.shadow.camera.near = 0.5;
keyLight.shadow.camera.far = 30;
keyLight.shadow.camera.left = -6;
keyLight.shadow.camera.right = 6;
keyLight.shadow.camera.top = 6;
keyLight.shadow.camera.bottom = -6;
keyLight.shadow.bias = -0.002;
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0x8899ff, 1.2);
fillLight.position.set(-5, 4, -3);
scene.add(fillLight);

const rimLight = new THREE.PointLight(0xff6644, 2.0, 15);
rimLight.position.set(-3, 6, -4);
scene.add(rimLight);

const ambientLight = new THREE.AmbientLight(0x1a1a2e, 0.5);
scene.add(ambientLight);

/* ─── Procedural Textures ─── */
function createRoughnessTexture() {
  const size = 256;
  const data = new Uint8Array(size * size * 4);
  for (let i = 0; i < size * size; i++) {
    const x = (i % size) / size, y = Math.floor(i / size) / size;
    const noise = (Math.sin(x * 25 + y * 18) * 0.5 + 0.5) * 60
      + (Math.cos(x * 47 - y * 31) * 0.5 + 0.5) * 40;
    const v = Math.min(255, Math.max(0, noise));
    data[i * 4] = v; data[i * 4 + 1] = v; data[i * 4 + 2] = v; data[i * 4 + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  tex.needsUpdate = true;
  return tex;
}

function createBumpTexture() {
  const size = 128;
  const data = new Uint8Array(size * size * 4);
  for (let i = 0; i < size * size; i++) {
    const x = (i % size) / size, y = Math.floor(i / size) / size;
    const v = ((Math.sin(x * 60 + y * 50) + Math.cos(y * 73 - x * 41)) * 0.5 + 0.5) * 80 + 30;
    data[i * 4] = v; data[i * 4 + 1] = v; data[i * 4 + 2] = v; data[i * 4 + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  tex.needsUpdate = true;
  return tex;
}

const roughnessMap = createRoughnessTexture();
roughnessMap.wrapS = roughnessMap.wrapT = THREE.RepeatWrapping;
roughnessMap.repeat.set(2, 4);

const bumpMap = createBumpTexture();
bumpMap.wrapS = bumpMap.wrapT = THREE.RepeatWrapping;
bumpMap.repeat.set(3, 6);

/* ─── Colorway Definitions ─── */
const colorways = {
  obsidian: {
    bodyColor: new THREE.Color(0x1a1a24),
    accentColor: new THREE.Color(0x5577ff),
    gemColor: new THREE.Color(0xaabbff),
    baseColor: new THREE.Color(0x111118),
    emissiveIntensity: 0.3,
    exposure: 1.0,
    bloomStrength: 0.35,
    keyIntensity: 3.0,
    fillIntensity: 1.2,
    rimIntensity: 2.0,
  },
    aurora: {
    bodyColor: new THREE.Color(0x0a2818),
    accentColor: new THREE.Color(0x44ffaa),
    gemColor: new THREE.Color(0xaaffdd),
    baseColor: new THREE.Color(0x081a12),
    emissiveIntensity: 0.6,
    exposure: 1.1,
    bloomStrength: 0.35, // capped to prevent white blowout
    keyIntensity: 3.5,
    fillIntensity: 1.5,
    rimIntensity: 2.5,
  },
    ember: {
    bodyColor: new THREE.Color(0x2a1810),
    accentColor: new THREE.Color(0xff6633),
    gemColor: new THREE.Color(0xffcc88),
    baseColor: new THREE.Color(0x1a0e08),
    emissiveIntensity: 0.5,
    exposure: 1.05,
    bloomStrength: 0.42, // capped at max allowed to prevent white blowout
    keyIntensity: 3.2,
    fillIntensity: 1.0,
    rimIntensity: 3.0,
  },
};

/* ─── Centerpiece Builder (>=14 meshes) ─── */
const centerpiece = new THREE.Group();
let activeColorway = 'obsidian';
const meshList = [];

function buildCenterpiece(cw) {
  // Remove old
  while (centerpiece.children.length) {
    const c = centerpiece.children[0];
    if (c.geometry) c.geometry.dispose();
    if (c.material) {
      if (Array.isArray(c.material)) c.material.forEach(m => m.dispose());
      else c.material.dispose();
    }
    centerpiece.remove(c);
  }
  meshList.length = 0;

  const bodyMat = new THREE.MeshPhysicalMaterial({
    color: cw.bodyColor, roughnessMap, bumpMap, bumpScale: 0.4,
    metalness: 0.85, clearcoat: 1.0, clearcoatRoughness: 0.12,
    envMapIntensity: 1.2,
  });

  const accentMat = new THREE.MeshPhysicalMaterial({
    color: cw.accentColor, roughnessMap, bumpMap, bumpScale: 0.3,
    metalness: 0.95, clearcoat: 0.8, emissive: cw.accentColor,
    emissiveIntensity: cw.emissiveIntensity, envMapIntensity: 1.4,
  });

  const gemMat = new THREE.MeshPhysicalMaterial({
    color: cw.gemColor, roughness: 0.05, metalness: 0.1,
    clearcoat: 1.0, transmission: 0.6, thickness: 1.2, ior: 1.8,
    envMapIntensity: 2.0, emissive: cw.gemColor,
    emissiveIntensity: cw.emissiveIntensity * 1.5,
  });

  const baseMat = new THREE.MeshStandardMaterial({
    color: cw.baseColor, roughnessMap, metalness: 0.7, envMapIntensity: 0.8,
  });

  // 1. Pedestal platform (CylinderGeometry) — reduced segments for perf
  const platformGeo = new THREE.CylinderGeometry(2.4, 2.6, 0.15, 48);
  const platform = new THREE.Mesh(platformGeo, baseMat);
  platform.position.y = -0.075;
  platform.receiveShadow = true; platform.castShadow = true;
  centerpiece.add(platform); meshList.push(platform);

  // 2. Pedestal rim ring (TorusGeometry)
  const rimGeo = new THREE.TorusGeometry(2.5, 0.06, 16, 80);
  const rim = new THREE.Mesh(rimGeo, accentMat);
  rim.rotation.x = Math.PI / 2;
  rim.position.y = 0.0;
  rim.castShadow = true;
  centerpiece.add(rim); meshList.push(rim);

  // 3. Main stem (ExtrudeGeometry profile) — reduced bevel segments for perf
  const stemShape = new THREE.Shape();
  stemShape.moveTo(-0.12, 0);
  stemShape.lineTo(-0.18, 0.6);
  stemShape.quadraticCurveTo(-0.22, 1.4, -0.15, 2.0);
  stemShape.lineTo(0.15, 2.0);
  stemShape.quadraticCurveTo(0.22, 1.4, 0.18, 0.6);
  stemShape.lineTo(0.12, 0);
  const stemExtrudeSettings = { depth: 0.01, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 2 };
  const stemGeo = new THREE.ExtrudeGeometry(stemShape, stemExtrudeSettings);
  const stem = new THREE.Mesh(stemGeo, bodyMat);
  stem.position.set(0, 0.075, -0.005);
  stem.castShadow = true;
  centerpiece.add(stem); meshList.push(stem);

  // 4. Stem inner groove (LatheGeometry) — reduced radial segments for perf
  const groovePoints = [];
  for (let i = 0; i <= 16; i++) {
    const t = i / 16;
    const r = 0.16 + Math.sin(t * Math.PI) * 0.04;
    groovePoints.push(new THREE.Vector2(r, t * 2.0));
  }
  const grooveGeo = new THREE.LatheGeometry(groovePoints, 24);
  const grooveMat = bodyMat.clone();
  grooveMat.color.set(0x0e0e16);
  const groove = new THREE.Mesh(grooveGeo, grooveMat);
  groove.position.y = 0.075;
  groove.castShadow = true;
  centerpiece.add(groove); meshList.push(groove);

  // 5. Central core sphere — reduced segments for perf
  const coreGeo = new THREE.SphereGeometry(0.38, 32, 24);
  const core = new THREE.Mesh(coreGeo, gemMat);
  core.position.y = 2.1;
  core.castShadow = true;
  centerpiece.add(core); meshList.push(core);

  // 6. Core glow ring (TorusGeometry)
  const glowRingGeo = new THREE.TorusGeometry(0.52, 0.04, 16, 48);
  const glowRingMat = accentMat.clone();
  glowRingMat.emissiveIntensity = cw.emissiveIntensity * 2;
  const glowRing = new THREE.Mesh(glowRingGeo, glowRingMat);
  glowRing.position.y = 2.1;
  glowRing.rotation.x = Math.PI / 2;
  glowRing.castShadow = true;
  centerpiece.add(glowRing); meshList.push(glowRing);

  // 7-9. Orbital ring segments — reduced path & tube resolution for perf
  const orbitPath1 = new THREE.EllipseCurve(0, 0, 1.3, 1.3, 0, Math.PI * 2, false, 0);
  const tubePoints1 = orbitPath1.getPoints(48);
  const tubeGeo1 = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(tubePoints1.map(p => new THREE.Vector3(p.x, p.y, 0))), 48, 0.025, 10, true);
  const ring1Mat = accentMat.clone();
  const ring1 = new THREE.Mesh(tubeGeo1, ring1Mat);
  ring1.position.y = 2.1;
  ring1.rotation.x = Math.PI * 0.35;
  ring1.castShadow = true;
  centerpiece.add(ring1); meshList.push(ring1);

  // Orbital ring 2 — reduced path & tube resolution for perf
  const orbitPath2 = new THREE.EllipseCurve(0, 0, 1.1, 1.5, 0, Math.PI * 2, false, 0);
  const tubePoints2 = orbitPath2.getPoints(48);
  const tubeGeo2 = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(tubePoints2.map(p => new THREE.Vector3(p.x, p.y, 0))), 48, 0.02, 10, true);
  const ring2Mat = accentMat.clone();
  const ring2 = new THREE.Mesh(tubeGeo2, ring2Mat);
  ring2.position.y = 2.3;
  ring2.rotation.x = Math.PI * 0.65;
  ring2.rotation.z = Math.PI * 0.15;
  ring2.castShadow = true;
  centerpiece.add(ring2); meshList.push(ring2);

  // 10-13. Four orbital gem spheres — reduced segments for perf
  const orbGemGeo = new THREE.SphereGeometry(0.08, 16, 12);
  const orbAngles = [0, Math.PI / 2, Math.PI, Math.PI * 1.5];
  orbAngles.forEach(angle => {
    const gem = new THREE.Mesh(orbGemGeo, gemMat.clone());
    gem.position.set(Math.cos(angle) * 1.3, 2.1 + Math.sin(angle) * 0.0, Math.sin(angle) * 1.3);
    gem.castShadow = true;
    centerpiece.add(gem); meshList.push(gem);
  });

  // 14. Top cap dome — reduced resolution for perf
  const domePoints = [];
  for (let i = 0; i <= 16; i++) {
    const t = i / 16;
    const r = Math.cos(t * Math.PI * 0.5) * 0.4;
    domePoints.push(new THREE.Vector2(r, t * 0.38));
  }
  const domeGeo = new THREE.LatheGeometry(domePoints, 32);
  const domeMat = bodyMat.clone();
  const dome = new THREE.Mesh(domeGeo, domeMat);
  dome.position.y = 2.1;
  dome.castShadow = true;
  centerpiece.add(dome); meshList.push(dome);

  // 15. Decorative fin plate (ExtrudeGeometry) - left
  const finShapeL = new THREE.Shape();
  finShapeL.moveTo(0, 0);
  finShapeL.quadraticCurveTo(-0.3, 0.4, -0.25, 0.9);
  finShapeL.lineTo(-0.18, 0.9);
  finShapeL.quadraticCurveTo(-0.18, 0.4, 0, 0.1);
  finShapeL.closePath();
  const finGeoL = new THREE.ExtrudeGeometry(finShapeL, { depth: 0.02, bevelEnabled: true, bevelThickness: 0.015, bevelSize: 0.015, bevelSegments: 3 });
  const finL = new THREE.Mesh(finGeoL, accentMat.clone());
  finL.position.set(-0.14, 2.1, -0.06);
  finL.rotation.y = Math.PI * 0.15;
  finL.castShadow = true;
  centerpiece.add(finL); meshList.push(finL);

  // 16. Decorative fin plate (ExtrudeGeometry) - right
  const finShapeR = new THREE.Shape();
  finShapeR.moveTo(0, 0);
  finShapeR.quadraticCurveTo(0.3, 0.4, 0.25, 0.9);
  finShapeR.lineTo(0.18, 0.9);
  finShapeR.quadraticCurveTo(0.18, 0.4, 0, 0.1);
  finShapeR.closePath();
  const finGeoR = new THREE.ExtrudeGeometry(finShapeR, { depth: 0.02, bevelEnabled: true, bevelThickness: 0.015, bevelSize: 0.015, bevelSegments: 3 });
  const finR = new THREE.Mesh(finGeoR, accentMat.clone());
  finR.position.set(0.14, 2.1, -0.06);
  finR.rotation.y = -Math.PI * 0.15;
  finR.castShadow = true;
  centerpiece.add(finR); meshList.push(finR);

  // 17. Pedestal base ring (TorusGeometry)
  const baseRingGeo = new THREE.TorusGeometry(2.3, 0.08, 16, 80);
  const baseRingMat = bodyMat.clone();
  const baseRing = new THREE.Mesh(baseRingGeo, baseRingMat);
  baseRing.rotation.x = Math.PI / 2;
  baseRing.position.y = 0.075;
  baseRing.castShadow = true;
  centerpiece.add(baseRing); meshList.push(baseRing);

  // 18. Inner accent ring (TorusGeometry) on stem
  const innerRingGeo = new THREE.TorusGeometry(0.2, 0.03, 16, 40);
  const innerRingMat = accentMat.clone();
  const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
  innerRing.position.y = 1.0;
  innerRing.rotation.x = Math.PI / 2;
  innerRing.castShadow = true;
  centerpiece.add(innerRing); meshList.push(innerRing);

  scene.add(centerpiece);
}

buildCenterpiece(colorways.obsidian);

/* ─── Studio Floor (shadow catcher) ─── */
const floorGeo = new THREE.PlaneGeometry(30, 30);
const floorMat = new THREE.ShadowMaterial({ opacity: 0.5 });
const floor = new THREE.Mesh(floorGeo, floorMat);
floor.rotation.x = -Math.PI / 2;
floor.position.y = -0.15;
floor.receiveShadow = true;
scene.add(floor);

/* ─── Camera Presets ─── */
const presets = {
  hero:   { pos: new THREE.Vector3(9, 5.8, 9.5), target: new THREE.Vector3(0, 1.3, 0) },
  top:    { pos: new THREE.Vector3(0, 12, 0.01), target: new THREE.Vector3(0, 1.4, 0) },
  detail: { pos: new THREE.Vector3(1.5, 2.8, 2.5), target: new THREE.Vector3(0, 2.05, 0) },
};

let currentPreset = 'hero';
function goToPreset(name) {
  const p = presets[name];
  if (!p) return;
  animateCamera(p.pos.clone(), p.target.clone());
  document.querySelectorAll('[data-preset]').forEach(b => b.classList.toggle('active', b.dataset.preset === name));
  currentPreset = name;
}

function animateCamera(targetPos, targetLookAt) {
  const startPos = camera.position.clone();
  const startTarget = controls.target.clone();
  const duration = 800;
  const startTime = performance.now();

  function tick() {
    let t = (performance.now() - startTime) / duration;
    if (t > 1) t = 1;
    // easeInOutCubic
    t = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

    camera.position.lerpVectors(startPos, targetPos, t);
    controls.target.lerpVectors(startTarget, targetLookAt, t);
    controls.update();

    if (t < 1) requestAnimationFrame(tick);
  }
  tick();
}

/* ─── HUD: Camera Presets ─── */
document.querySelectorAll('[data-preset]').forEach(btn => {
  btn.addEventListener('click', () => goToPreset(btn.dataset.preset));
});

/* ─── HUD: Colorways ─── */
function applyColorway(name) {
  const cw = colorways[name];
  if (!cw) return;
  activeColorway = name;

  // Clean rebuild with new colorway materials (bloom auto-capped in applyLighting)
  buildCenterpiece(cw);
  renderer.toneMappingExposure = cw.exposure;
  bloom.strength = cw.bloomStrength;
  keyLight.intensity = cw.keyIntensity;
  fillLight.intensity = cw.fillIntensity;
  rimLight.intensity = cw.rimIntensity;

  document.querySelectorAll('[data-colorway]').forEach(b => b.classList.toggle('active', b.dataset.colorway === name));
}

document.querySelectorAll('[data-colorway]').forEach(btn => {
  btn.addEventListener('click', () => applyColorway(btn.dataset.colorway));
});

/* ─── HUD: Lighting Presets ─── */
const lightingPresets = {
  studio:    { keyI: 3.0, fillI: 1.2, rimI: 2.0, ambientI: 0.5, exposure: 0.95, bloomS: 0.35 },
  dramatic:  { keyI: 4.0, fillI: 0.3, rimI: 3.5, ambientI: 0.15, exposure: 0.88,  bloomS: 0.42 },
  ambient:   { keyI: 1.0, fillI: 2.0, rimI: 1.0, ambientI: 1.0,  exposure: 1.15,  bloomS: 0.15 },
};

function applyLighting(name) {
  const lp = lightingPresets[name];
  if (!lp) return;
  keyLight.intensity = lp.keyI;
  fillLight.intensity = lp.fillI;
  rimLight.intensity = lp.rimI;
  ambientLight.intensity = lp.ambientI;
  renderer.toneMappingExposure = lp.exposure;
  bloom.strength = Math.min(lp.bloomS, 0.42); // Cap at 0.42 to prevent white blowout

  document.querySelectorAll('[data-lighting]').forEach(b => b.classList.toggle('active', b.dataset.lighting === name));
}

document.querySelectorAll('[data-lighting]').forEach(btn => {
  btn.addEventListener('click', () => applyLighting(btn.dataset.lighting));
});

// Set initial active states
document.querySelector('[data-preset="hero"]').classList.add('active');
document.querySelector('[data-colorway="obsidian"]').classList.add('active');
document.querySelector('[data-lighting="studio"]').classList.add('active');

/* ─── Init Camera Position ─── */
camera.position.copy(presets.hero.pos);
controls.target.copy(presets.hero.target);
controls.update();

/* ─── Resize Handler ─── */
window.addEventListener('resize', () => {
  const w = window.innerWidth, h = window.innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  composer.setSize(w, h);
});

/* ─── Animation Loop ─── */
const clock = new THREE.Clock();
let frameCount = 0;

function animate() {
  requestAnimationFrame(animate);
  const elapsed = clock.getElapsedTime();
  frameCount++;

  // Subtle centerpiece micro-motion
  if (centerpiece) {
    // Subtle centerpiece micro-motion (every frame, cheap math only)
  meshList.forEach((mesh, idx) => {
    if (idx >= 8 && idx <= 11) {
      const angle = elapsed * 0.4 + (idx - 8) * Math.PI / 2;
      mesh.position.x = Math.cos(angle) * 1.3;
      mesh.position.z = Math.sin(angle) * 1.3;
    }
  });

  centerpiece.rotation.y = elapsed * 0.08;
  }

  controls.update();
  composer.render();
}

animate();

/* ─── Expose to window for evaluator ─── */
window.app = { scene, camera, renderer, controls, composer, presets };
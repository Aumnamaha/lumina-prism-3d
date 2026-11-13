import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const canvas = document.getElementById('viewport');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0c0f14);

const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(3.4, 2.2, 4.2);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.enableZoom = true;
controls.target.set(0, 0.6, 0);
controls.update();

const hemiLight = new THREE.HemisphereLight(0xdbeafe, 0x1e293b, 0.65);
scene.add(hemiLight);

const keyLight = new THREE.DirectionalLight(0xffffff, 2.6);
keyLight.position.set(4, 6, 4);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(1024, 1024);
scene.add(keyLight);

const rimLight = new THREE.PointLight(0x38bdf8, 3.5, 15);
rimLight.position.set(-3, 2.5, -2.5);
scene.add(rimLight);

const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(14, 14),
  new THREE.MeshStandardMaterial({ color: 0x11161f, roughness: 0.85, metalness: 0.1 })
);
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

const assembly = new THREE.Group();
scene.add(assembly);

const baseMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.85, roughness: 0.25 });
const accentMat = new THREE.MeshPhysicalMaterial({ color: 0x0ea5e9, metalness: 0.2, roughness: 0.15, clearcoat: 1.0 });
const chromeMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.95, roughness: 0.12 });

const pedestal = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.25, 0.24, 48), baseMat);
pedestal.position.y = 0.12;
pedestal.castShadow = true;
pedestal.receiveShadow = true;
assembly.add(pedestal);

const core = new THREE.Mesh(new THREE.TorusKnotGeometry(0.52, 0.16, 120, 24), accentMat);
core.position.y = 1.05;
core.castShadow = true;
assembly.add(core);

for (let i = 0; i < 3; i++) {
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.88 + i * 0.12, 0.025, 16, 64), chromeMat);
  ring.position.y = 1.05;
  ring.rotation.set(0.4 * (i + 1), 0.6 * i, 0.2);
  ring.castShadow = true;
  assembly.add(ring);
}

for (const side of [-1, 1]) {
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.14, 24, 24), accentMat);
  cap.position.set(side * 0.95, 0.35, 0);
  cap.castShadow = true;
  assembly.add(cap);
}

const presets = {
  Hero: { pos: [3.4, 2.2, 4.2], target: [0, 0.8, 0] },
  Top: { pos: [0.01, 4.8, 0.4], target: [0, 0.7, 0] },
  Detail: { pos: [1.3, 1.35, 1.5], target: [0, 1.05, 0] },
};

function applyPreset(name) {
  const p = presets[name];
  if (!p) return;
  camera.position.set(...p.pos);
  controls.target.set(...p.target);
  controls.update();
}

document.getElementById('btn-hero').addEventListener('click', () => applyPreset('Hero'));
document.getElementById('btn-top').addEventListener('click', () => applyPreset('Top'));
document.getElementById('btn-detail').addEventListener('click', () => applyPreset('Detail'));

const colorways = [0x0ea5e9, 0xf97316, 0xa855f7];
let colorIdx = 0;
document.getElementById('btn-colorway').addEventListener('click', () => {
  colorIdx = (colorIdx + 1) % colorways.length;
  accentMat.color.setHex(colorways[colorIdx]);
});

let warmMood = false;
document.getElementById('btn-lighting').addEventListener('click', () => {
  warmMood = !warmMood;
  rimLight.color.setHex(warmMood ? 0xfbbf24 : 0x38bdf8);
  rimLight.intensity = warmMood ? 6.5 : 3.5;
  scene.background.setHex(warmMood ? 0x1a1310 : 0x0c0f14);
});

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

window.app = { scene, camera, renderer, controls, presets };

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

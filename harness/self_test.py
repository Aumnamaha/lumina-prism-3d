import shutil
from pathlib import Path

import config
from evaluator import evaluate_site
from scorer import score_metrics
from setup_vendor import ensure_vendor_assets


GOOD_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="icon" href="data:," />
  <title>ChronoCore 3D Showcase</title>
  <link rel="stylesheet" href="./style.css" />
  <script type="importmap">
  {
    "imports": {
      "three": "./vendor/three.module.js",
      "three/addons/": "./vendor/"
    }
  }
  </script>
</head>
<body>
  <canvas id="viewport"></canvas>
  <aside class="hud">
    <div class="group">
      <button id="btn-hero" type="button">Hero</button>
      <button id="btn-top" type="button">Top</button>
      <button id="btn-detail" type="button">Detail</button>
    </div>
    <div class="group">
      <button id="btn-colorway" type="button">Finish</button>
      <button id="btn-lighting" type="button">Lighting</button>
    </div>
  </aside>
  <script type="module" src="./main.js"></script>
</body>
</html>
"""

GOOD_STYLE_CSS = """* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 100%; height: 100%; overflow: hidden; background: #0c0f14; font-family: system-ui, sans-serif; }
#viewport { display: block; width: 100vw; height: 100vh; }
.hud {
  position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;
  max-width: calc(100vw - 24px); padding: 10px 14px;
  background: rgba(15, 20, 28, 0.78); border: 1px solid rgba(255,255,255,0.14);
  border-radius: 12px; backdrop-filter: blur(10px);
}
.group { display: flex; gap: 6px; }
button {
  padding: 7px 12px; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px;
  background: #1b2432; color: #f1f5f9; font-size: 13px; cursor: pointer;
}
button:hover { background: #29364a; }
"""

GOOD_MAIN_JS = """import * as THREE from 'three';
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
"""

BAD_INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <link rel="icon" href="data:," />
  <title>Bad Minimal Scene</title>
  <script type="importmap">
  { "imports": { "three": "./vendor/three.module.js" } }
  </script>
</head>
<body style="margin:0;overflow:hidden;">
  <button id="dead1" style="position:fixed;top:10px;left:10px;">Dead 1</button>
  <button id="dead2" style="position:fixed;top:10px;left:80px;">Dead 2</button>
  <script type="module" src="./main.js"></script>
</body>
</html>
"""

BAD_MAIN_JS = """import * as THREE from 'three';
const renderer = new THREE.WebGLRenderer();
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.z = 3;
const cube = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial({ color: 0xff0000 }));
scene.add(cube);
window.app = { scene, camera, renderer, controls: null, presets: {} };
function loop() { requestAnimationFrame(loop); renderer.render(scene, camera); }
loop();
"""


def write_fixture(fixture_dir: Path, html: str, css: str, js: str):
    fixture_dir.mkdir(parents=True, exist_ok=True)
    ensure_vendor_assets(fixture_dir)
    (fixture_dir / "index.html").write_text(html, encoding="utf-8")
    (fixture_dir / "style.css").write_text(css, encoding="utf-8")
    (fixture_dir / "main.js").write_text(js, encoding="utf-8")


def main():
    good_dir = config.FIXTURES_DIR / "good"
    bad_dir = config.FIXTURES_DIR / "bad"
    artifacts_good = config.ARTIFACTS_DIR / "selftest_good"
    artifacts_bad = config.ARTIFACTS_DIR / "selftest_bad"

    write_fixture(good_dir, GOOD_INDEX_HTML, GOOD_STYLE_CSS, GOOD_MAIN_JS)
    write_fixture(bad_dir, BAD_INDEX_HTML, "", BAD_MAIN_JS)

    print("=== 1/2 TESTING GOOD FIXTURE (Expect Score >= 95 & All Gates Passed) ===")
    good_metrics = evaluate_site(good_dir, artifacts_good, runs=1)
    good_score, good_notes, good_gates = score_metrics(good_metrics)
    print(f"GPU Renderer : {good_metrics['scene'].get('renderer')}")
    print(f"2xDPR FPS    : {good_metrics['fps']['avgFps']} (p5 low: {good_metrics['fps']['p5LowFps']})")
    print(f"Input Latency: {good_metrics['in_page_input_latency_ms']}ms")
    print(f"Probes       : {good_metrics['probes']}")
    print(f"Score        : {good_score}/100 | All Gates Passed: {good_gates}")
    if good_notes:
        print(f"Notes        : {good_notes}")

    assert good_gates, f"Good fixture failed gates! Notes: {good_notes}"
    assert good_score >= 95.0, f"Good fixture scored {good_score} (below 95.0)! Notes: {good_notes}"

    print("\n=== 2/2 TESTING BAD FIXTURE (Expect Score < 55 & Gates Failed) ===")
    bad_metrics = evaluate_site(bad_dir, artifacts_bad, runs=1)
    bad_score, bad_notes, bad_gates = score_metrics(bad_metrics)
    print(f"Probes       : {bad_metrics['probes']}")
    print(f"Score        : {bad_score}/100 | All Gates Passed: {bad_gates}")

    assert not bad_gates, "Bad fixture unexpectedly passed gates!"
    assert bad_score < 55.0, f"Bad fixture scored too high ({bad_score})!"

    shutil.rmtree(artifacts_good, ignore_errors=True)
    shutil.rmtree(artifacts_bad, ignore_errors=True)
    print("\n[PASS] Harness self-test succeeded! Arc A750 WebGL, MIME types, camera probes, and scoring verified.")


if __name__ == "__main__":
    main()

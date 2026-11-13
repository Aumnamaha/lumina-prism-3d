import functools
import http.server
import io
import math
import mimetypes
import statistics
import threading
import time
from pathlib import Path
import numpy as np
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright

import config

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")


class HarnessEnvError(RuntimeError):
    """Raised when local GPU/browser infrastructure fails."""


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".html": "text/html",
        ".json": "application/json",
    }

    def log_message(self, format, *args):
        pass


class LocalSiteServer:
    def __init__(self, directory: Path):
        handler = functools.partial(QuietHTTPRequestHandler, directory=str(directory))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *args):
        self.httpd.shutdown()
        self.httpd.server_close()


def _center_crop_array(png_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    crop = img.crop((int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)))
    return np.asarray(crop, dtype=np.int16)


def _is_scene_rendered(png_bytes: bytes) -> bool:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    crop = img.crop((int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)))
    stat = ImageStat.Stat(crop)
    return max(stat.stddev) > 5.0


def _canvas_diff_pct(png_a: bytes, png_b: bytes, channel_threshold: int = 8) -> float:
    arr_a = _center_crop_array(png_a)
    arr_b = _center_crop_array(png_b)
    if arr_a.shape != arr_b.shape:
        return 100.0
    max_channel_diff = np.max(np.abs(arr_a - arr_b), axis=2)
    changed = np.count_nonzero(max_channel_diff > channel_threshold)
    return round(float((changed / max_channel_diff.size) * 100.0), 2)


def _vec_dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _pose_delta(pose_a: dict | None, pose_b: dict | None) -> float:
    if not pose_a or not pose_b:
        return 0.0
    return _vec_dist(pose_a["pos"], pose_b["pos"]) + _vec_dist(pose_a["target"], pose_b["target"])


def _pose_is_distinct(pose: dict, existing_poses: list[dict], min_delta: float = 0.25) -> bool:
    return all(_pose_delta(pose, prev) >= min_delta for prev in existing_poses)


IN_PAGE_HOOKS = """
(() => {
    window.__inputLatencies = [];
    window.addEventListener('pointerdown', () => {
        const t0 = performance.now();
        requestAnimationFrame(() => {
            window.__inputLatencies.push(performance.now() - t0);
        });
    }, { capture: true, passive: true });

    window.__getCameraState = () => {
        const app = window.app || {};
        const cam = app.camera;
        if (!cam) return null;
        const tgt = (app.controls && app.controls.target) ? app.controls.target : { x: 0, y: 0, z: 0 };
        const dx = cam.position.x - tgt.x;
        const dy = cam.position.y - tgt.y;
        const dz = cam.position.z - tgt.z;
        return {
            pos: [cam.position.x, cam.position.y, cam.position.z],
            target: [tgt.x, tgt.y, tgt.z],
            dist: Math.hypot(dx, dy, dz)
        };
    };

    window.__checkHudBounds = () => {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const buttons = Array.from(document.querySelectorAll("button, [role='button']"));
        const clipped = [];
        for (const btn of buttons) {
            const r = btn.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            if (r.left < -1 || r.right > vw + 1 || r.top < -1 || r.bottom > vh + 1) {
                clipped.push((btn.innerText || btn.id || 'button').trim());
            }
        }
        let hasBackdrop = false;
        const sampleBtn = buttons[0];
        if (sampleBtn) {
            let el = sampleBtn.parentElement;
            while (el && el !== document.body) {
                const cs = getComputedStyle(el);
                const bg = cs.backgroundColor || '';
                const blur = cs.backdropFilter || cs.webkitBackdropFilter || '';
                if ((bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') || (blur && blur !== 'none')) {
                    hasBackdrop = true;
                    break;
                }
                el = el.parentElement;
            }
        }
        return {
            overflow: document.documentElement.scrollWidth > vw || clipped.length > 0,
            clippedButtons: clipped,
            hasBackdrop
        };
    };
})();
"""


def _run_single_pass(base_url: str, artifacts_dir: Path, save_screenshots: bool) -> dict:
    console_errors = []
    page_errors = []
    failed_requests = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                channel="chromium",
                headless=True,
                args=[
                    "--use-gl=angle",
                    "--use-angle=d3d11",
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                ],
            )
        except Exception as e:
            raise HarnessEnvError(f"Failed to launch Chromium browser: {e}") from e

        try:
            context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
            context.add_init_script(IN_PAGE_HOOKS)
            page = context.new_page()

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(str(err)))
            page.on("requestfailed", lambda req: failed_requests.append(f"{req.url} ({req.failure})"))

            t0 = time.perf_counter()
            page.goto(f"{base_url}/index.html", wait_until="load", timeout=15000)
            load_time_ms = round((time.perf_counter() - t0) * 1000, 1)
            page.wait_for_timeout(750)

            inspection = page.evaluate("""() => {
                const canvas = document.querySelector('canvas');
                if (!canvas) return { hasCanvas: false };
                const rect = canvas.getBoundingClientRect();
                const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
                let rendererStr = 'unknown';
                if (gl) {
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    if (ext) rendererStr = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
                }

                const app = window.app || {};
                const scene = app.scene;
                const renderer = app.renderer;
                const camera = app.camera;

                let totalMeshCount = 0;
                let centerpieceMeshCount = 0;
                let sculptedMeshCount = 0;
                let floorMeshCount = 0;
                let lightCount = 0;
                let shadowLightCount = 0;
                let pbrMaterialCount = 0;
                let proceduralTextureCount = 0;
                let hasEnvMap = false;

                let minX = Infinity, minY = Infinity, minZ = Infinity;
                let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;

                if (scene && typeof scene.traverse === 'function') {
                    scene.updateMatrixWorld(true);
                    hasEnvMap = Boolean(scene.environment);
                    scene.traverse((obj) => {
                        if (obj.isMesh && obj.geometry) {
                            totalMeshCount++;
                            const geo = obj.geometry;
                            const geoType = geo.type || '';
                            if (!geo.boundingBox) geo.computeBoundingBox();
                            const bb = geo.boundingBox.clone().applyMatrix4(obj.matrixWorld);
                            const spanX = bb.max.x - bb.min.x;
                            const spanZ = bb.max.z - bb.min.z;
                            const isFloor = geoType === 'PlaneGeometry' || (spanX > 6.0 && spanZ > 6.0 && (bb.max.y - bb.min.y) < 0.35);

                            if (isFloor) {
                                floorMeshCount++;
                            } else {
                                centerpieceMeshCount++;
                                minX = Math.min(minX, bb.min.x);
                                minY = Math.min(minY, bb.min.y);
                                minZ = Math.min(minZ, bb.min.z);
                                maxX = Math.max(maxX, bb.max.x);
                                maxY = Math.max(maxY, bb.max.y);
                                maxZ = Math.max(maxZ, bb.max.z);
                            }

                            const posAttr = geo.attributes && geo.attributes.position;
                            const vtxCount = posAttr ? posAttr.count : 0;
                            if (
                                geoType === 'LatheGeometry' ||
                                geoType === 'ExtrudeGeometry' ||
                                geoType === 'TubeGeometry' ||
                                (geoType === 'BufferGeometry' && vtxCount >= 200)
                            ) {
                                sculptedMeshCount++;
                            }

                            const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
                            for (const m of mats) {
                                if (!m) continue;
                                if (m.isMeshStandardMaterial || m.isMeshPhysicalMaterial) {
                                    pbrMaterialCount++;
                                }
                                if (m.envMap) hasEnvMap = true;
                                for (const tex of [m.map, m.roughnessMap, m.bumpMap, m.normalMap, m.metalnessMap]) {
                                    if (tex && tex.isTexture) proceduralTextureCount++;
                                }
                            }
                        }
                        if (obj.isLight) {
                            lightCount++;
                            if (obj.castShadow) shadowLightCount++;
                        }
                    });
                }

                let heroFramingClean = false;
                if (camera && Number.isFinite(minX) && Number.isFinite(maxY)) {
                    camera.updateMatrixWorld(true);
                    let maxAbsNdcX = 0;
                    let maxAbsNdcY = 0;
                    for (const x of [minX, maxX]) {
                        for (const y of [minY, maxY]) {
                            for (const z of [minZ, maxZ]) {
                                const v = camera.position.clone().set(x, y, z).project(camera);
                                maxAbsNdcX = Math.max(maxAbsNdcX, Math.abs(v.x));
                                maxAbsNdcY = Math.max(maxAbsNdcY, Math.abs(v.y));
                            }
                        }
                    }
                    heroFramingClean = maxAbsNdcX <= 0.92 && maxAbsNdcY >= 0.52 && maxAbsNdcY <= 0.88;
                }

                const desktopHud = window.__checkHudBounds();
                const hasBloom = Boolean(
                    app.composer ||
                    (app.passes && app.passes.length > 0) ||
                    document.documentElement.innerHTML.includes('UnrealBloomPass')
                );

                return {
                    hasCanvas: true,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    renderer: rendererStr,
                    pixelRatio: renderer && typeof renderer.getPixelRatio === 'function' ? renderer.getPixelRatio() : 0,
                    horizontalOverflow: desktopHud.overflow,
                    desktopClippedButtons: desktopHud.clippedButtons,
                    hasAppContract: Boolean(scene && renderer && camera),
                    polarAngleClamped: Boolean(
                        app.controls &&
                        typeof app.controls.maxPolarAngle === 'number' &&
                        app.controls.maxPolarAngle <= (Math.PI * 0.505)
                    ),
                    totalMeshCount,
                    centerpieceMeshCount,
                    sculptedMeshCount,
                    floorMeshCount,
                    heroFramingClean,
                    lightCount,
                    shadowLightCount,
                    shadowsEnabled: Boolean(renderer && renderer.shadowMap && renderer.shadowMap.enabled),
                    pbrMaterialCount,
                    proceduralTextureCount,
                    hasEnvMap,
                    hasBloom
                };
            }""")

            renderer_str = inspection.get("renderer", "")
            if any(sw in renderer_str.lower() for sw in ("swiftshader", "llvmpipe", "basic render")):
                raise HarnessEnvError(
                    f"GPU acceleration failed; Chromium fell back to software renderer: {renderer_str}"
                )

            shot_idle_1 = page.screenshot()
            page.wait_for_timeout(450)
            shot_idle_2 = page.screenshot()
            idle_diff_pct = _canvas_diff_pct(shot_idle_1, shot_idle_2)
            probe_non_blank = _is_scene_rendered(shot_idle_1)

            if save_screenshots:
                (artifacts_dir / "01_initial.png").write_bytes(shot_idle_1)

            cam_before_orbit = page.evaluate("() => window.__getCameraState ? window.__getCameraState() : null")

            page.evaluate("""() => {
                window.__fpsFrames = [];
                window.__fpsRunning = true;
                let last = performance.now();
                function tick(now) {
                    if (!window.__fpsRunning) return;
                    window.__fpsFrames.push(now - last);
                    last = now;
                    requestAnimationFrame(tick);
                }
                requestAnimationFrame(tick);
            }""")

            page.mouse.move(720, 450)
            page.mouse.down()
            for step in range(50):
                angle = (step / 50.0) * math.pi * 1.5
                mx = 720 + math.cos(angle) * 180
                my = 450 + math.sin(angle) * 90
                page.mouse.move(mx, my)
                page.wait_for_timeout(45)
            page.mouse.up()
            page.wait_for_timeout(250)

            fps_stats = page.evaluate("""() => {
                window.__fpsRunning = false;
                const deltas = window.__fpsFrames.slice(3);
                if (!deltas.length) return { avgFps: 0, p5LowFps: 0, sampleCount: 0 };
                const avgDelta = deltas.reduce((a, b) => a + b, 0) / deltas.length;
                const sorted = [...deltas].sort((a, b) => b - a);
                const p95Delta = sorted[Math.max(0, Math.floor(sorted.length * 0.05))];
                return {
                    avgFps: Math.round((1000 / avgDelta) * 10) / 10,
                    p5LowFps: Math.round((1000 / p95Delta) * 10) / 10,
                    sampleCount: deltas.length
                };
            }""")

            cam_after_orbit = page.evaluate("() => window.__getCameraState ? window.__getCameraState() : null")
            probe_orbit = False
            if cam_before_orbit and cam_after_orbit:
                rel_before = [p - t for p, t in zip(cam_before_orbit["pos"], cam_before_orbit["target"])]
                rel_after = [p - t for p, t in zip(cam_after_orbit["pos"], cam_after_orbit["target"])]
                orbit_shift = _vec_dist(rel_before, rel_after)
                probe_orbit = orbit_shift > (max(cam_before_orbit["dist"], 0.1) * 0.05)

            cam_before_zoom = cam_after_orbit
            page.mouse.move(720, 450)
            page.mouse.wheel(0, -600)
            page.wait_for_timeout(450)
            cam_after_zoom = page.evaluate("() => window.__getCameraState ? window.__getCameraState() : null")

            probe_zoom = False
            if cam_before_zoom and cam_after_zoom and cam_before_zoom["dist"] > 0.001:
                zoom_ratio_delta = abs(cam_after_zoom["dist"] - cam_before_zoom["dist"]) / cam_before_zoom["dist"]
                probe_zoom = zoom_ratio_delta >= 0.04

            shot_after_zoom = page.screenshot()
            if save_screenshots:
                (artifacts_dir / "02_after_zoom.png").write_bytes(shot_after_zoom)

            buttons = page.locator("button, [role='button']")
            button_count = buttons.count()
            distinct_poses = [cam_after_zoom] if cam_after_zoom else []
            non_camera_mutating_buttons = 0
            prev_shot = shot_after_zoom
            prev_pose = cam_after_zoom

            for idx in range(min(button_count, 8)):
                btn = buttons.nth(idx)
                if btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(650)
                    cur_pose = page.evaluate("() => window.__getCameraState ? window.__getCameraState() : null")
                    cur_shot = page.screenshot()

                    camera_moved = _pose_delta(prev_pose, cur_pose) > 0.05
                    pixels_changed = _canvas_diff_pct(prev_shot, cur_shot) > (idle_diff_pct + 1.0)

                    if cur_pose and _pose_is_distinct(cur_pose, distinct_poses):
                        distinct_poses.append(cur_pose)

                    if pixels_changed and not camera_moved:
                        non_camera_mutating_buttons += 1

                    prev_shot = cur_shot
                    prev_pose = cur_pose

            if save_screenshots:
                (artifacts_dir / "03_after_controls.png").write_bytes(prev_shot)

            probe_camera_presets_work = len(distinct_poses) >= 3
            probe_controls = non_camera_mutating_buttons >= 2

            in_page_latencies = page.evaluate("() => window.__inputLatencies || []")
            median_input_ms = round(statistics.median(in_page_latencies), 1) if in_page_latencies else 0.0

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(350)
            mobile_hud = page.evaluate("() => window.__checkHudBounds()")
            if save_screenshots:
                page.screenshot(path=str(artifacts_dir / "04_mobile.png"))
        finally:
            browser.close()

    return {
        "load_time_ms": load_time_ms,
        "scene": inspection,
        "fps": fps_stats,
        "idle_diff_pct": idle_diff_pct,
        "interactive_buttons": button_count,
        "distinct_camera_poses": len(distinct_poses),
        "working_buttons": non_camera_mutating_buttons,
        "in_page_input_latency_ms": median_input_ms,
        "mobile_overflow": mobile_hud.get("overflow", False),
        "mobile_clipped_buttons": mobile_hud.get("clippedButtons", []),
        "hud_has_backdrop": mobile_hud.get("hasBackdrop", False),
        "probes": {
            "non_blank_3d": probe_non_blank,
            "orbit_works": probe_orbit,
            "zoom_works": probe_zoom,
            "camera_presets_work": probe_camera_presets_work,
            "controls_mutate_3d": probe_controls,
            "multi_mesh_scene": inspection.get("centerpieceMeshCount", 0) >= config.STAGE1_MIN_MESHES,
            "studio_lighting_and_shadows": (
                inspection.get("lightCount", 0) >= 2
                and inspection.get("shadowsEnabled", False)
                and inspection.get("shadowLightCount", 0) >= 1
            ),
            "pbr_and_env_map": (
                inspection.get("pbrMaterialCount", 0) >= 3
                and inspection.get("hasEnvMap", False)
            ),
        },
        "console_errors": console_errors[:10],
        "page_errors": page_errors[:10],
        "failed_requests": failed_requests[:10],
    }


def evaluate_site(workspace_dir: Path, artifacts_dir: Path, runs: int = 3) -> dict:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    pass_results = []

    with LocalSiteServer(workspace_dir) as base_url:
        for idx in range(runs):
            res = _run_single_pass(base_url, artifacts_dir, save_screenshots=(idx == runs - 1))
            pass_results.append(res)

    last = pass_results[-1]
    all_console = list(dict.fromkeys(e for r in pass_results for e in r["console_errors"]))
    all_page = list(dict.fromkeys(e for r in pass_results for e in r["page_errors"]))
    all_failed = list(dict.fromkeys(e for r in pass_results for e in r["failed_requests"]))

    merged_probes = {
        k: all(r["probes"][k] for r in pass_results)
        for k in last["probes"]
    }

    return {
        "load_time_ms": round(statistics.median(r["load_time_ms"] for r in pass_results), 1),
        "scene": last["scene"],
        "fps": {
            "avgFps": round(statistics.median(r["fps"]["avgFps"] for r in pass_results), 1),
            "p5LowFps": round(statistics.median(r["fps"]["p5LowFps"] for r in pass_results), 1),
            "sampleCount": last["fps"].get("sampleCount", 0),
        },
        "interactive_buttons": last["interactive_buttons"],
        "distinct_camera_poses": min(r["distinct_camera_poses"] for r in pass_results),
        "working_buttons": min(r["working_buttons"] for r in pass_results),
        "in_page_input_latency_ms": round(
            statistics.median(r["in_page_input_latency_ms"] for r in pass_results), 1
        ),
        "mobile_overflow": any(r["mobile_overflow"] for r in pass_results),
        "mobile_clipped_buttons": last.get("mobile_clipped_buttons", []),
        "hud_has_backdrop": last.get("hud_has_backdrop", False),
        "probes": merged_probes,
        "all_probes_passed": all(merged_probes.values()),
        "console_errors": all_console[:10],
        "page_errors": all_page[:10],
        "failed_requests": all_failed[:10],
    }

import config
from critic import judge_screenshots


def score_metrics(metrics: dict, model_id: str = "auto") -> tuple[float, list[str], bool]:
    """
    4-Stage Progressive Rubric (0-100):
      - Stage 1 (40 pts): Core 3D scaffold, probes, zero runtime errors, >= 45 FPS at 2x DPR
      - Stage 2 (25 pts): Sculpted geometry (>=14 meshes, >=2 Lathe/Extrude/Tube), full Hero framing, zero mobile/desktop HUD clipping
      - Stage 3 (20 pts): Grounded studio stage, procedural CanvasTexture/DataTexture maps, UnrealBloomPass, floor polar-angle clamp, frosted HUD glass panel
      - Stage 4 (15 pts): VLM / aesthetic screenshot critique across Hero, Detail, and Mobile views
    """
    score = 0.0
    notes = []
    scene = metrics.get("scene", {})
    probes = metrics.get("probes", {})

    if not scene.get("hasAppContract"):
        notes.append("CRITICAL: Expose `window.app = { scene, camera, renderer, controls, presets }` in main.js.")

    # --- STAGE 1: Core Functional & Performance Foundation (40 pts) ---
    s1_weights = [
        ("non_blank_3d", 3.0, "Canvas has no visible 3D centerpiece."),
        ("multi_mesh_scene", 4.0, f"Need >= {config.STAGE1_MIN_MESHES} centerpiece meshes."),
        ("pbr_and_env_map", 4.0, "Need >= 3 PBR materials and scene.environment via RoomEnvironment."),
        ("studio_lighting_and_shadows", 3.0, "Need >= 2 lights with shadowMap enabled and castShadow."),
        ("camera_presets_work", 4.0, f"Only {metrics.get('distinct_camera_poses', 0)} distinct camera poses reached (need >= 3)."),
        ("orbit_works", 3.0, "OrbitControls drag did not move camera."),
        ("zoom_works", 3.0, "Mouse wheel zoom did not change camera distance."),
        ("controls_mutate_3d", 4.0, f"Only {metrics.get('working_buttons', 0)}/2 material/lighting toggle buttons mutated the scene."),
    ]
    for key, pts, msg in s1_weights:
        if probes.get(key):
            score += pts
        else:
            notes.append(f"STAGE 1 FAIL [{key}]: {msg}")

    raw_errors = (
        metrics.get("console_errors", [])
        + metrics.get("page_errors", [])
        + metrics.get("failed_requests", [])
    )
    if not raw_errors and scene.get("hasCanvas"):
        score += 6.0
    else:
        for err in raw_errors[:3]:
            notes.append(f"RUNTIME ERROR: {err}")

    avg_fps = metrics.get("fps", {}).get("avgFps", 0)
    p5_fps = metrics.get("fps", {}).get("p5LowFps", 0)
    pixel_ratio = scene.get("pixelRatio", 0)
    fps_ok = pixel_ratio >= 1.5 and avg_fps >= config.MIN_FPS_FLOOR and p5_fps >= (config.MIN_FPS_FLOOR * 0.7)
    if fps_ok:
        score += 6.0
    else:
        notes.append(f"PERF FAIL: 2xDPR FPS is {avg_fps} (p5={p5_fps}, dpr={pixel_ratio}); must be >= {config.MIN_FPS_FLOOR} FPS.")

    stage1_passed = metrics.get("all_probes_passed", False) and fps_ok and len(raw_errors) == 0

    # --- STAGE 2: Mobile/Desktop HUD Bounds, Hero Framing & Sculpted Geometry (25 pts) ---
    clipped_mobile = metrics.get("mobile_clipped_buttons", [])
    clipped_desktop = scene.get("desktopClippedButtons", [])
    hud_clean = not scene.get("horizontalOverflow") and not metrics.get("mobile_overflow")
    if hud_clean:
        score += 9.0
    else:
        notes.append(
            f"STAGE 2 FAIL [hud_bounds]: HUD buttons clipped off-screen! "
            f"Mobile (390px) clipped: {clipped_mobile or 'overflow'}; Desktop clipped: {clipped_desktop}."
        )

    if scene.get("heroFramingClean"):
        score += 6.0
    else:
        notes.append(
            "STAGE 2 FAIL [hero_framing]: Centerpiece edges clip in Hero camera viewport; pull Hero camera back or adjust target Y."
        )

    mesh_cnt = scene.get("centerpieceMeshCount", 0)
    sculpted_cnt = scene.get("sculptedMeshCount", 0)
    if mesh_cnt >= config.STAGE2_MIN_MESHES and sculpted_cnt >= 2:
        score += 10.0
    else:
        score += min(5.0, (mesh_cnt / config.STAGE2_MIN_MESHES) * 5.0)
        notes.append(
            f"STAGE 2 FAIL [sculpted_geometry]: Centerpiece has {mesh_cnt} meshes and {sculpted_cnt} sculpted profiles "
            f"(need >= {config.STAGE2_MIN_MESHES} joined non-plane meshes and >= 2 Lathe/Extrude/Tube parts)."
        )

    stage2_passed = (
        stage1_passed
        and hud_clean
        and scene.get("heroFramingClean", False)
        and mesh_cnt >= config.STAGE2_MIN_MESHES
        and sculpted_cnt >= 2
    )

    # --- STAGE 3: Studio Stage, Textures, Post-Processing, Floor Clamp & HUD Contrast (20 pts) ---
    has_floor = scene.get("floorMeshCount", 0) >= 1
    if has_floor:
        score += 4.0
    else:
        notes.append("STAGE 3 FAIL [studio_floor]: Add a grounded studio floor/cyclorama receiving shadows.")

    proc_tex = scene.get("proceduralTextureCount", 0)
    if proc_tex >= 1:
        score += 4.0
    else:
        notes.append("STAGE 3 FAIL [procedural_textures]: Add a procedural CanvasTexture or DataTexture roughnessMap/bumpMap.")

    has_bloom = scene.get("hasBloom", False)
    if has_bloom:
        score += 4.0
    else:
        notes.append("STAGE 3 FAIL [postprocessing]: Add EffectComposer + RenderPass + UnrealBloomPass exposed on window.app.composer.")

    polar_ok = scene.get("polarAngleClamped", False)
    if polar_ok:
        score += 4.0
    else:
        notes.append(
            "STAGE 3 FAIL [camera_floor_clamp]: Set `controls.maxPolarAngle = Math.PI * 0.48` so orbiting downward cannot dip underneath the studio stage disc."
        )

    hud_backdrop = metrics.get("hud_has_backdrop", False)
    if hud_backdrop:
        score += 4.0
    else:
        notes.append(
            "STAGE 3 FAIL [hud_contrast]: Wrap HUD controls in a frosted dark glass panel (background: rgba(10, 14, 22, 0.82); backdrop-filter: blur(12px)) anchored at the bottom on mobile (390px) so bright 3D bloom never washes out button labels."
        )

    stage3_passed = stage2_passed and has_floor and proc_tex >= 1 and has_bloom and polar_ok and hud_backdrop

    # --- STAGE 4: VLM Visual Critique Across Hero, Detail & Mobile Screenshots (15 pts) ---
    vlm_pts, vlm_notes = judge_screenshots(config.ARTIFACTS_DIR, metrics, model_id=model_id)
    score += vlm_pts
    notes.extend(vlm_notes)

    all_gates_passed = stage3_passed and vlm_pts >= 11.5
    return round(score, 2), notes, all_gates_passed

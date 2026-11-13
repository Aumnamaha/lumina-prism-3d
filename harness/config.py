from pathlib import Path

# Device 2 (RTX 5070 Ti) LM Studio OpenAI-compatible endpoint
QWEN_BASE_URL = "http://192.168.0.230:1234/v1"
QWEN_API_KEY = "lm-studio"
QWEN_MODEL = "auto"            # Auto-resolves loaded model slug from LM Studio /v1/models
VLM_MODEL = "auto"             # Uses loaded model if multimodal mmproj is enabled; falls back cleanly if text-only

# Sampling & Generation Budgets
TEMPERATURE = 0.6
TOP_P = 0.95
REQUEST_TIMEOUT_SEC = 600
MAX_TOKENS = 16384
API_MAX_RETRIES = 3
MAX_CONSECUTIVE_INFRA_FAILURES = 3
DISABLE_THINKING_ON_EDITS = False

# Directories
ROOT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = ROOT_DIR / "workspace"
ARTIFACTS_DIR = ROOT_DIR / ".eval_artifacts"
FIXTURES_DIR = ROOT_DIR / "fixtures"

# Evaluator & 4-Stage Ladder Rules
EVAL_RUNS = 3
MIN_FPS_FLOOR = 45.0
STAGE1_MIN_MESHES = 6
STAGE2_MIN_MESHES = 14
MAX_ITERATIONS = 18
TARGET_SCORE = 96.0
MAX_REPAIR_ATTEMPTS = 2
MAX_CHANGED_LINES = 180
PLATEAU_LIMIT = 3
MAX_PIVOTS = 2

PROJECT_BRIEF = (
    "Build a studio-grade interactive 3D product showcase web app using Three.js "
    "(loaded via local importmap from ./vendor/) featuring: "
    "(1) an intricately sculpted multi-part 3D centerpiece (>=14 non-plane meshes including custom "
    "LatheGeometry/ExtrudeGeometry/TubeGeometry profiles with zero floating air gaps), "
    "(2) procedural CanvasTexture/DataTexture PBR roughness/bump detail + PMREM RoomEnvironment reflections, "
    "(3) a grounded studio stage/pedestal with soft shadows and subtle EffectComposer + UnrealBloomPass glow, "
    "(4) smooth damped OrbitControls + zoom, >=3 camera presets (Hero, Top, Detail) where the full Hero "
    "centerpiece fits cleanly inside the viewport without edge clipping, colorway and lighting toggles, "
    "and (5) a responsive HUD where every button remains 100% inside the viewport at both 1440px and 390px."
)

INITIAL_BACKLOG = [
    "1. Fix mobile (390px) HUD layout so every button wraps cleanly inside the viewport with zero left/right clipping.",
    "2. Frame the Hero camera so 100% of the centerpiece bounding box fits inside the viewport with comfortable margin.",
    "3. Upgrade centerpiece geometry to >=14 joined meshes using sculpted LatheGeometry/ExtrudeGeometry/TubeGeometry profiles.",
    "4. Add procedural CanvasTexture/DataTexture roughness/bump maps, grounded studio floor/pedestal shadows, and subtle UnrealBloomPass post-processing.",
    "5. Refine specular highlights, colorway contrast, and micro-motion while holding >=45 FPS at 2x DPR."
]



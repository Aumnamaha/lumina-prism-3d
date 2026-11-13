import json
import posixpath
import re
import urllib.error
import urllib.request
from pathlib import Path

FALLBACK_VERSION = "0.170.0"

ROOT_ASSETS = [
    ("three.module.js", "build/three.module.js", "WebGLRenderer", True),
    ("three.core.js", "build/three.core.js", "", False),
    ("controls/OrbitControls.js", "examples/jsm/controls/OrbitControls.js", "OrbitControls", True),
    ("environments/RoomEnvironment.js", "examples/jsm/environments/RoomEnvironment.js", "RoomEnvironment", True),
    ("postprocessing/EffectComposer.js", "examples/jsm/postprocessing/EffectComposer.js", "EffectComposer", True),
    ("postprocessing/RenderPass.js", "examples/jsm/postprocessing/RenderPass.js", "RenderPass", True),
    ("postprocessing/UnrealBloomPass.js", "examples/jsm/postprocessing/UnrealBloomPass.js", "UnrealBloomPass", True),
    ("postprocessing/OutputPass.js", "examples/jsm/postprocessing/OutputPass.js", "OutputPass", True),
    ("postprocessing/ShaderPass.js", "examples/jsm/postprocessing/ShaderPass.js", "ShaderPass", True),
]


def resolve_three_version() -> str:
    try:
        req = urllib.request.Request(
            "https://registry.npmjs.org/three/latest",
            headers={"User-Agent": "autonomous-3d-harness/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            version = data.get("version")
            if version:
                return version
    except Exception:
        pass
    return FALLBACK_VERSION


def _fetch_js(url: str, expected_symbol: str = "", required: bool = True) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "autonomous-3d-harness/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} for {url}")
            raw = resp.read()
            text = raw.decode("utf-8", errors="strict")
            if len(text) < 32 or text.lstrip().startswith("<"):
                raise RuntimeError(f"Invalid JS payload returned from {url}")
            if expected_symbol and expected_symbol not in text:
                raise RuntimeError(f"Expected symbol '{expected_symbol}' missing in {url}")
            return raw
    except urllib.error.HTTPError as e:
        if not required and e.code == 404:
            return None
        raise RuntimeError(f"Failed to download {url}: {e}") from e
    except Exception as e:
        if not required:
            return None
        raise RuntimeError(f"Failed to download {url}: {e}") from e


def _download_with_deps(
    base_cdn: str,
    vendor_dir: Path,
    vendor_rel: str,
    cdn_rel: str,
    visited: set[str],
    expected_symbol: str = "",
    required: bool = True,
):
    if vendor_rel in visited:
        return
    visited.add(vendor_rel)

    url = f"{base_cdn}/{cdn_rel}"
    raw = _fetch_js(url, expected_symbol=expected_symbol, required=required)
    if raw is None:
        return

    dest = vendor_dir / vendor_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    print(f"[VENDOR] Verified & saved {vendor_rel}")

    text = raw.decode("utf-8", errors="ignore")
    for spec in re.findall(r"""(?:from|import)\s*['"](\.[^'"]+\.js)['"]""", text):
        next_vendor_rel = posixpath.normpath(posixpath.join(posixpath.dirname(vendor_rel), spec))
        next_cdn_rel = posixpath.normpath(posixpath.join(posixpath.dirname(cdn_rel), spec))
        if not next_vendor_rel.startswith(".."):
            _download_with_deps(base_cdn, vendor_dir, next_vendor_rel, next_cdn_rel, visited, required=True)


def ensure_vendor_assets(workspace_dir: Path):
    vendor_dir = workspace_dir / "vendor"
    marker = vendor_dir / ".vendor_version_v2"

    if marker.exists() and (vendor_dir / "postprocessing/UnrealBloomPass.js").exists():
        return

    version = resolve_three_version()
    base_cdn = f"https://cdn.jsdelivr.net/npm/three@{version}"
    print(f"[VENDOR] Resolving Three.js v{version} + PostProcessing addons from jsDelivr...")

    visited: set[str] = set()
    for vendor_rel, cdn_rel, symbol, required in ROOT_ASSETS:
        _download_with_deps(base_cdn, vendor_dir, vendor_rel, cdn_rel, visited, symbol, required)

    marker.write_text(version, encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "workspace"
    ensure_vendor_assets(root)
    print("[VENDOR] All Three.js core & postprocessing modules verified.")

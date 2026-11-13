import base64
import io
import json
import re
from pathlib import Path
from openai import OpenAI
from PIL import Image, ImageStat

import config

_VISION_AVAILABLE: bool | None = None


def _encode_png_resized(path: Path, max_dim: int = 768) -> str:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _heuristic_visual_grade(artifacts_dir: Path, metrics: dict) -> tuple[float, list[str]]:
    """Deterministic fallback when LM Studio's loaded GGUF does not have a vision mmproj attached."""
    p_init = artifacts_dir / "01_initial.png"
    if not p_init.exists():
        return 8.0, []

    img = Image.open(p_init).convert("RGB")
    stat = ImageStat.Stat(img)
    mean_luma = sum(stat.mean) / 3.0
    contrast = sum(stat.stddev) / 3.0

    pts = 6.0
    notes = []
    if 6.0 <= mean_luma <= 195.0 and contrast >= 20.0:
        pts += 4.0
    else:
        notes.append("VISUAL: Improve lighting contrast and rim separation against the studio backdrop.")

    if metrics.get("scene", {}).get("hasBloom"):
        pts += 3.0
    if metrics.get("scene", {}).get("proceduralTextureCount", 0) >= 1:
        pts += 2.0

    return min(15.0, pts), notes


def judge_screenshots(artifacts_dir: Path, metrics: dict, model_id: str) -> tuple[float, list[str]]:
    """
    Grades 01_initial.png, 03_after_controls.png, and 04_mobile.png (0-15 pts).
    Uses Device 2 VLM if supported; falls back cleanly if loaded GGUF lacks mmproj.
    """
    global _VISION_AVAILABLE
    shots = [
        artifacts_dir / "01_initial.png",
        artifacts_dir / "03_after_controls.png",
        artifacts_dir / "04_mobile.png",
    ]
    if not all(s.exists() for s in shots) or _VISION_AVAILABLE is False:
        return _heuristic_visual_grade(artifacts_dir, metrics)

    try:
        client = OpenAI(base_url=config.QWEN_BASE_URL, api_key=config.QWEN_API_KEY, max_retries=0)
        content = [
            {
                "type": "text",
                "text": (
                    "You are a senior 3D art director evaluating 3 screenshots of a Three.js product showcase "
                    "(1: Hero desktop, 2: Alternate colorway/detail view, 3: 390px mobile view). "
                    "Score visual quality strictly from 0 to 15 based on: "
                    "(a) sculpted mechanical/industrial design vs crude primitives, "
                    "(b) grounded pedestal/floor shadows (no floating void), "
                    "(c) PBR material richness, reflections & subtle bloom, "
                    "(d) clean unclipped HUD on both desktop and mobile. "
                    'Respond ONLY with JSON: {"visual_score": <0-15>, "critique": ["issue 1", "issue 2"]}'
                ),
            }
        ]
        for s in shots:
            b64 = _encode_png_resized(s)
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": content}],
            temperature=0.2,
            max_tokens=512,
            timeout=90,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = resp.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("Non-JSON VLM response")
        parsed = json.loads(match.group(0))
        _VISION_AVAILABLE = True
        v_score = max(0.0, min(15.0, float(parsed.get("visual_score", 8.0))))
        critiques = [f"VLM CRITIQUE: {c}" for c in parsed.get("critique", [])[:2] if c]
        return round(v_score, 2), critiques
    except Exception:
        _VISION_AVAILABLE = False
        return _heuristic_visual_grade(artifacts_dir, metrics)

import difflib
import json
import re
import subprocess
import time
from pathlib import Path
from openai import APIConnectionError, APIError, APITimeoutError, BadRequestError, OpenAI

import config
from evaluator import HarnessEnvError, evaluate_site
from scorer import score_metrics
from setup_vendor import ensure_vendor_assets


SYSTEM_PROMPT = """You are an elite creative technologist and Three.js engineer in an automated evaluator-optimizer loop.

TECHNICAL REQUIREMENTS:
1. Load Three.js ONLY from local vendored files via importmap in index.html:
   <script type="importmap">
   {
     "imports": {
       "three": "./vendor/three.module.js",
       "three/addons/": "./vendor/"
     }
   }
   </script>
   Available addons:
   - import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
   - import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
   - import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
   - import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
   - import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
   - import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
2. Expose `window.app = { scene, camera, renderer, controls, presets }` in main.js where `presets` maps view names (e.g. "Hero", "Top", "Detail") to camera positions/targets, and `controls` is your OrbitControls instance.
3. Call `renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))` (never hardcode 1).
4. Build a genuine multi-part 3D centerpiece (>=6 non-PlaneGeometry meshes), PBR materials (MeshStandardMaterial / MeshPhysicalMaterial), PMREMGenerator + RoomEnvironment reflections, >=2 lights with shadows enabled, and responsive HUD controls (camera presets + separate colorway/lighting toggles).
5. Include <link rel="icon" href="data:,"> in the <head> of index.html (prevents a favicon 404 console error).

OUTPUT FORMAT:
Always start with ===META===, followed by EITHER surgical ===EDIT: filename=== SEARCH/REPLACE blocks (preferred for incremental updates) OR ===FILE: filename=== full files (for initial scaffold or major structural fixes):

===META===
{"change_summary": "One-sentence summary of the single focused change", "updated_backlog": ["item 1", "item 2"]}
===END===

===EDIT: main.js===
<<<<<<< SEARCH
exact unique existing lines to replace
=======
new replacement lines
>>>>>>> REPLACE
===END===

(Or if creating/rewriting a whole file:)
===FILE: index.html===
complete file content
===END===
"""


class PatchApplyError(ValueError):
    """Raised when response blocks are unclosed, ambiguous, or fail to match."""


class LengthCutoffError(RuntimeError):
    """Raised when generation hits max_tokens; routes straight to smaller-edit repair."""


class ContextLimitError(RuntimeError):
    """Raised on HTTP 400 / context overflow without misdiagnosing Device 2 as offline."""


class InfraFailureError(RuntimeError):
    """Raised when Device 2's API endpoint is unreachable or times out."""


def run_git(args: list[str], cwd: Path) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout.strip()


def init_workspace(workspace: Path):
    workspace.mkdir(parents=True, exist_ok=True)
    ensure_vendor_assets(workspace)
    if not (workspace / ".git").exists():
        run_git(["init"], workspace)
        run_git(["config", "user.name", "Qwen-Optimizer"], workspace)
        run_git(["config", "user.email", "optimizer@local"], workspace)
        (workspace / ".gitignore").write_text(".eval_artifacts/\n__pycache__/\nvendor/\n", encoding="utf-8")
        for fname in ("index.html", "style.css", "main.js"):
            (workspace / fname).write_text("", encoding="utf-8")
        run_git(["add", "."], workspace)
        run_git(["commit", "-m", "init: workspace with vendored Three.js"], workspace)


def read_current_files(workspace: Path) -> dict[str, str]:
    files = {}
    for fname in ("index.html", "style.css", "main.js"):
        p = workspace / fname
        files[fname] = p.read_text(encoding="utf-8") if p.exists() else ""
    return files


def count_changed_lines(old_files: dict[str, str], new_files: dict[str, str]) -> int:
    total = 0
    for fname in ("index.html", "style.css", "main.js"):
        old_lines = old_files.get(fname, "").splitlines()
        new_lines = new_files.get(fname, "").splitlines()
        diff = difflib.unified_diff(old_lines, new_lines, n=0)
        for line in diff:
            if (line.startswith("+") and not line.startswith("+++")) or (
                line.startswith("-") and not line.startswith("---")
            ):
                total += 1
    return total


def write_files(workspace: Path, files: dict[str, str]):
    for fname in ("index.html", "style.css", "main.js"):
        if fname in files:
            (workspace / fname).write_text(files[fname], encoding="utf-8")


def strip_reasoning(text: str) -> str:
    """Strips Qwen3 thinking blocks even when the opening <think> tag lived in the prompt."""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _apply_search_replace(original: str, search_block: str, replace_block: str, fname: str) -> str:
    exact_count = original.count(search_block)
    if exact_count == 1:
        return original.replace(search_block, replace_block, 1)
    if exact_count > 1:
        raise PatchApplyError(
            f"Ambiguous SEARCH block in {fname} (matched {exact_count} places). "
            "Include more surrounding context lines so it matches once."
        )

    orig_lines = original.splitlines(keepends=True)
    search_lines = [l.strip() for l in search_block.splitlines()]
    if not search_lines:
        raise PatchApplyError(f"Empty SEARCH block for {fname}.")

    matching_indices = []
    for i in range(len(orig_lines) - len(search_lines) + 1):
        window = [orig_lines[i + j].strip() for j in range(len(search_lines))]
        if window == search_lines:
            matching_indices.append(i)

    if len(matching_indices) == 1:
        idx = matching_indices[0]
        replacement = replace_block if replace_block.endswith("\n") else replace_block + "\n"
        return "".join(orig_lines[:idx]) + replacement + "".join(orig_lines[idx + len(search_lines) :])
    if len(matching_indices) > 1:
        raise PatchApplyError(
            f"Ambiguous SEARCH block in {fname} ({len(matching_indices)} trimmed matches). Include more context."
        )

    raise PatchApplyError(f"Could not find SEARCH block in {fname}:\n{search_block[:240]}")


def parse_and_apply_response(raw_text: str, current_files: dict[str, str]) -> tuple[dict, dict[str, str]]:
    """Strips thinking traces, verifies block closure integrity, and applies ===FILE:=== / ===EDIT:=== blocks."""
    cleaned = strip_reasoning(raw_text)

    open_markers = re.findall(r"^===(?:META|FILE:[^\r\n=]+|EDIT:[^\r\n=]+)===\s*$", cleaned, flags=re.MULTILINE)
    close_markers = re.findall(r"^===END===\s*$", cleaned, flags=re.MULTILINE)
    if not open_markers or len(open_markers) != len(close_markers):
        raise PatchApplyError(
            f"Unclosed response blocks ({len(open_markers)} opened vs {len(close_markers)} ===END===)."
        )

    meta_match = re.search(r"===META===\s*(.*?)\s*===END===", cleaned, flags=re.DOTALL)
    meta = {}
    if meta_match:
        try:
            meta = json.loads(meta_match.group(1).strip())
        except json.JSONDecodeError:
            meta = {"change_summary": "Incremental update"}

    updated_files = dict(current_files)
    applied_any = False

    for match in re.finditer(r"===FILE:\s*([^\r\n=]+?)\s*===\r?\n(.*?)\r?\n===END===", cleaned, flags=re.DOTALL):
        fname = match.group(1).strip()
        if fname in ("index.html", "style.css", "main.js"):
            updated_files[fname] = match.group(2)
            applied_any = True

    for match in re.finditer(r"===EDIT:\s*([^\r\n=]+?)\s*===\r?\n(.*?)\r?\n===END===", cleaned, flags=re.DOTALL):
        fname = match.group(1).strip()
        if fname not in ("index.html", "style.css", "main.js"):
            continue
        body = match.group(2)
        sr_matches = list(
            re.finditer(
                r"<<<<<<< SEARCH\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n>>>>>>> REPLACE",
                body,
                flags=re.DOTALL,
            )
        )
        if not sr_matches:
            raise PatchApplyError(f"Malformed SEARCH/REPLACE block inside ===EDIT: {fname}===")
        for sr in sr_matches:
            updated_files[fname] = _apply_search_replace(updated_files[fname], sr.group(1), sr.group(2), fname)
            applied_any = True

    if not applied_any:
        raise PatchApplyError("No valid ===FILE:=== or ===EDIT:=== blocks found in response.")

    return meta, updated_files


def required_commit_margin(best_score: float) -> float:
    if best_score < 0:
        return 0.0
    if best_score < 70.0:
        return 1.5
    if best_score < 85.0:
        return 0.8
    return 0.35


def resolve_model_id(client: OpenAI, configured_model: str) -> str:
    """Queries LM Studio /v1/models so exact model slug mismatches never occur."""
    if configured_model and configured_model != "auto":
        return configured_model
    try:
        models = client.models.list()
        available = [m.id for m in models.data if "embed" not in m.id.lower()]
        if not available:
            raise InfraFailureError("LM Studio is reachable, but no chat/code model is currently loaded.")
        return available[0]
    except (APIConnectionError, APITimeoutError, APIError) as e:
        raise InfraFailureError(f"Could not query LM Studio /v1/models at {config.QWEN_BASE_URL}: {e}") from e


def call_qwen_with_retry(
    client: OpenAI,
    model_id: str,
    files: dict[str, str],
    report: dict | None,
    notes: list[str],
    backlog: list[str],
    reverted_history: list[str],
    pivot_instruction: str,
    edit_mode_instruction: str,
    disable_thinking: bool = False,
    repair_feedback: str = "",
) -> tuple[dict, dict[str, str]]:
    context_block = json.dumps(
        {
            "project_brief": config.PROJECT_BRIEF,
            "mode": edit_mode_instruction,
            "pivot_directive": pivot_instruction or "Normal incremental step.",
            "repair_feedback": repair_feedback or "None",
            "ranked_backlog": backlog,
            "latest_test_report": report if report else "No build yet. Create complete v1 files.",
            "diagnostic_priorities": notes,
            "previously_reverted_attempts": reverted_history[-5:],
        },
        indent=2,
    )

    user_prompt = (
        f"CURRENT STATE & DIAGNOSTICS:\n{context_block}\n\n"
        f"===CURRENT FILE: index.html===\n{files['index.html']}\n===END===\n\n"
        f"===CURRENT FILE: style.css===\n{files['style.css']}\n===END===\n\n"
        f"===CURRENT FILE: main.js===\n{files['main.js']}\n===END===\n"
    )

    extra_kwargs = {}
    if disable_thinking:
        extra_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

    last_patch_err = None
    for attempt in range(1, config.API_MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=config.TEMPERATURE,
                top_p=config.TOP_P,
                max_tokens=config.MAX_TOKENS,
                timeout=config.REQUEST_TIMEOUT_SEC,
                **extra_kwargs,
            )
            choice = resp.choices[0]
            raw = choice.message.content or ""
            if choice.finish_reason == "length" or not raw.strip():
                raise LengthCutoffError(
                    "Generation hit max_tokens or exhausted output budget inside thinking."
                )
            return parse_and_apply_response(raw, files)
        except BadRequestError as bad_req:
            raise ContextLimitError(f"HTTP 400 BadRequestError (check context size): {bad_req}") from bad_req
        except (APIConnectionError, APITimeoutError, APIError) as api_err:
            if attempt == config.API_MAX_RETRIES:
                raise InfraFailureError(f"Device 2 API error after {attempt} attempts: {api_err}") from api_err
            wait_s = attempt * 5
            print(f"[API RETRY {attempt}/{config.API_MAX_RETRIES}] ({api_err}); waiting {wait_s}s...")
            time.sleep(wait_s)
        except PatchApplyError as patch_err:
            last_patch_err = patch_err
            if attempt == config.API_MAX_RETRIES:
                raise
            user_prompt += f"\n\nFORMAT/PATCH ERROR ON PREVIOUS OUTPUT: {patch_err}\nFix and output complete valid blocks."

    raise last_patch_err


def revert_workspace(workspace: Path):
    run_git(["reset", "--hard", "HEAD"], workspace)
    run_git(["clean", "-fd", "-e", "vendor/"], workspace)


def main():
    init_workspace(config.WORKSPACE_DIR)
    client = OpenAI(base_url=config.QWEN_BASE_URL, api_key=config.QWEN_API_KEY, max_retries=0)
    active_model = resolve_model_id(client, config.QWEN_MODEL)

    best_score = -1.0
    best_gates_passed = False
    no_gain_streak = 0
    consecutive_infra_failures = 0
    pivots_used = 0
    backlog = list(config.INITIAL_BACKLOG)
    reverted_history = []
    latest_report = None
    latest_notes = ["Build initial working v1 3D showcase passing all scene-graph and camera-state probes."]

    print(f"Starting Stage-Gated Optimizer Loop -> LM Studio @ {config.QWEN_BASE_URL} (Model: {active_model})")

    for step in range(1, config.MAX_ITERATIONS + 1):
        print(
            f"\n=== LOOP {step}/{config.MAX_ITERATIONS} "
            f"(Best: {max(0.0, best_score)}/100 | All Gates Passed: {best_gates_passed}) ==="
        )

        pivot_directive = ""
        if no_gain_streak >= config.PLATEAU_LIMIT:
            if pivots_used >= config.MAX_PIVOTS:
                print("Plateau reached after maximum pivots. Stopping gracefully.")
                break
            pivots_used += 1
            no_gain_streak = 0
            pivot_directive = (
                "STRATEGY PIVOT: Previous incremental edits plateaued. "
                "Rethink the implementation behind the failing probe or lowest-scoring rubric area."
            )
            print(f"[WILL] Triggering Strategy Pivot #{pivots_used}...")

        enforce_diff_cap = best_gates_passed
        edit_instruction = (
            f"Core probes passed. Use surgical ===EDIT: filename=== SEARCH/REPLACE blocks "
            f"(<= {config.MAX_CHANGED_LINES} changed lines)."
            if enforce_diff_cap
            else "Initial build / probe-fixing stage: full ===FILE: filename=== or ===EDIT: filename=== blocks allowed."
        )

        baseline_files = read_current_files(config.WORKSPACE_DIR)
        candidate_files = dict(baseline_files)
        repair_feedback = ""
        committed_this_loop = False
        last_summary = "Unnamed attempt"
        last_failure_reason = ""
        had_infra_error = False

        for repair_idx in range(config.MAX_REPAIR_ATTEMPTS + 1):
            label = "PROPOSE" if repair_idx == 0 else f"REPAIR {repair_idx}/{config.MAX_REPAIR_ATTEMPTS}"
            disable_thinking = config.DISABLE_THINKING_ON_EDITS and (enforce_diff_cap or repair_idx > 0)
            try:
                meta, candidate_files = call_qwen_with_retry(
                    client=client,
                    model_id=active_model,
                    files=candidate_files,
                    report=latest_report,
                    notes=latest_notes,
                    backlog=backlog,
                    reverted_history=reverted_history,
                    pivot_instruction=pivot_directive,
                    edit_mode_instruction=edit_instruction,
                    disable_thinking=disable_thinking,
                    repair_feedback=repair_feedback,
                )
                consecutive_infra_failures = 0
            except LengthCutoffError as len_err:
                last_failure_reason = str(len_err)
                repair_feedback = last_failure_reason
                if all(not v.strip() for v in baseline_files.values()):
                    edit_instruction = (
                        "CRITICAL: Previous response truncated. Output a SMALLER full scaffold using "
                        "===FILE: filename=== blocks only (main.js <= 150 lines, minimal CSS, no comments)."
                    )
                else:
                    edit_instruction = (
                        f"CRITICAL: Previous response truncated at max_tokens. Output ONLY compact "
                        f"===EDIT: filename=== SEARCH/REPLACE blocks (<= {config.MAX_CHANGED_LINES} changed lines)."
                    )
                print(f"[LENGTH CUTOFF -> REPAIR] {last_failure_reason}")
                continue
            except ContextLimitError as ctx_err:
                print(f"\n[ABORT - CONTEXT OVERFLOW] {ctx_err}")
                return
            except InfraFailureError as infra_err:
                had_infra_error = True
                consecutive_infra_failures += 1
                last_failure_reason = str(infra_err)
                print(
                    f"[INFRA ERROR {consecutive_infra_failures}/{config.MAX_CONSECUTIVE_INFRA_FAILURES}] "
                    f"{infra_err}"
                )
                if consecutive_infra_failures >= config.MAX_CONSECUTIVE_INFRA_FAILURES:
                    print("\n[ABORT - DEVICE 2 UNREACHABLE] Consecutive API failures exceeded limit.")
                    return
                break
            except PatchApplyError as patch_err:
                last_failure_reason = f"Patch/format error: {patch_err}"
                print(f"[PATCH FAIL] {last_failure_reason}")
                break

            last_summary = meta.get("change_summary", "Incremental update")
            changed_lines = count_changed_lines(baseline_files, candidate_files)
            print(f"[QWEN - {label}] {last_summary} ({changed_lines} lines changed)")

            if enforce_diff_cap and changed_lines > config.MAX_CHANGED_LINES:
                last_failure_reason = (
                    f"Diff too large ({changed_lines} lines > {config.MAX_CHANGED_LINES} limit). "
                    "Make ONE smaller surgical SEARCH/REPLACE edit."
                )
                repair_feedback = last_failure_reason
                candidate_files = dict(baseline_files)
                continue

            write_files(config.WORKSPACE_DIR, candidate_files)

            try:
                metrics = evaluate_site(config.WORKSPACE_DIR, config.ARTIFACTS_DIR, runs=config.EVAL_RUNS)
            except HarnessEnvError as env_err:
                revert_workspace(config.WORKSPACE_DIR)
                print(f"\n[ABORT - ENVIRONMENT ERROR] {env_err}")
                return
            except Exception as eval_crash:
                last_failure_reason = f"Playwright evaluation crashed: {eval_crash}"
                repair_feedback = last_failure_reason
                print(f"[EVAL CRASH] {last_failure_reason}")
                continue

            score, notes, all_gates_passed = score_metrics(metrics, model_id=active_model)
            gpu_name = metrics.get("scene", {}).get("renderer", "unknown")
            avg_fps = metrics.get("fps", {}).get("avgFps", 0)
            p5_fps = metrics.get("fps", {}).get("p5LowFps", 0)
            samples = metrics.get("fps", {}).get("sampleCount", 0)
            lat_ms = metrics.get("in_page_input_latency_ms", 0)
            passed_count = sum(1 for v in metrics["probes"].values() if v)
            total_probes = len(metrics["probes"])

            print(
                f"[EVAL] GPU: {gpu_name} | 2xDPR FPS: {avg_fps} (p5: {p5_fps}, n={samples}) | "
                f"Input: {lat_ms}ms | Probes: {passed_count}/{total_probes} | Score: {score}/100"
            )

            margin = required_commit_margin(best_score)
            threshold = 0.0 if best_score < 0 else round(best_score + margin, 2)

            if score >= threshold:
                delta = round(score - max(0.0, best_score), 2)
                print(f"[GIT COMMIT] Improved (+{delta}) -> {score}/100")
                best_score = score
                best_gates_passed = all_gates_passed
                no_gain_streak = 0
                latest_report = metrics
                latest_notes = notes
                if meta.get("updated_backlog"):
                    backlog = meta["updated_backlog"]
                run_git(["add", "."], config.WORKSPACE_DIR)
                run_git(["commit", "-m", f"loop {step} [{score}/100]: {last_summary}"], config.WORKSPACE_DIR)
                committed_this_loop = True
                break

            exact_errors = (
                metrics.get("console_errors", [])
                + metrics.get("page_errors", [])
                + metrics.get("failed_requests", [])
            )
            last_failure_reason = (
                f"Scored {score}/100 (needed >= {threshold}). "
                f"Errors: {exact_errors}. Diagnostics: {notes[:3]}"
            )
            repair_feedback = last_failure_reason
            print(f"[REPAIR NEEDED] {last_failure_reason}")

        if not committed_this_loop:
            if read_current_files(config.WORKSPACE_DIR) != baseline_files:
                print("[GIT REVERT] Reverting workspace to last committed state.")
                revert_workspace(config.WORKSPACE_DIR)
            if not had_infra_error:
                no_gain_streak += 1
                reverted_history.append(f"Attempt '{last_summary}' failed -> {last_failure_reason[:240]}")

        if best_score >= config.TARGET_SCORE and best_gates_passed:
            print(f"\nAll scene-graph + camera-state probes passed AND target score reached ({best_score}/100)!")
            break

    print(f"\nFinished. Best committed build in: {config.WORKSPACE_DIR} (Score: {best_score}/100)")


if __name__ == "__main__":
    main()


# Autonomous Dual-Device 3D Optimizer Loop

## Architecture
- **Device 2 (Cortex — RTX 5070 Ti 12GB @ 192.168.1.189:1234):** Serves `Qwen3.6-35B-A3B-GGUF` via LM Studio OpenAI-compatible API.
- **Device 1 (Heart & Will — Intel Arc A750 8GB):** Runs the deterministic evaluator-optimizer loop (`harness/controller.py`), D3D11 hardware-accelerated Playwright stress tests (`harness/evaluator.py`), stage-gated rubric scoring (`harness/scorer.py`), and `git` commit/revert state management.

## Data Contract (`window.app`)
The generated 3D web app in `workspace/` must expose:
`window.app = { scene, camera, renderer, controls, presets }`

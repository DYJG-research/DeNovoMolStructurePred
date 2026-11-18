#!/usr/bin/env bash
set -euo pipefail

# Resolve repository-relative model and adapter paths independently of the caller's cwd.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd -- "${SOURCE_ROOT}"

# =============================================================================
# Experiment 1: deploy the Override-V3 Qwen3-14B LoRA adapter (ms-swift + vLLM)
#
# Required env vars:
#   MODEL     - path to (or ModelScope id of) the Qwen3-14B base model
#   ADAPTERS  - path to the Override-V3 checkpoint-80 adapter directory
#               (download from ModelScope - see DATA.md)
#
# Usage:
#   MODEL=/path/to/Qwen3-14B \
#   ADAPTERS=/path/to/override_v3/checkpoint-80 \
#   bash scripts/formula/serve_override.sh
#
# Core fixed options (do not change for the published model):
#   temperature=0, max_new_tokens=32, enable_thinking=false
# =============================================================================

: "${MODEL:?MODEL (Qwen3-14B base model path/id) is required}"
: "${ADAPTERS:?ADAPTERS (Override-V3 checkpoint-80 adapter path) is required}"

swift deploy \
  --model "${MODEL}" \
  --adapters "${ADAPTERS}" \
  --infer_backend vllm \
  --temperature 0 \
  --max_new_tokens 32 \
  --enable_thinking false

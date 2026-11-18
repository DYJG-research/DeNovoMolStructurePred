#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export PYTHONPATH="$CODE_ROOT${PYTHONPATH:+:$PYTHONPATH}"
# PROJECT_ROOT defaults to the repository root; override only the data root
# if exp2 data lives under a different `work/` tree (see DATA.md).
PROJECT_ROOT="${PROJECT_ROOT:-$CODE_ROOT}"
NEW_DIR="${PROJECT_ROOT}/work/predicted_formula_multihyp_v1"
RANK_DIR="${NEW_DIR}/cross_formula/xgb_oof_v1"
V2_DIR="${RANK_DIR}/pairwise_verifier_v2"

INPUT="${V2_DIR}/pairwise_supervised_full.jsonl"

cd "${PROJECT_ROOT}"

for FOLD in 2 3 4 5; do

    FOLD_DIR="${V2_DIR}/fold${FOLD}_oof"

    echo
    echo "================================================================"
    echo "PREPARING FOLD ${FOLD}"
    echo "================================================================"

    python -u \
      -m pipeline.structure.verification.prepare_pairwise_fold \
      --input "${INPUT}" \
      --target-fold "${FOLD}" \
      --output-dir "${FOLD_DIR}" \
      --seed 20260820

    echo
    cat "${FOLD_DIR}/split_stats.json"

done

echo
echo "================================================================"
echo "ALL FOLDS PREPARED"
echo "================================================================"

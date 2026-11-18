# Molecular-formula pipeline

Run commands from the repository root. Python entry points use `python -m`; use each module's `--help` after installing its dependencies. All paths in examples are explicit local paths, not bundled assets. See [DATA.md](../DATA.md).

## Stage order and interfaces

| Stage | Module under `pipeline.formula` | Inputs → outputs |
| :--- | :--- | :--- |
| Chemical candidate utilities | `candidates.formula_candidates`, `candidates.evaluate_candidate_union` | Precursor/fragment evidence → chemically constrained candidate sets |
| Build ranking data | `ranking.build_preranker_dataset` | Spectrum records and candidate builders → feature matrices, groups, metadata |
| Train formula pre-ranker | `ranking.train_preranker` | Training/validation features → XGBoost model |
| Export shortlist | `ranking.export_shortlist` | Model and candidate features → ranked formula shortlist |
| Prepare listwise initialization | `verification.build_listwise_sft` | Candidate examples → listwise SFT records |
| Prepare formula verification | `verification.build_override_sft` | Required training records and candidate rankings → KEEP/SWAP SFT records |
| Run formula verifier | `verification.infer_override` | **Already gated** shortlist → model decisions |
| Assemble predictions | `verification.merge_override_predictions` | Full shortlist plus decisions → complete formula predictions |
| Evaluate | `evaluation.evaluate_predictions` | Shortlist and verifier decisions → formula metrics |

Use the training partition for model fitting and the validation partition for selection. Keep evaluation IDs and labels separate from predictor inputs.

## Dataset generation

Inspect arguments before constructing candidate features:

```bash
python -m pipeline.formula.ranking.build_preranker_dataset --help
python -m pipeline.formula.ranking.train_preranker --help
python -m pipeline.formula.ranking.export_shortlist --help
```

For full-test candidate construction, explicitly choose the complete test partition and retain spectra whose candidate pool does not contain the reference formula. Sampling and gold-containing-pool filters intended for training must not silently reduce the test denominator.

Repository-owned chemistry/builder modules have source-relative defaults. Their existing override flags can still select an alternative implementation explicitly.

## Train and serve the formula verifier

Shell entry points:

- [train_listwise.sh](../scripts/formula/train_listwise.sh): listwise LoRA initialization.
- [train_override.sh](../scripts/formula/train_override.sh): KEEP/SWAP adaptation.
- [serve_override.sh](../scripts/formula/serve_override.sh): model endpoint for inference.

Typical environment configuration:

```bash
MODEL=/absolute/path/to/Qwen3-14B \
DATASET=/absolute/path/to/listwise_train.jsonl \
OUTPUT_DIR=/absolute/path/to/listwise_adapter \
bash scripts/formula/train_listwise.sh

MODEL=/absolute/path/to/Qwen3-14B \
INIT_ADAPTER=/absolute/path/to/checkpoint-1227 \
DATASET=/absolute/path/to/override_train.jsonl \
VAL_DATASET=/absolute/path/to/override_validation.jsonl \
OUTPUT_DIR=/absolute/path/to/override_adapter \
bash scripts/formula/train_override.sh

MODEL=/absolute/path/to/Qwen3-14B \
ADAPTERS=/absolute/path/to/checkpoint-80 \
bash scripts/formula/serve_override.sh
```

Read the launchers before starting a job and select GPU devices appropriate to your machine. Training and serving require a compatible ms-swift/vLLM/CUDA installation, separate from the CPU-side evaluation tools.

## Verification, merging, and evaluation

The intended formula gate is normalized shortlist margin **z < 0.15**. The `infer_override` client expects an already-gated input; it does not filter the full shortlist itself. Check its endpoint/model configuration before making requests.

The evaluation module also provides a configurable `collect` subcommand:

```bash
python -m pipeline.formula.evaluation.evaluate_predictions collect --help
python -m pipeline.formula.evaluation.evaluate_predictions score --help
```

Merge existing decision files without calling a model:

```bash
mkdir -p work/formula results
python -m pipeline.formula.verification.merge_override_predictions \
  --full data/exp1/preranker_test17556_all_top30_xgb20k_val3000.jsonl \
  --pred data/exp1/override_v3_test17556_gate015_pred.jsonl \
  --output work/formula/final_test17556_xgb_llm_v3.jsonl
```

Score a matching shortlist and decision file:

```bash
python -m pipeline.formula.evaluation.evaluate_predictions score \
  --shortlist-jsonl data/exp1/preranker_test17556_all_top30_xgb20k_val3000.jsonl \
  --predictions data/exp1/override_v3_test17556_gate015_pred.jsonl \
  --gate-threshold 0.15 \
  --expected-n 17556 \
  --mass-valid-ppm 5 \
  --output-json results/formula_metrics.json
```

### Metric definitions

- **Top-1/3/5:** reference neutral formula appears among the leading predictions.
- **Mass validity:** leading formula/adduct assignment is within 5 ppm of the precursor.
- **Formula validity:** chemical parsing and rule checks pass; this is not formula accuracy.
- **Adduct accuracy:** inferred leading adduct matches the annotated reference adduct, used for evaluation rather than as a supplied candidate-generation input.

## Handoff to structure prediction

The assembled formula JSONL is consumed by `pipeline.structure.inputs.convert_formula_predictions` together with the original spectra. Continue with the [structure guide](structure_pipeline.md). Preserve sample IDs across the two stages.

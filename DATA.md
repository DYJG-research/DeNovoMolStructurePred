# Data and pretrained models

This repository contains source code. Store datasets, model weights, and generated results outside the source packages. Paths below are recommended storage conventions; pass the corresponding CLI arguments or launcher environment variables explicitly.

## Availability

| Resource | Location | Status |
| :--- | :--- | :--- |
| MassSpecGym benchmark | <https://github.com/pluskal-lab/MassSpecGym> | Upstream benchmark |
| Qwen3-14B base model | <https://www.modelscope.cn/models/Qwen/Qwen3-14B> | External base model |
| Fine-tuned adapters and formula XGBoost pre-ranker | Local model directories | Hosting links omitted for anonymous review; weights not bundled |
| Study-specific dataset exports, candidate pools, SFT records, and predictions | Zenodo | Record links pending |

External model contents have not been independently downloaded or validated as part of this source reorganization. A base model is required in addition to the LoRA adapters.

## Local model layout

| Local artifact path | Role |
| :--- | :--- |
| `exp1_listwise_sft/checkpoint-1227/` | Listwise formula-reranker initialization adapter |
| `exp1_override_v3/checkpoint-80/` | Formula KEEP/SWAP verifier adapter |
| `exp2_pairwise_verifier/checkpoint-194/` | Pairwise structure-verifier adapter |
| `exp1_xgb_preranker/preranker_xgb_train20000_val3000.json` | Formula candidate pre-ranker |

The checkpoint and artifact names are retained so existing weight files remain usable with the reorganized source.

Place the required model artifacts under `models/` or another local directory. Point `MODEL`, `ADAPTERS`, `INIT_ADAPTER`, or the relevant CLI argument to the actual local path. A base model is required in addition to the adapters. Model hosting links and account-specific download commands are omitted for anonymous review; no anonymous download endpoint is supplied here.

## Which data are available for review?

- **Bundled demo:** the [synthetic example](examples/smoke/README.md) contains three hand-authored spectra, inputs, and expected outputs. It is not drawn from MassSpecGym and needs no downloads.
- **Upstream benchmark:** use the [MassSpecGym project](https://github.com/pluskal-lab/MassSpecGym) for its download and license instructions. Its upstream distributions are not substitutes for the exact study export or the study-specific predictions. The [optional subset instructions](docs/reproducibility.md#optional-prepare-inputs-for-a-few-local-study-spectra) operate on an already-local compatible study export and matching predictions.
- **Study archive:** the prediction and reference artifacts required by the [headline scoring commands](docs/reproducibility.md#recompute-the-headline-tables-from-saved-predictions) are not bundled. Scoring requires the matching test-ID list, formula shortlist and gate decisions, ordered structure predictions, and test references.

## Choose the inputs for your task

### Evaluate predictions

- Reference records restricted to the intended benchmark split.
- Formula predictions or structure predictions with matching sample IDs.
- For MCES, compatible `myopic-mces`, PuLP, and a supported solver.

Retain every expected evaluation ID, including explicit empty predictions. Check for duplicate and missing IDs before evaluating. Formula evaluation can enforce `--expected-n`; not every structure evaluator independently enforces complete split coverage.

### Run pretrained inference

In addition to the evaluation inputs:

- Spectrum records containing precursor information, polarity, and MS/MS peaks.
- Formula candidate inputs and the trained formula pre-ranker.
- Qwen3-14B and the relevant formula/structure adapters.
- SIRIUS/MSNovelist for generating new structure candidates, or supplied candidate outputs.
- Structure-ranking artifacts and the candidate features expected by the selected ranking stage.

### Rebuild training and intermediate files

In addition to inference inputs:

- Training and validation split records.
- Candidate feature matrices and ranking-group metadata.
- Listwise, override, and pairwise SFT datasets.
- Any required exclusion-ID lists and fold metadata.

Model weights alone are not sufficient to reconstruct all training inputs.

## Study artifact inventory

The following names are referenced by the code or run guides. Their Zenodo download links have not yet been provided; they are **not bundled with this repository**.

| Artifact | Purpose |
| :--- | :--- |
| `MassSpecGym1.5.json` | Study dataset export; 231,104 spectra, including 17,556 test spectra |
| `MassSpecGym1.5_retrieval_candidates_formula.json` | Formula candidate input |
| `MassSpecGym1.5_retrieval_candidates_mass.json` | Mass candidate input |
| `preranker_*.X.f32.bin` and associated metadata | Formula-ranking feature matrices |
| `preranker_test17556_all_top30_xgb20k_val3000.jsonl` | Formula Top-30 shortlist |
| `preranker_test17556_gate015_only.jsonl` | Preselected ambiguous formula cases |
| `override_v3_test17556_gate015_pred.jsonl` | Formula-verifier decisions |
| `final_test17556_xgb_llm_v3.jsonl` | Formula predictions consumed by the structure-input converter |
| Formula listwise and override SFT JSONL files | Formula-verifier training inputs |
| `top10_sirius_candidates.jsonl` | SIRIUS/MSNovelist structure candidates |
| `branch_candidates_after_lattice.jsonl` | Formula-Lattice branch candidates |
| `global_formula_structure_pool.jsonl` | Merged structure candidates |
| `xgb_oof_v1/` | Ranking features, labels, grouped-validation scores, and predictions |
| Pairwise supervised/context JSONL files | Structure-verifier training and inference records |
| `final_margin01_predictions.jsonl` | Structure predictions for evaluation |
| Propagation-depth and reference-formula inputs | Controlled mechanism experiments |

Do not infer a dataset's version or experimental configuration from its filename alone. Use matching records, checkpoints, and ranking features together.

## Local storage conventions

```text
data/
  exp1/                 Spectrum exports, formula candidates, SFT records
  exp2/                 Structure candidates and pairwise records
models/
  Qwen3-14B/
  exp1_listwise_sft/checkpoint-1227/
  exp1_override_v3/checkpoint-80/
  exp2_pairwise_verifier/checkpoint-194/
  exp1_xgb_preranker/
work/                   Generated intermediates and predictions
results/                Evaluation summaries
```

These directories are ignored by Git. Source files belong under `pipeline/`, not in the data tree.

For executable module names, argument examples, and source prerequisites, see the [formula guide](docs/formula_pipeline.md) and [structure guide](docs/structure_pipeline.md).

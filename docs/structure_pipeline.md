# Multi-hypothesis structure pipeline

Run Python modules from the repository root. Install the dependencies and prepare matching artifacts as described in [DATA.md](../DATA.md). Pass explicit paths and propagation depth: some utility defaults target smaller configurations.

## Source prerequisites

The following project sources must be supplied before their corresponding stages can execute:

| Source | Affected operations |
| :--- | :--- |
| `pipeline/structure/multiformula_common.py` | Input validation, leakage checking, branch construction, SIRIUS input construction, global-pool assembly, multi-hypothesis lattice prediction |
| `pipeline/structure/generation/build_branch_shard_manifests.py` | Sharded SIRIUS launcher |

The entry points report missing source prerequisites rather than substituting a different implementation. These are project code dependencies, not Python packages to install from PyPI.

## Stage order

| Stage | Module under `pipeline.structure` | Inputs → outputs |
| :--- | :--- | :--- |
| Formula/spectrum handoff | `inputs.convert_formula_predictions` | Formula shortlist and source spectra → multi-formula input |
| Validate and audit | `inputs.validate_multiformula_input`, `inputs.check_ground_truth_leakage` | Multi-formula records → validation/audit reports |
| Build branches | `inputs.build_formula_branches` | Spectrum/formula hypotheses → branch manifest |
| Build SIRIUS inputs | `generation.build_sirius_input` | Branch manifest → branch-level `.ms` inputs |
| Generate and parse | SIRIUS launcher; `generation.parse_sirius_summary` | SIRIUS/MSNovelist exports → structure candidates |
| Expand and merge | `lattice.predict_multihypothesis`, `lattice.build_global_pool` | Branch candidates → expanded branches and global structure pool |
| Build ranking features | `ranking.build_rank_dataset`, then `ranking.add_rdkit_features` | Global candidates and training references → feature records |
| Grouped ranking utility | `ranking.train_oof_ranker` | Labeled candidate groups → out-of-fold scores and ranking summaries |
| Build verifier records | `verification.build_pairwise_dataset`, `verification.prepare_pairwise_fold` | Compatible scored candidates and fold metadata → SFT/context records |
| Pairwise inference | `verification.infer_pairwise` | Model endpoint and context records → confirmed candidate preferences |
| Prediction assembly | `verification.merge_pairwise_oof`, `verification.synchronize_pairwise_predictions` | Matching scores and decisions → assembled predictions |
| Evaluate | `evaluation.evaluate_pairwise_fast`, `evaluation.compute_mces` | Predictions and split-specific references → evaluation summaries |

The shell launchers orchestrate several operations. Inspect their commands before manually repeating an internal parsing or pool-assembly step.

## Convert formula predictions

```bash
mkdir -p work/structure
python -m pipeline.structure.inputs.convert_formula_predictions \
  --exp1 work/formula/final_test17556_xgb_llm_v3.jsonl \
  --massspecgym data/exp1/MassSpecGym1.5.json \
  --top-k 10 \
  --output work/structure/multiformula_input.jsonl \
  --stats work/structure/conversion_stats.json
```

The converter joins records by sample ID and retrieves full spectra from the source dataset. Do not use prompt-truncated peaks as a substitute for full spectra in a formal run. Review conversion statistics before continuing.

Use each input module's `--help` to select paths and the expected formula count:

```bash
python -m pipeline.structure.inputs.validate_multiformula_input --help
python -m pipeline.structure.inputs.build_formula_branches --help
python -m pipeline.structure.generation.build_sirius_input --help
```

These commands require the shared source helper listed above.

## SIRIUS/MSNovelist

[run_sirius_sharded.sh](../scripts/structure/run_sirius_sharded.sh) requires explicit paths:

```bash
PROJECT_ROOT="$PWD" \
SIRIUS_BIN=/absolute/path/to/sirius \
BRANCH_MANIFEST=/absolute/path/to/branch_manifest.jsonl \
SIRIUS_INPUT_ROOT=/absolute/path/to/sirius_inputs \
RUN_ROOT=/absolute/path/to/sirius_runs \
MERGED_CANDIDATES=/absolute/path/to/top10_sirius_candidates.jsonl \
bash scripts/structure/run_sirius_sharded.sh
```

Use SIRIUS **6.3.7** with MSNovelist available and the appropriate external access configuration. Inspect the launcher before execution: a run can rebuild shard outputs, so use a dedicated work directory rather than an irreplaceable result directory.

The independent single-formula input/parser tools are under `generation.prepare_single_formula_sirius_input` and `generation.parse_single_formula_summary`.

## Formula-Lattice and the global pool

The reusable graph-edit chemistry is in `lattice.formula_lattice_core`; the multi-hypothesis predictor and global-pool builder use it without changing the stage interfaces.

```bash
PROJECT_ROOT="$PWD" \
BRANCH_MANIFEST=/absolute/path/to/branch_manifest.jsonl \
MERGED_CANDIDATES=/absolute/path/to/top10_sirius_candidates.jsonl \
LATTICE_ROOT=/absolute/path/to/lattice_run \
bash scripts/structure/run_multihypothesis_lattice.sh
```

The method includes same-formula transfer between spectra and formula-neighbour graph editing. Keep the intended processing batch and candidate provenance consistent across runs. Input/reference label attachment belongs to evaluation or supervised-data construction, not predictor prompts.

## Ranking and pairwise verification

Inspect the separate ranking stages in dependency order:

```bash
python -m pipeline.structure.ranking.build_rank_dataset --help
python -m pipeline.structure.ranking.add_rdkit_features --help
python -m pipeline.structure.ranking.train_oof_ranker --help
python -m pipeline.structure.verification.build_pairwise_dataset --help
python -m pipeline.structure.verification.infer_pairwise --help
```

- Ranking features, candidate IDs, fold metadata, and verifier contexts must refer to the same candidate set.
- The grouped ranking utility fits and scores the supplied labeled groups; do not treat it as a generic frozen-model prediction command.
- Pairwise data preparation requires score records with the fold/provenance fields it consumes. Check the schema of supplied score artifacts before chaining stages.
- The manuscript's structure-verification margin is **0.1**. Pass the intended margin explicitly rather than relying on generic utility defaults.
- Use the **structure** verifier adapter (`checkpoint-194`), not the formula adapter.
- The API client compares a leading candidate with challengers. The matching merge utility must retain candidate IDs and the full ranked list consistently.
- Fold-based helpers select their own fold and paths; configure each fold explicitly. The [fold preparation launcher](../scripts/structure/prepare_pairwise_folds.sh) prepares the additional folds.

These operations require your own configured model endpoint and compatible ms-swift/vLLM deployment. Basic repository tests never call that endpoint.

## Evaluation

Create output directories and evaluate a matching set of predictions:

```bash
mkdir -p results
python -m pipeline.structure.evaluation.evaluate_pairwise_fast \
  --predictions data/exp2/final_margin01_predictions.jsonl \
  --massspecgym data/exp1/MassSpecGym1.5.json \
  --output results/structure_metrics.json \
  --with-truth work/structure/predictions_with_truth.jsonl

python -m pipeline.structure.evaluation.compute_mces \
  --truth data/exp2/test_truth.jsonl \
  --predictions data/exp2/final_margin01_predictions.jsonl \
  --threshold 15 \
  --invalid-distance 100 \
  --cap 100 \
  --output results/mces_metrics.json
```

The truth file for MCES must contain **only the intended evaluation IDs**. Check exact, unique coverage of all 17,556 test IDs before scoring; supplied prediction rows determine the denominator of the fast evaluator. Retain explicit empty predictions rather than silently omitting IDs.

Metrics:

- **Exact match:** first InChIKey block, representing 2D connectivity.
- **ECFP4:** radius-2, 2048-bit Morgan fingerprints; maximum Tanimoto similarity among the first K structures; missing/invalid predictions receive zero.
- **MCES:** `myopic-mces==1.0.0`, `pulp==2.9.0`, threshold 15, stronger-bound handling; minimum distance among the first K structures, with invalid/missing distance 100 and cap 100.

Additional candidate-pool, cross-formula, per-fold, and summary evaluators are grouped under `pipeline.structure.evaluation`.

## Controlled formula conditions

`mechanisms.build_predicted_top10_input` constructs the dedicated Top-10 experiment input and requires its specified precursor artifacts. `mechanisms.build_reference_formula_input` constructs the reference-formula condition with `mechanisms.reference_formula_chemistry`. These utilities have distinct prerequisites; do not assume their outputs are interchangeable with a generic converter solely because the requested K is the same.

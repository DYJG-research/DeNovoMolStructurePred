# Review and reproducibility guide

Use the path appropriate to what you want to verify. Run the commands from the repository root, not from an extracted data archive.

| Goal | Included here | Additional requirements |
| :--- | :--- | :--- |
| Run a small, offline check | [Synthetic example](../examples/smoke/README.md), runner, expected output | Python only; no package installation, network, GPU, or model weights |
| Recompute headline metrics from saved predictions | Evaluation code, commands, and input contracts below | Release-matched predictions, references, and test IDs; RDKit for structure scoring, plus PuLP and myopic-mces for MCES |
| Regenerate predictions or retrain | Source and stage guides | Study inputs, matching models/features/configurations, SIRIUS/MSNovelist, and a compatible GPU software stack for model steps |

## Environment and timing

The synthetic demo was tested in fresh Python virtual environments without pip or third-party packages on Ubuntu 22.04.4 LTS, x86-64, Linux kernel 5.15.0-94-generic. With Python already installed, there is no package installation step. Five runs with each interpreter took 0.47–0.51 s with Python 3.10.12 (median 0.49 s) and 0.55–0.57 s with Python 3.13.13 (median 0.56 s). These are demo wall times on one host, not guarantees or training/inference times. The demo requires no CUDA, RDKit, or XGBoost. Windows and macOS were not tested.

The manuscript reports Python **3.11.15**, RDKit **2026.03.4**, SIRIUS **6.3.7** with MSNovelist, and an experiment host with **eight NVIDIA A100-SXM4-80GB GPUs**. This is reported hardware, not a minimum requirement or evidence that every stage used eight GPUs. The exact original OS/distribution, driver, CUDA, PyTorch, XGBoost, Java, MSNovelist, ms-swift, vLLM, and solver versions are not established in this checkout. Original package installation times, stage wall times, and peak memory or compute hours are likewise not established.

For saved-prediction scoring, formula replay uses only Python. Structure 2D exact/ECFP4 scoring requires RDKit. MCES also needs `pulp==2.9.0`, `myopic-mces==1.0.0`, and an available PuLP solver. For example, on a compatible CPU host with Python 3.11, create a separate scoring environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install 'rdkit>=2024.0' 'pulp==2.9.0' 'myopic-mces==1.0.0'
```

This is a dependency specification, not an independently validated lockfile. For a benchmark comparison, use and report the exact RDKit build and solver; for the full workflow, see [requirements.txt](../requirements.txt) and the [installation instructions](../README.md#installation). Install the PyTorch build appropriate for the driver/CUDA combination, and verify compatibility with ms-swift/vLLM separately; do not infer it from the A100 model name.

## Recompute the headline tables from saved predictions

The study artifacts below are **not bundled or anonymously downloadable from this checkout**; see [DATA.md](../DATA.md). These commands require matching predictions, references, and test IDs for the benchmark run. No GPU or model service is required for saved-prediction scoring.

### Inputs and coverage

| Input | Contract |
| :--- | :--- |
| Versioned test-ID list | 17,556 unique spectrum identifiers, one per line, from the predefined test partition |
| Formula shortlist JSONL | One object per test `identifier`, with `true_formula`, `true_adduct` (evaluation-only), ordered `shortlist` entries (`formula`, `best_adduct`, stored `ppm_error`), and `z_margin` or aligned `preranker_scores` |
| Formula decisions JSONL | Unique `identifier` and `decision` (`KEEP`/`SWAP`) for the evaluated gate; a decision file is not a full test-partition manifest |
| Structure predictions JSONL | One object per test `identifier`, with ordered `predictions` SMILES, or `predictions: []` for an empty pool |
| Structure truth JSONL | One object per test `identifier` with valid `true_smiles`; project the matching, test-only references into this format if the study archive supplies them in a larger export |

Before scoring, compare the unique ID sets of the full shortlist, structure predictions, and structure truth with the same test-ID list. Require exactly one row per ID and no missing/extra rows. Check that every decision ID is unique and eligible for the formula gate; report any gated samples without a decision. Do not drop empty predictions, change to intersection-only scoring, or use the candidate count as the spectrum denominator. Formula `--expected-n` checks the row count only; the fast structure scorer counts prediction rows, and MCES in truth scope counts unique valid truth IDs.

Set `ARCHIVE` to the directory with the matched inputs. File names below are expected local names, not release identifiers or a guarantee of provenance.

```bash
ARCHIVE=data/review-archive
OUT=results/recomputed
mkdir -p "$OUT"

python -m pipeline.formula.evaluation.evaluate_predictions score \
  --shortlist-jsonl "$ARCHIVE/preranker_test17556_all_top30_xgb20k_val3000.jsonl" \
  --predictions "$ARCHIVE/override_v3_test17556_gate015_pred.jsonl" \
  --gate-threshold 0.15 --expected-n 17556 --mass-valid-ppm 5 \
  --output-json "$OUT/formula_metrics.json"

python -m pipeline.structure.evaluation.evaluate_pairwise_fast \
  --predictions "$ARCHIVE/final_margin01_predictions.jsonl" \
  --massspecgym "$ARCHIVE/test_truth.jsonl" \
  --output "$OUT/structure_metrics.json" \
  --with-truth "$OUT/predictions_with_truth.jsonl"

python -m pipeline.structure.evaluation.compute_mces \
  --truth "$ARCHIVE/test_truth.jsonl" \
  --predictions "$ARCHIVE/final_margin01_predictions.jsonl" \
  --scope truth --threshold 15 --invalid-distance 100 --cap 100 \
  --output "$OUT/mces_metrics.json"
```

Check `best.baseline` and `best.final` in the formula report. Accuracies and rates in the JSON are fractions; multiply by 100 for percent. The scorer applies `SWAP` only below the gate, and the mass-valid rate uses the stored ppm values.

The structure report measures 2D connectivity via the first InChIKey block and ECFP4 Tanimoto (radius 2, 2,048 bits); it is not stereochemical validation. MCES reports `mces_at_1` and `mces_at_10` (lower is better). Check the recorded solver and pair errors when interpreting the averages. The [plotting utilities](../figures/README.md) render embedded numbers; they do not recompute metrics from these commands.

The single **predicted** Top-1 formula propagation setting is a restricted comparison for the multi-hypothesis method. It uses the same downstream procedure with fewer formula hypotheses; it is not the separate reference-formula control. Report external baselines as quoted or rerun as appropriate and identify the corresponding split and configuration. This repository does not establish that every external baseline was rerun.

## Optional: prepare inputs for a few local study spectra

Begin with [the upstream MassSpecGym project](https://github.com/pluskal-lab/MassSpecGym) for its data instructions and license. Upstream distributions are not asserted to be identical to the study's `MassSpecGym1.5.json` export and do not provide matching study-specific formula predictions. The following commands are for a **compatible local study export** and matching formula predictions, not a download or a conversion of raw upstream TSV. The [synthetic example](../examples/smoke/README.md) is the only bundled download-free dataset.

Save a few exact identifiers, one per line, from the intended split in `data/review-subset-ids.txt`. The extractor keeps their explicit order and fails on a missing or duplicate selected ID in either source. It streams JSONL, but loads an input JSON array into memory; for large arrays, prepare a compatible JSONL export first if memory is limited. IDs and full peaks are preserved. The extracted spectra can contain benchmark references: use the **converted handoff**, not the extracted raw records, as model input.

```bash
SUBSET=work/review-subset
python -B scripts/select_study_subset.py \
  --spectra data/exp1/MassSpecGym1.5.json \
  --formulas work/formula/final_test17556_xgb_llm_v3.jsonl \
  --ids data/review-subset-ids.txt --out "$SUBSET"
python -B -m pipeline.structure.inputs.convert_formula_predictions \
  --exp1 "$SUBSET/formulas.jsonl" --massspecgym "$SUBSET/spectra.jsonl" --top-k 10 \
  --output "$SUBSET/structure_input.jsonl" --stats "$SUBSET/conversion_stats.json"
python -B -m pipeline.structure.inputs.validate_multiformula_input \
  --input "$SUBSET/structure_input.jsonl" --max-formulas 10 \
  --stats "$SUBSET/validation_stats.json"
python -B -m pipeline.structure.inputs.check_ground_truth_leakage \
  --input "$SUBSET/structure_input.jsonl"
```

Compare the output `sample_id` list with `ids.txt` and inspect conversion statistics for missing spectra, missing full peaks, or malformed shortlists. The converter's `--limit` is not a split selector. It reads the ordered `shortlist`, not the merger's separate `final_formula`; use the dedicated, matched Top-10 experiment inputs for manuscript replication. The subset prepares model inputs; it does not run structure generation or measure benchmark accuracy.

## Regenerate or retrain

Follow the [formula](formula_pipeline.md) and [structure](structure_pipeline.md) stage guides with matching artifacts from [DATA.md](../DATA.md). Full formula test feature generation must retain all test IDs, including spectra for which the correct formula is missing from the candidate pool. Match the baseline or ten-predicted-formula setup, use the intended 0.1 structure verifier margin, and confirm the score/fold provenance expected by the pairwise stage. An OOF score file is not automatically a frozen ranker or a compatible fold handoff. Reconstruction of SIRIUS-input code and a passing demo do not validate SIRIUS/MSNovelist, model weights, the original environment, or the full training workflow.

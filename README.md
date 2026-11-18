# Anonymous Research Code

Research code for predicting molecular formulas and de novo molecular structures from tandem mass spectra. Instead of committing to one predicted formula, the framework retains multiple chemically plausible hypotheses, generates structures in parallel formula-conditioned branches, and compares the resulting candidates in a shared ranking space.

## Quick start: offline reviewer demo

From the repository root, with Python already installed:

```bash
python -B scripts/run_smoke_demo.py
```

Expected final line:

```text
PASS: formula Top-1 2/3 -> 3/3; 6 SIRIUS inputs (4+2); pairwise 3 rows, 1 promotion, 1 empty.
```

The [three synthetic inputs and expected outputs](examples/smoke/README.md) are included. No package installation, network, GPU, or model weights are required. Tested on Ubuntu 22.04.4 LTS (x86-64) with Python 3.10.12 and 3.13.13; median run times were 0.49 and 0.56 seconds, respectively (five runs each). The demo replays supplied scores and decisions and prepares SIRIUS inputs; it does **not** run SIRIUS/MSNovelist, trained models, or the manuscript benchmark. For scoring archived predictions, environment details, and a local study subset, see the [review and reproducibility guide](docs/reproducibility.md).

## Method overview

1. **Chemically constrained formula inference.** Enumerate formula candidates, construct spectral and chemical features, rank candidates with XGBoost, and selectively verify ambiguous leading assignments with a fine-tuned Qwen3-14B model.
2. **Multi-hypothesis structure generation.** Propagate the top molecular-formula hypotheses through independent SIRIUS/MSNovelist branches.
3. **Formula-Lattice expansion.** Extend candidate accessibility through same-formula spectral transfer and chemically constrained formula-neighbour graph editing.
4. **Joint structure ranking and verification.** Merge formula-conditioned pools, rank structures across formulas, and selectively compare the leading structure with challengers using a separately fine-tuned verifier.

The main configuration propagates **10 predicted formulas**. Reference-formula experiments are a separate controlled condition, not an input requirement for the main method.

## Results reported in the manuscript

[Source Data workbook](results/Source_Data.xlsx): main paper results for Figs. 2 and 3.

Evaluation uses the predefined **MassSpecGym test partition: 17,556 spectra**. The values below are manuscript-reported results, not results recomputed during repository preparation.

### Molecular-formula prediction

| Metric | Value |
| :--- | ---: |
| Top-1 accuracy | 63.87% |
| Top-3 accuracy | 77.34% |
| Top-5 accuracy | 81.44% |
| Mass-valid rate, absolute error ≤ 5 ppm | 91.25% |
| Formula validity | 100.00% |
| Adduct accuracy | 79.90% |

### De novo structure prediction

| Metric | Top-1 | Top-10 |
| :--- | ---: | ---: |
| Exact structure accuracy | 20.50% | 27.20% |
| ECFP4 Tanimoto similarity | 0.4291 | 0.5177 |
| MCES distance ↓ | 15.17 | 10.91 |

Exact recovery is evaluated at the **2D connectivity** level using the first InChIKey block. These metrics do not establish stereochemical identification.

## Repository organization

```text
pipeline/
  formula/
    candidates/       Chemical enumeration and candidate-union utilities
    ranking/          Feature generation, XGBoost training, shortlist export
    verification/     Listwise/override data, verifier inference, prediction merging
    evaluation/       Molecular-formula evaluation
  structure/
    inputs/           Prediction conversion, validation, formula branches
    generation/       SIRIUS inputs and exported structure parsing
    lattice/          Graph-edit chemistry and multi-hypothesis expansion
    ranking/          Ranking features and grouped cross-validation utilities
    verification/     Pairwise datasets, inference, prediction assembly
    evaluation/       Exact match, fingerprints, MCES, fold summaries
    mechanisms/       Reference-formula and propagation-depth input construction
scripts/
  formula/            LoRA training and model-serving launchers
  structure/          SIRIUS, lattice, and fold-preparation launchers
figures/scripts/      Standalone plotting utilities
docs/                 Stage-by-stage run guides
tests/                Dependency-free repository and interface checks
```

Run Python modules from the repository root with `python -m pipeline.…`. Script names describe their purpose; the run guides specify the dependency order.

## Installation

The manuscript reports **Python 3.11.15**, **RDKit 2026.03.4**, **SIRIUS 6.3.7**, and experiments on a server with **eight NVIDIA A100-SXM4-80GB GPUs**. Resource needs depend on the stage; feature processing and evaluation do not require loading the language model.

From the supplied source directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Optional: standalone plotting utilities
python -m pip install -r requirements-figures.txt
```

[requirements.txt](requirements.txt) lists the Python dependencies for the research pipeline. See [Environment and timing](docs/reproducibility.md#environment-and-timing) for the tested demo environment, recorded experiment versions, and GPU setup requirements. The offline demo does not use these dependencies.

Additional tools:

| Tool | Purpose |
| :--- | :--- |
| SIRIUS 6.3.7 with MSNovelist | Formula-conditioned structure generation |
| ms-swift and a compatible vLLM/PyTorch/CUDA stack | Qwen3-14B LoRA training and serving |
| A supported PuLP solver | MCES evaluation |
| ModelScope SDK, optional | Downloading pretrained weights |

## Data and pretrained models

See **[DATA.md](DATA.md)** for artifact roles, model paths, and local storage conventions.

- **Benchmark:** [MassSpecGym](https://github.com/pluskal-lab/MassSpecGym).
- **Adapters and formula pre-ranker:** place the required artifacts in local directories as described in [DATA.md](DATA.md). Hosting links are omitted for anonymous review; weights are not included.
- **Base language model:** [Qwen/Qwen3-14B](https://www.modelscope.cn/models/Qwen/Qwen3-14B).
- **Study-specific datasets and intermediate predictions:** see the [artifact inventory](DATA.md#study-artifact-inventory).

## Running the pipeline

| Task | Guide |
| :--- | :--- |
| Formula candidate construction, ranking, verification, and evaluation | [Formula pipeline](docs/formula_pipeline.md) |
| Formula branches, SIRIUS, lattice, structure ranking, verification, and evaluation | [Structure pipeline](docs/structure_pipeline.md) |
| Standalone plotting utilities and output conventions | [Figures](figures/README.md) |

Three tasks require different inputs:

- **Evaluate existing predictions:** use matching reference records and prediction files; no language-model weights are needed.
- **Run pretrained inference:** additionally obtain candidate inputs, XGBoost artifacts, the base model, and the corresponding adapters.
- **Rebuild training and intermediates:** additionally obtain training/validation records, candidate features, SFT datasets, and external generation tools.

## Basic validation

The structural and synthetic interface tests use the Python standard library and do not download data, load models, call APIs, or run SIRIUS:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

These checks validate repository organization, syntax, internal paths, and selected file interfaces. They do not replace a full benchmark evaluation.

## License

[Apache License 2.0](LICENSE). Third-party software, benchmark data, base-model weights, and externally hosted artifacts remain subject to their own licenses and access conditions.

## Chemically Constrained Multi-Hypothesis Inference for De Novo Molecular Structure Prediction from Tandem Mass Spectra

Research code for predicting molecular formulas and de novo molecular structures from tandem mass spectra. Instead of committing to one predicted formula, the framework retains multiple chemically plausible hypotheses, generates structures in parallel formula-conditioned branches, and compares the resulting candidates in a shared ranking space.

**Authors:** Jianbin Guo, Hongmin Du, Sibo Wei (first author), Kangjun Liu (second author), Wenpeng Lu, Peng Zhang, Lei Wang, Yin Luo, Lifeng Dong, and Hongjun Yang.

**Repository:** <https://github.com/DYJG-research/DeNovoMolStructurePred>

## Method overview

1. **Chemically constrained formula inference.** Enumerate formula candidates, construct spectral and chemical features, rank candidates with XGBoost, and selectively verify ambiguous leading assignments with a fine-tuned Qwen3-14B model.
2. **Multi-hypothesis structure generation.** Propagate the top molecular-formula hypotheses through independent SIRIUS/MSNovelist branches.
3. **Formula-Lattice expansion.** Extend candidate accessibility through same-formula spectral transfer and chemically constrained formula-neighbour graph editing.
4. **Joint structure ranking and verification.** Merge formula-conditioned pools, rank structures across formulas, and selectively compare the leading structure with challengers using a separately fine-tuned verifier.

The main configuration propagates **10 predicted formulas**. Reference-formula experiments are a separate controlled condition, not an input requirement for the main method.

## Results reported in the manuscript

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

```bash
git clone https://github.com/DYJG-research/DeNovoMolStructurePred.git
cd DeNovoMolStructurePred
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Optional: standalone plotting utilities
python -m pip install -r requirements-figures.txt
```

The requirements specify Python dependencies, **not a fully locked environment**. Install a PyTorch build appropriate for your CUDA environment before GPU training or serving.

Additional tools:

| Tool | Purpose |
| :--- | :--- |
| SIRIUS 6.3.7 with MSNovelist and compatible Java | Formula-conditioned structure generation |
| ms-swift and a compatible vLLM/PyTorch/CUDA stack | Qwen3-14B LoRA training and serving |
| A supported PuLP solver | MCES evaluation |
| ModelScope SDK, optional | Downloading pretrained weights |

## Data and pretrained models

See **[DATA.md](DATA.md)** for artifact roles, model paths, and local storage conventions. Large data files and weights are not included in Git.

- **Benchmark:** [MassSpecGym](https://github.com/pluskal-lab/MassSpecGym).
- **Adapters and formula pre-ranker:** [eibicidi/mols on ModelScope](https://www.modelscope.cn/models/eibicidi/mols).
- **Base language model:** [Qwen/Qwen3-14B](https://www.modelscope.cn/models/Qwen/Qwen3-14B).
- **Study-specific datasets and intermediate predictions:** Zenodo record links are pending. Do not assume they are available from this checkout.

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

**Source prerequisites:** the structure workflow also requires the project helper `pipeline/structure/multiformula_common.py` and the shard-manifest builder used by the SIRIUS launcher. These files are not included in this checkout. The [structure guide](docs/structure_pipeline.md) identifies the affected steps. Full end-to-end execution requires those sources and the external artifacts; this repository preparation does not constitute a complete experimental rerun.

## Basic validation

The structural and synthetic interface tests use the Python standard library and do not download data, load models, call APIs, or run SIRIUS:

```bash
python -m unittest discover -s tests -v
```

These checks validate repository organization, syntax, internal paths, and selected file interfaces. They do not replace a full benchmark evaluation.

## Citation

Please cite the manuscript:

> Jianbin Guo, Hongmin Du, Sibo Wei, Kangjun Liu, Wenpeng Lu, Peng Zhang, Lei Wang, Yin Luo, Lifeng Dong, and Hongjun Yang. *Chemically Constrained Multi-Hypothesis Inference for De Novo Molecular Structure Prediction from Tandem Mass Spectra*.

A publication DOI will be added when available.

## License

[Apache License 2.0](LICENSE). Third-party software, benchmark data, base-model weights, and externally hosted artifacts remain subject to their own licenses and access conditions.

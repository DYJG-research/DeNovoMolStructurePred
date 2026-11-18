# Plotting utilities

The standalone sources in [scripts/](scripts/) cover formula prediction, adduct dependence, ablations, structure comparison, propagation depth, and candidate-pool coverage.

## Install and run

From the repository root:

```bash
python -m pip install -r requirements-figures.txt
MPLBACKEND=Agg python figures/scripts/fig2a_formula_accuracy.py
```

Scripts write PDF, SVG, and PNG files under `./figures/`, relative to the **working directory**. Generated renders are ignored by Git. For interactive display, omit `MPLBACKEND=Agg`.

## Source and output names

| Source in `scripts/` | Output stem |
| :--- | :--- |
| `fig2a_formula_accuracy.py` | `fig2a_formula_accuracy_final` |
| `fig2b_adduct_dependence.py` | `fig2c_adduct_dependence` |
| `fig2c_formula_ablation.py` | `fig2dd_ablation_formula_accuracy` (PDF); `fig2dd__ablation_formula_accuracy` (PNG/SVG) |
| `fig2d_prediction_reliability.py` | `fig2e_prediction_reliability` |
| `fig2e_reference_formula_coverage.py` | `fig2e_reference_formula_coverage` |
| `fig3a_structure_top1_comparison.py` | `fig4a_rank1_accuracy_mces` |
| `fig3b_structure_ablation.py` | `fig2b_ablation_slope_compact` |
| `fig3c_structure_top10_comparison.py` | `fig4b_top10_accuracy_mces` |
| `fig3d_formula_hypothesis_trends.py` | `fig_formula_hypothesis_trends` |
| `fig3e_fingerprint_similarity.py` | `fig4c_denovo_ecfp4_dumbbell_refined` |
| `fig3f_empty_candidate_pools.py` | `fig2f_formula_lattice_reduction_gong_shape` |

## Data handling

These scripts are plotting utilities: they contain embedded numeric arrays and **do not calculate benchmark metrics from predictions**. Before preparing publication figures, supply the source data associated with the intended experiment and verify it against the manuscript. Running a plotting script is not experimental validation and does not guarantee a panel matching the current manuscript.

No pre-generated publication panels or presentation files are distributed here. The latest manuscript-reported results are summarized in the [repository README](../README.md).

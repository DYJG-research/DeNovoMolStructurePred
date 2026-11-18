# Offline synthetic demo

From the repository root, with Python already installed:

```bash
python -B scripts/run_smoke_demo.py
```

No package installation, network, GPU, or model weights are required. The command prints the path of a new temporary output directory, then verifies the generated files and exits with status 0 on success. The final line should be:

```text
PASS: formula Top-1 2/3 -> 3/3; 6 SIRIUS inputs (4+2); pairwise 3 rows, 1 promotion, 1 empty.
```

[inputs.json](inputs.json) contains three hand-authored spectra and prefilled shortlists, formula references and decisions, and independent pairwise scores and decisions. It contains no MassSpecGym data. The m/z, peak, and stored ppm values are illustrative interface fixtures, not validated instrument measurements or a physical mass-accuracy benchmark. [expected_summary.json](expected_summary.json) gives the stable machine-readable expected result.

| Output under the printed directory | What to inspect |
| :--- | :--- |
| `demo_summary.json`, `formula_metrics.json` | One gated SWAP and one gated KEEP; a third case is ungated. Formula Top-1 changes from 2/3 to 3/3 on these fixtures only. |
| `merged_formulas.jsonl`, `structure_input.jsonl` | The SWAP updates the final assignment but leaves the original shortlist order, which the structure converter uses. Full peaks are retained. Scoring labels are not included in the structure handoff. |
| `branches.jsonl`, `shards/`, `sirius_inputs/` | Six branch rows across two shards (four and two), with one matching `.ms` input per branch. SIRIUS/MSNovelist is **not** run. |
| `structure_predictions.jsonl`, `pairwise_summary.json` | Independent replay of supplied structure scores and a pairwise decision. One candidate is promoted; all three rows, including one empty prediction, are retained. Label hits use fixture labels, not 2D molecular identity. |

This demonstrates scoring, input preparation, and prediction assembly on a small example. It does not generate formulas or structures from scratch, run trained models, or reproduce manuscript results. See the [reproducibility guide](../../docs/reproducibility.md) for measured timing and the separate benchmark instructions. The output directory may be removed once you have inspected the files.

#!/usr/bin/env python3
"""Run and check the offline synthetic review example."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "smoke"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run_module(module, *args):
    result = subprocess.run(
        [sys.executable, "-B", "-m", f"pipeline.{module}", *map(str, args)],
        cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ValueError(f"{module} failed ({result.returncode}):\n{result.stdout}{result.stderr}")


def index(rows, key="identifier"):
    mapping = {row[key]: row for row in rows}
    require(len(mapping) == len(rows), f"Duplicate {key}")
    return mapping


def formula_replay(fixture, out):
    shortlist, truth = index(fixture["shortlists"]), index(fixture["formula_truth"])
    decisions = index(fixture["formula_decisions"])
    require(shortlist.keys() == truth.keys(), "Shortlist and truth IDs differ")
    require(decisions.keys() == {sid for sid, row in shortlist.items() if row["z_margin"] < 0.15},
            "Expected exactly the gated decision IDs")
    require(sorted(row["decision"] for row in decisions.values()) == ["KEEP", "SWAP"],
            "Expected one synthetic KEEP and one SWAP")
    scoring = write_rows(out / "scoring_shortlist.jsonl", [dict(row, **truth[sid]) for sid, row in shortlist.items()])
    model_input = write_rows(out / "shortlist.jsonl", shortlist.values())
    decision_path = write_rows(out / "formula_decisions.jsonl", decisions.values())
    report = out / "formula_metrics.json"
    run_module("formula.evaluation.evaluate_predictions", "score", "--shortlist-jsonl", scoring,
               "--predictions", decision_path, "--gate-threshold", 0.15, "--expected-n", 3,
               "--mass-valid-ppm", 5, "--output-json", report)
    best = load(report)["best"]
    before, after = best["baseline"], best["final"]
    require(before["N"] == after["N"] == 3 and after["Top-3 Accuracy"] == after["Top-5 Accuracy"] == 1,
            "Unexpected formula scoring coverage")
    merged = out / "merged_formulas.jsonl"
    run_module("formula.verification.merge_override_predictions", "--full", model_input,
               "--pred", decision_path, "--output", merged)
    merged_rows = index(read_rows(merged))
    require(merged_rows.keys() == shortlist.keys(), "Formula assembly dropped IDs")
    for sid, row in merged_rows.items():
        require(row["shortlist"] == shortlist[sid]["shortlist"], f"Shortlist changed for {sid}")
        require((row["final_formula"], row["final_adduct"]) == (truth[sid]["true_formula"], truth[sid]["true_adduct"]),
                f"Unexpected final formula or adduct for {sid}")
    return merged, {"samples": after["N"], "gated": best.get("gated", 0), "swaps": best.get("swaps", 0),
                    "top1_before": round(before["Top-1 Accuracy"] * before["N"]),
                    "top1_after": round(after["Top-1 Accuracy"] * after["N"])}


def prepare_structure(fixture, merged, out):
    spectra = index(fixture["spectra"])
    spectra_path = write_rows(out / "spectra.jsonl", spectra.values())
    handoff, stats = out / "structure_input.jsonl", out / "conversion_stats.json"
    run_module("structure.inputs.convert_formula_predictions", "--exp1", merged, "--massspecgym", spectra_path,
               "--top-k", 2, "--output", handoff, "--stats", stats)
    converted = index(read_rows(handoff), "sample_id")
    require(converted.keys() == spectra.keys() and load(stats)["output_rows"] == len(spectra),
            "Spectrum handoff dropped IDs")
    shortlists = index(fixture["shortlists"])
    for sid, row in converted.items():
        require(row["peaks"] == spectra[sid]["peaks"], f"Spectrum peaks changed for {sid}")
        observed = [(h["rank"], h["formula"], h["adduct"]) for h in row["formula_hypotheses"]]
        wanted = [(i, c["formula"], c["best_adduct"]) for i, c in enumerate(shortlists[sid]["shortlist"], 1)]
        require(observed == wanted, f"Structure handoff changed ranked shortlist for {sid}")
    run_module("structure.inputs.validate_multiformula_input", "--input", handoff, "--max-formulas", 2,
               "--stats", out / "validation_stats.json")
    run_module("structure.inputs.check_ground_truth_leakage", "--input", handoff)
    manifest, ms_dir, shard_dir = out / "branches.jsonl", out / "sirius_inputs", out / "shards"
    run_module("structure.inputs.build_formula_branches", "--input", handoff, "--max-formulas", 2,
               "--shard-size", 4, "--output", manifest, "--stats", out / "branch_stats.json")
    run_module("structure.generation.build_sirius_input", "--branches", manifest, "--output-dir", ms_dir,
               "--stats", out / "sirius_input_stats.json")
    shard_stats = out / "shard_stats.json"
    run_module("structure.generation.build_branch_shard_manifests", "--branches", manifest,
               "--output-dir", shard_dir, "--stats", shard_stats)
    branches = read_rows(manifest)
    index(branches, "branch_id")
    expected_files = set()
    per_shard = load(shard_stats)["shard_counts"]
    for shard in per_shard:
        members = [row for row in branches if f"shard_{row['shard_id']:05d}" == shard]
        require(len(members) == per_shard[shard] and members == read_rows(shard_dir / f"{shard}.jsonl"),
                f"Shard membership differs for {shard}")
        for branch in members:
            target = ms_dir / shard / f"{branch['branch_id']}.ms"
            expected_files.add(target)
            headers, peaks = target.read_text(encoding="utf-8").split(">ms2\n", 1)
            for key, val in (("compound", branch["branch_id"]), ("formula", branch["formula"]),
                             ("ionization", branch["adduct"])):
                require(f">{key} {val}\n" in headers, f"Incorrect .ms {key} header: {target.name}")
            require([list(map(float, line.split())) for line in peaks.splitlines() if line.strip()]
                    == spectra[branch["sample_id"]]["peaks"], f"Incorrect .ms peaks: {target.name}")
    require(set(ms_dir.rglob("*.ms")) == expected_files, "Unexpected .ms file set")
    return {"spectra": len(converted), "branches": len(branches), "ms_files": len(expected_files), "shard_counts": per_shard}


def pairwise_replay(fixture, out):
    scores = write_rows(out / "pairwise_scores.jsonl", fixture["structure_scores"])
    samples = write_rows(out / "pairwise_samples.jsonl", ({"sample_id": r["identifier"]} for r in fixture["spectra"]))
    folds = out / "pairwise_folds"
    for fold in range(1, 6):
        folder = "fold1_pilot" if fold == 1 else f"fold{fold}_oof"
        write_rows(folds / folder / f"fold{fold}_pairwise_predictions.jsonl",
                   fixture["pairwise_decisions"] if fold == 1 else [])
    predictions, summary = out / "structure_predictions.jsonl", out / "pairwise_summary.json"
    run_module("structure.verification.merge_pairwise_oof", "--scores", scores, "--samples", samples,
               "--v2-dir", folds, "--threshold", 0.1, "--policy", "final_lowest_rank_confirmed",
               "--output", predictions, "--summary", summary)
    rows, metrics = index(read_rows(predictions)), load(summary)
    require(rows.keys() == index(fixture["spectra"]).keys(), "Structure replay dropped a sample")
    expected_orders = {"synthetic-a": ["a2", "a1"], "synthetic-b": ["b1", "b2"], "synthetic-c": []}
    score_by_id = index(fixture["structure_scores"], "candidate_id")
    for sid, order in expected_orders.items():
        require(rows[sid]["candidate_ids"] == order and rows[sid]["predictions"] == [score_by_id[c]["smiles"] for c in order],
                f"IDs and SMILES out of sync for {sid}")
    require([sid for sid, row in rows.items() if row["pairwise_applied"]] == ["synthetic-a"],
            "Pairwise decision applied to the wrong sample")
    return {"samples": metrics["num_samples"], "promotions": metrics["changed"], "empty": metrics["num_empty_predictions"],
            "label_top1_before": metrics["baseline_top1_hits"], "label_top1_after": metrics["final_top1_hits"],
            "label_top10_before": metrics["baseline_top10_hits"], "label_top10_after": metrics["final_top10_hits"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    out = Path(tempfile.mkdtemp(prefix="massspec-smoke-"))
    print(f"Demo outputs: {out}", flush=True)
    try:
        fixture = load(EXAMPLE / "inputs.json")
        merged, formula = formula_replay(fixture, out)
        summary = {"formula": formula, "structure_preparation": prepare_structure(fixture, merged, out),
                   "pairwise_replay": pairwise_replay(fixture, out)}
        (out / "demo_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        require(summary == load(EXAMPLE / "expected_summary.json"), "Unexpected summary; inspect demo_summary.json")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print("PASS: formula Top-1 2/3 -> 3/3; 6 SIRIUS inputs (4+2); pairwise 3 rows, 1 promotion, 1 empty.")


if __name__ == "__main__":
    main()

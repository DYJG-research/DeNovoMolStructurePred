"""Synthetic tests for the reconstructed structure-preparation interfaces."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pipeline.structure.generation.build_branch_shard_manifests import build_manifests
from pipeline.structure.multiformula_common import (
    canonical_formula, find_forbidden_paths, normalize_adduct, normalize_polarity,
    read_jsonl, validate_model_row, write_jsonl,
)

ROOT = Path(__file__).resolve().parents[1]


def model_row():
    return {
        "sample_id": "sample-a", "precursor_mz": 61.0, "polarity": "pos",
        "peaks": [[25.0, 0], [45.0, 2.0]],
        "formula_hypotheses": [
            {"rank": 2, "formula": "C2H6O", "adduct": "[M+Na]+"},
            {"rank": 1, "formula": "C2H5OF", "adduct": "[M + H]+", "ppm_error": -1.5},
        ],
    }


class TemporaryWorkspace(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def run_module(self, name, *args):
        return subprocess.run(
            [sys.executable, "-m", f"pipeline.structure.{name}", *map(str, args)],
            cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True, text=True, check=False,
        )

    def rows(self, path):
        return [row for _, row in read_jsonl(path)]


class CommonTests(TemporaryWorkspace):
    def test_jsonl_line_numbers_and_errors(self):
        path = self.work / "rows.jsonl"
        path.write_text('\n{"value":"é"}\n\n{"value":2}', encoding="utf-8")
        self.assertEqual([(2, {"value": "é"}), (4, {"value": 2})], list(read_jsonl(path)))
        for invalid in ("[]", "{"):
            path.write_text('\n{"value":1}\n' + invalid, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"rows\.jsonl:3:"):
                list(read_jsonl(path))
        output = self.work / "nested" / "out.jsonl"
        write_jsonl(output, iter([{"value": "é"}]))
        self.assertEqual('{"value": "é"}\n', output.read_text(encoding="utf-8"))

    def test_chemistry_and_ion_normalization(self):
        self.assertEqual("C2H5FO", canonical_formula("OC2H5F"))
        self.assertEqual("ClH", canonical_formula("HCl"))
        self.assertEqual("C2H6O", canonical_formula("CH3CH3O"))
        for invalid in ("C0H6", "C2H6O+", "C-H", "Xx2", "C(OH)2", ""):
            self.assertIsNone(canonical_formula(invalid), invalid)
        self.assertEqual("[M+FA-H]-", normalize_adduct(" [M + FA - H]- "))
        self.assertIsNone(normalize_adduct("-"))
        self.assertEqual("negative", normalize_polarity("NEG"))

    def test_validates_without_mutating_and_preserves_absolute_ranks(self):
        row = model_row()
        row["formula_hypotheses"][0]["rank"] = 12
        row["formula_hypotheses"][1]["rank"] = 11
        row["formula_hypotheses"][1]["confidence"] = None
        snapshot = json.dumps(row)
        self.assertEqual([], validate_model_row(row, max_formulas=10))
        self.assertEqual(snapshot, json.dumps(row))

    def test_validation_errors_and_bad_sample_id_cli(self):
        row = model_row()
        row.update(sample_id=[], precursor_mz="inf", peaks=[[25, -1]])
        row["formula_hypotheses"][0].update(rank=True, score="nan", adduct="[M-H]-")
        errors = validate_model_row(row, max_formulas=10)
        for field in ("sample_id", "precursor_mz", "peaks[0]", ".rank", ".score", ".adduct"):
            self.assertTrue(any(field in err for err in errors), errors)
        source, stats = self.work / "source.jsonl", self.work / "report.json"
        write_jsonl(source, [row])
        result = self.run_module("inputs.validate_multiformula_input", "--input", source, "--stats", stats)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(1, json.loads(stats.read_text())["bad"])
        for invalid_ranks in ((1, 1), (1, 3), (2, 1.5)):
            row = model_row()
            for h, rank in zip(row["formula_hypotheses"], invalid_ranks):
                h["rank"] = rank
            self.assertTrue(any("rank" in err for err in validate_model_row(row, max_formulas=10)))

    def test_truth_paths_do_not_block_generated_structure_fields(self):
        row = {"target_formula": "C2H6O", "candidates": [{"smiles": "CCO", "inchikey2d": "dummy"}]}
        self.assertEqual([], find_forbidden_paths(row))
        row["candidates"][0]["true_smiles"] = None
        row["metadata"] = {"formula": "C2H6O", "experiment": "synthetic"}
        self.assertEqual(["candidates[0].true_smiles", "metadata.formula"], find_forbidden_paths(row))
        audit_input = self.work / "audit.jsonl"
        write_jsonl(audit_input, [row])
        audit = self.run_module("inputs.check_ground_truth_leakage", "--input", audit_input)
        self.assertNotEqual(0, audit.returncode)
        self.assertIn("candidates[0].true_smiles", audit.stdout)


class ShardTests(TemporaryWorkspace):
    def setUp(self):
        super().setUp()
        self.manifest = self.work / "manifest.jsonl"
        self.shards = self.work / "shards"
        self.stats = self.work / "stats.json"
        self.a = {"branch_id": "a", "shard_id": 7, "formula": "C2H5OF"}
        self.b = {"branch_id": "b", "shard_id": 0, "peaks": [[25, 1]]}
        self.c = {"branch_id": "c", "shard_id": 7, "extra": {"score": None}}

    def test_group_sparse_interleaved_ids_and_clean_only_generated_files(self):
        write_jsonl(self.manifest, [self.a, self.b, self.c])
        result = self.run_module(
            "generation.build_branch_shard_manifests", "--branches", self.manifest,
            "--output-dir", self.shards, "--stats", self.stats,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([self.a, self.c], self.rows(self.shards / "shard_00007.jsonl"))
        self.assertEqual([self.b], self.rows(self.shards / "shard_00000.jsonl"))
        self.assertTrue((self.shards / "shard_00007.jsonl").read_bytes().endswith(b"\n"))
        self.assertEqual({
            "branches": 3, "num_shards": 2, "shard_counts": {"shard_00000": 1, "shard_00007": 2},
            "output_dir": str(self.shards),
        }, json.loads(self.stats.read_text()))
        keep = self.shards / "shard_notes.jsonl"
        keep.touch()
        (self.shards / "shard_00008.jsonl").mkdir()
        symlink = self.shards / "shard_00009.jsonl"
        symlink.symlink_to(keep)
        write_jsonl(self.manifest, [self.b])
        build_manifests(self.manifest, self.shards, self.stats)
        self.assertTrue((self.shards / "shard_00007.jsonl").exists())
        build_manifests(self.manifest, self.shards, self.stats, clean=True)
        self.assertEqual(
            {"shard_00000.jsonl", "shard_00008.jsonl", "shard_00009.jsonl", "shard_notes.jsonl"},
            {path.name for path in self.shards.iterdir()},
        )
        self.assertTrue(symlink.is_symlink())

    def test_invalid_input_leaves_existing_outputs_unchanged(self):
        write_jsonl(self.manifest, [self.a])
        build_manifests(self.manifest, self.shards, self.stats)
        existing = self.shards / "shard_00007.jsonl"
        before = existing.read_bytes(), self.stats.read_bytes()
        first = json.dumps(self.b) + "\n\n"
        for text in ("\n", first + "{", first + json.dumps(self.b), first + json.dumps({"branch_id": "x", "shard_id": True})):
            self.manifest.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                build_manifests(self.manifest, self.shards, self.stats, clean=True)
            self.assertEqual(before, (existing.read_bytes(), self.stats.read_bytes()))
            self.assertFalse((self.shards / "shard_00000.jsonl").exists())

    def test_output_conflicts_do_not_replace_or_remove_input(self):
        self.shards.mkdir()
        prior = self.shards / "shard_00000.jsonl"
        write_jsonl(prior, [self.a])
        for row in (self.a, self.b):
            write_jsonl(prior, [row])
            with self.assertRaises(ValueError):
                build_manifests(prior, self.shards, self.stats, clean=True)
            self.assertEqual([row], self.rows(prior))
        with self.assertRaises(ValueError):
            build_manifests(prior, self.work / "other", prior)
        write_jsonl(self.manifest, [self.b])
        target = self.work / "new-shards"
        with self.assertRaisesRegex(ValueError, "conflicts"):
            build_manifests(self.manifest, target, target / "shard_00000.jsonl/report.json")
        self.assertFalse(target.exists())


class PreparationChainTests(TemporaryWorkspace):
    def test_preparation_cli_and_sirius_merge_with_cached_synthetic_candidates(self):
        first = model_row()
        second = dict(model_row(), sample_id="sample-b", polarity="neg", formula_hypotheses=[
            {"rank": 1, "formula": "HCl", "adduct": "[M-H]-"},
        ])
        input_path, manifest = self.work / "input.jsonl", self.work / "manifest.jsonl"
        ms_root, run_root = self.work / "ms", self.work / "run"
        write_jsonl(input_path, [first, second])
        for name, args in (
            ("inputs.validate_multiformula_input", ["--input", input_path, "--stats", self.work / "validate.json"]),
            ("inputs.check_ground_truth_leakage", ["--input", input_path]),
            ("inputs.build_formula_branches", ["--input", input_path, "--output", manifest,
                                               "--stats", self.work / "branch.json", "--shard-size", "2"]),
            ("generation.build_sirius_input", ["--branches", manifest, "--output-dir", ms_root,
                                               "--stats", self.work / "ms.json"]),
        ):
            proc = self.run_module(name, *args)
            self.assertEqual(0, proc.returncode, proc.stderr)
        branches = self.rows(manifest)
        self.assertEqual([("C2H5FO", 0), ("C2H6O", 0), ("ClH", 1)],
                         [(row["formula"], row["shard_id"]) for row in branches])
        write_jsonl(run_root / "shard_00099" / "branch_candidates.jsonl", [{"branch_id": "stale"}])
        for row in branches:
            tag = f"shard_{row['shard_id']:05d}"
            ms = (ms_root / tag / f"{row['branch_id']}.ms").read_text()
            self.assertIn(f">compound {row['branch_id']}\n", ms)
            self.assertIn(f">formula {row['formula']}\n", ms)
        for tag, group in (("shard_00000", branches[:2]), ("shard_00001", branches[2:])):
            write_jsonl(run_root / tag / "branch_candidates.jsonl", [dict(row, candidates=[]) for row in reversed(group)])
        manifest.write_text("\n" + manifest.read_text().rstrip("\n"), encoding="utf-8")
        merged = self.work / "merged.jsonl"
        proc = subprocess.run(
            ["bash", str(ROOT / "scripts/structure/run_sirius_sharded.sh")],
            cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PROJECT_ROOT=str(ROOT), SIRIUS_BIN=str(self.work / "not-installed"),
                     BRANCH_MANIFEST=str(manifest), SIRIUS_INPUT_ROOT=str(ms_root), RUN_ROOT=str(run_root),
                     MERGED_CANDIDATES=str(merged), REBUILD_SHARDS="0", PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual(branches, self.rows(run_root / "branch_shards/shard_00000.jsonl")
                         + self.rows(run_root / "branch_shards/shard_00001.jsonl"))
        self.assertEqual([row["branch_id"] for row in branches],
                         [row["branch_id"] for row in self.rows(merged)])
        self.assertEqual(2, proc.stdout.count("[SKIP]"))

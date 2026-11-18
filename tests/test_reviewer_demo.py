"""Exercise the reviewer commands and their published artifacts."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class ReviewerDemoTests(unittest.TestCase):
    def run_command(self, *args, temp):
        return subprocess.run(
            [sys.executable, "-B", *map(str, args)], cwd=ROOT,
            env={**os.environ, "TMPDIR": str(temp), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, check=False,
        )

    def test_documented_command_and_matched_subset(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            result = self.run_command("scripts/run_smoke_demo.py", temp=temp)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("6 SIRIUS inputs (4+2); pairwise 3 rows, 1 promotion, 1 empty.", result.stdout)
            out = Path(result.stdout.splitlines()[0].removeprefix("Demo outputs: "))
            expected = json.loads((ROOT / "examples/smoke/expected_summary.json").read_text())
            self.assertEqual(expected, json.loads((out / "demo_summary.json").read_text()))
            self.assertEqual(6, len(list((out / "sirius_inputs").rglob("*.ms"))))
            self.assertEqual([], rows(out / "structure_predictions.jsonl")[-1]["predictions"])

            ids = temp / "ids.txt"
            ids.write_text("synthetic-c\nsynthetic-a\n", encoding="utf-8")
            spectra = temp / "spectra.json"
            spectra.write_text(json.dumps(rows(out / "spectra.jsonl")), encoding="utf-8")
            subset = temp / "subset"
            result = self.run_command("scripts/select_study_subset.py", "--spectra", spectra,
                                      "--formulas", out / "merged_formulas.jsonl", "--ids", ids,
                                      "--out", subset, temp=temp)
            self.assertEqual(0, result.returncode, result.stderr)
            result = self.run_command("-m", "pipeline.structure.inputs.convert_formula_predictions",
                                      "--exp1", subset / "formulas.jsonl", "--massspecgym", subset / "spectra.jsonl",
                                      "--top-k", "2", "--output", subset / "structure_input.jsonl",
                                      "--stats", subset / "conversion_stats.json", temp=temp)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(["synthetic-c", "synthetic-a"],
                             [r["sample_id"] for r in rows(subset / "structure_input.jsonl")])
            for module, extra in (
                ("validate_multiformula_input", ["--stats", subset / "validation_stats.json"]),
                ("check_ground_truth_leakage", []),
            ):
                result = self.run_command("-m", f"pipeline.structure.inputs.{module}",
                                          "--input", subset / "structure_input.jsonl", *extra, temp=temp)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_missing_or_duplicate_selected_ids_fail_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            ids, spectra, formulas, out = (temp / name for name in ("ids.txt", "spectra.jsonl", "formulas.jsonl", "out"))
            ids.write_text("one\n", encoding="utf-8")
            spectra.write_text('{"identifier":"one"}\n', encoding="utf-8")
            for text, message in (("", "Missing requested IDs"), ('{"identifier":"one"}\n' * 2, "Duplicate requested ID")):
                formulas.write_text(text, encoding="utf-8")
                result = self.run_command("scripts/select_study_subset.py", "--spectra", spectra, "--formulas", formulas,
                                          "--ids", ids, "--out", out, temp=temp)
                self.assertNotEqual(0, result.returncode)
                self.assertIn(message, result.stderr)
                self.assertFalse(out.exists())

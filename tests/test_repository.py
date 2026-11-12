"""Dependency-free checks for the source layout and portable file interfaces."""

import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTests(unittest.TestCase):
    def test_all_python_sources_parse(self):
        sources = list((ROOT / "pipeline").rglob("*.py"))
        sources += list((ROOT / "figures" / "scripts").glob("*.py"))
        self.assertEqual(41, sum(p.name != "__init__.py" for p in (ROOT / "pipeline").rglob("*.py")))
        self.assertEqual(11, len(list((ROOT / "figures" / "scripts").glob("*.py"))))
        for path in sources:
            with self.subTest(path=path.relative_to(ROOT)):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_package_initializers(self):
        for source in (ROOT / "pipeline").rglob("*.py"):
            directory = source.parent
            while directory != ROOT:
                self.assertTrue((directory / "__init__.py").is_file(), str(directory))
                directory = directory.parent

    def test_shell_syntax(self):
        scripts = list((ROOT / "scripts").rglob("*.sh"))
        self.assertEqual(6, len(scripts))
        for path in scripts:
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_internal_package_imports_resolve(self):
        missing = {"pipeline.structure.multiformula_common"}
        for path in (ROOT / "pipeline").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                elif isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                for module in modules:
                    if not module.startswith("pipeline.") or module in missing:
                        continue
                    target = ROOT.joinpath(*module.split("."))
                    self.assertTrue(target.with_suffix(".py").is_file() or (target / "__init__.py").is_file(), f"{path}: {module}")

    def test_markdown_relative_links_exist(self):
        docs = [ROOT / "README.md", ROOT / "DATA.md", ROOT / "figures" / "README.md"]
        docs += list((ROOT / "docs").glob("*.md"))
        for path in docs:
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if target.startswith(("https://", "http://", "mailto:", "#")):
                    continue
                target = target.split("#", 1)[0]
                self.assertTrue((path.parent / target).exists(), f"{path}: {target}")

    def test_readme_module_names_resolve(self):
        for path in [ROOT / "README.md", *list((ROOT / "docs").glob("*.md"))]:
            for module in re.findall(r"python -m (pipeline\.[A-Za-z0-9_.]+)", path.read_text(encoding="utf-8")):
                if module.endswith("."):
                    continue
                self.assertTrue(ROOT.joinpath(*module.split(".")).with_suffix(".py").is_file(), f"{path}: {module}")

    def test_source_relative_formula_defaults(self):
        for module in (
            "pipeline.formula.candidates.evaluate_candidate_union",
            "pipeline.formula.verification.build_listwise_sft",
            "pipeline.formula.evaluation.evaluate_predictions",
        ):
            result = subprocess.run([sys.executable, "-m", module, "--help"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_missing_structure_helper_has_clear_diagnostic(self):
        helper = ROOT / "pipeline" / "structure" / "multiformula_common.py"
        if helper.exists():
            self.skipTest("Shared helper has been supplied")
        result = subprocess.run([sys.executable, "-m", "pipeline.structure.inputs.validate_multiformula_input", "--help"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("multiformula_common.py", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_blocked_launchers_do_not_create_outputs(self):
        if (ROOT / "pipeline" / "structure" / "multiformula_common.py").exists():
            self.skipTest("Shared helper has been supplied")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must_not_be_created"
            env = dict(os.environ, PROJECT_ROOT=directory, SIRIUS_BIN="/not/a/sirius", BRANCH_MANIFEST="/not/a/manifest", SIRIUS_INPUT_ROOT="/not/an/input", RUN_ROOT=str(output), MERGED_CANDIDATES=str(output / "candidates.jsonl"), LATTICE_ROOT=str(output))
            for name in ("run_sirius_sharded.sh", "run_multihypothesis_lattice.sh"):
                result = subprocess.run(["bash", str(ROOT / "scripts" / "structure" / name)], cwd=directory, env=env, capture_output=True, text=True)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("Missing source", result.stderr)
                self.assertFalse(output.exists())

    def test_release_omits_superseded_guides_and_renders(self):
        self.assertFalse((ROOT / "docs" / "experiment1_file_manifest.txt").exists())
        self.assertFalse((ROOT / "docs" / "experiment2_file_manifest.txt").exists())
        self.assertFalse(any((ROOT / "figures" / "outputs").glob("*")))


class FileInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "pipeline" / "structure" / "inputs" / "convert_formula_predictions.py"
        spec = importlib.util.spec_from_file_location("formula_converter_for_tests", path)
        cls.converter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.converter)

    def test_converter_recovers_full_spectrum(self):
        row = {"spectrum": {"peaks": [{"mz": "25", "intensity": 4}, {"mz": -1, "intensity": 2}, {"mz": 50, "intensity": 0}]}}
        self.assertEqual([[25.0, 4.0], [50.0, 0.0]], self.converter.find_full_peaks(row))

    def test_converter_accepts_parallel_arrays(self):
        self.assertEqual([[10.0, 0.5]], self.converter.find_full_peaks({"spectrum": {"mzs": [10], "intensities": [0.5]}}))

    def test_converter_rejects_duplicate_reference_ids(self):
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            self.converter.build_dataset_index([{"identifier": "a"}, {"identifier": "a"}])

    def test_converter_reads_json_and_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            records = [{"identifier": "a"}, {"identifier": "b"}]
            path.write_text(json.dumps(records), encoding="utf-8")
            self.assertEqual(records, self.converter.load_rows(path))
            path.write_text("\n".join(map(json.dumps, records)), encoding="utf-8")
            self.assertEqual(records, self.converter.load_rows(path))

    def test_override_merge_preserves_records_and_decisions(self):
        shortlist = [{"formula": "C2H6O", "best_adduct": "[M+H]+"}, {"formula": "CH2O2", "best_adduct": "[M+Na]+"}]
        rows = [{"identifier": name, "shortlist": shortlist} for name in ("keep", "swap", "ungated")]
        decisions = [{"identifier": "keep", "decision": "KEEP"}, {"identifier": "swap", "decision": "SWAP"}]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            full, pred, output = [directory / name for name in ("full.jsonl", "decisions.jsonl", "output.jsonl")]
            full.write_text("\n".join(map(json.dumps, rows)) + "\n", encoding="utf-8")
            pred.write_text("\n".join(map(json.dumps, decisions)) + "\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "pipeline.formula.verification.merge_override_predictions", "--full", str(full), "--pred", str(pred), "--output", str(output)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            merged = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["keep", "swap", "ungated"], [row["identifier"] for row in merged])
            self.assertEqual(["C2H6O", "CH2O2", "C2H6O"], [row["final_formula"] for row in merged])
            self.assertTrue(all(row["shortlist"] == shortlist for row in merged))


if __name__ == "__main__":
    unittest.main()

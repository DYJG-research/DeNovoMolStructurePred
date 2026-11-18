"""Shared chemistry normalization, JSONL I/O, and validation for structure inputs."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


_ADDUCT = re.compile(r"\[(?:[1-9][0-9]*)?M(?:[+-][A-Za-z0-9]+)*\](?:[1-9][0-9]*)?[+-]")
_TRUTH_KEYS = {"ground_truth", "groundtruth", "truth", "gold", "label", "labels"}
_TRUTH_PREFIXES = ("ground_truth_", "groundtruth_", "truth_", "gold_", "true_", "gt_")
_REFERENCE_KEYS = {
    "reference_formula", "reference_adduct", "reference_smiles", "reference_inchi",
    "reference_inchikey", "reference_inchikey2d", "target_smiles", "target_inchi",
    "target_inchikey", "target_inchikey2d",
}
_STRUCTURE_KEYS = {"smiles", "inchi", "inchikey", "inchikey2d", "inchikey_2d"}


FORMULA_RE = re.compile(r"([A-Z][a-z]?)([0-9]*)")

SUPPORTED_ELEMENTS = {"C", "H", "N", "O", "P", "S", "F", "Cl", "Br", "I", "Si"}


def parse_formula(formula: str) -> Optional[Dict[str, int]]:
    """Parse a molecular formula into element counts."""
    if not isinstance(formula, str):
        return None

    formula = formula.strip()
    if not formula:
        return None

    pos = 0
    counts: Dict[str, int] = {}

    for match in FORMULA_RE.finditer(formula):
        if match.start() != pos:
            return None

        element, number = match.groups()

        if element not in SUPPORTED_ELEMENTS:
            return None

        if number.startswith("0"):
            return None
        try:
            n = int(number) if number else 1
        except ValueError:
            return None

        counts[element] = counts.get(element, 0) + n
        pos = match.end()

    if pos != len(formula) or not counts:
        return None

    return counts


def format_formula(counts: Dict[str, int]) -> str:
    """Format a neutral molecular formula in Hill order."""
    order = ["C", "H"] if "C" in counts else []
    order += sorted(counts.keys() - set(order))
    return "".join(
        element + (str(counts[element]) if counts[element] > 1 else "")
        for element in order if counts.get(element, 0) > 0
    )


def canonical_formula(formula: str) -> Optional[str]:
    """Return a neutral formula in Hill order, or None for invalid input."""
    counts = parse_formula(formula)
    return format_formula(counts) if counts else None


def canonicalize_neutral_formula(formula: str) -> Optional[str]:
    return canonical_formula(formula)


ADDUCT_ALIASES = {
    "[M+H]+": "[M+H]+",
    "M+H": "[M+H]+",
    "M+H+": "[M+H]+",
    "[M+NA]+": "[M+Na]+",
    "M+NA": "[M+Na]+",
    "[M+NH4]+": "[M+NH4]+",
    "M+NH4": "[M+NH4]+",
    "[M+K]+": "[M+K]+",
    "M+K": "[M+K]+",
    "[M-H]-": "[M-H]-",
    "M-H": "[M-H]-",
    "[M+CL]-": "[M+Cl]-",
    "M+CL": "[M+Cl]-",
    "[M+FA-H]-": "[M+FA-H]-",
    "M+FA-H": "[M+FA-H]-",
    "[M+AC-H]-": "[M+Ac-H]-",
    "M+AC-H": "[M+Ac-H]-",
}

def normalize_adduct(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = "".join(value.split()).replace("−", "-")
    normalized = ADDUCT_ALIASES.get(cleaned.upper(), cleaned)
    return normalized if _ADDUCT.fullmatch(normalized) else None


def normalize_polarity(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    value = str(value).strip().lower()

    if value in {"positive", "pos", "+", "p", "1"}:
        return "positive"

    if value in {"negative", "neg", "-", "n", "-1"}:
        return "negative"

    return None


def polarity_from_adduct(adduct: Optional[str]) -> Optional[str]:
    if not adduct:
        return None

    adduct = str(adduct).strip()

    if adduct.endswith("+"):
        return "positive"

    if adduct.endswith("-"):
        return "negative"

    return None


def read_jsonl(path: str | Path) -> Iterator[Tuple[int, Dict[str, Any]]]:
    """Yield (1-based line number, parsed object) for a JSONL file."""
    path = Path(path)

    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            if not raw.strip():
                continue

            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_no}: invalid JSON: {exc}"
                ) from exc

            if not isinstance(row, dict):
                raise ValueError(
                    f"{path}:{line_no}: expected a JSON object"
                )

            yield line_no, row


def write_jsonl(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            )


def find_forbidden_paths(obj: Any) -> List[str]:
    """Report label field paths, not whether unlabelled values came from truth."""
    hits = []

    def walk(value, path="", parent=""):
        if isinstance(value, dict):
            for key, item in value.items():
                name = key.casefold().replace("-", "_").replace(" ", "_")
                child = f"{path}.{key}" if path else key
                if (
                    name in _TRUTH_KEYS or name.startswith(_TRUTH_PREFIXES)
                    or name in _REFERENCE_KEYS
                    or (not path and name in _STRUCTURE_KEYS)
                    or (parent == "molecule" and name in _STRUCTURE_KEYS | {"formula", "adduct"})
                    or (parent == "metadata" and name in {"formula", "molecular_formula"})
                ):
                    hits.append(child)
                else:
                    walk(item, child, name)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]", parent)

    walk(obj)
    return hits


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def validate_model_row(row: Dict[str, Any], max_formulas: int = 5) -> List[str]:
    """Return validation errors without modifying order, ranks, or values."""
    if max_formulas < 1:
        raise ValueError("max_formulas must be positive")
    if not isinstance(row, dict):
        return ["row must be a JSON object"]
    errors = [f"forbidden ground-truth field: {p}" for p in find_forbidden_paths(row)]
    sid = row.get("sample_id")
    if not isinstance(sid, str) or not sid.strip():
        errors.append("sample_id must be a nonempty string")
    precursor = _finite_number(row.get("precursor_mz"))
    if precursor is None or precursor <= 0:
        errors.append("precursor_mz must be finite and positive")
    polarity = normalize_polarity(row.get("polarity"))
    if polarity is None:
        errors.append("polarity must be positive or negative")
    peaks = row.get("peaks")
    if not isinstance(peaks, list) or not peaks:
        errors.append("peaks must be a nonempty list of [m/z, intensity] pairs")
    else:
        for index, peak in enumerate(peaks):
            if not isinstance(peak, (list, tuple)) or len(peak) != 2:
                errors.append(f"peaks[{index}] must be an [m/z, intensity] pair")
                break
            mz, intensity = map(_finite_number, peak)
            if mz is None or mz <= 0 or intensity is None or intensity < 0:
                errors.append(f"peaks[{index}] requires finite m/z > 0 and intensity >= 0")
                break
    hypotheses = row.get("formula_hypotheses")
    if not isinstance(hypotheses, list) or not 1 <= len(hypotheses) <= max_formulas:
        errors.append(f"formula_hypotheses must contain 1 to {max_formulas} objects")
        return errors
    ranks = []
    for index, item in enumerate(hypotheses):
        prefix = f"formula_hypotheses[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        rank = item.get("rank")
        if isinstance(rank, str) and re.fullmatch(r"[0-9]+", rank):
            try:
                rank = int(rank)
            except ValueError:
                pass
        if type(rank) is not int or rank < 1:
            errors.append(f"{prefix}.rank must be a positive integer")
        else:
            ranks.append(rank)
        if canonical_formula(item.get("formula")) is None:
            errors.append(f"{prefix}.formula must be a valid neutral formula")
        adduct = normalize_adduct(item.get("adduct"))
        if adduct is None:
            errors.append(f"{prefix}.adduct must be a bracketed ion with a charge")
        elif polarity and polarity_from_adduct(adduct) != polarity:
            errors.append(f"{prefix}.adduct charge does not match polarity")
        for field in ("score", "confidence", "ppm_error", "dbe"):
            if item.get(field) is not None and _finite_number(item[field]) is None:
                errors.append(f"{prefix}.{field} must be finite or null")
    if len(ranks) == len(hypotheses):
        ranks.sort()
        if any(b != a + 1 for a, b in zip(ranks, ranks[1:])):
            errors.append("formula_hypotheses ranks must be unique and consecutive")
    return errors

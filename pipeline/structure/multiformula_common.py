"""Reconstructed file and validation interfaces for the multi-formula pipeline."""

import json
import math
import re
from pathlib import Path

from pipeline.structure.mechanisms.reference_formula_chemistry import (
    normalize_polarity as normalize_polarity,
    parse_formula,
)

_FORMULA = re.compile(r"(?:[A-Z][a-z]?(?:[1-9][0-9]*)?)+")
_ADDUCT = re.compile(r"\[(?:[1-9][0-9]*)?M(?:[+-][A-Za-z0-9]+)*\](?:[1-9][0-9]*)?[+-]")
_TRUTH_KEYS = {"ground_truth", "groundtruth", "truth", "gold", "label", "labels"}
_TRUTH_PREFIXES = ("ground_truth_", "groundtruth_", "truth_", "gold_", "true_", "gt_")
_REFERENCE_KEYS = {
    "reference_formula", "reference_adduct", "reference_smiles", "reference_inchi",
    "reference_inchikey", "reference_inchikey2d", "target_smiles", "target_inchi",
    "target_inchikey", "target_inchikey2d",
}
_STRUCTURE_KEYS = {"smiles", "inchi", "inchikey", "inchikey2d", "inchikey_2d"}


def read_jsonl(path):
    """Yield (physical line number, JSON object), skipping blank lines."""
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{number}: expected a JSON object")
            yield number, row


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def canonical_formula(value):
    """Return a neutral formula in Hill order, or None for invalid input."""
    if not isinstance(value, str) or not _FORMULA.fullmatch(value.strip()):
        return None
    try:
        counts = parse_formula(value)
    except ValueError:
        return None
    if not counts:
        return None
    order = ["C", "H"] if "C" in counts else []
    order += sorted(counts.keys() - set(order))
    return "".join(
        element + (str(counts[element]) if counts[element] > 1 else "")
        for element in order if element in counts
    )


def normalize_adduct(value):
    if not isinstance(value, str):
        return None
    value = "".join(value.split())
    return value if _ADDUCT.fullmatch(value) else None


def find_forbidden_paths(obj):
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


def _finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def validate_model_row(row, *, max_formulas):
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
        elif polarity and adduct[-1] != ("+" if polarity == "positive" else "-"):
            errors.append(f"{prefix}.adduct charge does not match polarity")
        for field in ("score", "confidence", "ppm_error", "dbe"):
            if item.get(field) is not None and _finite_number(item[field]) is None:
                errors.append(f"{prefix}.{field} must be finite or null")
    if len(ranks) == len(hypotheses):
        ranks.sort()
        if any(b != a + 1 for a, b in zip(ranks, ranks[1:])):
            errors.append("formula_hypotheses ranks must be unique and consecutive")
    return errors

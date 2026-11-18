#!/usr/bin/env python3
"""Extract a matched, explicit-ID subset of local study spectra and formula predictions."""

import argparse
import json
from pathlib import Path


def records(path):
    """Stream JSONL; standard-library JSON-array input is loaded in memory."""
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                break
        else:
            return
        if line.lstrip().startswith("["):
            stream.seek(0)
            yield from json.load(stream)
        else:
            yield json.loads(line)
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def select(path, identifiers):
    wanted = set(identifiers)
    rows = {}
    for row in records(path):
        if not isinstance(row, dict):
            raise ValueError(f"Expected record objects in {path}")
        sid = row.get("identifier")
        if sid in wanted:
            if sid in rows:
                raise ValueError(f"Duplicate requested ID {sid!r} in {path}")
            rows[sid] = row
    missing = wanted - rows.keys()
    if missing:
        raise ValueError(f"Missing requested IDs in {path}: {', '.join(sorted(missing))}")
    return [rows[sid] for sid in identifiers]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spectra", type=Path, required=True, help="Compatible local JSON array or JSONL")
    parser.add_argument("--formulas", type=Path, required=True, help="Matching formula prediction JSONL")
    parser.add_argument("--ids", type=Path, required=True, help="One exact identifier per line, from the intended split")
    parser.add_argument("--out", type=Path, required=True, help="New subset output directory")
    args = parser.parse_args()
    try:
        identifiers = [line.strip() for line in args.ids.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not identifiers or len(set(identifiers)) != len(identifiers):
            raise ValueError("The ID list must be nonempty and contain no duplicates")
        spectra = select(args.spectra, identifiers)
        formulas = select(args.formulas, identifiers)
        args.out.mkdir(parents=True, exist_ok=False)
        for name, rows in (("spectra.jsonl", spectra), ("formulas.jsonl", formulas)):
            with (args.out / name).open("x", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        (args.out / "ids.txt").write_text("\n".join(identifiers) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"[ERROR] {exc}\n")
    print(f"Extracted {len(identifiers)} matched IDs to {args.out}")


if __name__ == "__main__":
    main()

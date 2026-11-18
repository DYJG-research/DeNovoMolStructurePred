"""Split a multi-formula branch manifest into SIRIUS shard manifests."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from pipeline.structure.multiformula_common import read_jsonl

DEFAULT_SHARD_SIZE = 500
_SHARD_FILE = re.compile(r"shard_(?:[0-9]{5}|[1-9][0-9]{5,})\.jsonl")


def _same_path(first, second):
    return first.resolve() == second.resolve() or (
        first.exists() and second.exists() and first.samefile(second)
    )


def _check_destination(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"not a regular output file: {path}")


def build_manifests(branches, output_dir, stats, *, clean=False, shard_size=DEFAULT_SHARD_SIZE):
    """Group rows by existing IDs, assigning a shard by position only when absent."""
    if type(shard_size) is not int or shard_size <= 0:
        raise ValueError("shard_size must be a positive integer")
    branches, output_dir, stats = map(Path, (branches, output_dir, stats))
    if _same_path(branches, stats):
        raise ValueError("stats path must not be the input manifest")
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise ValueError(f"not an output directory: {output_dir}")
    if _same_path(output_dir, stats) or _same_path(output_dir, branches):
        raise ValueError("output directory must differ from input and stats paths")
    if stats.parent.resolve() == output_dir.resolve() and _SHARD_FILE.fullmatch(stats.name):
        raise ValueError("stats path must not use a reserved shard filename")
    _check_destination(stats)

    counts = Counter()
    seen_ids = set()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".shard-manifests-", dir=output_dir.parent) as temporary:
        stage = Path(temporary)
        for number, row in read_jsonl(branches):
            branch_id = row.get("branch_id")
            if not isinstance(branch_id, str) or not branch_id.strip():
                raise ValueError(f"{branches}:{number}: branch_id must be a nonempty string")
            if branch_id in seen_ids:
                raise ValueError(f"{branches}:{number}: duplicate branch_id {branch_id!r}")
            seen_ids.add(branch_id)
            shard = row.get("shard_id")
            if shard is None:
                shard = (len(seen_ids) - 1) // shard_size
            if type(shard) is not int or shard < 0:
                raise ValueError(f"{branches}:{number}: shard_id must be a nonnegative integer")
            tag = f"shard_{shard:05d}"
            try:
                encoded = json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            except ValueError as exc:
                raise ValueError(f"{branches}:{number}: {exc}") from exc
            with (stage / f"{tag}.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded + "\n")
            counts[tag] += 1
        if not counts:
            raise ValueError(f"{branches}: input contains no branches")

        tags = sorted(counts, key=lambda tag: int(tag.split("_")[1]))
        names = {f"{tag}.jsonl" for tag in tags}
        for name in sorted(names):
            target = output_dir / name
            _check_destination(target)
            if (_same_path(target, branches) or _same_path(target, stats)
                    or target.resolve() in stats.resolve().parents):
                raise ValueError(f"shard output conflicts with input or stats: {target}")
        stale = (
            [path for path in output_dir.iterdir()
             if path.name not in names and _SHARD_FILE.fullmatch(path.name)
             and not path.is_symlink() and path.is_file()]
            if clean and output_dir.exists() else []
        )
        for path in stale:
            if _same_path(path, branches) or _same_path(path, stats):
                raise ValueError(f"cleanup would remove input or stats: {path}")

        report = {
            "branches": len(seen_ids), "num_shards": len(counts),
            "shard_counts": {tag: counts[tag] for tag in tags},
            "output_dir": str(output_dir),
        }
        output_dir.mkdir(exist_ok=True)
        stats.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=stats.parent, delete=False) as stream:
            staged_stats = Path(stream.name)
        try:
            staged_stats.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            for name in sorted(names):
                (stage / name).replace(output_dir / name)
            for path in stale:
                path.unlink()
            staged_stats.replace(stats)
        finally:
            staged_stats.unlink(missing_ok=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branches", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--stats", required=True)
    parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE,
                        help="Rows per shard when shard_id is absent (default: %(default)s)")
    parser.add_argument("--clean", action="store_true", help="Remove stale files with generated shard names")
    args = parser.parse_args()
    try:
        report = build_manifests(args.branches, args.output_dir, args.stats,
                                 clean=args.clean, shard_size=args.shard_size)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"[ERROR] {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

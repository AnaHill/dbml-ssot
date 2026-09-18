#!/usr/bin/env python3
"""Wraps the DBML source content in a ```dbml code block, e.g. for the
Obsidian DBML Visualizer plugin or other markdown preview.

Default: dbml/schema.dbml, or the whole dbml/ folder if schema.dbml is
missing. You can pass a single file, a folder, or a list of names/files/
folders in the GIVEN order (see scripts/_dbml_source.py).

A purely generated view — not a source of truth, never maintained by hand.
Re-run whenever the DBML source changes.
"""
import argparse
import sys
from pathlib import Path

from _dbml_source import describe_paths, read_dbml_paths, resolve_dbml_paths

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dbml_files",
        nargs="*",
        help="file(s)/folder, default: dbml/schema.dbml or the whole dbml/ folder",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("generated/preview.md"),
        help="default: generated/preview.md",
    )
    args = parser.parse_args()

    try:
        paths = resolve_dbml_paths(args.dbml_files)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    source_desc = describe_paths(paths)
    dbml_source = read_dbml_paths(paths)

    output = (
        f"<!-- Generated: python scripts/preview_md.py {source_desc} -o {args.output} — "
        f"do not edit by hand, source is {source_desc} -->\n\n"
        "```dbml\n" + dbml_source.rstrip("\n") + "\n```\n"
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

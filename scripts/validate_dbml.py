#!/usr/bin/env python3
"""Validates the syntax of the DBML source (default: dbml/schema.dbml, or the
whole dbml/ folder if schema.dbml is missing).

You can pass a single file, a folder (reads all .dbml files in alphabetical
order), or a list of names/files/folders — in which case they're used in the
GIVEN order, e.g.:
  python scripts/validate_dbml.py 10_silver 30_snowflake
"""
import argparse
import sys

from pydbml import PyDBML

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
    args = parser.parse_args()

    try:
        paths = resolve_dbml_paths(args.dbml_files)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    source_desc = describe_paths(paths)

    try:
        db = PyDBML(read_dbml_paths(paths))
    except Exception as e:
        print(f"ERROR ({source_desc}): {e}", file=sys.stderr)
        return 1

    print(
        f"OK ({source_desc}): {len(db.tables)} tables, "
        f"{len(db.refs)} relations, {len(db.table_groups)} groups."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

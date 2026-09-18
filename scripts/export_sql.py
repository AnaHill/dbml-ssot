#!/usr/bin/env python3
"""Generates SQL DDL from the DBML source (default: dbml/schema.dbml, or the
whole dbml/ folder if schema.dbml is missing).

You can pass a single file, a folder, or a list of names/files/folders in
the GIVEN order (see scripts/_dbml_source.py).

Use only when real SQL is actually needed (e.g. for the target platform).
The generated SQL is PyDBML's generic DDL — not guaranteed to be the target
platform's (Fabric/Databricks) dialect as-is. Not run automatically as part
of any sync process.
"""
import argparse
import sys
from pathlib import Path

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
    parser.add_argument(
        "-o", "--output", type=Path, help="file to write the SQL to (default: stdout)"
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

    sql = db.sql

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(sql, encoding="utf-8")
        print(f"Written: {args.output}")
    else:
        print(sql)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

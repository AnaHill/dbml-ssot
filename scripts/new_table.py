#!/usr/bin/env python3
"""Prints a ready-made DBML table skeleton to paste into schema.dbml."""
import argparse
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

TEMPLATE = """Table {name} {{
  {name}_id  integer  [pk, increment]

  Note: '''
    source table: {source}
    notebook: {notebook}
  '''
}}"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="table name, e.g. dim_area")
    parser.add_argument("--source", required=True, help="source table, e.g. mes_bronze.Area")
    parser.add_argument("--notebook", required=True, help="orchestrating notebook path")
    args = parser.parse_args()

    print(TEMPLATE.format(name=args.name, source=args.source, notebook=args.notebook))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

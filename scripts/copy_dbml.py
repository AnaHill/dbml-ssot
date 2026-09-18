#!/usr/bin/env python3
"""Copies the DBML source content to the clipboard (Windows), ready to paste
into e.g. https://dbdiagram.io.

Default: dbml/schema.dbml, or the whole dbml/ folder if schema.dbml is
missing. You can pass a single file, a folder, or a list of names/files/
folders in the GIVEN order (see scripts/_dbml_source.py).

dbdiagram.io's free tier doesn't support Table/TableGroup color settings
(`color`, `headercolor`) — they're removed by default from the code copied
to the clipboard (the source files themselves stay untouched, so colors are
preserved for e.g. dbdiagram.io's paid tier or another color-aware tool).
Use --keep-colors if you don't want them removed.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from _dbml_source import describe_paths, read_dbml_paths, resolve_dbml_paths

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

HEADER_RE = re.compile(r"^(Table|TableGroup)(\s+\S+)\s*\[([^\]]*)\](\s*\{)", re.MULTILINE)
COLOR_KEYS = {"color", "headercolor"}


def strip_colors(dbml_source: str) -> tuple[str, int]:
    """Removes color/headercolor settings from Table and TableGroup headers.

    Returns (modified_source, number_of_color_settings_removed).
    """
    removed = 0

    def repl(m: re.Match) -> str:
        nonlocal removed
        kind, name, attrs, tail = m.groups()
        # split on commas that aren't inside a simple quoted string
        parts = [
            p.strip()
            for p in re.split(r",(?=(?:[^']*'[^']*')*[^']*$)", attrs)
            if p.strip()
        ]
        kept = [p for p in parts if p.split(":", 1)[0].strip().lower() not in COLOR_KEYS]
        removed += len(parts) - len(kept)
        if kept:
            return f"{kind}{name} [{', '.join(kept)}]{tail}"
        return f"{kind}{name}{tail}"

    return HEADER_RE.sub(repl, dbml_source), removed


def copy_to_clipboard(text: str) -> None:
    # Works around clip.exe's unreliable Unicode support: writes to a
    # temporary UTF-8 (BOM) file and reads it into the clipboard via
    # PowerShell, so accented characters survive intact.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8-sig", delete=False
    ) as f:
        f.write(text)
        temp_path = f.name
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"Get-Content -Raw -Encoding UTF8 '{temp_path}' | Set-Clipboard",
            ],
            check=True,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dbml_files",
        nargs="*",
        help="file(s)/folder, default: dbml/schema.dbml or the whole dbml/ folder",
    )
    parser.add_argument(
        "--keep-colors",
        action="store_true",
        help="don't remove color/headercolor settings (dbdiagram.io's paid tier supports them)",
    )
    args = parser.parse_args()

    try:
        paths = resolve_dbml_paths(args.dbml_files)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    dbml_source = read_dbml_paths(paths)

    removed = 0
    if not args.keep_colors:
        dbml_source, removed = strip_colors(dbml_source)

    copy_to_clipboard(dbml_source)
    note = f", {removed} color setting(s) removed (dbdiagram.io free tier)" if removed else ""
    print(
        f"Copied to clipboard ({describe_paths(paths)}, {len(dbml_source)} "
        f"characters{note}) — paste into dbdiagram.io."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

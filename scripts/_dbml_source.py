"""Shared helper for loading the DBML source. The one exception to the
"no cross-imports" principle — every file in scripts/ is allowed to import
this one small helper, but not each other.

Supports three input shapes (as argparse `nargs="*"` positional tokens):

  - No argument -> default: dbml/schema.dbml if it exists, otherwise the
    whole dbml/ folder (all .dbml files in alphabetical order).
  - One file or folder -> a folder expands to all its .dbml files in
    alphabetical order.
  - A list of names/files/folders -> used in the GIVEN order. A bare
    filename with no path/extension (e.g. "10_silver") is looked up inside
    the dbml/ folder. This lets you, say in a debugging scenario where the
    dbml/ folder holds both schema.dbml and separate scratch files, pick
    exactly the ones you want: `10_silver 30_snowflake`.

Usage in scripts (in two steps, so a path-resolution error and a DBML
parse error can be reported separately, without the latter retrying an
already-failed path):

    paths = resolve_dbml_paths(args.dbml_files)      # may raise FileNotFoundError
    source_desc = describe_paths(paths)
    db = PyDBML(read_dbml_paths(paths))               # may raise a PyDBML error
"""
from pathlib import Path

DEFAULT_DIR = Path("dbml")
DEFAULT_FILE = DEFAULT_DIR / "schema.dbml"


def _resolve_one(token: str) -> list[Path]:
    path = Path(token)

    if path.is_dir():
        files = sorted(path.glob("*.dbml"))
        if not files:
            raise FileNotFoundError(f"No .dbml files in directory {path}")
        return files

    if path.is_file():
        return [path]

    for candidate in (path.with_suffix(".dbml"), DEFAULT_DIR / f"{token}.dbml"):
        if candidate.is_file():
            return [candidate]

    raise FileNotFoundError(f"File or directory not found: {token}")


def resolve_dbml_paths(tokens: list[str] | None) -> list[Path]:
    if not tokens:
        if DEFAULT_FILE.is_file():
            return [DEFAULT_FILE]
        return _resolve_one(str(DEFAULT_DIR))
    return [p for token in tokens for p in _resolve_one(token)]


def read_dbml_paths(paths: list[Path]) -> str:
    return "\n\n".join(p.read_text(encoding="utf-8") for p in paths)


def describe_paths(paths: list[Path]) -> str:
    return ", ".join(str(p) for p in paths)

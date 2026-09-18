"""Integration test for preview_md.py."""
import subprocess
import sys


def test_preview_md_wraps_dbml(tmp_path, fixtures_dir, repo_root):
    output = tmp_path / "preview.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/preview_md.py",
            str(fixtures_dir / "valid.dbml"),
            "-o",
            str(output),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0

    content = output.read_text(encoding="utf-8")
    assert "```dbml" in content
    assert "Table silver.dim_widget" in content
    assert content.rstrip().endswith("```")

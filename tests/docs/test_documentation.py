import re
from pathlib import Path

import pytest

from app.config import Settings

ROOT = Path(__file__).parents[2]


@pytest.mark.unit
def test_local_markdown_links_resolve_portably():
    markdown_files = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    unresolved = []
    for markdown_file in markdown_files:
        content = markdown_file.read_text(encoding="utf-8")
        for target in link_pattern.findall(content):
            target = target.strip().split("#", maxsplit=1)[0]
            if not target or re.match(r"^(https?|mailto):", target, re.IGNORECASE):
                continue
            if target.startswith("file:"):
                unresolved.append((markdown_file.relative_to(ROOT), target))
                continue
            if not (markdown_file.parent / target).exists():
                unresolved.append((markdown_file.relative_to(ROOT), target))
    assert unresolved == []


@pytest.mark.unit
def test_env_example_lists_all_settings_aliases():
    expected = {field.alias or name.upper() for name, field in Settings.model_fields.items()}
    example = ROOT / ".env.example"
    keys = {
        line.split("=", maxsplit=1)[0].strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert keys == expected


@pytest.mark.unit
def test_readme_documents_runtime_install_and_start_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pip install -r requirements.txt" in readme
    assert "uvicorn app.main:app" in readme
    assert "pytest -v" in readme

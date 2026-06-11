from __future__ import annotations

from pathlib import Path

import yaml
from langchain_core.tools import tool

from .common import WORKSPACE_ROOT


@tool
def modify_yaml_file(file_path: str, updated_content: str) -> str:
    """Overwrite a YAML manifest inside the active workspace with updated content."""
    path = Path(file_path).resolve()
    if not str(path).startswith(str(WORKSPACE_ROOT.resolve())):
        raise ValueError("Refusing to modify files outside the migration workspace")
    list(yaml.safe_load_all(updated_content))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated_content, encoding="utf-8")
    return f"Updated {path}"

from __future__ import annotations

from pathlib import Path

import yaml
from langchain_core.tools import tool

from .common import WORKSPACE_ROOT


@tool
def modify_yaml_file(file_path: str, updated_content: str) -> str:
    """Overwrite one YAML manifest inside the migration workspace with corrected YAML content.

    Use this only when a review comment or validation error requires a manual YAML fix after cloning/conversion.
    Args:
        file_path: Absolute path to an existing or new YAML file under the migration workspace.
        updated_content: Complete replacement YAML content for the file.
    Returns:
        Path of the file that was updated.
    """
    path = Path(file_path).resolve()
    if not str(path).startswith(str(WORKSPACE_ROOT.resolve())):
        raise ValueError("Refusing to modify files outside the migration workspace")
    list(yaml.safe_load_all(updated_content))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated_content, encoding="utf-8")
    return f"Updated {path}"

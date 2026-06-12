from __future__ import annotations

from .conversion import convert_ingress
from .editing import modify_yaml_file
from .github import clone_repo, create_github_pr, push_branch
from .skills import load_skill
from .validation import validate_yaml

TOOLS = [
    load_skill,
    clone_repo,
    convert_ingress,
    modify_yaml_file,
    validate_yaml,
    push_branch,
    create_github_pr,
]


def get_tool_by_name(name: str):
    """Get a tool by its name, handling prefixed names like 'default_api:clone_repo' or 'default_api.clone_repo'."""
    # Try exact match first
    for tool in TOOLS:
        if tool.name == name:
            return tool

    # Try matching just the suffix after the last dot or colon (e.g., 'clone_repo' from 'default_api:clone_repo' or 'default_api.clone_repo')
    suffix = name.split(":")[-1] if ":" in name else (name.split(".")[-1] if "." in name else name)
    for tool in TOOLS:
        if tool.name == suffix:
            return tool

    return None


__all__ = ["TOOLS", "get_tool_by_name"]

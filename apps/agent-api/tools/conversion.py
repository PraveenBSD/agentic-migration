from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from langchain_core.tools import tool

from .common import (
    get_run_context,
    set_run_context,
    _copy_generated_manifests,
    _ingress_to_gateway_docs,
    _manifest_root,
    _run_ingress2gateway,
)


@tool
def convert_ingress(manifest_path: str, branch_name: str, overwrite_existing: bool = True) -> str:
    """Convert Nginx Ingress manifests to Gateway API manifests inside an existing cloned repo."""
    context = get_run_context(branch_name)
    if not context:
        raise ValueError(f"No repository context found for branch {branch_name}")

    repo_dir = Path(context["repo_dir"])
    workspace = Path(context["workspace_dir"])
    generated_dir = workspace / "generated-gateway-api"
    logs: List[str] = []

    source = _manifest_root(repo_dir, manifest_path)
    cli = shutil.which("ingress2gateway") or shutil.which("ingress2eg")
    if cli:
        converted_by_cli = _run_ingress2gateway(cli, source, generated_dir, logs)
        if not converted_by_cli:
            logs.append("ingress2gateway did not emit Gateway API YAML; using built-in deterministic fallback converter.")
            converted = _ingress_to_gateway_docs(source, generated_dir)
            logs.append(f"Fallback converter generated Gateway API manifests for {converted} Ingress object(s).")
    else:
        logs.append("ingress2gateway/ingress2eg not found; using built-in deterministic fallback converter.")
        converted = _ingress_to_gateway_docs(source, generated_dir)
        logs.append(f"Fallback converter generated Gateway API manifests for {converted} Ingress object(s).")

    _copy_generated_manifests(repo_dir, manifest_path, generated_dir, overwrite=overwrite_existing)
    context["manifest_path"] = manifest_path
    context["overwrite_existing"] = overwrite_existing

    source = _manifest_root(repo_dir, manifest_path)
    if overwrite_existing:
        context["validation_path"] = str(source)
    else:
        context["validation_path"] = str(source if source.is_dir() else source.parent)

    set_run_context(branch_name, context)
    return "\n".join(part for part in logs if part)

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
    """Convert NGINX Ingress YAML manifests into Envoy Gateway / Gateway API YAML inside the cloned workspace.

    Call this after clone_repo and before validate_yaml. This tool records the real path to validate as validation_path in run context. The next validate_yaml call should use that real validation_path, not an example or placeholder path.
    Args:
        manifest_path: Path to the Ingress file or directory relative to the cloned repository root, exactly like the user context path.
        branch_name: The same migration branch originally passed to clone_repo.
        overwrite_existing: If true, replace/copy generated Gateway API manifests into the source manifest path; if false, write separate generated files.
    Returns:
        Conversion logs and stores validation_path in run context for validate_yaml.
    """
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
    logs.append(f"validation_path={context['validation_path']}")
    logs.append("Next: call validate_yaml with yaml_file_path set to validation_path.")
    return "\n".join(part for part in logs if part)

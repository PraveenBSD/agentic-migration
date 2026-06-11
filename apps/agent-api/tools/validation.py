from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from langchain_core.tools import tool

from .common import _find_yaml_files, _run


@tool
def validate_yaml(yaml_file_path: str) -> str:
    """Validate Kubernetes YAML with kubeconform -strict, falling back to YAML parsing when kubeconform is absent."""
    path = Path(yaml_file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))
    kubeconform = shutil.which("kubeconform")
    if kubeconform:
        result = _run([kubeconform, "-strict", "-ignore-missing-schemas", str(path)], check=False)
        if result.returncode != 0:
            output = result.stdout + result.stderr
            if "failed downloading schema" not in output:
                raise RuntimeError(output)
            files = _find_yaml_files(path)
            for yaml_file in files:
                with yaml_file.open("r", encoding="utf-8") as handle:
                    list(yaml.safe_load_all(handle))
            return (
                "kubeconform could not download remote schemas; "
                f"YAML syntax parsed successfully for {len(files)} file(s).\n\n{output}"
            )
        return result.stdout or f"kubeconform passed for {path}"

    files = _find_yaml_files(path)
    for yaml_file in files:
        with yaml_file.open("r", encoding="utf-8") as handle:
            list(yaml.safe_load_all(handle))
    return f"kubeconform not found; YAML syntax parsed successfully for {len(files)} file(s)."

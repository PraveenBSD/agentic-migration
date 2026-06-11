from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import yaml
from git import Repo

WORKSPACE_ROOT = Path(
    os.getenv("MIGRATION_WORKSPACE_ROOT", Path(tempfile.gettempdir()) / "gitops-migration-workspaces")
)
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


def _discover_repo_root() -> Path:
    configured = os.getenv("MIGRATION_REPO_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "examples").exists():
            return parent
    return current.parent.parent


REPO_ROOT = _discover_repo_root()
EXAMPLES_ROOT = Path(os.getenv("MIGRATION_EXAMPLES_ROOT", REPO_ROOT / "examples")).expanduser().resolve()
EXAMPLE_TEMPLATES = {
    "retail-platform": EXAMPLES_ROOT / "retail-platform",
}
RUN_CONTEXT: Dict[str, Dict[str, Any]] = {}

STATE_DB_PATH = Path(os.getenv("MIGRATION_STATE_DB", WORKSPACE_ROOT / "migration_state.db"))
STATE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _state_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(STATE_DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_context (
            branch_name TEXT PRIMARY KEY,
            context_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _load_run_context(branch_name: str) -> Dict[str, Any]:
    if branch_name in RUN_CONTEXT:
        return RUN_CONTEXT[branch_name]

    conn = _state_db_connection()
    row = conn.execute("SELECT context_json FROM run_context WHERE branch_name = ?", (branch_name,)).fetchone()
    if not row:
        return {}

    try:
        context = json.loads(row["context_json"])
    except json.JSONDecodeError:
        context = {}

    RUN_CONTEXT[branch_name] = context
    return context


def _persist_run_context(branch_name: str, context: Dict[str, Any]) -> None:
    RUN_CONTEXT[branch_name] = context
    conn = _state_db_connection()
    conn.execute(
        "INSERT INTO run_context(branch_name, context_json, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(branch_name) DO UPDATE SET context_json=excluded.context_json, updated_at=excluded.updated_at",
        (branch_name, json.dumps(context), datetime.utcnow().isoformat() + "Z"),
    )
    conn.commit()


def get_run_context(branch_name: str) -> Dict[str, Any]:
    return _load_run_context(branch_name)


def set_run_context(branch_name: str, context: Dict[str, Any]) -> None:
    _persist_run_context(branch_name, context)


def _safe_branch_name(value: Optional[str] = None) -> str:
    raw = value or f"agentic-gateway-migration-{uuid.uuid4().hex[:8]}"
    return re.sub(r"[^A-Za-z0-9._/-]", "-", raw).strip("/").replace("..", ".")


def _repo_full_name(repo_url: str) -> str:
    if repo_url.startswith("example://"):
        return repo_url.removeprefix("example://")
    if Path(repo_url).expanduser().exists():
        return Path(repo_url).expanduser().resolve().name
    if repo_url.startswith("git@github.com:"):
        return repo_url.split(":", 1)[1].removesuffix(".git")
    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return repo_url.removesuffix(".git")


def _repo_name(repo_url: str) -> str:
    return _repo_full_name(repo_url).split("/")[-1]


def _example_template(repo_url: str) -> Optional[Path]:
    if not repo_url.startswith("example://"):
        return None
    name = repo_url.removeprefix("example://")
    template = EXAMPLE_TEMPLATES.get(name)
    if not template or not template.exists():
        raise FileNotFoundError(f"Unknown bundled example template: {name}")
    return template


def _with_token(repo_url: str, token: Optional[str]) -> str:
    if not token or "github.com" not in repo_url or repo_url.startswith("git@"):
        return repo_url
    parsed = urlparse(repo_url)
    if parsed.username:
        return repo_url
    return parsed._replace(netloc=f"x-access-token:{token}@{parsed.netloc}").geturl()


def _run(args: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=check)


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", value)


def _extract_yaml_from_cli_output(value: str) -> str:
    text = _strip_ansi(value)
    match = re.search(r"(?m)^(apiVersion:|---\s*$)", text)
    if not match:
        return ""
    return text[match.start() :].strip() + "\n"


def _ensure_bot_identity(repo: Repo) -> None:
    repo.git.config("user.name", os.getenv("MIGRATION_GIT_AUTHOR_NAME", "GitOps Migration Agent"))
    repo.git.config("user.email", os.getenv("MIGRATION_GIT_AUTHOR_EMAIL", "gitops-migration-agent@example.invalid"))


def _workspace_for_branch(branch_name: str) -> Path:
    return WORKSPACE_ROOT / re.sub(r"[^A-Za-z0-9._-]", "-", branch_name)


def _manifest_root(repo_dir: Path, manifest_path: str) -> Path:
    root = (repo_dir / manifest_path).resolve()
    if not str(root).startswith(str(repo_dir.resolve())):
        raise ValueError("manifest_path must stay inside the cloned repository")
    if not root.exists():
        raise FileNotFoundError(f"Manifest path does not exist: {manifest_path}")
    return root


def _copy_or_clone_source(repo_url: str, repo_dir: Path, branch_name: str, logs: List[str]) -> tuple[Repo, str]:
    template = _example_template(repo_url)
    if template:
        logs.append(f"Using bundled example template {repo_url} from {template}")
        shutil.copytree(template, repo_dir)
        repo = Repo.init(repo_dir, initial_branch="main")
        _ensure_bot_identity(repo)
        repo.git.add(A=True)
        repo.index.commit("Seed bundled migration example")
        repo.git.checkout("-b", branch_name)
        return repo, "main"

    local_path = Path(repo_url).expanduser()
    if local_path.exists():
        logs.append(f"Copying local repository/template from {local_path.resolve()} into {repo_dir}")
        shutil.copytree(local_path, repo_dir, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        repo = Repo.init(repo_dir, initial_branch="main")
        _ensure_bot_identity(repo)
        repo.git.add(A=True)
        repo.index.commit("Seed local migration source")
        repo.git.checkout("-b", branch_name)
        return repo, "main"

    token = os.getenv("GITHUB_TOKEN")
    clone_url = _with_token(repo_url, token)
    logs.append(f"Cloning {_repo_full_name(repo_url)} into {repo_dir}")
    Repo.clone_from(clone_url, repo_dir)
    repo = Repo(repo_dir)
    base_branch = repo.active_branch.name if not repo.head.is_detached else "main"
    repo.git.checkout("-b", branch_name)
    return repo, base_branch


def _find_yaml_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path] if path.suffix in {".yaml", ".yml"} else []
    return sorted([*path.rglob("*.yaml"), *path.rglob("*.yml")])


def _has_underscore_header_hint(annotations: Dict[str, Any]) -> bool:
    if any("_" in key for key in annotations):
        return True
    snippet = "\n".join(str(value) for value in annotations.values())
    return bool(re.search(r"\b[A-Za-z0-9]+_[A-Za-z0-9_]+\b", snippet))


def _nginx_duration_to_gateway(value: str) -> str:
    text = str(value).strip()
    if re.fullmatch(r"\d+", text):
        return f"{text}s"
    return text


def _nginx_size_to_gateway(value: str) -> str:
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)([kKmMgG])?", text)
    if not match:
        return text
    amount, unit = match.groups()
    if not unit:
        return amount
    suffix = {"k": "Ki", "m": "Mi", "g": "Gi"}[unit.lower()]
    return f"{amount}{suffix}"


def _ingress_to_gateway_docs(input_path: Path, output_path: Path) -> int:
    converted = 0
    output_path.mkdir(parents=True, exist_ok=True)
    for yaml_file in _find_yaml_files(input_path):
        with yaml_file.open("r", encoding="utf-8") as handle:
            docs = [doc for doc in yaml.safe_load_all(handle) if doc]

        out_docs: List[Dict[str, Any]] = []
        for doc in docs:
            if doc.get("kind") != "Ingress":
                continue
            converted += 1
            meta = doc.get("metadata", {})
            spec = doc.get("spec", {})
            namespace = meta.get("namespace", "default")
            name = meta.get("name", yaml_file.stem)
            annotations = meta.get("annotations", {}) or {}
            hostname = None

            gateway_name = f"{name}-gateway"
            out_docs.append(
                {
                    "apiVersion": "gateway.networking.k8s.io/v1",
                    "kind": "Gateway",
                    "metadata": {"name": gateway_name, "namespace": namespace},
                    "spec": {
                        "gatewayClassName": "envoy-gateway",
                        "listeners": [
                            {
                                "name": "http",
                                "protocol": "HTTP",
                                "port": 80,
                                "allowedRoutes": {"namespaces": {"from": "Same"}},
                            }
                        ],
                    },
                }
            )

            rules = []
            for rule in spec.get("rules", []) or []:
                host = rule.get("host")
                for path_rule in (rule.get("http", {}) or {}).get("paths", []) or []:
                    backend = path_rule.get("backend", {}) or {}
                    service = backend.get("service", {}) or {}
                    port = service.get("port", {}) or {}
                    path_type = path_rule.get("pathType", "PathPrefix")
                    if path_type in {"Prefix", "ImplementationSpecific"}:
                        path_type = "PathPrefix"
                    route: Dict[str, Any] = {
                        "matches": [
                            {
                                "path": {
                                    "type": path_type,
                                    "value": path_rule.get("path", "/"),
                                }
                            }
                        ],
                        "backendRefs": [
                            {
                                "name": service.get("name"),
                                "port": port.get("number") or port.get("name"),
                            }
                        ],
                    }
                    rules.append(route)

                if host:
                    hostname = host
                else:
                    hostname = None

            http_route: Dict[str, Any] = {
                "apiVersion": "gateway.networking.k8s.io/v1",
                "kind": "HTTPRoute",
                "metadata": {"name": f"{name}-route", "namespace": namespace},
                "spec": {"parentRefs": [{"name": gateway_name}], "rules": rules or []},
            }
            if hostname:
                http_route["spec"]["hostnames"] = [hostname]
            out_docs.append(http_route)

            timeout = annotations.get("nginx.ingress.kubernetes.io/proxy-read-timeout")
            if timeout:
                out_docs.append(
                    {
                        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
                        "kind": "BackendTrafficPolicy",
                        "metadata": {"name": f"{name}-timeouts", "namespace": namespace},
                        "spec": {
                            "targetRefs": [
                                {
                                    "group": "gateway.networking.k8s.io",
                                    "kind": "HTTPRoute",
                                    "name": f"{name}-route",
                                }
                            ],
                            "timeout": {"http": {"requestTimeout": _nginx_duration_to_gateway(timeout)}},
                        },
                    }
                )

            body_size = annotations.get("nginx.ingress.kubernetes.io/proxy-body-size")
            if body_size:
                out_docs.append(
                    {
                        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
                        "kind": "BackendTrafficPolicy",
                        "metadata": {"name": f"{name}-body-size", "namespace": namespace},
                        "spec": {
                            "targetRefs": [
                                {
                                    "group": "gateway.networking.k8s.io",
                                    "kind": "HTTPRoute",
                                    "name": f"{name}-route",
                                }
                            ],
                            "requestBuffer": {"limit": _nginx_size_to_gateway(body_size)},
                        },
                    }
                )

            if _has_underscore_header_hint(annotations):
                out_docs.append(
                    {
                        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
                        "kind": "ClientTrafficPolicy",
                        "metadata": {"name": f"{name}-headers", "namespace": namespace},
                        "spec": {
                            "targetRefs": [
                                {
                                    "group": "gateway.networking.k8s.io",
                                    "kind": "Gateway",
                                    "name": gateway_name,
                                }
                            ],
                            "headers": {"withUnderscoresAction": "Allow"},
                        },
                    }
                )

        if out_docs:
            relative = yaml_file.relative_to(input_path if input_path.is_dir() else input_path.parent)
            target = output_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as handle:
                yaml.safe_dump_all(out_docs, handle, sort_keys=False)
    return converted


def _copy_generated_manifests(repo_dir: Path, manifest_path: str, generated_dir: Path, overwrite: bool = True) -> None:
    target_root = repo_dir / manifest_path
    if target_root.is_file():
        target_root = target_root.parent
    for generated_file in _find_yaml_files(generated_dir):
        relative = generated_file.relative_to(generated_dir)
        destination = target_root / relative
        if not overwrite:
            destination = destination.with_name(destination.stem + ".gateway" + destination.suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_file, destination)


def _run_ingress2gateway(cli: str, source: Path, generated_dir: Path, logs: List[str]) -> bool:
    generated_count = 0
    input_root = source if source.is_dir() else source.parent
    for yaml_file in _find_yaml_files(source):
        relative = yaml_file.relative_to(input_root)
        target = generated_dir / relative
        args = [
            cli,
            "print",
            "--providers=ingress-nginx",
            "--emitter=envoy-gateway",
            "--input-file",
            str(yaml_file),
            "--output",
            "yaml",
        ]
        result = _run(args, check=False)
        logs.append("$ " + " ".join(args))
        if result.stdout:
            logs.append(_strip_ansi(result.stdout))
        if result.stderr:
            logs.append(_strip_ansi(result.stderr))
        if result.returncode != 0:
            continue

        generated_yaml = _extract_yaml_from_cli_output(result.stdout)
        if not generated_yaml:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(generated_yaml, encoding="utf-8")
        generated_count += 1

    if generated_count:
        logs.append(f"ingress2gateway generated Gateway API manifests for {generated_count} file(s).")
    return generated_count > 0

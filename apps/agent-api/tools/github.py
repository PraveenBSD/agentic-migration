from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

from git import Repo
try:
    from github import Github, GithubException
except Exception:
    Github = None
    GithubException = Exception
from langchain_core.tools import tool

from .common import (
    get_run_context,
    set_run_context,
    _copy_or_clone_source,
    _ensure_bot_identity,
    _example_template,
    _repo_full_name,
    _repo_name,
    _safe_branch_name,
    _workspace_for_branch,
)


@tool
def clone_repo(repo_url: str, branch_name: str) -> str:
    """Clone/copy a source repository and create a feature branch."""
    branch_name = _safe_branch_name(branch_name)
    workspace = _workspace_for_branch(branch_name)
    repo_dir = workspace / _repo_name(repo_url)
    logs: List[str] = []

    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    _, base_branch = _copy_or_clone_source(repo_url, repo_dir, branch_name, logs)
    context = {
        "repo_dir": str(repo_dir),
        "workspace_dir": str(workspace),
        "repo_url": repo_url,
        "repo_full_name": _repo_full_name(repo_url),
        "base_branch": base_branch,
        "is_local_source": bool(_example_template(repo_url) or Path(repo_url).expanduser().exists()),
    }
    set_run_context(branch_name, context)
    return "\n".join(part for part in logs if part)


@tool
def push_branch(branch_name: str, commit_message: str) -> str:
    """Commit staged changes and push the feature branch to GitHub."""
    context = get_run_context(branch_name)
    repo_dir = Path(context.get("repo_dir", ""))
    if not repo_dir.exists():
        raise FileNotFoundError(f"No cloned repository found for branch {branch_name}")

    repo = Repo(repo_dir)
    _ensure_bot_identity(repo)
    if repo.is_dirty(untracked_files=True):
        repo.git.add(A=True)
        repo.index.commit(commit_message)
    else:
        return "No manifest changes were detected; nothing to commit."

    if context.get("is_local_source"):
        return f"Created local migration commit on {branch_name} at {repo_dir}. Local example sources are not pushed to GitHub."

    token = os.getenv("GITHUB_TOKEN")
    if token:
        repo.git.push("--set-upstream", "origin", branch_name)
        return f"Pushed {branch_name} to origin."

    return f"Created local migration commit on {branch_name} at {repo_dir}. Set GITHUB_TOKEN to push branch."


@tool
def create_github_pr(repo_name: str, branch_name: str, title: str, description: str) -> str:
    """Create a GitHub pull request for a pushed feature branch."""
    context = get_run_context(branch_name)
    if context.get("is_local_source"):
        return f"Local migration commit on {branch_name} at {context.get('repo_dir')}. Local example sources are not pushed to GitHub."

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return "GITHUB_TOKEN is required to create a pull request."

    if Github is None:
        return "Install PyGithub to create a pull request automatically."

    gh = Github(token)
    full_name = repo_name if "/" in repo_name else context.get("repo_full_name", repo_name)
    gh_repo = gh.get_repo(full_name)
    owner = full_name.split("/", 1)[0]
    base = os.getenv("GITHUB_BASE_BRANCH", context.get("base_branch", "main"))
    head = f"{owner}:{branch_name}"

    existing = list(gh_repo.get_pulls(state="open", head=head, base=base))
    if existing:
        pr = existing[0]
        pr.edit(title=title, body=description)
        context["pr_number"] = pr.number
        context["pr_url"] = pr.html_url
        set_run_context(branch_name, context)
        return f"Updated existing pull request: {pr.html_url}"

    try:
        pr = gh_repo.create_pull(
            title=title,
            body=description,
            head=branch_name,
            base=base,
        )
    except GithubException as exc:
        if getattr(exc, "status", None) != 422:
            raise

        existing = list(gh_repo.get_pulls(state="open", head=head, base=base))
        if not existing:
            raise
        pr = existing[0]
        pr.edit(title=title, body=description)
        context["pr_number"] = pr.number
        context["pr_url"] = pr.html_url
        set_run_context(branch_name, context)
        return f"Updated existing pull request after duplicate-PR response: {pr.html_url}"

    context["pr_number"] = pr.number
    context["pr_url"] = pr.html_url
    set_run_context(branch_name, context)
    return pr.html_url

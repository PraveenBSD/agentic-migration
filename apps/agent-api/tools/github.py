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


def _validate_pr_description(description: str) -> None:
    description = (description or "").strip()
    normalized = " ".join(description.lower().split())
    placeholder_phrases = (
        "migration summary from step",
        "summary from step",
        "see step",
        "see above",
        "as described above",
        "tbd",
        "todo",
        "n/a",
    )

    if not description or any(phrase in normalized for phrase in placeholder_phrases):
        raise ValueError(
            "PR description must be the actual Markdown migration summary, not a "
            "placeholder or reference to another step. Include the migration summary, "
            "Ingress files found, Ingress behavior, Envoy/Gateway changes, and "
            "validation result."
        )

    if len(description) < 80:
        raise ValueError(
            "PR description is too short. Provide the full Markdown migration summary "
            "with source behavior, generated Envoy/Gateway changes, and validation result."
        )


@tool
def clone_repo(repo_url: str, branch_name: str) -> str:
    """Start a migration run by cloning or copying the source repository into a workspace and creating a migration branch.

    Call this first before conversion, validation, push, or PR creation.
    Args:
        repo_url: GitHub URL, local path, or bundled example URL such as example://retail-platform.
        branch_name: New feature branch for this migration. Use the suggested migration branch from context; do not use main, master, or develop.
    Returns:
        Clone/copy logs and stores repository context for later tools under branch_name.
    """
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
    """Commit converted manifests on the migration branch and push that branch to GitHub when possible.

    Call this after convert_ingress and validate_yaml have completed.
    Args:
        branch_name: The same migration branch originally passed to clone_repo.
        commit_message: Short description of the migration commit.
    Returns:
        A push result, local-commit result, or message explaining that no changes/token were available.
    """
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
    """Create or update an open GitHub pull request for the pushed migration branch.

    Call this after push_branch succeeds or reports that the branch is ready. This tool never closes or merges pull requests; it only opens a new PR or updates the title/body of an existing open PR.
    Args:
        repo_name: Repository full name in owner/repo form, for example teqade-admin/agentic-migration.
        branch_name: The same migration branch used for clone_repo, convert_ingress, validate_yaml, and push_branch.
        title: Concise pull request title.
        description: Markdown PR body summarizing changed files, Ingress behavior, Envoy/Gateway API changes, and validation results.
    Returns:
        Pull request URL, existing PR update URL, or an explicit reason a PR cannot be created.
    """
    _validate_pr_description(description)

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

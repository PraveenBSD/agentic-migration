from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from tools.common import _safe_branch_name, get_run_context
from tools.review import _numbered_lines, _review_comment_context


class AgentContextBuilder:
    """Build the user-context payload supplied to the LLM."""

    def build(self, state: Dict[str, Any]) -> str:
        context: Dict[str, Any] = dict(state)
        if not context.get("branch_name"):
            context["suggested_branch_name"] = _safe_branch_name()
            state["suggested_branch_name"] = context["suggested_branch_name"]

        if state.get("review_comment"):
            self._add_review_file_context(context, state)

        return (
            "Use the available tools to complete the GitOps request. "
            "Keep all useful information in state through tool results and final response.\n\n"
            f"Context:\n{json.dumps(context, indent=2)}"
        )

    def _add_review_file_context(self, context: Dict[str, Any], state: Dict[str, Any]) -> None:
        comment = state.get("review_comment", {})
        branch_name = state.get("branch_name", "")
        run_context = get_run_context(branch_name) if branch_name else {}
        repo_dir = Path(run_context.get("repo_dir", ""))
        relative_path = comment.get("path")
        if not relative_path or not repo_dir.exists():
            return

        target = (repo_dir / relative_path).resolve()
        if not str(target).startswith(str(repo_dir.resolve())) or not target.exists():
            return

        current = target.read_text(encoding="utf-8")
        context["review_file_path"] = str(target)
        context["review_comment_context"] = _review_comment_context(comment)
        context["review_file_numbered"] = _numbered_lines(current)
        context["review_file_content"] = current

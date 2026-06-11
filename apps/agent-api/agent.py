from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.messages import ToolMessage

from tools.common import _repo_full_name, _safe_branch_name, get_run_context
from tools.llm import get_llm
from tools.registry import get_tool_by_name
from tools.review import _numbered_lines, _review_comment_context
from tools.tool_executor import invoke_tool

AgentState = Dict[str, Any]

SYSTEM_PROMPT_MIGRATION = """You are a GitOps migration agent with access to repository, conversion, validation, editing, push, and pull-request tools.
Use the available tools yourself to complete the user's migration request end to end.
Choose any needed branch name, keep using it consistently, validate generated YAML before pull-request work, and make only repository changes that belong to the migration.
When creating the pull request, write a useful title and description from the tool results and validation output.
After the work is complete, stop calling tools and briefly summarize what happened.
"""

SYSTEM_PROMPT_REVIEW = """You are a GitOps review feedback agent with access to YAML editing, validation, push, and pull-request tools.
Use the available tools yourself to address the review comment.
Make the smallest correct manifest edit, validate the edited YAML, push the correction, and then stop calling tools with a brief summary.
Do not change unrelated files or unrelated fields.
"""


class Agent:
    def execute(self, state: AgentState) -> AgentState:
        raise NotImplementedError("Agent must implement execute()")


class GitOpsAgent(Agent):
    def __init__(self, max_iterations: int = 20) -> None:
        self.max_iterations = max_iterations
        self.llm = get_llm()
        print("[GitOpsAgent] Initialized LLM", file=sys.stderr, flush=True)

    def execute(self, state: AgentState) -> AgentState:
        if not self.llm:
            state["status"] = "failed"
            state["errors"] = ["LLM provider is not configured"]
            return state

        try:
            return self._execute_with_llm_tools(state)
        except Exception as exc:
            print(f"[Agent] ERROR: {exc}", file=sys.stderr, flush=True)
            state["status"] = "failed"
            state["errors"] = [str(exc)]
            return state

    def _execute_with_llm_tools(self, state: AgentState) -> AgentState:
        prompt = SYSTEM_PROMPT_REVIEW if state.get("review_comment") else SYSTEM_PROMPT_MIGRATION
        messages: List[Any] = [
            ("system", prompt),
            ("human", self._build_user_context(state)),
        ]

        logs: List[str] = []
        validation_logs: List[str] = []
        branch_name = _safe_branch_name(state.get("branch_name")) if state.get("branch_name") else ""
        pr_description = ""
        pr_result = ""
        final_response = ""

        for iteration in range(1, self.max_iterations + 1):
            print(f"[Agent] LLM tool iteration {iteration}", file=sys.stderr, flush=True)
            response = self.llm.invoke(messages)
            final_response = self._response_text(response)
            native_tool_calls = self._native_tool_calls(response)

            if native_tool_calls:
                messages.append(response)
                tool_calls = native_tool_calls
            else:
                messages.append(("assistant", final_response))
                tool_calls = self._text_tool_calls(final_response)

            if not tool_calls:
                break

            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_input = tool_call["args"]
                tool_id = tool_call.get("id")

                if tool_input.get("branch_name"):
                    branch_name = _safe_branch_name(tool_input["branch_name"])
                    tool_input["branch_name"] = branch_name

                result = self._invoke_named_tool(tool_name, tool_input)
                logs.append(f"[{tool_name}] {result}")

                if self._tool_name_matches(tool_name, "validate_yaml"):
                    validation_logs.append(result)
                if self._tool_name_matches(tool_name, "create_github_pr"):
                    pr_description = str(tool_input.get("description", ""))
                    pr_result = result

                print(f"[Agent] Tool result from {tool_name}: {result[:200]}", file=sys.stderr, flush=True)
                if tool_id:
                    messages.append(ToolMessage(content=result, tool_call_id=tool_id))
                else:
                    messages.append(("user", f"Tool result from {tool_name}:\n{result}"))

        return self._finalize_state(
            state=state,
            branch_name=branch_name,
            logs=logs,
            validation_logs=validation_logs,
            pr_description=pr_description,
            pr_result=pr_result,
            final_response=final_response,
        )

    def _build_user_context(self, state: AgentState) -> str:
        context: Dict[str, Any] = dict(state)
        if not context.get("branch_name"):
            context["suggested_branch_name"] = _safe_branch_name()

        if state.get("review_comment"):
            self._add_review_file_context(context, state)

        return (
            "Use the available tools to complete this request. "
            "Call tools directly; do not only describe what should happen.\n\n"
            f"Context:\n{json.dumps(context, indent=2)}"
        )

    def _add_review_file_context(self, context: Dict[str, Any], state: AgentState) -> None:
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

    def _invoke_named_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        tool_func = get_tool_by_name(tool_name)
        if not tool_func:
            return f"Tool {tool_name} not found"
        return invoke_tool(tool_func, tool_input)

    def _finalize_state(
        self,
        state: AgentState,
        branch_name: str,
        logs: List[str],
        validation_logs: List[str],
        pr_description: str,
        pr_result: str,
        final_response: str,
    ) -> AgentState:
        if not logs:
            state["status"] = "failed"
            state["errors"] = ["The LLM completed without calling any tools"]
            if final_response:
                key = "correction_logs" if state.get("review_comment") else "conversion_logs"
                state[key] = final_response
            return state

        context = get_run_context(branch_name) if branch_name else {}
        repo_url = state.get("repo_url", context.get("repo_url", ""))
        all_logs = "\n".join(logs)
        common_updates = {
            "branch_name": branch_name or state.get("branch_name"),
            "workspace_dir": context.get("workspace_dir", state.get("workspace_dir")),
            "repo_full_name": context.get("repo_full_name", _repo_full_name(repo_url) if repo_url else None),
            "validation_logs": "\n".join(validation_logs) or state.get("validation_logs"),
        }

        if state.get("review_comment"):
            state.update(
                {
                    **common_updates,
                    "correction_logs": all_logs,
                    "status": "review_feedback_processed",
                }
            )
            return state

        state.update(
            {
                **common_updates,
                "conversion_logs": all_logs,
                "pr_description": pr_description or state.get("pr_description"),
                "pr_url": context.get("pr_url", pr_result or state.get("pr_url")),
                "pr_number": context.get("pr_number", state.get("pr_number")),
                "overwrite_existing": state.get("overwrite_existing", True),
                "status": "completed",
            }
        )
        return state

    def _native_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        tool_calls = []
        for tool_call in getattr(response, "tool_calls", []) or []:
            tool_name = tool_call.get("name") or tool_call.get("tool")
            tool_input = tool_call.get("args") or {}
            if not tool_name:
                continue
            tool_calls.append(
                {
                    "name": tool_name,
                    "args": tool_input if isinstance(tool_input, dict) else {},
                    "id": tool_call.get("id"),
                }
            )
        return tool_calls

    def _text_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        tool_calls = []
        decoder = json.JSONDecoder()

        for match in re.finditer(r"TOOL_CALL:\s*([\w.:]+)", text):
            tool_name = match.group(1)
            input_match = re.search(r"TOOL_INPUT:\s*", text[match.end() :])
            if not input_match:
                tool_calls.append({"name": tool_name, "args": {}, "id": None})
                continue

            input_start = match.end() + input_match.end()
            payload = text[input_start:].lstrip()
            if not payload:
                tool_calls.append({"name": tool_name, "args": {}, "id": None})
                continue

            try:
                tool_input, _ = decoder.raw_decode(payload)
            except json.JSONDecodeError as exc:
                print(f"[parse] Failed to parse input for {tool_name}: {exc}", file=sys.stderr, flush=True)
                continue

            tool_calls.append(
                {
                    "name": tool_name,
                    "args": tool_input if isinstance(tool_input, dict) else {},
                    "id": None,
                }
            )

        return tool_calls

    def _response_text(self, response: Any) -> str:
        if not hasattr(response, "content"):
            return str(response)
        content = response.content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    def _tool_name_matches(self, tool_name: str, expected: str) -> bool:
        return tool_name == expected or tool_name.endswith(f".{expected}") or tool_name.endswith(f":{expected}")

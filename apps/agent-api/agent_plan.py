from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from tools.common import get_run_context


class SkillPlanManager:
    """Extract and advance tool-oriented workflow steps from loaded skill text."""

    KNOWN_TOOLS = {
        "clone_repo",
        "convert_ingress",
        "validate_yaml",
        "push_branch",
        "create_github_pr",
        "modify_yaml_file",
    }

    def steps_from_skill(self, skill_text: str) -> List[Dict[str, str]]:
        """Return all workflow steps, including instruction-only and end steps."""
        steps = []
        for step in self.display_steps_from_skill(skill_text):
            runtime_step = dict(step)
            if runtime_step["kind"] == "end":
                runtime_step["tool"] = "__end__"
            steps.append(runtime_step)
        return steps

    def display_steps_from_skill(self, skill_text: str) -> List[Dict[str, str]]:
        """Return every numbered workflow step for UI/planning display."""
        steps = []
        for line in skill_text.splitlines():
            match = re.match(r"\s*(\d+)\.\s+(.*)", line)
            if not match:
                continue
            text = match.group(2).strip()
            tools = [tool for tool in self.KNOWN_TOOLS if f"`{tool}`" in text or tool in text]
            is_end = bool(re.search(r"\bstop\b|\bend\b|\bfinish\b|\bcomplete\b", text, flags=re.IGNORECASE))
            steps.append(
                {
                    "number": match.group(1),
                    "step": text,
                    "tool": tools[0] if tools else "",
                    "kind": "tool" if tools else ("end" if is_end else "instruction"),
                }
            )
        return steps

    def current_step(self, state: Dict[str, Any]) -> Dict[str, str] | None:
        plan_steps = state.get("plan_steps") or []
        completed_tools = set(state.get("completed_tools", []))
        completed_instructions = set(state.get("completed_instruction_steps", []))
        for index, step in enumerate(plan_steps):
            tool_name = step.get("tool")
            if tool_name == "__end__":
                previous_tool_steps = [
                    item.get("tool")
                    for item in plan_steps[:index]
                    if item.get("tool") and item.get("tool") != "__end__"
                ]
                return step if all(tool in completed_tools for tool in previous_tool_steps) else None
            if not tool_name:
                if step.get("number") not in completed_instructions:
                    return step
                continue
            if tool_name not in completed_tools:
                return step
        return None

    def is_at_end(self, state: Dict[str, Any]) -> bool:
        current = self.current_step(state)
        return bool(current and current.get("tool") == "__end__")

    def next_message(self, state: Dict[str, Any], branch_name: str) -> str:
        next_step = self.current_step(state)
        if not next_step:
            return ""

        tool_name = next_step["tool"]
        if tool_name == "__end__":
            return (
                "End step from the plan:\n"
                f"- {next_step['step']}\n"
                "The required tool workflow is complete. Do not call more tools. "
                "Return a concise final summary with the PR URL or the reason a PR could not be created."
            )

        instruction_text = ""
        if not tool_name:
            state.setdefault("completed_instruction_steps", []).append(next_step.get("number", ""))
            instruction_text = (
                "Next instruction from the plan:\n"
                f"- {next_step['step']}\n"
                "Complete this reasoning step using the tool results already in context. "
                "Do not call a separate tool for this instruction.\n\n"
            )
            next_step = self.current_step(state)
            if not next_step:
                return instruction_text

            tool_name = next_step["tool"]
            if tool_name == "__end__":
                return (
                    instruction_text
                    + "End step from the plan:\n"
                    + f"- {next_step['step']}\n"
                    + "The required tool workflow is complete. Do not call more tools. "
                    + "Return a concise final summary with the PR URL or the reason a PR could not be created."
                )

        context = get_run_context(branch_name) if branch_name else {}
        hints = {
            "task": state.get("task"),
            "repo_url": state.get("repo_url"),
            "manifest_path": state.get("manifest_path") or context.get("manifest_path"),
            "branch_name": branch_name or state.get("branch_name") or state.get("suggested_branch_name"),
            "repo_name": context.get("repo_full_name"),
            "validation_path": context.get("validation_path"),
            "overwrite_existing": state.get("overwrite_existing", True),
        }
        hint_text = json.dumps({key: value for key, value in hints.items() if value}, indent=2)
        return (
            instruction_text +
            "Next step from the plan:\n"
            f"- {next_step['step']}\n"
            f"Call `{tool_name}` next using the real values below. "
            "Do not repeat a completed successful tool unless the latest tool result explicitly requires retry.\n"
            f"{hint_text}"
        )

from __future__ import annotations

import sys
from typing import Any, Callable, Dict, List

from langchain_core.messages import ToolMessage

from agent_context import AgentContextBuilder
from agent_logging import AgentLogger
from agent_plan import SkillPlanManager
from agent_tool_calls import ToolCallParser
from tools.common import _repo_full_name, _safe_branch_name, get_run_context
from tools.llm import get_llm
from tools.registry import get_tool_by_name
from tools.tool_executor import invoke_tool

AgentState = Dict[str, Any]

SYSTEM_PROMPT_GITOPS = """You are a generic GitOps agent.
For a repository task, you must use tools.

First, call `load_skill` with the task from the user context.
Then follow the loaded skill instructions and keep working with tools until the task is complete.
Do not give a final answer before the repository work is done.
Keep all work scoped to the requested repository and branch.
Never close or merge pull requests. Creating or updating a PR means opening it for human review.

If native tool calling is not available, request exactly one tool at a time using this JSON shape:
{"name": "tool_name", "parameters": {"argument": "value"}}
Wait for the tool result before requesting the next tool.
"""

SYSTEM_PROMPT_REVIEW = """You are a generic GitOps review agent.
Use the available tools to understand the review comment, edit only the required files, validate when useful, push the correction, and stop.
"""


class GitOpsAgent:
    def __init__(self, max_iterations: int = 20, event_sink: Callable[[Dict[str, Any]], None] | None = None) -> None:
        self.max_iterations = max_iterations
        self.llm = get_llm()
        self.logger = AgentLogger(event_sink=event_sink)
        self.context_builder = AgentContextBuilder()
        self.planner = SkillPlanManager()
        self.tool_parser = ToolCallParser()
        print("[GitOpsAgent] Initialized LLM", file=sys.stderr, flush=True)

    def execute(self, state: AgentState) -> AgentState:
        if not self.llm:
            state["status"] = "failed"
            state["errors"] = ["LLM provider is not configured"]
            return state

        try:
            return self._run(state)
        except Exception as exc:
            print(f"[Agent] ERROR: {exc}", file=sys.stderr, flush=True)
            state["status"] = "failed"
            state["errors"] = [str(exc)]
            return state

    def _run(self, state: AgentState) -> AgentState:
        self._init_state(state)

        prompt = SYSTEM_PROMPT_REVIEW if state.get("review_comment") else SYSTEM_PROMPT_GITOPS
        user_context = self.context_builder.build(state)
        messages: List[Any] = [
            ("system", prompt),
            ("human", user_context),
        ]
        self._remember(state, "system", prompt)
        self._remember(state, "human", user_context)

        branch_name = _safe_branch_name(state.get("branch_name")) if state.get("branch_name") else ""
        final_response = ""
        tool_less_retries = 0
        stop_requested = False

        for iteration in range(1, self.max_iterations + 1):
            if stop_requested:
                break

            self.logger.iteration_start(iteration, self.planner.current_step(state))
            response = self.llm.invoke(messages)
            final_response = self.tool_parser.response_text(response)
            tool_calls = self.tool_parser.native_tool_calls(response)
            if tool_calls:
                self.logger.llm_response(iteration, final_response, tool_calls, source="native")

            self.logger.trace(
                state,
                {
                    "type": "llm_response",
                    "iteration": iteration,
                    "content": final_response,
                    "tool_calls": tool_calls,
                },
            )
            self._remember(state, "assistant", final_response, tool_calls=tool_calls)

            if tool_calls:
                messages.append(response)
            else:
                text_tool_calls = self.tool_parser.text_tool_calls(final_response)
                if not text_tool_calls:
                    self.logger.llm_response(iteration, final_response, [], source="none")
                    if tool_less_retries < 1 and state["tool_results"]:
                        tool_less_retries += 1
                        self.logger.trace_debug(
                            state,
                            iteration,
                            "CONTINUE_REQUEST",
                            "LLM returned no tool call; asking it to continue with the next required tool.",
                        )
                        self.logger.event(iteration, "continue", "No tool call returned; asking for the next plan step.")
                        messages.append(
                            (
                                "human",
                                "You did not call a tool. Continue with the next required tool from the loaded skill. "
                                "If the task is complete, explain which terminal tool result proves it is complete.",
                            )
                        )
                        continue
                    self.logger.trace_debug(state, iteration, "STOP", "No native or text tool calls returned by LLM")
                    self.logger.event(iteration, "stop", "No tool call returned.")
                    break
                tool_less_retries = 0
                tool_calls = text_tool_calls
                messages.append(("assistant", final_response))
                self.logger.trace_debug(state, iteration, "TEXT_TOOL_CALLS", tool_calls)
                self.logger.trace(state, {"type": "text_tool_calls", "iteration": iteration, "tool_calls": tool_calls})
                self.logger.llm_response(iteration, final_response, tool_calls, source="text")

            for tool_call in tool_calls:
                tool_less_retries = 0
                tool_name = tool_call["name"]
                tool_input, branch_name = self._prepare_tool_input(tool_call["args"], branch_name)
                tool_id = tool_call.get("id")
                self.logger.trace_debug(
                    state,
                    iteration,
                    "TOOL_CALL",
                    {
                        "tool": tool_name,
                        "input": tool_input,
                    },
                )
                self.logger.tool_call(iteration, tool_name, tool_input)

                result = self._invoke_named_tool(tool_name, tool_input)
                self._record_tool_result(state, tool_name, tool_input, result)
                self.logger.tool_result(iteration, tool_name, result)

                if tool_id:
                    messages.append(ToolMessage(content=result, tool_call_id=tool_id))
                else:
                    messages.append(("user", f"Tool result from {tool_name}:\n{result}"))
                self._remember(state, "tool", result, name=tool_name, input=tool_input)
                if self.planner.is_at_end(state):
                    end_step = self.planner.next_message(state, branch_name)
                    if end_step:
                        self.logger.trace_debug(state, iteration, "NEXT_STEP", end_step)
                        self.logger.next_step(iteration, end_step)
                    stop_requested = True
                    break

                next_step = self.planner.next_message(state, branch_name)
                if next_step:
                    messages.append(("human", next_step))
                    self._remember(state, "human", next_step)
                    self.logger.trace_debug(state, iteration, "NEXT_STEP", next_step)
                    self.logger.next_step(iteration, next_step)
                else:
                    self.logger.trace_debug(state, iteration, "NEXT", "Tool result added to conversation; continuing to next LLM iteration")

        state["final_llm_response"] = final_response
        return self._finalize_state(state, branch_name)

    def _init_state(self, state: AgentState) -> None:
        state.setdefault("conversation", [])
        state.setdefault("agent_trace", [])
        state.setdefault("tool_results", [])
        state.setdefault("completed_tools", [])
        state.setdefault("completed_instruction_steps", [])

    def _invoke_named_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        tool_func = get_tool_by_name(tool_name)
        if not tool_func:
            return f"Tool {tool_name} not found"
        return invoke_tool(tool_func, tool_input)

    def _prepare_tool_input(self, tool_input: Dict[str, Any], branch_name: str) -> tuple[Dict[str, Any], str]:
        prepared = dict(tool_input)
        if prepared.get("branch_name"):
            branch_name = _safe_branch_name(prepared["branch_name"])
            prepared["branch_name"] = branch_name
        return prepared, branch_name

    def _record_tool_result(self, state: AgentState, tool_name: str, tool_input: Dict[str, Any], result: str) -> None:
        canonical_name = self.tool_parser.canonical_tool_name(tool_name)
        entry = {
            "tool": canonical_name,
            "input": tool_input,
            "output": result,
            "success": not result.startswith("Error invoking"),
        }
        state["tool_results"].append(entry)
        self.logger.trace(state, {"type": "tool_result", **entry})

        if entry["success"] and canonical_name not in state["completed_tools"]:
            state["completed_tools"].append(canonical_name)
        if canonical_name == "load_skill":
            state["loaded_skill"] = result
            state["plan_steps"] = self.planner.steps_from_skill(result)
        if canonical_name == "validate_yaml":
            state["validation_logs"] = self._append_text(state.get("validation_logs"), result)
        if canonical_name == "create_github_pr":
            state["pr_description"] = str(tool_input.get("description", ""))
            state["pr_url"] = result

    def _finalize_state(self, state: AgentState, branch_name: str) -> AgentState:
        context = get_run_context(branch_name) if branch_name else {}
        repo_url = state.get("repo_url", context.get("repo_url", ""))
        tool_log = "\n".join(f"[{item['tool']}] {item['output']}" for item in state["tool_results"])

        updates = {
            "branch_name": branch_name or state.get("branch_name"),
            "workspace_dir": context.get("workspace_dir", state.get("workspace_dir")),
            "repo_full_name": context.get("repo_full_name", _repo_full_name(repo_url) if repo_url else None),
        }

        if state.get("review_comment"):
            state.update({**updates, "correction_logs": tool_log, "status": "review_feedback_processed"})
            return state

        if not state["tool_results"]:
            state.update(
                {
                    **updates,
                    "status": "failed",
                    "errors": [
                        "The LLM completed without calling any tools. "
                        f"Final LLM response: {state.get('final_llm_response') or '<empty>'}"
                    ],
                }
            )
            return state

        completed_tools = set(state.get("completed_tools", []))
        status = "completed" if "create_github_pr" in completed_tools else "incomplete"
        errors = None
        if status == "incomplete":
            errors = [
                "The agent ran tools but stopped before create_github_pr. "
                f"Final LLM response: {state.get('final_llm_response') or '<empty>'}"
            ]

        state.update(
            {
                **updates,
                "conversion_logs": tool_log,
                "overwrite_existing": state.get("overwrite_existing", True),
                "status": status,
            }
        )
        if errors:
            state["errors"] = errors
        return state

    def _remember(self, state: AgentState, role: str, content: str, **extra: Any) -> None:
        state["conversation"].append({"role": role, "content": content, **extra})

    def _append_text(self, current: Any, value: str) -> str:
        return f"{current}\n{value}" if current else value

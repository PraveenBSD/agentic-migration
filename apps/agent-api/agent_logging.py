from __future__ import annotations

import json
import re
import sys
from typing import Any, Callable, Dict, List


class AgentLogger:
    """Small logging and trace helper for GitOps agent runs."""

    def __init__(self, event_sink: Callable[[Dict[str, Any]], None] | None = None) -> None:
        self.event_sink = event_sink

    def trace(self, state: Dict[str, Any], event: Dict[str, Any]) -> None:
        state["agent_trace"].append(event)

    def trace_debug(self, state: Dict[str, Any], iteration: int, event: str, payload: Any) -> None:
        self.trace(
            state,
            {
                "type": "debug",
                "iteration": iteration,
                "event": event,
                "payload": payload,
            },
        )

    def iteration_start(self, iteration: int, current_step: Dict[str, str] | None) -> None:
        detail = f"step={current_step['tool']} - {current_step['step']}" if current_step else "step=planning"
        self.event(iteration, "start", detail)

    def llm_response(
        self,
        iteration: int,
        response_text: str,
        tool_calls: List[Dict[str, Any]],
        source: str,
    ) -> None:
        if tool_calls:
            planned = ", ".join(call["name"] for call in tool_calls)
            self.event(iteration, "llm", f"tool_calls={planned} source={source}")
            return

        summary = self.compact_text(response_text or "<empty>", 180)
        self.event(iteration, "llm", f"no tool call; response={summary}")

    def tool_call(self, iteration: int, tool_name: str, tool_input: Dict[str, Any]) -> None:
        self.event(iteration, "tool_call", f"{tool_name} {self.compact_json(tool_input)}")

    def tool_result(self, iteration: int, tool_name: str, result: str) -> None:
        status = "error" if result.startswith("Error invoking") else "ok"
        summary = self.compact_text(result, 220)
        self.event(iteration, "tool_result", f"{tool_name} status={status} result={summary}")

    def next_step(self, iteration: int, next_step_message: str) -> None:
        first_lines = [line.strip() for line in next_step_message.splitlines() if line.strip()]
        step_line = next((line for line in first_lines if line.startswith("- ")), "")
        call_line = next((line for line in first_lines if line.startswith("Call `")), "")
        if step_line or call_line:
            self.event(iteration, "next_step", " ".join(part for part in (step_line, call_line) if part))
            return
        self.event(iteration, "next_step", self.compact_text(next_step_message, 180))

    def event(self, iteration: int, event: str, message: str) -> None:
        print(f"[Agent][{iteration:02d}][{event}] {message}", file=sys.stderr, flush=True)
        if self.event_sink:
            self.event_sink(
                {
                    "type": "progress",
                    "iteration": iteration,
                    "event": event,
                    "message": message,
                }
            )

    def compact_json(self, value: Dict[str, Any]) -> str:
        redacted = self.redact(value)
        return self.compact_text(json.dumps(redacted, sort_keys=True, default=str), 260)

    def compact_text(self, value: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value)).strip()
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."

    def redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if re.search(r"token|secret|password|key", str(key), flags=re.IGNORECASE):
                    redacted[key] = "<redacted>"
                else:
                    redacted[key] = self.redact(item)
            return redacted
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        return value

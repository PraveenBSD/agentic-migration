from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


class ToolCallParser:
    """Normalize native and text-emitted LLM tool calls into one shape."""

    def native_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
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

    def text_tool_calls(self, text: str) -> List[Dict[str, Any]]:
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

        if tool_calls:
            return tool_calls[:1]

        for payload in self.json_blocks(text):
            parsed = self.parse_json_tool_call(payload)
            if parsed:
                return [parsed]

        return []

    def json_blocks(self, text: str) -> List[str]:
        blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if blocks:
            return blocks

        candidates = []
        decoder = json.JSONDecoder()
        index = 0
        while index < len(text):
            start = text.find("{", index)
            if start == -1:
                break
            try:
                _, end = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                index = start + 1
                continue
            candidates.append(text[start : start + end])
            index = start + end
        return candidates

    def parse_json_tool_call(self, payload: str) -> Dict[str, Any] | None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        tool_name = data.get("name") or data.get("tool")
        tool_input = data.get("parameters") or data.get("args") or data.get("input") or {}
        if not tool_name or not isinstance(tool_input, dict):
            return None

        return {"name": str(tool_name), "args": tool_input, "id": None}

    def response_text(self, response: Any) -> str:
        if not hasattr(response, "content"):
            return str(response)
        content = response.content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    def canonical_tool_name(self, tool_name: str) -> str:
        return tool_name.split(":")[-1].split(".")[-1]

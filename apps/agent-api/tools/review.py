from __future__ import annotations

import json
from typing import Dict


def _numbered_lines(value: str, line_start: int = 1) -> str:
    return "\n".join(f"{index:04d}: {line}" for index, line in enumerate(value.splitlines(), start=line_start))


def _review_comment_context(comment: Dict[str, Any]) -> str:
    start_line = comment.get("start_line") or comment.get("original_start_line")
    metadata = {
        "path": comment.get("path"),
        "line": comment.get("line"),
        "start_line": comment.get("start_line"),
        "original_line": comment.get("original_line"),
        "original_start_line": comment.get("original_start_line"),
        "side": comment.get("side"),
        "start_side": comment.get("start_side"),
        "subject_type": comment.get("subject_type"),
    }
    context = [
        "GitHub review comment metadata:",
        json.dumps(metadata, indent=2, sort_keys=True),
    ]
    if start_line:
        context.extend(["", f"Review range starts at line {start_line}."])
    if comment.get("diff_hunk"):
        context.extend(["", "GitHub diff hunk for this review comment:", str(comment.get("diff_hunk"))])
    return "\n".join(context)

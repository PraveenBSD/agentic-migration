from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from langchain_core.tools import tool

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"

SKILL_ALIASES: Dict[str, str] = {
    "ingress": "migrate-nginx-to-envoy-skill.md",
    "nginx": "migrate-nginx-to-envoy-skill.md",
    "envoy": "migrate-nginx-to-envoy-skill.md",
    "gateway": "migrate-nginx-to-envoy-skill.md",
    "gateway api": "migrate-nginx-to-envoy-skill.md",
    "migrate-nginx-to-envoy": "migrate-nginx-to-envoy-skill.md",
}


def matching_skill_path(task: str) -> Path | None:
    """Return the best matching local skill path for a task."""
    requested = task.strip().lower()
    for keyword, filename in SKILL_ALIASES.items():
        if keyword in requested:
            return (SKILLS_ROOT / filename).resolve()
    return None


def read_skill(task: str) -> str:
    """Read the best matching local skill file for a task."""
    path = matching_skill_path(task)
    if not path:
        available = ", ".join(sorted(path.stem for path in SKILLS_ROOT.glob("*.md")))
        return f"No exact skill matched task '{task}'. Available skills: {available}"

    if not str(path).startswith(str(SKILLS_ROOT.resolve())) or not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path.name}")

    return path.read_text(encoding="utf-8")


def list_available_skills() -> List[Dict[str, str]]:
    """Return available local skill files with a short description."""
    skills = []
    for path in sorted(SKILLS_ROOT.glob("*.md")):
        title = path.stem
        summary = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text.startswith("# "):
                title = text.removeprefix("# ").strip()
            elif text and not text.startswith("#"):
                summary = text
                break
        skills.append({"name": path.stem, "title": title, "description": summary})
    return skills


@tool
def load_skill(task: str) -> str:
    """Load the best matching GitOps skill instructions for the user's task.

    Call this before repository tools when the task requires a specialized workflow. Pass a short task description such as "migrate nginx ingress to envoy gateway". The tool returns the full Markdown skill file that should be followed for the rest of the run.
    Args:
        task: User task or skill name to match against available skills.
    Returns:
        Markdown skill instructions, including goal, workflow, PR expectations, and recovery notes.
    """
    return read_skill(task)

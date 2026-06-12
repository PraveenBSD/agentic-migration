from __future__ import annotations

import hmac
import json
import os
import queue
import threading
from hashlib import sha256
from typing import Any, Dict, Iterator, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from tools.llm import get_llm, llm_provider_config
from tools.skills import list_available_skills, matching_skill_path, read_skill
from agent import GitOpsAgent
from agent_plan import SkillPlanManager


app = FastAPI(title="AI GitOps Ingress-to-Gateway Migration Agent", version="0.1.0")

AGENT = GitOpsAgent()
PLANNER = SkillPlanManager()
ACTIVE_PR_STATES: Dict[int, Dict[str, Any]] = {}


class MigrationRequest(BaseModel):
    repo_url: str = Field(..., description="HTTPS or SSH GitHub repository URL")
    manifest_path: str = Field(..., description="Directory or YAML file containing Ingress manifests")
    branch_name: Optional[str] = Field(default=None, description="Optional migration branch name")
    overwrite_existing: bool = Field(
        default=True,
        description="Overwrite original manifests with generated Gateway API files. If false, write separate .gateway.yaml files.",
    )
    git_token: Optional[str] = Field(default=None, description="Optional token scoped to this migration run")


class MigrationResponse(BaseModel):
    status: str
    branch_name: Optional[str] = None
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    workspace_dir: Optional[str] = None
    conversion_logs: Optional[str] = None
    validation_logs: Optional[str] = None
    pr_description: Optional[str] = None
    execution_plan: Optional[str] = None
    overwrite_existing: Optional[bool] = None
    correction_logs: Optional[str] = None
    errors: Optional[list] = None


class MigrationPlanRequest(BaseModel):
    repo_url: str = Field(..., description="HTTPS or SSH GitHub repository URL")
    manifest_path: str = Field(..., description="Directory or YAML file containing Ingress manifests")
    branch_name: Optional[str] = Field(default=None, description="Optional migration branch name")
    task: str = Field(
        default="Migrate Kubernetes NGINX Ingress manifests to Envoy Gateway / Gateway API resources",
        description="Task used to select the matching local skill",
    )


class MigrationPlanResponse(BaseModel):
    skill_name: str
    skill_title: str
    plan_markdown: str
    steps: list[Dict[str, str]]


class LLMTestRequest(BaseModel):
    question: str = Field(..., description="Question to send to the configured LLM provider")


class LLMTestResponse(BaseModel):
    status: str
    provider: str
    model: str
    answer: str


class SkillInfo(BaseModel):
    name: str
    title: str
    description: str


def _verify_signature(raw_body: bytes, signature: Optional[str]) -> None:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        return
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing GitHub webhook signature")
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")


def _migration_state(request: MigrationRequest) -> Dict[str, Any]:
    return {
        "task": "Migrate Kubernetes NGINX Ingress manifests to Envoy Gateway / Gateway API resources",
        "repo_url": request.repo_url,
        "manifest_path": request.manifest_path,
        "branch_name": request.branch_name,
        "overwrite_existing": request.overwrite_existing,
    }


def _skill_title(skill_text: str, fallback: str) -> str:
    for line in skill_text.splitlines():
        text = line.strip()
        if text.startswith("# "):
            return text.removeprefix("# ").strip()
    return fallback


def _plan_markdown(request: MigrationPlanRequest, skill_title: str, steps: list[Dict[str, str]]) -> str:
    branch = request.branch_name or "agent-generated migration branch"
    lines = [
        "Plan:",
        "",
        f"Preparation: load skill `{skill_title}`.",
        "",
        "Execution:",
    ]
    for step in steps:
        lines.append(f"{step['number']}. {step['step']}")
    lines.extend(
        [
            "",
            "Context:",
            f"- Repository: `{request.repo_url}`",
            f"- Manifest path: `{request.manifest_path}`",
            f"- Branch: `{branch}`",
            "",
            "Reply `approve` to proceed, or provide corrections.",
        ]
    )
    return "\n".join(lines)


def _with_scoped_github_token(request: MigrationRequest, run) -> Any:
    previous_token = os.getenv("GITHUB_TOKEN")
    if request.git_token:
        os.environ["GITHUB_TOKEN"] = request.git_token

    try:
        return run()
    finally:
        if request.git_token:
            if previous_token is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = previous_token


def _record_active_pr_state(state: Dict[str, Any]) -> None:
    pr_number = state.get("pr_number")
    if pr_number:
        ACTIVE_PR_STATES[int(pr_number)] = dict(state)


@app.post("/api/v1/migrate", response_model=MigrationResponse)
def migrate(request: MigrationRequest) -> MigrationResponse:
    try:
        state = _with_scoped_github_token(request, lambda: AGENT.execute(_migration_state(request)))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _record_active_pr_state(state)

    return MigrationResponse(**state)


@app.post("/api/v1/plan", response_model=MigrationPlanResponse)
def migration_plan(request: MigrationPlanRequest) -> MigrationPlanResponse:
    skill_text = read_skill(request.task)
    skill_path = matching_skill_path(request.task)
    skill_name = skill_path.stem if skill_path else "unknown"
    skill_title = _skill_title(skill_text, skill_name)
    steps = PLANNER.display_steps_from_skill(skill_text)
    return MigrationPlanResponse(
        skill_name=skill_name,
        skill_title=skill_title,
        steps=steps,
        plan_markdown=_plan_markdown(request, skill_title, steps),
    )


def _migration_stream(request: MigrationRequest) -> Iterator[str]:
    events: queue.Queue[Dict[str, Any] | None] = queue.Queue()

    def emit(event: Dict[str, Any]) -> None:
        events.put(event)

    def worker() -> None:
        try:
            emit({"type": "start", "message": "Migration request accepted."})
            agent = GitOpsAgent(event_sink=emit)
            state = _with_scoped_github_token(request, lambda: agent.execute(_migration_state(request)))
            _record_active_pr_state(state)
            emit({"type": "final", "state": MigrationResponse(**state).dict()})
        except Exception as exc:
            emit({"type": "error", "message": str(exc)})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        event = events.get()
        if event is None:
            break
        yield json.dumps(event, default=str) + "\n"


@app.post("/api/v1/migrate/stream")
def migrate_stream(request: MigrationRequest) -> StreamingResponse:
    return StreamingResponse(
        _migration_stream(request),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/llm/test", response_model=LLMTestResponse)
def test_llm(request: LLMTestRequest) -> LLMTestResponse:
    config = llm_provider_config()
    llm = get_llm()
    if llm is None:
        setup_hint = (
            f"Ensure Ollama is running at {config.get('base_url')} and the model is pulled."
            if config["provider"] == "ollama"
            else f"Set {config['api_key_name']} and restart the backend."
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"LLM provider '{config['provider']}' is not configured. "
                f"{setup_hint}"
            ),
        )

    try:
        response = llm.invoke(
            [
                ("system", "Answer concisely. This is a health check for the configured migration-agent LLM."),
                ("human", request.question),
            ]
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc

    content = getattr(response, "content", response)
    if isinstance(content, list):
        answer = "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    else:
        answer = str(content)

    return LLMTestResponse(
        status="ok",
        provider=config["provider"],
        model=config["model"],
        answer=answer,
    )


@app.get("/api/v1/skills", response_model=list[SkillInfo])
def skills() -> list[SkillInfo]:
    return [SkillInfo(**skill) for skill in list_available_skills()]


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(default=None),
    x_hub_signature_256: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    raw_body = await request.body()
    _verify_signature(raw_body, x_hub_signature_256)
    payload = await request.json()

    if x_github_event != "pull_request_review_comment":
        return {"status": "ignored", "reason": f"Unsupported event {x_github_event}"}

    pr_number = payload.get("pull_request", {}).get("number")
    if not pr_number:
        raise HTTPException(status_code=400, detail="Webhook payload does not include pull_request.number")

    state = ACTIVE_PR_STATES.get(int(pr_number))
    if not state:
        raise HTTPException(status_code=404, detail=f"No active migration state for PR #{pr_number}")

    state["review_comment"] = payload.get("comment", {})
    corrected = AGENT.execute(state)
    ACTIVE_PR_STATES[int(pr_number)] = dict(corrected)
    return {
        "status": corrected.get("status"),
        "pr_number": pr_number,
        "correction_logs": corrected.get("correction_logs"),
    }


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}

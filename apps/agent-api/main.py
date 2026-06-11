from __future__ import annotations

import hmac
import os
from hashlib import sha256
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from tools.llm import get_llm, llm_provider_config
from agent import GitOpsAgent


app = FastAPI(title="AI GitOps Ingress-to-Gateway Migration Agent", version="0.1.0")

AGENT = GitOpsAgent()
ACTIVE_PR_STATES: Dict[int, Dict[str, Any]] = {}


class MigrationRequest(BaseModel):
    repo_url: str = Field(..., description="HTTPS or SSH GitHub repository URL")
    manifest_path: str = Field(..., description="Directory or YAML file containing Ingress manifests")
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
    overwrite_existing: Optional[bool] = None
    correction_logs: Optional[str] = None
    errors: Optional[list] = None


class LLMTestRequest(BaseModel):
    question: str = Field(..., description="Question to send to the configured LLM provider")


class LLMTestResponse(BaseModel):
    status: str
    provider: str
    model: str
    answer: str


def _verify_signature(raw_body: bytes, signature: Optional[str]) -> None:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        return
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing GitHub webhook signature")
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")


@app.post("/api/v1/migrate", response_model=MigrationResponse)
def migrate(request: MigrationRequest) -> MigrationResponse:
    previous_token = os.getenv("GITHUB_TOKEN")
    if request.git_token:
        os.environ["GITHUB_TOKEN"] = request.git_token

    try:
        state = AGENT.execute(
            {
                "repo_url": request.repo_url,
                "manifest_path": request.manifest_path,
                "overwrite_existing": request.overwrite_existing,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if request.git_token:
            if previous_token is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = previous_token

    pr_number = state.get("pr_number")
    if pr_number:
        ACTIVE_PR_STATES[int(pr_number)] = dict(state)

    return MigrationResponse(**state)


@app.post("/api/v1/llm/test", response_model=LLMTestResponse)
def test_llm(request: LLMTestRequest) -> LLMTestResponse:
    config = llm_provider_config()
    llm = get_llm()
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"LLM provider '{config['provider']}' is not configured. "
                f"Set {config['api_key_name']} and restart the backend."
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

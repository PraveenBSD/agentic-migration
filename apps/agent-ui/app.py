from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Iterator, List

import requests
import streamlit as st


DEFAULT_BACKEND_URL = os.getenv("MIGRATION_BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="GitOps Agent", layout="centered")

st.markdown(
    """
    <style>
    :root {
        --agent-bg: #05080d;
        --agent-panel: #0b111c;
        --agent-panel-2: #101827;
        --agent-border: #1f2f46;
        --agent-text: #d7e5f5;
        --agent-muted: #7f93ad;
        --agent-green: #39ff88;
        --agent-cyan: #28d7ff;
        --agent-amber: #ffcc66;
        --agent-red: #ff5f7a;
    }

    .stApp {
        background:
            linear-gradient(180deg, rgba(5, 8, 13, 0.92), rgba(5, 8, 13, 0.98)),
            radial-gradient(circle at 20% 0%, rgba(40, 215, 255, 0.16), transparent 28%),
            radial-gradient(circle at 80% 8%, rgba(57, 255, 136, 0.11), transparent 24%);
        color: var(--agent-text);
    }

    .block-container {
        max-width: 1080px;
        padding-top: 2rem;
    }

    h1, h2, h3 {
        color: var(--agent-text);
        letter-spacing: 0;
    }

    h1 {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        font-size: 2.15rem;
        border-bottom: 1px solid var(--agent-border);
        padding-bottom: 0.75rem;
        margin-bottom: 0.35rem;
    }

    h1::before {
        content: "$ ";
        color: var(--agent-green);
    }

    .agent-subtitle {
        color: var(--agent-muted);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        margin-bottom: 1.4rem;
    }

    section[data-testid="stSidebar"] {
        background: #070b12;
        border-right: 1px solid var(--agent-border);
    }

    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p {
        color: var(--agent-muted);
    }

    div[data-testid="stTabs"] button {
        color: var(--agent-muted);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }

    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: var(--agent-green);
        border-bottom-color: var(--agent-green);
    }

    div[data-testid="stForm"],
    div[data-testid="stExpander"],
    div[data-testid="stStatusWidget"],
    div[data-testid="stChatMessage"] {
        background: rgba(11, 17, 28, 0.92);
        border: 1px solid var(--agent-border);
        border-radius: 8px;
        box-shadow: 0 0 0 1px rgba(40, 215, 255, 0.03), 0 16px 40px rgba(0, 0, 0, 0.24);
    }

    div[data-testid="stChatMessage"] {
        padding: 0.35rem 0.55rem;
    }

    div[data-testid="stChatMessage"] p,
    div[data-testid="stMarkdownContainer"] p,
    li {
        color: var(--agent-text);
    }

    .stCaptionContainer,
    .stCaptionContainer p {
        color: var(--agent-muted);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }

    label, .stCheckbox label p {
        color: var(--agent-muted);
    }

    input, textarea {
        background-color: #060a11 !important;
        color: var(--agent-text) !important;
        border: 1px solid var(--agent-border) !important;
        border-radius: 6px !important;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }

    input:focus, textarea:focus {
        border-color: var(--agent-cyan) !important;
        box-shadow: 0 0 0 1px rgba(40, 215, 255, 0.5) !important;
    }

    .stButton > button,
    .stFormSubmitButton > button {
        background: linear-gradient(180deg, #12301f, #0c2116);
        color: var(--agent-green);
        border: 1px solid rgba(57, 255, 136, 0.55);
        border-radius: 6px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        font-weight: 700;
    }

    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        background: #163b27;
        color: #c8ffd9;
        border-color: var(--agent-green);
        box-shadow: 0 0 18px rgba(57, 255, 136, 0.18);
    }

    pre, code {
        background: #05080d !important;
        color: var(--agent-green) !important;
        border: 1px solid var(--agent-border);
        border-radius: 6px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace !important;
    }

    a {
        color: var(--agent-cyan) !important;
    }

    .agent-chip-row {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 1rem 0 1.35rem;
    }

    .agent-chip {
        background: rgba(16, 24, 39, 0.88);
        border: 1px solid var(--agent-border);
        border-radius: 8px;
        padding: 0.8rem 0.9rem;
        min-height: 84px;
    }

    .agent-chip strong {
        display: block;
        color: var(--agent-green);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        margin-bottom: 0.25rem;
    }

    .agent-chip span {
        color: var(--agent-muted);
        font-size: 0.88rem;
    }

    @media (max-width: 760px) {
        .agent-chip-row {
            grid-template-columns: 1fr;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("GitOps Agent")
st.markdown(
    """
    <div class="agent-subtitle">llm@cluster:~$ plan -> tool_call -> observe -> pull_request</div>
    <div class="agent-chip-row">
        <div class="agent-chip"><strong>SKILL LOADER</strong><span>loads GitOps runbooks into agent context</span></div>
        <div class="agent-chip"><strong>TOOL LOOP</strong><span>clone, convert, validate, push, PR</span></div>
        <div class="agent-chip"><strong>REVIEW READY</strong><span>humans start from generated diffs</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

backend_url = st.sidebar.text_input("Backend URL", DEFAULT_BACKEND_URL).rstrip("/")


def api_get(path: str) -> Any:
    response = requests.get(f"{backend_url}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def stream_migration(payload: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    with requests.post(f"{backend_url}/api/v1/migrate/stream", json=payload, stream=True, timeout=900) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            yield json.loads(line)


def skill_list() -> List[Dict[str, str]]:
    try:
        return api_get("/api/v1/skills")
    except requests.RequestException:
        return []


def migration_plan(details: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "repo_url": details["repo_url"],
        "manifest_path": details["manifest_path"],
        "branch_name": details.get("branch_name") or None,
    }
    response = requests.post(f"{backend_url}/api/v1/plan", json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def append_message(role: str, content: str) -> None:
    st.session_state.chat_messages.append({"role": role, "content": content})


def detect_migration_intent(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in ("migrate", "migration", "ingress", "gateway", "envoy"))


def extract_repo_url(text: str) -> str:
    match = re.search(r"(https://github\.com/[^\s]+?\.git|https://github\.com/[^\s]+|git@github\.com:[^\s]+?\.git|example://[A-Za-z0-9._/-]+)", text)
    return match.group(1).rstrip(".,") if match else ""


def extract_manifest_path(text: str) -> str:
    match = re.search(r"(?:path|manifest|folder|directory)\s*(?:is|=|:)?\s*([A-Za-z0-9_./-]+)", text, flags=re.IGNORECASE)
    return match.group(1).rstrip(".,") if match else ""


def extract_branch_name(text: str) -> str:
    match = re.search(r"(?:branch)\s*(?:is|=|:)?\s*([A-Za-z0-9._/-]+)", text, flags=re.IGNORECASE)
    return match.group(1).rstrip(".,") if match else ""


def missing_details() -> List[str]:
    details = st.session_state.pending_request
    missing = []
    if not details.get("repo_url"):
        missing.append("repository URL")
    if not details.get("manifest_path"):
        missing.append("manifest path")
    if not details.get("branch_name") and not details.get("auto_branch"):
        missing.append("branch name, or say `auto`")
    return missing


def handle_chat(user_text: str) -> None:
    append_message("user", user_text)
    lowered = user_text.lower().strip()

    if "skill" in lowered and any(word in lowered for word in ("what", "list", "available", "have")):
        skills = skill_list()
        if not skills:
            append_message("assistant", "I could not load skills from the backend.")
            return
        lines = ["Available skills:"]
        for skill in skills:
            lines.append(f"- `{skill['name']}`: {skill['title']} - {skill['description']}")
        append_message("assistant", "\n".join(lines))
        return

    if lowered in {"approve", "approved", "yes proceed", "proceed"}:
        details = st.session_state.pending_request
        if not details or not details.get("plan_ready"):
            append_message("assistant", "I do not have a migration plan ready yet. Tell me the repo and manifest path first.")
            return
        st.session_state.run_approved_migration = True
        append_message("assistant", "Approved. I will start the migration now.")
        return

    if detect_migration_intent(user_text) or st.session_state.pending_request:
        details = st.session_state.pending_request or {
            "overwrite_existing": True,
            "git_token": None,
        }
        if lowered in {"auto", "automatic", "generate", "agent generated", "agent-generated"}:
            details["auto_branch"] = True
        repo_url = extract_repo_url(user_text)
        manifest_path = extract_manifest_path(user_text)
        branch_name = extract_branch_name(user_text)
        if repo_url:
            details["repo_url"] = repo_url
        if manifest_path:
            details["manifest_path"] = manifest_path
        if branch_name:
            details["branch_name"] = branch_name

        skills = skill_list()
        if skills:
            details["skill_title"] = skills[0]["title"]

        st.session_state.pending_request = details
        missing = missing_details()
        if missing:
            append_message("assistant", f"I can help with that. Please provide: {', '.join(missing)}.")
            return

        details["plan_ready"] = True
        try:
            plan = migration_plan(details)
        except requests.RequestException as exc:
            append_message("assistant", f"I could not generate a plan from the backend skill: {exc}")
            return
        details["plan"] = plan
        append_message("assistant", plan["plan_markdown"])
        return

    append_message(
        "assistant",
        "Ask me to list skills, or ask me to migrate a repository. Example: `Migrate https://github.com/org/repo.git from Ingress to Gateway, path k8s/overlays/prod/ingress`.",
    )


def render_result(data: Dict[str, Any]) -> None:
    st.subheader("Result")
    st.write(f"Status: `{data.get('status')}`")
    if data.get("branch_name"):
        st.write(f"Feature branch: `{data.get('branch_name')}`")
    if data.get("workspace_dir"):
        st.write(f"Workspace: `{data.get('workspace_dir')}`")
    pr_url = data.get("pr_url")
    if pr_url and str(pr_url).startswith("http"):
        st.markdown(f"Pull request: [{pr_url}]({pr_url})")
    elif pr_url:
        st.info(pr_url)
    if data.get("errors"):
        st.error("\n".join(str(error) for error in data["errors"]))

    with st.expander("Conversion logs"):
        st.code(data.get("conversion_logs") or "No conversion logs returned.")
    with st.expander("Validation logs"):
        st.code(data.get("validation_logs") or "No validation logs returned.")
    with st.expander("Generated PR summary"):
        st.markdown(data.get("pr_description") or "No PR summary returned.")


STEP_ICONS = {
    "pending": "◇",
    "running": "◆",
    "done": "✓",
    "failed": "✕",
    "instruction": "•",
}


def initial_steps(plan: Dict[str, Any] | None) -> List[Dict[str, str]]:
    if plan and plan.get("steps"):
        return [
            {
                "number": step.get("number", str(index)),
                "label": step.get("step", "Plan step"),
                "tool": step.get("tool", ""),
                "kind": step.get("kind", "instruction"),
                "status": "pending",
                "detail": "Waiting",
            }
            for index, step in enumerate(plan["steps"], start=1)
        ]

    return [
        {
            "number": "1",
            "label": "Run migration workflow",
            "tool": "",
            "kind": "instruction",
            "status": "pending",
            "detail": "Waiting for backend plan",
        }
    ]


def update_steps_from_event(steps: List[Dict[str, str]], event: Dict[str, Any]) -> None:
    if event.get("type") != "progress":
        return

    message = event.get("message", "")
    event_name = event.get("event")
    tool_name = ""
    if event_name in {"tool_call", "tool_result"}:
        tool_name = message.split(" ", 1)[0]

    if not tool_name:
        return

    step = next((item for item in steps if item.get("tool") == tool_name), None)
    if not step:
        return

    if event_name == "tool_call":
        step["status"] = "running"
        step["detail"] = "Running"
    elif event_name == "tool_result":
        failed = "status=error" in message
        step["status"] = "failed" if failed else "done"
        step["detail"] = "Failed" if failed else "Completed"

        if not failed:
            next_step_index = steps.index(step) + 1
            while next_step_index < len(steps) and not steps[next_step_index].get("tool"):
                if steps[next_step_index].get("kind") == "end":
                    break
                steps[next_step_index]["status"] = "done"
                steps[next_step_index]["detail"] = "Included in next tool call"
                next_step_index += 1


def render_step_board(steps: List[Dict[str, str]], container: Any) -> None:
    with container.container():
        for step in steps:
            status = step["status"]
            if not step.get("tool") and status == "pending":
                status = "instruction"
            icon = STEP_ICONS[status]
            left, middle, right = st.columns([0.08, 0.68, 0.24], vertical_alignment="center")
            left.markdown(f"### {icon}")
            middle.markdown(f"**{step['number']}. {step['label']}**  \n`{step['detail']}`")
            right.markdown(f"`{status}`")


def run_migration_with_stream(payload: Dict[str, Any], status_label: str, plan: Dict[str, Any] | None) -> Dict[str, Any]:
    final_state: Dict[str, Any] = {}
    steps = initial_steps(plan)
    with st.status(status_label, expanded=True) as status:
        board = st.empty()
        render_step_board(steps, board)
        for event in stream_migration(payload):
            event_type = event.get("type")
            if event_type == "progress":
                update_steps_from_event(steps, event)
                render_step_board(steps, board)
            elif event_type == "start":
                status.update(label=event.get("message", "Migration started."), state="running", expanded=True)
            elif event_type == "final":
                final_state = event.get("state") or {}
                for step in steps:
                    if step["status"] in {"running", "pending"}:
                        step["status"] = "done"
                        step["detail"] = "Completed"
                render_step_board(steps, board)
                status.update(label="Migration workflow finished", state="complete", expanded=False)
            elif event_type == "error":
                for step in steps:
                    if step["status"] == "running":
                        step["status"] = "failed"
                        step["detail"] = "Failed"
                render_step_board(steps, board)
                status.update(label="Migration failed", state="error", expanded=True)
                raise RuntimeError(event.get("message", "Migration failed"))

    return final_state


tab_chat, tab_form = st.tabs(["Chat", "Direct Migration"])

with tab_chat:
    st.caption("Chat with the GitOps agent. Ask for skills, plan a migration, approve, then run.")
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": "Hi. Ask `What skills do you have?` or tell me which repo you want to migrate.",
            }
        ]
    if "pending_request" not in st.session_state:
        st.session_state.pending_request = {}
    if "run_approved_migration" not in st.session_state:
        st.session_state.run_approved_migration = False

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_prompt = st.chat_input("Message the GitOps agent")
    if user_prompt:
        handle_chat(user_prompt)
        st.rerun()

    details = st.session_state.pending_request
    if details and not details.get("plan_ready"):
        with st.form("chat_details_form"):
            st.subheader("Migration details")
            repo_url = st.text_input("Repository URL", value=details.get("repo_url", ""))
            manifest_path = st.text_input("Manifest path", value=details.get("manifest_path", ""))
            branch_name = st.text_input("Branch name", value=details.get("branch_name", ""))
            auto_branch = st.checkbox("Let the agent generate the branch name", value=details.get("auto_branch", False))
            git_token = st.text_input("Git access token", type="password")
            overwrite_existing = st.checkbox("Overwrite existing files", value=details.get("overwrite_existing", True))
            submitted = st.form_submit_button("Create plan")
        if submitted:
            details.update(
                {
                    "repo_url": repo_url,
                    "manifest_path": manifest_path,
                    "branch_name": branch_name if not auto_branch else "",
                    "auto_branch": auto_branch,
                    "git_token": git_token or None,
                    "overwrite_existing": overwrite_existing,
                }
            )
            if missing_details():
                append_message("assistant", f"Please provide: {', '.join(missing_details())}.")
            else:
                try:
                    plan = migration_plan(details)
                except requests.RequestException as exc:
                    append_message("assistant", f"I could not generate a plan from the backend skill: {exc}")
                else:
                    details["plan_ready"] = True
                    details["plan"] = plan
                    append_message("assistant", plan["plan_markdown"])
            st.rerun()

    if details and details.get("plan_ready"):
        if st.button("Approve and run", type="primary"):
            st.session_state.run_approved_migration = True
            append_message("assistant", "Approved. I will start the migration now.")
            st.rerun()

    if st.session_state.run_approved_migration:
        st.session_state.run_approved_migration = False
        details = st.session_state.pending_request
        payload = {
            "repo_url": details["repo_url"],
            "manifest_path": details["manifest_path"],
            "overwrite_existing": details.get("overwrite_existing", True),
            "git_token": details.get("git_token") or None,
        }
        if details.get("branch_name"):
            payload["branch_name"] = details["branch_name"]
        try:
            data = run_migration_with_stream(payload, "Running approved migration...", details.get("plan"))
        except (requests.RequestException, RuntimeError) as exc:
            append_message("assistant", f"Migration failed: {exc}")
        else:
            st.session_state.last_result = data
            append_message("assistant", f"Migration finished with status `{data.get('status')}`.")
            st.rerun()

    if st.session_state.get("last_result"):
        render_result(st.session_state.last_result)

with tab_form:
    use_example = st.checkbox("Use bundled retail-platform example", value=True)
    default_repo = "example://retail-platform" if use_example else ""
    default_path = "k8s/overlays/prod" if use_example else ""

    with st.form("migration_form"):
        repo_url = st.text_input(
            "Target repository URL or local template",
            value=default_repo,
            placeholder="https://github.com/org/repo.git",
        )
        manifest_path = st.text_input(
            "Ingress manifest directory or file",
            value=default_path,
            placeholder="k8s/ingress",
        )
        branch_name = st.text_input(
            "Branch name",
            value="",
            placeholder="Leave empty to let the agent generate one",
        )
        overwrite_existing = st.checkbox(
            "Overwrite existing files",
            value=True,
            help="If false, generated Gateway API manifests are written as separate .gateway.yaml files alongside the original Ingress manifests.",
        )
        git_token = st.text_input(
            "Git access token",
            type="password",
            help="Optional. Not needed for the bundled example.",
        )
        submitted = st.form_submit_button("Start migration")

    if submitted:
        if not repo_url or not manifest_path:
            st.error("Repository URL and manifest path are required.")
        else:
            payload = {
                "repo_url": repo_url,
                "manifest_path": manifest_path,
                "branch_name": branch_name or None,
                "overwrite_existing": overwrite_existing,
                "git_token": git_token or None,
            }
            try:
                plan = migration_plan(payload)
                data = run_migration_with_stream(payload, "Dispatching migration to the agent engine...", plan)
            except (requests.RequestException, RuntimeError) as exc:
                detail = str(exc)
                response = getattr(exc, "response", None)
                if response is not None:
                    try:
                        detail = response.json().get("detail", detail)
                    except ValueError:
                        detail = response.text or detail
                st.error(detail)
            else:
                time.sleep(0.2)
                render_result(data)

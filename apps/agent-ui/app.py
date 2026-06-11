from __future__ import annotations

import os
import time

import requests
import streamlit as st


DEFAULT_BACKEND_URL = os.getenv("MIGRATION_BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="GitOps Gateway Migration", layout="centered")
st.title("GitOps Ingress-to-Gateway Migration")

backend_url = st.sidebar.text_input("Backend URL", DEFAULT_BACKEND_URL).rstrip("/")
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
        status = st.status("Dispatching migration to the agent engine...", expanded=True)
        payload = {
            "repo_url": repo_url,
            "manifest_path": manifest_path,
            "overwrite_existing": overwrite_existing,
            "git_token": git_token or None,
        }
        try:
            response = requests.post(f"{backend_url}/api/v1/migrate", json=payload, timeout=900)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            status.update(label="Migration failed", state="error", expanded=True)
            detail = str(exc)
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    detail = response.json().get("detail", detail)
                except ValueError:
                    detail = response.text or detail
            st.error(detail)
        else:
            status.write("Repository cloned and conversion workflow completed.")
            if data.get("validation_logs"):
                status.write("YAML validation completed.")
            if data.get("pr_url"):
                status.write("Pull request step completed.")
            time.sleep(0.2)
            status.update(label="Migration workflow finished", state="complete", expanded=False)

            st.subheader("Result")
            st.write(f"Status: `{data.get('status')}`")
            st.write(f"Feature branch: `{data.get('branch_name')}`")
            if data.get("workspace_dir"):
                st.write(f"Workspace: `{data.get('workspace_dir')}`")
            pr_url = data.get("pr_url")
            if pr_url and pr_url.startswith("http"):
                st.markdown(f"Pull request: [{pr_url}]({pr_url})")
            elif pr_url:
                st.info(pr_url)

            with st.expander("Conversion logs"):
                st.code(data.get("conversion_logs") or "No conversion logs returned.")
            with st.expander("Validation logs"):
                st.code(data.get("validation_logs") or "No validation logs returned.")
            with st.expander("Generated PR summary"):
                st.markdown(data.get("pr_description") or "No PR summary returned.")

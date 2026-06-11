# Agentic Migration Guide

This project migrates Kubernetes Nginx Ingress manifests to Envoy Gateway / Gateway API manifests with an LLM-driven agent. The application gives the agent a repository, a manifest path, and a set of tools. The agent decides which tools to call, observes each result, and continues until it has completed the migration or review correction.

## Core Idea

The core is `GitOpsAgent` in `apps/agent-api/agent.py`.

`GitOpsAgent` is not a hardcoded workflow graph. It is a tool-using LLM loop:

1. Build a context object from the API request.
2. Send that context to the configured LLM.
3. Let the LLM choose tool calls.
4. Execute each requested tool.
5. Send tool results back to the LLM.
6. Repeat until the LLM stops calling tools.
7. Collect logs, validation output, branch details, and PR details into the API response.

The important distinction is that Python provides capabilities, while the LLM decides the order of operations.

## Request Flow

The FastAPI app in `apps/agent-api/main.py` exposes the entrypoints:

- `POST /api/v1/migrate` starts a migration.
- `POST /webhook/github` handles pull request review comments.
- `POST /api/v1/llm/test` checks the configured LLM.

For a migration request, `apps/agent-api/main.py` creates a state object like:

```json
{
  "repo_url": "example://retail-platform",
  "manifest_path": "k8s/overlays/prod",
  "overwrite_existing": true
}
```

Then it calls:

```python
AGENT.execute(state)
```

The agent adds a suggested branch name if one was not provided, sends the context to the LLM, and starts the tool loop.

## Tool Loop

The agent supports native LangChain tool calls and a text fallback format.

Native tool call path:

1. The LLM returns an assistant message with `tool_calls`.
2. The agent resolves each tool name with `get_tool_by_name`.
3. The agent invokes the tool with `invoke_tool`.
4. The agent appends a `ToolMessage` with the result.
5. The LLM sees the result and decides the next action.

Text fallback path:

```text
TOOL_CALL: validate_yaml
TOOL_INPUT: {"yaml_file_path": "/path/to/file.yaml"}
```

This fallback exists for providers or responses that do not produce native tool-call objects.

## Available Tools

Tools are registered in `apps/agent-api/tools/registry.py`.

### `clone_repo`

Defined in `apps/agent-api/tools/github.py`.

Clones a GitHub repository or copies a local/bundled example into an isolated workspace. It also creates the feature branch and stores run context such as `repo_dir`, `workspace_dir`, `repo_full_name`, and `base_branch`.

### `convert_ingress`

Defined in `apps/agent-api/tools/conversion.py`.

Converts Nginx Ingress manifests into Gateway API manifests. It uses `ingress2gateway` or `ingress2eg` when available, and falls back to the built-in deterministic converter when those CLIs are not installed.

### `validate_yaml`

Defined in `apps/agent-api/tools/validation.py`.

Validates Kubernetes YAML with `kubeconform -strict` when available. If schemas cannot be downloaded, it falls back to YAML parsing so the agent still gets a useful syntax validation result.

### `modify_yaml_file`

Defined in `apps/agent-api/tools/editing.py`.

Overwrites a YAML file inside the migration workspace after parsing the proposed content as YAML. It refuses to modify files outside the workspace.

### `push_branch`

Defined in `apps/agent-api/tools/github.py`.

Commits changed files and pushes the feature branch. For bundled or local examples, it creates a local commit and does not push to GitHub.

### `create_github_pr`

Defined in `apps/agent-api/tools/github.py`.

Creates a GitHub pull request for the branch. If a PR already exists for the same branch, it updates and returns the existing PR instead of failing with a duplicate-PR error.

## State And Context

Run context is stored by branch name in `apps/agent-api/tools/common.py`.

The context lets later tools discover what earlier tools produced. For example:

- `clone_repo` stores `repo_dir` and `workspace_dir`.
- `convert_ingress` stores `manifest_path`, `overwrite_existing`, and `validation_path`.
- `create_github_pr` stores `pr_number` and `pr_url`.

At the end of the loop, `GitOpsAgent` reads this context and returns fields such as:

```json
{
  "status": "completed",
  "branch_name": "agentic-gateway-migration-abc12345",
  "workspace_dir": "/tmp/gitops-migration-workspaces/agentic-gateway-migration-abc12345",
  "validation_logs": "...",
  "pr_url": "https://github.com/org/repo/pull/123"
}
```

## Example Walkthrough

Use the bundled example:

```text
Repository URL: example://retail-platform
Manifest path: k8s/overlays/prod
Overwrite existing files: true
```

A typical agent run may look like this:

1. The user submits the migration request through the Streamlit UI or FastAPI.
2. `apps/agent-api/main.py` passes the request state to `GitOpsAgent`.
3. The agent asks the LLM to complete the migration using tools.
4. The LLM chooses `clone_repo` with a generated branch name.
5. The tool copies `examples/retail-platform` into an isolated workspace and creates a local git branch.
6. The LLM observes the clone result and chooses `convert_ingress`.
7. The converter reads manifests under `k8s/overlays/prod` and writes Gateway API resources.
8. The LLM chooses `validate_yaml` using the validation path from the conversion result/context.
9. If validation reports YAML or schema issues that can be fixed, the LLM may choose `modify_yaml_file`, then `validate_yaml` again.
10. Once validation is acceptable, the LLM chooses `push_branch`.
11. For the bundled example, the push tool creates a local commit and reports that example sources are not pushed to GitHub.
12. The LLM may choose `create_github_pr`; for a local example, the tool returns a local-only message instead of opening a remote PR.
13. The LLM stops calling tools and summarizes the result.
14. The API response includes the branch, workspace, logs, validation output, and PR/local result.

## Review Comment Flow

GitHub review comments enter through `POST /webhook/github`.

The webhook handler looks up the active PR state, attaches the review comment, and calls `GitOpsAgent` again. In review mode, the agent adds the reviewed file content and GitHub comment metadata to the LLM context.

A typical review correction may be:

1. LLM reads the comment and the reviewed manifest.
2. LLM calls `modify_yaml_file` with the corrected full YAML.
3. LLM calls `validate_yaml`.
4. LLM calls `push_branch` with a review-specific commit message.
5. LLM stops and reports that feedback was processed.

## Safety Boundaries

The tools provide guardrails around the LLM:

- `modify_yaml_file` only writes inside the migration workspace.
- `clone_repo` works in isolated workspaces under `MIGRATION_WORKSPACE_ROOT`.
- `push_branch` commits only the cloned workspace changes.
- `create_github_pr` is idempotent for duplicate branch PRs.
- Live cluster access is not part of the toolset; the agent cannot run `kubectl` unless such a tool is added later.

## How To Extend The Agent

To add a new capability:

1. Create a tool function with `@tool`.
2. Add it to `TOOLS` in `apps/agent-api/tools/registry.py`.
3. Make the tool return concise, useful text.
4. Add any persistent run context with `set_run_context` if later tools need it.
5. Update this guide with the new tool and when the LLM should use it.

The agent loop does not need a new hardcoded step. Once the tool is registered, the LLM can choose it when the request and tool description make it relevant.

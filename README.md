# AI GitOps Ingress-to-Gateway Migration Agent

This repo contains a working Streamlit + FastAPI prototype for migrating Nginx Ingress manifests to Envoy Gateway / Gateway API manifests with an LLM-driven tool agent.

## Bundled Example

The repo includes a small application template at `examples/retail-platform`.

Use it from the UI with:

- Repository URL: `example://retail-platform`
- Manifest path: `k8s/overlays/prod`

The backend copies the example into an isolated workspace, initializes a local git repo, creates a feature branch, converts the Ingress, validates YAML, and creates a local migration commit. No GitHub token is needed for the bundled example.

## Architecture

- `apps/agent-api/`: FastAPI service and LLM-driven migration agent
- `apps/agent-ui/`: Streamlit UI
- `agentic-app/`: Helm chart for deploying the API and UI together
- `examples/`: bundled migration examples retained at the repository root
- SQLite state persistence for migration run context is stored under `MIGRATION_STATE_DB` or the workspace root

See `AGENTIC_MIGRATION.md` for a walkthrough of how the agent works, how tools are used, and what happens during an example migration.

## Run

API:

```bash
cd apps/agent-api
pip install -r requirements.txt
uvicorn main:app --reload
```

UI:

```bash
cd apps/agent-ui
pip install -r requirements.txt
streamlit run app.py
```

For real GitHub repositories, provide a repository URL, manifest path, and a token with permissions to push a feature branch and create a pull request.

## Docker

Build both images from the repository root:

```bash
docker build -f apps/agent-api/Dockerfile -t agent-api:local .
docker build -f apps/agent-ui/Dockerfile -t agent-ui:local .
```

Run the API:

```bash
docker run --rm -p 8000:8000 \
  -e MIGRATION_LLM_PROVIDER=openai \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  agent-api:local
```

Run the UI:

```bash
docker run --rm -p 8501:8501 \
  -e MIGRATION_BACKEND_URL=http://host.docker.internal:8000 \
  agent-ui:local
```

## Helm

The combined chart lives in `agentic-app/`.

```bash
helm upgrade --install agentic-app ./agentic-app \
  --set api.image.repository=agent-api \
  --set api.image.tag=local \
  --set ui.image.repository=agent-ui \
  --set ui.image.tag=local
```

## LLM Provider

Review-comment self-correction needs an LLM. Select the provider with `MIGRATION_LLM_PROVIDER`.

OpenAI:

```bash
export MIGRATION_LLM_PROVIDER=openai
export OPENAI_API_KEY="your-openai-key"
export MIGRATION_LLM_MODEL="gpt-4o"
```

Gemini:

```bash
export MIGRATION_LLM_PROVIDER=gemini
export GOOGLE_API_KEY="your-google-ai-studio-key"
export MIGRATION_LLM_MODEL="gemini-2.5-flash"
```

For GitHub PR creation and webhook correction commits, also set:

```bash
export GITHUB_TOKEN="your-github-token"
export GITHUB_WEBHOOK_SECRET="your-webhook-secret"
```

Test the configured LLM:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/llm/test \
  -H "Content-Type: application/json" \
  -d '{"question":"Which LLM provider is currently responding?"}'
```

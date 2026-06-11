# Agent API

FastAPI service that hosts the LLM-driven GitOps migration agent.

## What It Does

- Accepts migration requests at `POST /api/v1/migrate`.
- Runs `GitOpsAgent`, which lets the configured LLM choose and call migration tools.
- Handles GitHub review-comment webhooks at `POST /webhook/github`.
- Stores run context in SQLite under `MIGRATION_STATE_DB` or the migration workspace root.

## Local Run

From this directory:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

For the bundled example, run from the repository root or set:

```bash
export MIGRATION_EXAMPLES_ROOT=/path/to/agentic-migration/examples
```

## Environment

- `MIGRATION_LLM_PROVIDER`: `openai` or `gemini`
- `MIGRATION_LLM_MODEL`: model name for the selected provider
- `OPENAI_API_KEY`: required for OpenAI
- `GOOGLE_API_KEY`: required for Gemini
- `GITHUB_TOKEN`: optional token for branch push and PR creation
- `GITHUB_WEBHOOK_SECRET`: optional webhook signature secret
- `MIGRATION_WORKSPACE_ROOT`: workspace and default SQLite location
- `MIGRATION_STATE_DB`: explicit SQLite database path
- `MIGRATION_EXAMPLES_ROOT`: location of bundled examples

## Docker

Build from the repository root:

```bash
docker build -f apps/agent-api/Dockerfile -t agent-api:local .
```

Run:

```bash
docker run --rm -p 8000:8000 \
  -e MIGRATION_LLM_PROVIDER=openai \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  agent-api:local
```

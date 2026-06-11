# Agentic App Helm Chart

Deploys the migration API and Streamlit UI together.

## Install

Build and push images first, then set image repositories:

```bash
helm upgrade --install agentic-app ./agentic-app \
  --set api.image.repository=ghcr.io/example/agent-api \
  --set api.image.tag=latest \
  --set ui.image.repository=ghcr.io/example/agent-ui \
  --set ui.image.tag=latest
```

## Secrets

For quick local testing, values can provide secret strings under `api.secretEnv`.

For shared environments, prefer an existing Kubernetes Secret:

```bash
kubectl create secret generic agentic-app-secrets \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN"

helm upgrade --install agentic-app ./agentic-app \
  --set api.existingSecret=agentic-app-secrets
```

The API reads:

- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `GITHUB_TOKEN`
- `GITHUB_WEBHOOK_SECRET`

## Services

- API service: `<release-name>-agentic-app-api:8000`
- UI service: `<release-name>-agentic-app-ui:8501`

The chart automatically sets `MIGRATION_BACKEND_URL` in the UI to the API service URL.

# Agent UI

Streamlit UI for starting migration runs and viewing agent output.

## Local Run

From this directory:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

By default, the UI calls `http://localhost:8000`. Override it with:

```bash
export MIGRATION_BACKEND_URL=http://localhost:8000
```

## Docker

Build from the repository root:

```bash
docker build -f apps/agent-ui/Dockerfile -t agent-ui:local .
```

Run:

```bash
docker run --rm -p 8501:8501 \
  -e MIGRATION_BACKEND_URL=http://host.docker.internal:8000 \
  agent-ui:local
```

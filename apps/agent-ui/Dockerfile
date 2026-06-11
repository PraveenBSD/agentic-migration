FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MIGRATION_BACKEND_URL=http://agent-api:8000

WORKDIR /app

COPY apps/agent-ui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/agent-ui/ .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]

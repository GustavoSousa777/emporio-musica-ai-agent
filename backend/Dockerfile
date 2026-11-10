FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DB_PATH=/app/data/emporio.db \
    CONVERSATIONS_DB_PATH=/app/state/conversations.db \
    RAG_INDEX_PATH=/app/state/policies_index.json

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY data/raw ./data/raw
COPY data/policies ./data/policies

RUN useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p /app/state \
    && python -m app.database.seed --db "$DB_PATH" --report /tmp/data_quality.md \
    && python -m app.rag.build_index --lexical-only \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]

CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT}"]

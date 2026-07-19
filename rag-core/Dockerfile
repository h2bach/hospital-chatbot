FROM python:3.13-slim

WORKDIR /app
ENV PYTHONPATH=/app/rag-core PYTHONUNBUFFERED=1

COPY rag-core/rag_core /app/rag-core/rag_core
COPY rag-core/artifacts/data-rag-latest /app/data-rag-latest
COPY rag-core/artifacts/data-rag /app/data-rag
COPY docs /app/docs
COPY ai-agent/static /app/static

EXPOSE 6689

CMD ["python", "-m", "rag_core.app", "--host", "0.0.0.0", "--port", "6689", "--chunks", "/app/data-rag-latest/chunks_latest.jsonl", "--documents", "/app/data-rag-latest/documents_latest.jsonl", "--static", "/app/static"]

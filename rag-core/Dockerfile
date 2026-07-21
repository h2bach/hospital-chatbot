FROM python:3.13-slim

WORKDIR /app
ENV PYTHONPATH=/app/rag-core PYTHONUNBUFFERED=1

COPY rag-core/rag_core /app/rag-core/rag_core
COPY rag-core/artifacts/data-rag-latest/chunks_latest.jsonl /app/data-rag-latest/chunks_latest.jsonl
COPY rag-core/artifacts/data-rag-latest/documents_latest.jsonl /app/data-rag-latest/documents_latest.jsonl
COPY rag-core/artifacts/data-rag/chunks.jsonl /app/data-rag/chunks.jsonl
COPY rag-core/artifacts/data-rag/documents.jsonl /app/data-rag/documents.jsonl
COPY ai-agent/static /app/static

EXPOSE 6689

CMD ["python", "-m", "rag_core.app", "--host", "0.0.0.0", "--port", "6689", "--chunks", "/app/data-rag-latest/chunks_latest.jsonl", "--documents", "/app/data-rag-latest/documents_latest.jsonl", "--static", "/app/static"]

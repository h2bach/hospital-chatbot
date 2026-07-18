"""
Ollama embedding function.

Local embeddings via Ollama's OpenAI-incompatible ``/api/embeddings`` endpoint.
Default model: nomic-embed-text (768-dim). No external API, no API key.

The class is a plain callable ``(list[str]) -> list[list[float]]`` so it can be
used directly by the vector store. Requests are issued concurrently (bounded)
to keep ingest and multi-text embedding fast.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import httpx


class OllamaEmbedder:
    """Callable embedder backed by a local Ollama server.

    Uses a single persistent httpx client with a connection pool. This is
    critical for latency: creating a fresh client per request adds ~2s of
    connection setup overhead on Windows, while a pooled client keeps warm
    embedding calls at ~90-100ms.
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        max_concurrency: int = 5,
        timeout: float = 60.0,
        keep_alive: str = "30m",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_concurrency = max(1, max_concurrency)
        self.timeout = timeout
        self.keep_alive = keep_alive
        self._url = f"{self.base_url}/api/embeddings"
        self._client_lock = threading.Lock()
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Lazily create and reuse a pooled httpx client (thread-safe)."""
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = httpx.Client(
                        timeout=self.timeout,
                        limits=httpx.Limits(
                            max_connections=self.max_concurrency + 2,
                            max_keepalive_connections=self.max_concurrency + 2,
                        ),
                    )
        return self._client

    # Safety cap: nomic-embed-text context is ~2048 tokens (~2 chars/token for
    # dense Vietnamese/table text). Truncate very long inputs so one oversized
    # text never fails the whole batch. 3000 chars verified safe.
    _MAX_CHARS = 3000

    def _embed_one(self, text: str) -> list[float]:
        if len(text) > self._MAX_CHARS:
            text = text[: self._MAX_CHARS]
        resp = self._get_client().post(
            self._url,
            json={
                "model": self.model,
                "prompt": text,
                # Keep the model resident so subsequent calls avoid reload cost.
                "keep_alive": self.keep_alive,
            },
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    def __call__(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            if len(texts) == 1:
                return [self._embed_one(texts[0])]

            results: list[list[float]] = [None] * len(texts)  # type: ignore[list-item]
            workers = min(self.max_concurrency, len(texts))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(self._embed_one, t): i
                    for i, t in enumerate(texts)
                }
                for fut in futures:
                    idx = futures[fut]
                    results[idx] = fut.result()
            return results
        except Exception as exc:  # pragma: no cover - surfaced to caller
            raise RuntimeError(
                f"Ollama embedding failed ({self.model} @ {self.base_url}): {exc}. "
                f"Ensure Ollama is running and the model is pulled "
                f"(`ollama pull {self.model}`)."
            ) from exc

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return self(([text]))[0]

    def warmup(self) -> None:
        """
        Pre-open the connection pool and load the model.

        On Windows, opening a new connection costs ~2s. We open
        ``max_concurrency`` connections in parallel once at startup so later
        concurrent embedding batches reuse warm keep-alive connections.
        """
        n = self.max_concurrency
        try:
            self([f"warmup {i}" for i in range(n)])
        except Exception:
            # Warmup is best-effort; real calls will surface any error.
            pass


__all__ = ["OllamaEmbedder"]

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_core.chunking import ChunkingConfig
from rag_core.ingestion.pipeline import ingest_markdown, write_artifacts
from rag_core.storage import CanonicalStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a traceable HeartCare Markdown document")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--document-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--target-tokens", type=int, default=256)
    parser.add_argument("--max-tokens", type=int, default=384)
    args = parser.parse_args()
    config = json.loads(args.document_config.read_text(encoding="utf-8"))
    result = ingest_markdown(args.input.read_text(encoding="utf-8"), config,
                             ChunkingConfig(args.target_tokens, args.max_tokens))
    write_artifacts(result, args.output)
    if args.database:
        store = CanonicalStore(args.database)
        store.upsert_ingestion(result.document, result.version, result.sections, result.chunks, result.citations)
        store.close()
    print(json.dumps({"document_id": result.document.document_id, "chunks": len(result.chunks),
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()


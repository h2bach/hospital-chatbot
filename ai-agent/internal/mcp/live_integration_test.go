package mcp

import (
	"context"
	"os"
	"testing"
	"time"
)

func TestLiveMCPRAGPreservesStructuredEvidence(t *testing.T) {
	url := os.Getenv("LIVE_MCP_URL")
	if url == "" {
		t.Skip("LIVE_MCP_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	client, err := NewMCPClient(ctx, url)
	if err != nil {
		t.Fatalf("connect live MCP: %v", err)
	}
	defer client.Disconnect()
	result, err := client.CallToolStructured(ctx, "searchRAG", map[string]any{
		"query": "SPECT/CT tưới máu cơ tim gắng sức Tetrofosmin",
		"top_k": 5,
	})
	if err != nil {
		t.Fatalf("call live RAG tool: %v", err)
	}
	evidence := NormalizeEvidence("searchRAG", result, time.Now())
	if len(evidence) == 0 {
		t.Fatalf("live MCP lost structured RAG evidence; fields=%v structured_type=%T", StructuredFieldNames(result), result.Structured)
	}
	if evidence[0].Citation.SourceKind != "rag_document" || evidence[0].Citation.Location.ChunkID == "" {
		t.Fatalf("invalid normalized live evidence: %#v", evidence[0].Citation)
	}
}

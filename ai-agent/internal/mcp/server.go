package mcp

import (
	"agent/internal/rag"
	"net/http"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func NewMCPServer(providers ...rag.KnowledgeProvider) http.Handler {
	impl := mcp_sdk.Implementation{
		Name:    "hanoi-heart-hospital-public-info-mcp",
		Version: "v2.0",
	}
	server := mcp_sdk.NewServer(&impl, nil)

	var knowledge rag.KnowledgeProvider
	if len(providers) > 0 {
		knowledge = providers[0]
	}
	bindTools(server, knowledge)

	handler := mcp_sdk.NewStreamableHTTPHandler(func(r *http.Request) *mcp_sdk.Server {
		return server
	}, nil)
	return handler
}

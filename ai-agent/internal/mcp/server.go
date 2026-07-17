package mcp

import (
	"net/http"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func NewMCPServer() http.Handler {
	impl := mcp_sdk.Implementation{
		Name: "mcp-server",
		Version: "v1.0",
	}
	server := mcp_sdk.NewServer(&impl, nil)

	bindTools(server)

	handler := mcp_sdk.NewStreamableHTTPHandler(func(r *http.Request) *mcp_sdk.Server {
		return server
	}, nil)
	return handler
}

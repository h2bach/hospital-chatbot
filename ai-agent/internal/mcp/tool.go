package mcp

import (
	"agent/internal/mcp/tools"
	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func bindTools(server *mcp_sdk.Server) {
	mcp_sdk.AddTool(server, &tools.CheckTimeTool, tools.CheckTimeHandler)
}

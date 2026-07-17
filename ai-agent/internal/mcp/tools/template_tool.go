package tools

import (
	"fmt"
	"context"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

var TemplateTool = mcp_sdk.Tool{
	Name: "templateTool",
	Description: "a template api tool",
}

type TemplateToolInput struct {
	Param1 string `json:"param1" jsonschema:"mock param 1"`
	Param2 string `json:"param2" jsonschema:"mock param 2"`
}

type TemplateToolOutput struct {
	Output string `json:"output" jsonschema:"a mock output"`
}

func TemplateToolHandler(ctx context.Context, request *mcp_sdk.CallToolRequest, input TemplateToolInput) (
	*mcp_sdk.CallToolResult,
	TemplateToolOutput,
	error,
) {
	return nil, TemplateToolOutput{
		fmt.Sprintf("param1: %s\nparam2:%s", input.Param1, input.Param2),
	}, nil
}

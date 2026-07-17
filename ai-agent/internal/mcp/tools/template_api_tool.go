package tools

import (
	"fmt"
	"context"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

var ApiTool = mcp_sdk.Tool{
	Name: "templateApiTool",
	Description: "a template api tool",
}

type ApiToolInput struct {
	Param1 string `json:"param1" jsonschema:"mock param 1"`
	Param2 string `json:"param2" jsonschema:"mock param 2"`
}

type ApiToolOutput struct {
	Output string `json:"output" jsonschema:"a mock output"`
}

func ApiToolHandler(ctx context.Context, request *mcp_sdk.CallToolRequest, input ApiToolInput) (
	*mcp_sdk.CallToolResult,
	ApiToolOutput,
	error,
) {
	return nil, ApiToolOutput{
		fmt.Sprintf("param1: %s\nparam2:%s", input.Param1, input.Param2),
	}, nil
}

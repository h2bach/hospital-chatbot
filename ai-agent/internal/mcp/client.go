package mcp

import (
	"context"
	"errors"
	"strings"
	"sync/atomic"
	"time"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	DEFAULT_RETRY_TIME = 5 * time.Second
)

var (
	ErrNoToolsAvailable = errors.New("error no tools is available")
)

type MCPClient struct {
	SDKClient *mcp_sdk.Client
	URL string
	Transport mcp_sdk.Transport

	retrying atomic.Bool
	tools []mcp_sdk.Tool
	session *mcp_sdk.ClientSession
}

func NewMCPClient(ctx context.Context, url string) (*MCPClient, error) {
	client := MCPClient{}
	impl := mcp_sdk.Implementation{
		Name: "agent-client",
		Version: "v1.0.0",
	}
	client.SDKClient = mcp_sdk.NewClient(&impl, nil)
	client.URL = url
	client.Transport = &mcp_sdk.StreamableClientTransport{
		Endpoint: client.URL,
	}

	session, err := client.SDKClient.Connect(ctx, client.Transport, nil)
	if err == nil {
		client.session = session
	} else {
		client.Retry(ctx)
	}
	return &client, err
}

func (client *MCPClient) Disconnect() {
	if client.session != nil {
		client.session.Close()
	}
}

func (client *MCPClient) Retry(ctx context.Context) {
	if !client.retrying.CompareAndSwap(false, true) {
		return
	}

	go func() {
		defer client.retrying.Store(false)
		timer := time.NewTicker(DEFAULT_RETRY_TIME)
		defer timer.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-timer.C:
				session, err := client.SDKClient.Connect(ctx, client.Transport, nil)
				if err != nil {
					continue
				} 

				client.session = session
				return
			}
		}
	}()
}

func (client *MCPClient) IsRetrying() bool {
	return client.retrying.Load()
}

func (client *MCPClient) Tools(ctx context.Context) ([]mcp_sdk.Tool, error) {
	if client.session == nil {
		return nil, ErrNoToolsAvailable
	}
	if client.tools != nil {
		return client.tools, nil
	}

	tools := client.session.Tools(ctx, nil)
	result := make([]mcp_sdk.Tool, 0)
	for tool, err := range tools {
		if err == nil {
			result = append(result, *tool)
		}
	}
	client.tools = result
	return result, nil
}

func (client *MCPClient) CallTool(ctx context.Context, toolName string, args map[string]any) (string, error) {
	if tools, _ := client.Tools(ctx); len(tools) == 0 || client.session == nil {
		return "", ErrNoToolsAvailable
	}

	params := mcp_sdk.CallToolParams{
		Name: toolName,
		Arguments: args,
	}
	callResult, err := client.session.CallTool(ctx, &params)
	if err != nil {
		client.tools = nil
		return "", err
	}

	var b strings.Builder
	for _, content := range callResult.Content {
		if textContent, ok := content.(*mcp_sdk.TextContent); ok {
			b.WriteString(textContent.Text + "\n")
		} else {
			return "", errors.New("error marshalling text content")
		}
	}
	return b.String(), nil
}

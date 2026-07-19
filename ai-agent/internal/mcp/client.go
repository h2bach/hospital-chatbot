package mcp

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

type ToolResult struct {
	Text       string
	Structured any
	IsError    bool
}

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
	mu       sync.Mutex
	tools    []mcp_sdk.Tool
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

	err := client.connect(ctx)
	if err != nil {
		client.Retry(ctx)
	}
	return &client, err
}

func (client *MCPClient) Disconnect() {
	client.mu.Lock()
	session := client.session
	client.session = nil
	client.tools = nil
	client.mu.Unlock()
	if session != nil {
		session.Close()
	}
}

func (client *MCPClient) connect(ctx context.Context) error {
	client.mu.Lock()
	defer client.mu.Unlock()
	if client.session != nil {
		return nil
	}
	session, err := client.SDKClient.Connect(ctx, client.Transport, nil)
	if err != nil {
		return err
	}
	client.session = session
	client.tools = nil
	return nil
}

func (client *MCPClient) Retry(ctx context.Context) {
	if !client.retrying.CompareAndSwap(false, true) {
		return
	}

	go func() {
		defer client.retrying.Store(false)
		if client.connect(ctx) == nil {
			return
		}
		timer := time.NewTicker(DEFAULT_RETRY_TIME)
		defer timer.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-timer.C:
				if client.connect(ctx) == nil {
					return
				}
			}
		}
	}()
}

func (client *MCPClient) IsRetrying() bool {
	return client.retrying.Load()
}

func (client *MCPClient) Tools(ctx context.Context) ([]mcp_sdk.Tool, error) {
	if err := client.connect(ctx); err != nil {
		client.Retry(ctx)
		return nil, ErrNoToolsAvailable
	}
	client.mu.Lock()
	if client.tools != nil {
		result := append([]mcp_sdk.Tool(nil), client.tools...)
		client.mu.Unlock()
		return result, nil
	}
	session := client.session
	client.mu.Unlock()

	tools := session.Tools(ctx, nil)
	result := make([]mcp_sdk.Tool, 0)
	for tool, err := range tools {
		if err == nil {
			result = append(result, *tool)
		}
	}
	client.mu.Lock()
	client.tools = append([]mcp_sdk.Tool(nil), result...)
	client.mu.Unlock()
	return result, nil
}

func (client *MCPClient) CallTool(ctx context.Context, toolName string, args map[string]any) (string, error) {
	result, err := client.CallToolDetailed(ctx, toolName, args)
	if err != nil {
		return "", err
	}
	return result.Text, nil
}

// CallToolDetailed preserves both MCP text and structuredContent. Citation
// generation must use the structured value rather than trying to recover
// provenance from a human-readable tool response.
func (client *MCPClient) CallToolDetailed(ctx context.Context, toolName string, args map[string]any) (ToolResult, error) {
	if tools, _ := client.Tools(ctx); len(tools) == 0 {
		return ToolResult{}, ErrNoToolsAvailable
	}
	client.mu.Lock()
	session := client.session
	client.mu.Unlock()
	if session == nil {
		return ToolResult{}, ErrNoToolsAvailable
	}

	params := mcp_sdk.CallToolParams{
		Name: toolName,
		Arguments: args,
	}
	callResult, err := session.CallTool(ctx, &params)
	if err != nil {
		client.mu.Lock()
		client.tools = nil
		if client.session == session {
			client.session = nil
		}
		client.mu.Unlock()
		client.Retry(ctx)
		return ToolResult{}, err
	}

	var b strings.Builder
	for _, content := range callResult.Content {
		if textContent, ok := content.(*mcp_sdk.TextContent); ok {
			b.WriteString(textContent.Text + "\n")
		} else {
			return ToolResult{}, errors.New("error marshalling text content")
		}
	}
	structured := decodeStructuredContent(callResult.StructuredContent, strings.TrimSpace(b.String()))
	return ToolResult{
		Text:       strings.TrimSpace(b.String()),
		Structured: structured,
		IsError:    callResult.IsError,
	}, nil
}

func decodeStructuredContent(structured any, text string) any {
	if raw, ok := structured.(json.RawMessage); ok {
		var decoded any
		if len(raw) > 0 && json.Unmarshal(raw, &decoded) == nil {
			return decoded
		}
	}
	if structured != nil {
		return structured
	}

	// Typed MCP tools also expose their structured output as a JSON text block.
	// Some transports/providers omit structuredContent while preserving that
	// standards-compatible fallback. Recover the object here so provenance is
	// never discarded merely because of transport capability differences.
	var decoded any
	if strings.HasPrefix(text, "{") && json.Unmarshal([]byte(text), &decoded) == nil {
		return decoded
	}
	return nil
}

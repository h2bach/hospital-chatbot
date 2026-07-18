package mcp

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	DEFAULT_RETRY_TIME = time.Second
)

var (
	ErrNoToolsAvailable = errors.New("error no tools is available")
)

// ToolClient is the Agent-facing MCP boundary. Keeping it as an interface
// makes the orchestration testable without bypassing the real SDK in runtime.
type ToolClient interface {
	Disconnect()
	Retry(context.Context)
	Tools(context.Context) ([]mcp_sdk.Tool, error)
	CallTool(context.Context, string, map[string]any) (string, error)
}

type MCPClient struct {
	SDKClient *mcp_sdk.Client
	URL       string
	Transport mcp_sdk.Transport

	retrying atomic.Bool
	mu       sync.RWMutex
	tools    []mcp_sdk.Tool
	session  *mcp_sdk.ClientSession
}

var _ ToolClient = (*MCPClient)(nil)

func NewMCPClient(ctx context.Context, url string) (*MCPClient, error) {
	client := NewDeferredMCPClient(url)
	session, err := client.SDKClient.Connect(ctx, client.Transport, nil)
	if err == nil {
		client.session = session
	} else {
		client.Retry(ctx)
	}
	return client, err
}

// NewDeferredMCPClient constructs the SDK client without connecting. The HTTP
// server uses this form so it can bind /mcp first, then start the self-client.
func NewDeferredMCPClient(url string) *MCPClient {
	client := &MCPClient{}
	impl := mcp_sdk.Implementation{
		Name:    "agent-client",
		Version: "v1.0.0",
	}
	client.SDKClient = mcp_sdk.NewClient(&impl, nil)
	client.URL = url
	client.Transport = &mcp_sdk.StreamableClientTransport{
		Endpoint: client.URL,
	}
	return client
}

func (client *MCPClient) Disconnect() {
	client.mu.Lock()
	session := client.session
	client.session = nil
	client.tools = nil
	client.mu.Unlock()
	if session != nil {
		_ = session.Close()
	}
}

func (client *MCPClient) Retry(ctx context.Context) {
	client.mu.RLock()
	connected := client.session != nil
	client.mu.RUnlock()
	if connected {
		return
	}
	if !client.retrying.CompareAndSwap(false, true) {
		return
	}

	go func() {
		defer client.retrying.Store(false)
		for {
			session, err := client.SDKClient.Connect(ctx, client.Transport, nil)
			if err == nil {
				client.mu.Lock()
				oldSession := client.session
				client.session = session
				client.tools = nil
				client.mu.Unlock()
				if oldSession != nil && oldSession != session {
					_ = oldSession.Close()
				}
				return
			}
			timer := time.NewTimer(DEFAULT_RETRY_TIME)
			select {
			case <-ctx.Done():
				timer.Stop()
				return
			case <-timer.C:
			}
		}
	}()
}

func (client *MCPClient) IsRetrying() bool {
	return client.retrying.Load()
}

func (client *MCPClient) Tools(ctx context.Context) ([]mcp_sdk.Tool, error) {
	client.mu.RLock()
	session := client.session
	if client.tools != nil {
		result := append([]mcp_sdk.Tool(nil), client.tools...)
		client.mu.RUnlock()
		return result, nil
	}
	client.mu.RUnlock()
	if session == nil {
		return nil, ErrNoToolsAvailable
	}

	tools := session.Tools(ctx, nil)
	result := make([]mcp_sdk.Tool, 0)
	for tool, err := range tools {
		if err == nil {
			result = append(result, *tool)
		}
	}
	if len(result) == 0 {
		return nil, ErrNoToolsAvailable
	}
	client.mu.Lock()
	if client.session == session {
		client.tools = append([]mcp_sdk.Tool(nil), result...)
	}
	client.mu.Unlock()
	return append([]mcp_sdk.Tool(nil), result...), nil
}

func (client *MCPClient) CallTool(ctx context.Context, toolName string, args map[string]any) (string, error) {
	if tools, _ := client.Tools(ctx); len(tools) == 0 {
		return "", ErrNoToolsAvailable
	}
	client.mu.RLock()
	session := client.session
	client.mu.RUnlock()
	if session == nil {
		return "", ErrNoToolsAvailable
	}

	params := mcp_sdk.CallToolParams{
		Name:      toolName,
		Arguments: args,
	}
	callResult, err := session.CallTool(ctx, &params)
	if err != nil {
		client.mu.Lock()
		if client.session == session {
			client.session = nil
		}
		client.tools = nil
		client.mu.Unlock()
		_ = session.Close()
		client.Retry(ctx)
		return "", err
	}
	if callResult.IsError {
		var messages []string
		for _, content := range callResult.Content {
			if textContent, ok := content.(*mcp_sdk.TextContent); ok && strings.TrimSpace(textContent.Text) != "" {
				messages = append(messages, strings.TrimSpace(textContent.Text))
			}
		}
		if len(messages) == 0 {
			return "", errors.New("MCP tool returned an error result")
		}
		return "", fmt.Errorf("MCP tool returned an error result: %s", strings.Join(messages, "; "))
	}
	// Tools registered with AddTool expose the typed payload here. Prefer it
	// over concatenating display-oriented Content blocks: the executor and FPT
	// evidence ledger need exactly one valid JSON object per tool call.
	if callResult.StructuredContent != nil {
		encoded, marshalErr := json.Marshal(callResult.StructuredContent)
		if marshalErr != nil {
			return "", fmt.Errorf("marshal structured tool content: %w", marshalErr)
		}
		return string(encoded), nil
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

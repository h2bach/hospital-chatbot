package llm

import (
	"context"
	"fmt"
	"strings"
	"sync/atomic"

	"agent/internal/agent"
	"agent/internal/domain"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
	"google.golang.org/genai"
)

type GeminiClient struct {
	GeminiAPIKey string
	keys         []string
	clients      []*genai.Client
	nextKey      atomic.Uint64
}

func parseAPIKeys(value string) []string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return r == ',' || r == ';' || r == '\n' || r == '\r'
	})
	keys := make([]string, 0, len(parts))
	seen := make(map[string]struct{}, len(parts))
	for _, part := range parts {
		key := strings.Trim(strings.TrimSpace(part), "\"'")
		if key == "" {
			continue
		}
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		keys = append(keys, key)
	}
	return keys
}

// NewGeminiClient accepts one key or a comma/newline-separated key list.
// Calls rotate round-robin and fail over to the remaining keys on errors.
func NewGeminiClient(ctx context.Context, apiKeys string) (*GeminiClient, error) {
	keys := parseAPIKeys(apiKeys)
	if len(keys) == 0 {
		return nil, fmt.Errorf("no Gemini API keys configured")
	}
	clients := make([]*genai.Client, 0, len(keys))
	for _, key := range keys {
		client, err := genai.NewClient(ctx, &genai.ClientConfig{APIKey: key})
		if err != nil {
			return nil, fmt.Errorf("initialize Gemini client: %w", err)
		}
		clients = append(clients, client)
	}
	return &GeminiClient{GeminiAPIKey: keys[0], keys: keys, clients: clients}, nil
}

func (client *GeminiClient) Chat(ctx context.Context, agentContext domain.Context) (*agent.LLMOutput, error) {
	contents := []*genai.Content{}
	for _, message := range agentContext.Messages {
		// Gemini does not have role "tool", so switch role to "user",
		// and indicates that the text is tool output
		if message.Role == domain.ToolRole {
			message.Role = domain.UserRole
			message.Content = "Tool output: " + message.Content
		}
		contents = append(
			contents,
			&genai.Content{
				Role: string(message.Role),
				Parts: []*genai.Part{
					{Text: message.Content},
				},
			},
		)
	}

	start := client.nextKey.Add(1) - 1
	var lastErr error
	for offset := range client.clients {
		index := (start + uint64(offset)) % uint64(len(client.clients))
		chatResult, err := client.clients[index].Models.GenerateContent(ctx, "gemini-3.5-flash", contents, &genai.GenerateContentConfig{
			Tools: toolListAdapter(agentContext.Tools),
		})
		if err != nil {
			lastErr = err
			continue
		}
		if chatResult == nil || len(chatResult.Candidates) == 0 || chatResult.Candidates[0] == nil || chatResult.Candidates[0].Content == nil {
			lastErr = fmt.Errorf("gemini returned no answer content")
			continue
		}
		result := agent.LLMOutput{}
		for _, part := range chatResult.Candidates[0].Content.Parts {
			switch {
			case part.Text != "":
				result.Text = part.Text
			case part.FunctionCall != nil:
				result.ToolName = part.FunctionCall.Name
				result.Args = part.FunctionCall.Args
			}
		}
		return &result, nil
	}
	return nil, fmt.Errorf("all Gemini API keys failed: %w", lastErr)
}

func toolListAdapter(tools []mcp_sdk.Tool) []*genai.Tool {
	fnDecls := []*genai.FunctionDeclaration{}
	for _, tool := range tools {
		fnDecl := genai.FunctionDeclaration{
			Name:                 tool.Name,
			Description:          tool.Description,
			ParametersJsonSchema: tool.InputSchema,
		}
		fnDecls = append(fnDecls, &fnDecl)
	}

	result := []*genai.Tool{{FunctionDeclarations: fnDecls}}
	return result
}

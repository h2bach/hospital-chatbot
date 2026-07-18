package llm

import (
	"context"
	"encoding/json"
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
	Model        string
	keys         []string
	clients      []*genai.Client
	nextKey      atomic.Uint64
}

const defaultGeminiModel = "gemini-3.5-flash"

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
	return NewGeminiClientWithModel(ctx, apiKeys, defaultGeminiModel)
}

func NewGeminiClientWithModel(ctx context.Context, apiKeys, model string) (*GeminiClient, error) {
	keys := parseAPIKeys(apiKeys)
	if len(keys) == 0 {
		return nil, fmt.Errorf("no Gemini API keys configured")
	}
	model = strings.TrimSpace(model)
	if model == "" {
		model = defaultGeminiModel
	}
	clients := make([]*genai.Client, 0, len(keys))
	for _, key := range keys {
		client, err := genai.NewClient(ctx, &genai.ClientConfig{APIKey: key})
		if err != nil {
			return nil, fmt.Errorf("initialize Gemini client: %w", err)
		}
		clients = append(clients, client)
	}
	return &GeminiClient{GeminiAPIKey: keys[0], Model: model, keys: keys, clients: clients}, nil
}

func (client *GeminiClient) Chat(ctx context.Context, agentContext domain.Context) (*agent.LLMOutput, error) {
	contents := []*genai.Content{}
	var systemInstruction *genai.Content
	pendingToolName := ""
	pendingToolID := ""
	toolCallNumber := 0
	for _, message := range agentContext.Messages {
		switch message.Role {
		case domain.SystemRole:
			systemInstruction = &genai.Content{Parts: []*genai.Part{{Text: message.Content}}}
		case domain.AgentRole:
			if strings.HasPrefix(message.Content, "Tool Call: ") {
				name, args := parseGeminiToolCall(message.Content)
				toolCallNumber++
				pendingToolName = name
				pendingToolID = fmt.Sprintf("tool-call-%d", toolCallNumber)
				contents = append(contents, &genai.Content{
					Role:  "model",
					Parts: []*genai.Part{{FunctionCall: &genai.FunctionCall{ID: pendingToolID, Name: name, Args: args}}},
				})
				continue
			}
			contents = append(contents, &genai.Content{Role: "model", Parts: []*genai.Part{{Text: message.Content}}})
		case domain.ToolRole:
			response := map[string]any{"output": message.Content}
			contents = append(contents, &genai.Content{
				Role: "user",
				Parts: []*genai.Part{{FunctionResponse: &genai.FunctionResponse{
					ID: pendingToolID, Name: pendingToolName, Response: response,
				}}},
			})
			pendingToolName = ""
			pendingToolID = ""
		default:
			contents = append(contents, &genai.Content{Role: "user", Parts: []*genai.Part{{Text: message.Content}}})
		}
	}

	start := client.nextKey.Add(1) - 1
	var lastErr error
	for offset := range client.clients {
		index := (start + uint64(offset)) % uint64(len(client.clients))
		chatResult, err := client.clients[index].Models.GenerateContent(ctx, client.Model, contents, &genai.GenerateContentConfig{
			Tools:             toolListAdapter(agentContext.Tools),
			SystemInstruction: systemInstruction,
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

func parseGeminiToolCall(content string) (string, map[string]any) {
	lines := strings.SplitN(content, "\n", 2)
	name := strings.TrimSpace(strings.TrimPrefix(lines[0], "Tool Call: "))
	args := map[string]any{}
	if len(lines) == 2 {
		encoded := strings.TrimSpace(strings.TrimPrefix(lines[1], "Args: "))
		_ = json.Unmarshal([]byte(encoded), &args)
	}
	return name, args
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

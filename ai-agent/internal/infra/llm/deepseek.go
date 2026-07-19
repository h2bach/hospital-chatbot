package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"sync/atomic"

	"agent/internal/agent"
	"agent/internal/domain"
)

const (
	defaultDeepSeekBaseURL = "https://api.deepseek.com"
	defaultDeepSeekModel   = "deepseek-chat"
)

// DeepSeekClient implements agent.LLMClient using the DeepSeek API.
// The DeepSeek API is OpenAI-compatible, so requests follow the
// /chat/completions format described at https://api-docs.deepseek.com/.
type DeepSeekClient struct {
	BaseURL  string
	Model    string
	Thinking string
	keys     []string
	nextKey  atomic.Uint64
	http     *http.Client
}

// NewDeepSeekClient creates a new DeepSeek client with the default model.
func NewDeepSeekClient(apiKeys string) (*DeepSeekClient, error) {
	return NewDeepSeekClientWithModel(apiKeys, "", "")
}

// NewDeepSeekClientWithModel creates a new DeepSeek client with a specific model
// and optional base URL override. If model or baseURL are empty, defaults apply.
func NewDeepSeekClientWithModel(apiKeys, model, baseURL string) (*DeepSeekClient, error) {
	keys := parseAPIKeys(apiKeys)
	if len(keys) == 0 {
		return nil, fmt.Errorf("no DeepSeek API keys configured")
	}
	model = strings.TrimSpace(model)
	if model == "" {
		model = defaultDeepSeekModel
	}
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/");
	if baseURL == "" {
		baseURL = defaultDeepSeekBaseURL
	}
	thinking := strings.TrimSpace(os.Getenv("DEEPSEEK_THINKING"))
	return &DeepSeekClient{
		BaseURL:  baseURL,
		Model:    model,
		Thinking: thinking,
		keys:     keys,
		http:     &http.Client{},
	}, nil
}

// --- Request / Response types (OpenAI-compatible) ---

type deepseekThinking struct {
	Type string `json:"type"`
}

type deepseekChatRequest struct {
	Model       string                `json:"model"`
	Messages    []deepseekMessage     `json:"messages"`
	Temperature float32               `json:"temperature,omitempty"`
	MaxTokens   int                   `json:"max_tokens,omitempty"`
	Tools       []deepseekToolWrapper `json:"tools,omitempty"`
	ToolChoice  string                `json:"tool_choice,omitempty"`
	Thinking    *deepseekThinking     `json:"thinking,omitempty"`
	Stream      bool                  `json:"stream"`
}

type deepseekMessage struct {
	Role             string             `json:"role"`
	Content          string             `json:"content,omitempty"`
	ReasoningContent *string            `json:"reasoning_content,omitempty"`
	ToolCalls        []deepseekToolCall `json:"tool_calls,omitempty"`
	ToolCallID       string             `json:"tool_call_id,omitempty"`
}

type deepseekToolWrapper struct {
	Type     string           `json:"type"`
	Function deepseekFunction `json:"function"`
}

type deepseekFunction struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	Parameters  any    `json:"parameters,omitempty"`
}

type deepseekToolCall struct {
	ID       string             `json:"id,omitempty"`
	Type     string             `json:"type,omitempty"`
	Function deepseekToolCallFn `json:"function"`
}

type deepseekToolCallFn struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}

type deepseekChatResponse struct {
	Choices []struct {
		Message deepseekMessage `json:"message"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
		Type    string `json:"type"`
	} `json:"error,omitempty"`
}

// Chat sends a chat completion request to the DeepSeek API, rotating across
// configured API keys and failing over when a key returns an error.
func (client *DeepSeekClient) Chat(ctx context.Context, agentContext domain.Context) (*agent.LLMOutput, error) {
	messages := make([]deepseekMessage, 0, len(agentContext.Messages))
	pendingToolCallID := ""
	toolCallNumber := 0

	for _, message := range agentContext.Messages {
		content := message.Content
		switch message.Role {
		case domain.SystemRole:
			messages = append(messages, deepseekMessage{Role: "system", Content: content})
		case domain.UserRole:
			messages = append(messages, deepseekMessage{Role: "user", Content: content})
		case domain.AgentRole:
			reasoningContent := message.ReasoningContent
			if strings.HasPrefix(message.Content, "Tool Call: ") {
				name, args := parseDeepSeekToolCall(message.Content)
				toolCallNumber++
				pendingToolCallID = fmt.Sprintf("call_%d", toolCallNumber)
				messages = append(messages, deepseekMessage{
					Role:             "assistant",
					ReasoningContent: &reasoningContent,
					ToolCalls: []deepseekToolCall{{
						ID:   pendingToolCallID,
						Type: "function",
						Function: deepseekToolCallFn{
							Name:      name,
							Arguments: args,
						},
					}},
				})
				continue
			}
			messages = append(messages, deepseekMessage{
				Role:             "assistant",
				Content:          content,
				ReasoningContent: &reasoningContent,
			})
		case domain.ToolRole:
			if pendingToolCallID != "" {
				messages = append(messages, deepseekMessage{
					Role:       "tool",
					Content:    content,
					ToolCallID: pendingToolCallID,
				})
				pendingToolCallID = ""
				continue
			}
			messages = append(messages, deepseekMessage{Role: "tool", Content: content})
		}
	}

	// Build tools list
	tools := make([]deepseekToolWrapper, 0, len(agentContext.Tools))
	for _, tool := range agentContext.Tools {
		tools = append(tools, deepseekToolWrapper{
			Type: "function",
			Function: deepseekFunction{
				Name:        tool.Name,
				Description: tool.Description,
				Parameters:  tool.InputSchema,
			},
		})
	}

	requestBody := deepseekChatRequest{
		Model:       client.Model,
		Messages:    messages,
		Temperature: 0.3,
		MaxTokens:   8192,
		Tools:       tools,
		Stream:      false,
	}
	if client.Thinking != "" {
		requestBody.Thinking = &deepseekThinking{Type: client.Thinking}
	}
	if len(tools) > 0 {
		requestBody.ToolChoice = "auto"
	}

	body, err := json.Marshal(requestBody)
	if err != nil {
		return nil, fmt.Errorf("encode DeepSeek request: %w", err)
	}

	// Round-robin key rotation with failover
	start := client.nextKey.Add(1) - 1
	var lastErr error
	for offset := range client.keys {
		index := (start + uint64(offset)) % uint64(len(client.keys))
		result, err := client.doRequest(ctx, client.keys[index], body)
		if err == nil {
			return result, nil
		}
		lastErr = err
	}
	return nil, fmt.Errorf("all DeepSeek API keys failed: %w", lastErr)
}

func (client *DeepSeekClient) doRequest(ctx context.Context, key string, body []byte) (*agent.LLMOutput, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, client.BaseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create DeepSeek request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("call DeepSeek API: %w", err)
	}
	defer resp.Body.Close()
	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read DeepSeek response: %w", err)
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("DeepSeek API returned HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(responseBody)))
	}

	var response deepseekChatResponse
	if err := json.Unmarshal(responseBody, &response); err != nil {
		return nil, fmt.Errorf("decode DeepSeek response: %w", err)
	}
	if response.Error != nil {
		return nil, fmt.Errorf("DeepSeek API error [%s]: %s", response.Error.Type, response.Error.Message)
	}
	if len(response.Choices) == 0 {
		return nil, fmt.Errorf("DeepSeek returned no choices")
	}

	message := response.Choices[0].Message
	reasoningContent := ""
	if message.ReasoningContent != nil {
		reasoningContent = *message.ReasoningContent
	}

	if len(message.ToolCalls) > 0 {
		call := message.ToolCalls[0]
		args := map[string]any{}
		if call.Function.Arguments != "" {
			if err := json.Unmarshal([]byte(call.Function.Arguments), &args); err != nil {
				return nil, fmt.Errorf("decode DeepSeek tool arguments: %w", err)
			}
		}
		return &agent.LLMOutput{
			ToolName:         call.Function.Name,
			Args:             args,
			ReasoningContent: reasoningContent,
		}, nil
	}

	text := strings.TrimSpace(message.Content)
	if text == "" {
		return nil, fmt.Errorf("DeepSeek returned an empty answer")
	}
	return &agent.LLMOutput{
		Text:             text,
		ReasoningContent: reasoningContent,
	}, nil
}

func parseDeepSeekToolCall(content string) (string, string) {
	lines := strings.SplitN(content, "\n", 2)
	name := strings.TrimSpace(strings.TrimPrefix(lines[0], "Tool Call: "))
	args := "{}"
	if len(lines) == 2 {
		args = strings.TrimSpace(strings.TrimPrefix(lines[1], "Args: "))
	}
	if args == "" {
		args = "{}"
	}
	return name, args
}

var _ agent.LLMClient = (*DeepSeekClient)(nil)

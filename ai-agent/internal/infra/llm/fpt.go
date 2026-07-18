package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strings"
	"sync/atomic"
	"time"

	"agent/internal/agent"
	"agent/internal/domain"
)

const (
	defaultFPTBaseURL     = "https://mkp-api.fptcloud.com"
	defaultFPTTemperature = float32(0.3)
	defaultFPTHTTPTimeout = 60 * time.Second
	maxFPTResponseBytes   = 4 << 20
	maxFPTErrorTextBytes  = 1024
)

type FPTClient struct {
	BaseURL string
	Model   string
	keys    []string
	nextKey atomic.Uint64
	http    *http.Client
}

func NewFPTClient(apiKeys, model, baseURL string) (*FPTClient, error) {
	keys := parseAPIKeys(apiKeys)
	if len(keys) == 0 {
		return nil, fmt.Errorf("no FPT API keys configured")
	}
	model = strings.TrimSpace(model)
	if model == "" {
		return nil, fmt.Errorf("no FPT model configured")
	}
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if baseURL == "" {
		baseURL = defaultFPTBaseURL
	}
	parsedBaseURL, err := url.Parse(baseURL)
	if err != nil || (parsedBaseURL.Scheme != "http" && parsedBaseURL.Scheme != "https") || parsedBaseURL.Host == "" {
		return nil, fmt.Errorf("invalid FPT base URL %q", baseURL)
	}
	if parsedBaseURL.RawQuery != "" || parsedBaseURL.Fragment != "" {
		return nil, fmt.Errorf("invalid FPT base URL %q: query and fragment are not allowed", baseURL)
	}
	return &FPTClient{
		BaseURL: baseURL,
		Model:   model,
		keys:    keys,
		http:    &http.Client{Timeout: defaultFPTHTTPTimeout},
	}, nil
}

type fptChatRequest struct {
	Model       string           `json:"model"`
	Messages    []fptMessage     `json:"messages"`
	Temperature float32          `json:"temperature"`
	Tools       []fptToolWrapper `json:"tools,omitempty"`
}

type fptMessage struct {
	Role       string        `json:"role"`
	Content    string        `json:"content"`
	ToolCalls  []fptToolCall `json:"tool_calls,omitempty"`
	ToolCallID string        `json:"tool_call_id,omitempty"`
}

type fptToolWrapper struct {
	Type     string      `json:"type"`
	Function fptFunction `json:"function"`
}

type fptFunction struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	Parameters  any    `json:"parameters,omitempty"`
}

type fptToolCall struct {
	ID       string        `json:"id,omitempty"`
	Type     string        `json:"type,omitempty"`
	Function fptToolCallFn `json:"function"`
}

type fptToolCallFn struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}

type fptChatResponse struct {
	Choices []struct {
		Message      fptMessage `json:"message"`
		FinishReason string     `json:"finish_reason"`
	} `json:"choices"`
}

type fptErrorResponse struct {
	Error struct {
		Message string `json:"message"`
		Type    string `json:"type"`
		Code    any    `json:"code"`
	} `json:"error"`
}

func (client *FPTClient) Chat(ctx context.Context, agentContext domain.Context) (*agent.LLMOutput, error) {
	if client == nil || client.http == nil {
		return nil, fmt.Errorf("FPT client is not initialized")
	}
	temperature := defaultFPTTemperature
	if agentContext.Deterministic {
		temperature = 0
	}
	if math.IsNaN(float64(temperature)) || math.IsInf(float64(temperature), 0) || temperature < 0 || temperature > 2 {
		return nil, fmt.Errorf("invalid FPT temperature %.3f", temperature)
	}

	messages := make([]fptMessage, 0, len(agentContext.Messages))
	pendingToolCallID := ""
	toolCallNumber := 0
	for _, message := range agentContext.Messages {
		role := strings.ToLower(string(message.Role))
		content := message.Content
		switch message.Role {
		case domain.SystemRole:
			role = "system"
		case domain.UserRole:
			role = "user"
		case domain.AgentRole:
			role = "assistant"
			if strings.HasPrefix(message.Content, "Tool Call: ") {
				name, args := parseToolCallMessage(message.Content)
				toolCallNumber++
				pendingToolCallID = fmt.Sprintf("tool-call-%d", toolCallNumber)
				messages = append(messages, fptMessage{
					Role: "assistant",
					ToolCalls: []fptToolCall{{
						ID:   pendingToolCallID,
						Type: "function",
						Function: fptToolCallFn{
							Name:      name,
							Arguments: args,
						},
					}},
				})
				continue
			}
		case domain.ToolRole:
			role = "tool"
			if pendingToolCallID != "" {
				messages = append(messages, fptMessage{Role: role, Content: content, ToolCallID: pendingToolCallID})
				pendingToolCallID = ""
				continue
			}
		}
		messages = append(messages, fptMessage{Role: role, Content: content})
	}

	tools := make([]fptToolWrapper, 0, len(agentContext.Tools))
	for _, tool := range agentContext.Tools {
		tools = append(tools, fptToolWrapper{
			Type: "function",
			Function: fptFunction{
				Name:        tool.Name,
				Description: tool.Description,
				Parameters:  tool.InputSchema,
			},
		})
	}
	requestBody := fptChatRequest{
		Model:       client.Model,
		Messages:    messages,
		Temperature: temperature,
		Tools:       tools,
	}
	body, err := json.Marshal(requestBody)
	if err != nil {
		return nil, fmt.Errorf("encode FPT request: %w", err)
	}

	start := client.nextKey.Add(1) - 1
	var lastErr error
	for offset := range client.keys {
		if err := ctx.Err(); err != nil {
			return nil, fmt.Errorf("FPT inference canceled: %w", err)
		}
		index := (start + uint64(offset)) % uint64(len(client.keys))
		result, err := client.request(ctx, client.keys[index], body)
		if err == nil {
			return result, nil
		}
		lastErr = err
	}
	return nil, fmt.Errorf("all FPT API keys failed: %w", lastErr)
}

func parseToolCallMessage(content string) (string, string) {
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

func (client *FPTClient) request(ctx context.Context, key string, body []byte) (*agent.LLMOutput, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, client.BaseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create FPT request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("call FPT inference: %w", err)
	}
	defer resp.Body.Close()
	responseBody, err := readLimitedResponse(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read FPT response: %w", err)
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return nil, fptHTTPStatusError(resp.StatusCode, resp.Header.Get("X-Request-Id"), responseBody)
	}

	var response fptChatResponse
	if err := json.Unmarshal(responseBody, &response); err != nil {
		return nil, fmt.Errorf("decode FPT response: %w", err)
	}
	if len(response.Choices) == 0 {
		return nil, fmt.Errorf("FPT returned no choices")
	}
	if len(response.Choices) > 1 {
		return nil, fmt.Errorf("FPT returned %d choices; exactly one is required", len(response.Choices))
	}
	choice := response.Choices[0]
	switch strings.ToLower(strings.TrimSpace(choice.FinishReason)) {
	case "length":
		return nil, fmt.Errorf("FPT response was truncated because the token limit was reached")
	case "content_filter":
		return nil, fmt.Errorf("FPT response was blocked by the provider content filter")
	}
	message := choice.Message
	if len(message.ToolCalls) > 0 {
		if len(message.ToolCalls) > 1 {
			return nil, fmt.Errorf("FPT returned %d tool calls; this agent supports one per turn", len(message.ToolCalls))
		}
		call := message.ToolCalls[0]
		if strings.TrimSpace(call.Function.Name) == "" {
			return nil, fmt.Errorf("FPT returned a tool call without a function name")
		}
		args := map[string]any{}
		if call.Function.Arguments != "" {
			if err := json.Unmarshal([]byte(call.Function.Arguments), &args); err != nil {
				return nil, fmt.Errorf("decode FPT tool arguments: %w", err)
			}
			if args == nil {
				return nil, fmt.Errorf("decode FPT tool arguments: expected a JSON object")
			}
		}
		return &agent.LLMOutput{ToolName: call.Function.Name, Args: args}, nil
	}
	if strings.TrimSpace(message.Content) == "" {
		return nil, fmt.Errorf("FPT returned an empty answer")
	}
	return &agent.LLMOutput{Text: message.Content}, nil
}

func readLimitedResponse(reader io.Reader) ([]byte, error) {
	limited := io.LimitReader(reader, maxFPTResponseBytes+1)
	body, err := io.ReadAll(limited)
	if err != nil {
		return nil, err
	}
	if len(body) > maxFPTResponseBytes {
		return nil, fmt.Errorf("response body exceeds %d bytes", maxFPTResponseBytes)
	}
	return body, nil
}

func fptHTTPStatusError(status int, requestID string, body []byte) error {
	detail := ""
	var providerError fptErrorResponse
	if json.Unmarshal(body, &providerError) == nil {
		detail = strings.TrimSpace(providerError.Error.Message)
	}
	if detail == "" {
		detail = strings.TrimSpace(string(body))
	}
	detail = strings.Join(strings.Fields(detail), " ")
	if len(detail) > maxFPTErrorTextBytes {
		detail = detail[:maxFPTErrorTextBytes] + "..."
	}
	requestID = strings.TrimSpace(requestID)
	if requestID != "" && detail != "" {
		return fmt.Errorf("FPT inference returned HTTP %d (request %s): %s", status, requestID, detail)
	}
	if requestID != "" {
		return fmt.Errorf("FPT inference returned HTTP %d (request %s)", status, requestID)
	}
	if detail != "" {
		return fmt.Errorf("FPT inference returned HTTP %d: %s", status, detail)
	}
	return fmt.Errorf("FPT inference returned HTTP %d", status)
}

var _ agent.LLMClient = (*FPTClient)(nil)

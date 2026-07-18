package llm

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
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
	BaseURL  string
	Model    string
	VLMModel string
	keys     []string
	nextKey  atomic.Uint64
	http     *http.Client
}

type FPTSpeechToText struct {
	BaseURL string
	Model   string
	keys    []string
	http    *http.Client
}

func NewFPTSpeechToTextFromEnvironment() (*FPTSpeechToText, error) {
	model := strings.TrimSpace(os.Getenv("FPT_STT_MODEL"))
	if model == "" {
		return nil, nil
	}
	keys := parseAPIKeys(os.Getenv("FPT_API_KEYS"))
	if len(keys) == 0 {
		keys = parseAPIKeys(os.Getenv("FPT_API_KEY"))
	}
	if len(keys) == 0 {
		return nil, fmt.Errorf("FPT_STT_MODEL is configured but no FPT API key is configured")
	}
	baseURL, err := normalizeFPTBaseURL(os.Getenv("FPT_BASE_URL"))
	if err != nil {
		return nil, err
	}
	return &FPTSpeechToText{BaseURL: baseURL, Model: model, keys: keys, http: &http.Client{Timeout: defaultFPTHTTPTimeout}}, nil
}

func (client *FPTSpeechToText) Transcribe(ctx context.Context, filename, contentType string, audio []byte) (string, error) {
	var lastErr error
	for _, key := range client.keys {
		text, err := client.transcribeWithKey(ctx, key, filename, contentType, audio)
		if err == nil {
			return text, nil
		}
		lastErr = err
	}
	return "", fmt.Errorf("all FPT STT API keys failed: %w", lastErr)
}

func (client *FPTSpeechToText) transcribeWithKey(ctx context.Context, key, filename, contentType string, audio []byte) (string, error) {
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("file", filename)
	if err != nil {
		return "", fmt.Errorf("create audio form: %w", err)
	}
	if _, err := part.Write(audio); err != nil {
		return "", fmt.Errorf("encode audio form: %w", err)
	}
	_ = writer.WriteField("model", client.Model)
	_ = writer.WriteField("response_format", "json")
	_ = writer.WriteField("language", "vi")
	if err := writer.Close(); err != nil {
		return "", fmt.Errorf("close audio form: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, client.BaseURL+"/audio/transcriptions", &body)
	if err != nil {
		return "", fmt.Errorf("create FPT STT request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	if contentType != "" {
		req.Header.Set("X-Audio-Content-Type", contentType)
	}
	resp, err := client.http.Do(req)
	if err != nil {
		return "", fmt.Errorf("call FPT STT: %w", err)
	}
	defer resp.Body.Close()
	responseBody, err := readLimitedResponse(resp.Body)
	if err != nil {
		return "", fmt.Errorf("read FPT STT response: %w", err)
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return "", fmt.Errorf("FPT STT returned HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(responseBody)))
	}
	var response struct {
		Text       string `json:"text"`
		Transcript string `json:"transcript"`
		Hypotheses []struct {
			Utterance string `json:"utterance"`
		} `json:"hypotheses"`
	}
	if err := json.Unmarshal(responseBody, &response); err != nil {
		return "", fmt.Errorf("decode FPT STT response: %w", err)
	}
	text := strings.TrimSpace(response.Text)
	if text == "" {
		text = strings.TrimSpace(response.Transcript)
	}
	if text == "" && len(response.Hypotheses) > 0 {
		text = strings.TrimSpace(response.Hypotheses[0].Utterance)
	}
	if text == "" {
		return "", fmt.Errorf("FPT STT returned empty text")
	}
	return text, nil
}

func NewFPTClient(apiKeys, model, baseURL string) (*FPTClient, error) {
	return NewFPTClientWithVLM(apiKeys, model, "", baseURL)
}

func NewFPTClientWithVLM(apiKeys, model, vlmModel, baseURL string) (*FPTClient, error) {
	keys := parseAPIKeys(apiKeys)
	if len(keys) == 0 {
		return nil, fmt.Errorf("no FPT API keys configured")
	}
	model = strings.TrimSpace(model)
	if model == "" {
		return nil, fmt.Errorf("no FPT model configured")
	}
	baseURL, err := normalizeFPTBaseURL(baseURL)
	if err != nil {
		return nil, err
	}
	return &FPTClient{
		BaseURL:  baseURL,
		Model:    model,
		VLMModel: strings.TrimSpace(vlmModel),
		keys:     keys,
		http:     &http.Client{Timeout: defaultFPTHTTPTimeout},
	}, nil
}

func normalizeFPTBaseURL(raw string) (string, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(raw), "/")
	if baseURL == "" {
		baseURL = defaultFPTBaseURL
	}
	parsed, err := url.Parse(baseURL)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		return "", fmt.Errorf("invalid FPT base URL %q", baseURL)
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", fmt.Errorf("invalid FPT base URL %q: query and fragment are not allowed", baseURL)
	}
	return baseURL, nil
}

type fptChatRequest struct {
	Model       string           `json:"model"`
	Messages    []fptMessage     `json:"messages"`
	Temperature float32          `json:"temperature"`
	Tools       []fptToolWrapper `json:"tools,omitempty"`
}

type fptMessage struct {
	Role       string        `json:"role"`
	Content    any           `json:"content"`
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
	requestModel := client.Model
	pendingToolCallID := ""
	toolCallNumber := 0
	for _, message := range agentContext.Messages {
		role := strings.ToLower(string(message.Role))
		content := message.Content
		var messageContent any = content
		if len(message.Images) > 0 {
			if client.VLMModel == "" {
				return nil, fmt.Errorf("FPT_VLM_MODEL is required for image messages; FPT_MODEL %q is text-only", client.Model)
			}
			requestModel = client.VLMModel
			if len(message.Images) > 2 {
				return nil, fmt.Errorf("FPT VLM supports at most 2 images")
			}
			parts := make([]fptContentPart, 0, len(message.Images)+1)
			if strings.TrimSpace(content) != "" {
				parts = append(parts, fptContentPart{Type: "text", Text: content})
			}
			for _, image := range message.Images {
				if image.MIMEType != "image/jpeg" && image.MIMEType != "image/png" {
					return nil, fmt.Errorf("FPT VLM supports only JPEG and PNG images")
				}
				parts = append(parts, fptContentPart{
					Type:     "image_url",
					ImageURL: &fptImageURL{URL: "data:" + image.MIMEType + ";base64," + base64.StdEncoding.EncodeToString(image.Data)},
				})
			}
			messageContent = parts
		}
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
		messages = append(messages, fptMessage{Role: role, Content: messageContent})
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
		Model:       requestModel,
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

type fptContentPart struct {
	Type     string       `json:"type"`
	Text     string       `json:"text,omitempty"`
	ImageURL *fptImageURL `json:"image_url,omitempty"`
}

type fptImageURL struct {
	URL string `json:"url"`
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
			return nil, fmt.Errorf("FPT returned %d tool calls; this adapter accepts one per model turn", len(message.ToolCalls))
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
	text, ok := message.Content.(string)
	if !ok || strings.TrimSpace(text) == "" {
		return nil, fmt.Errorf("FPT returned an empty answer")
	}
	return &agent.LLMOutput{Text: text}, nil
}

func readLimitedResponse(reader io.Reader) ([]byte, error) {
	body, err := io.ReadAll(io.LimitReader(reader, maxFPTResponseBytes+1))
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

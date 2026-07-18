package llm

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"agent/internal/domain"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestDeepSeekChat_TextResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer test-key" {
			t.Errorf("unexpected Authorization header: %s", r.Header.Get("Authorization"))
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("unexpected Content-Type: %s", r.Header.Get("Content-Type"))
		}

		var req deepseekChatRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if req.Model != "deepseek-chat" {
			t.Errorf("model = %q, want deepseek-chat", req.Model)
		}
		if req.Stream {
			t.Error("stream should be false")
		}

		resp := deepseekChatResponse{
			Choices: []struct {
				Message deepseekMessage `json:"message"`
			}{
				{Message: deepseekMessage{Role: "assistant", Content: "Xin chào!"}},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client, err := NewDeepSeekClientWithModel("test-key", "deepseek-chat", server.URL)
	if err != nil {
		t.Fatalf("NewDeepSeekClientWithModel() error = %v", err)
	}

	output, err := client.Chat(context.Background(), domain.Context{
		Messages: []domain.Message{
			{Role: domain.SystemRole, Content: "You are a helpful assistant."},
			{Role: domain.UserRole, Content: "Xin chào"},
		},
	})
	if err != nil {
		t.Fatalf("Chat() error = %v", err)
	}
	if output.Text != "Xin chào!" {
		t.Errorf("Chat() text = %q, want %q", output.Text, "Xin chào!")
	}
}

func TestDeepSeekChat_ToolCallResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := deepseekChatResponse{
			Choices: []struct {
				Message deepseekMessage `json:"message"`
			}{
				{Message: deepseekMessage{
					Role: "assistant",
					ToolCalls: []deepseekToolCall{{
						ID:   "call_1",
						Type: "function",
						Function: deepseekToolCallFn{
							Name:      "getHospitalInfo",
							Arguments: `{"query":"Tim Hà Nội"}`,
						},
					}},
				}},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client, err := NewDeepSeekClientWithModel("test-key", "", server.URL)
	if err != nil {
		t.Fatalf("NewDeepSeekClientWithModel() error = %v", err)
	}

	output, err := client.Chat(context.Background(), domain.Context{
		Messages: []domain.Message{
			{Role: domain.UserRole, Content: "Bệnh viện Tim Hà Nội ở đâu?"},
		},
		Tools: []mcp_sdk.Tool{{
			Name:        "getHospitalInfo",
			Description: "Get hospital information",
		}},
	})
	if err != nil {
		t.Fatalf("Chat() error = %v", err)
	}
	if output.ToolName != "getHospitalInfo" {
		t.Errorf("Chat() tool = %q, want getHospitalInfo", output.ToolName)
	}
	if output.Args["query"] != "Tim Hà Nội" {
		t.Errorf("Chat() args = %v, want query=Tim Hà Nội", output.Args)
	}
}

func TestDeepSeekChat_ErrorResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
		w.Write([]byte(`{"error":{"message":"Rate limit reached","type":"rate_limit_error"}}`))
	}))
	defer server.Close()

	client, err := NewDeepSeekClientWithModel("test-key", "", server.URL)
	if err != nil {
		t.Fatalf("NewDeepSeekClientWithModel() error = %v", err)
	}

	_, err = client.Chat(context.Background(), domain.Context{
		Messages: []domain.Message{
			{Role: domain.UserRole, Content: "Hello"},
		},
	})
	if err == nil {
		t.Fatal("Chat() expected error for 429 response")
	}
}

func TestDeepSeekChat_KeyRotation(t *testing.T) {
	var receivedKeys []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedKeys = append(receivedKeys, r.Header.Get("Authorization"))
		resp := deepseekChatResponse{
			Choices: []struct {
				Message deepseekMessage `json:"message"`
			}{
				{Message: deepseekMessage{Role: "assistant", Content: "ok"}},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client, err := NewDeepSeekClientWithModel("key1,key2", "", server.URL)
	if err != nil {
		t.Fatalf("NewDeepSeekClientWithModel() error = %v", err)
	}

	ctx := context.Background()
	msgCtx := domain.Context{Messages: []domain.Message{{Role: domain.UserRole, Content: "a"}}}

	client.Chat(ctx, msgCtx)
	client.Chat(ctx, msgCtx)

	if len(receivedKeys) != 2 {
		t.Fatalf("expected 2 requests, got %d", len(receivedKeys))
	}
	if receivedKeys[0] == receivedKeys[1] {
		t.Error("expected different keys for consecutive requests (round-robin)")
	}
}

func TestNewDeepSeekClient_NoKeys(t *testing.T) {
	_, err := NewDeepSeekClient("")
	if err == nil {
		t.Fatal("expected error for empty keys")
	}
}

func TestNewDeepSeekClient_DefaultModel(t *testing.T) {
	client, err := NewDeepSeekClientWithModel("test-key", "", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if client.Model != defaultDeepSeekModel {
		t.Errorf("Model = %q, want %q", client.Model, defaultDeepSeekModel)
	}
	if client.BaseURL != defaultDeepSeekBaseURL {
		t.Errorf("BaseURL = %q, want %q", client.BaseURL, defaultDeepSeekBaseURL)
	}
}

func TestDeepSeekChat_ReasoningContentPassedBack(t *testing.T) {
	var capturedMessages []deepseekMessage
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req deepseekChatRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		capturedMessages = req.Messages

		resp := deepseekChatResponse{
			Choices: []struct {
				Message deepseekMessage `json:"message"`
			}{
				{Message: deepseekMessage{Role: "assistant", Content: "Done"}},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client, err := NewDeepSeekClientWithModel("test-key", "deepseek-reasoner", server.URL)
	if err != nil {
		t.Fatalf("NewDeepSeekClientWithModel() error = %v", err)
	}

	_, err = client.Chat(context.Background(), domain.Context{
		Messages: []domain.Message{
			{Role: domain.UserRole, Content: "Hello"},
			{
				Role:             domain.AgentRole,
				Content:          "Tool Call: getInfo\nArgs: {}",
				ReasoningContent: "Thinking step 1",
			},
			{Role: domain.ToolRole, Content: "Info result"},
		},
	})
	if err != nil {
		t.Fatalf("Chat() error = %v", err)
	}

	foundAssistant := false
	for _, msg := range capturedMessages {
		if msg.Role == "assistant" {
			foundAssistant = true
			if msg.ReasoningContent == nil {
				t.Errorf("assistant message missing ReasoningContent pointer")
			} else if *msg.ReasoningContent != "Thinking step 1" {
				t.Errorf("assistant ReasoningContent = %q, want %q", *msg.ReasoningContent, "Thinking step 1")
			}
		}
	}
	if !foundAssistant {
		t.Errorf("expected assistant message in captured messages")
	}
}

func TestDeepSeekChat_DisabledThinking(t *testing.T) {
	t.Setenv("DEEPSEEK_THINKING", "disabled")

	var capturedThinking *deepseekThinking
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req deepseekChatRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		capturedThinking = req.Thinking

		resp := deepseekChatResponse{
			Choices: []struct {
				Message deepseekMessage `json:"message"`
			}{
				{Message: deepseekMessage{Role: "assistant", Content: "Hello"}},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client, err := NewDeepSeekClientWithModel("test-key", "deepseek-v4-flash", server.URL)
	if err != nil {
		t.Fatalf("NewDeepSeekClientWithModel() error = %v", err)
	}

	_, err = client.Chat(context.Background(), domain.Context{
		Messages: []domain.Message{
			{Role: domain.UserRole, Content: "Hello"},
		},
	})
	if err != nil {
		t.Fatalf("Chat() error = %v", err)
	}

	if capturedThinking == nil {
		t.Fatal("expected Thinking field in request payload")
	}
	if capturedThinking.Type != "disabled" {
		t.Errorf("Thinking.Type = %q, want %q", capturedThinking.Type, "disabled")
	}
}

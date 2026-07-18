package llm

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"agent/internal/domain"
)

func TestFPTChatUsesDeterministicTemperaturePerCall(t *testing.T) {
	requestBody := make(chan fptChatRequest, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer secret" {
			t.Errorf("Authorization = %q", got)
		}
		var body fptChatRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Errorf("decode request: %v", err)
		}
		requestBody <- body
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"choices":[{"message":{"role":"assistant","content":"grounded"},"finish_reason":"stop"}]}`)
	}))
	defer server.Close()

	client, err := NewFPTClient("secret", " fpt-model ", server.URL)
	if err != nil {
		t.Fatalf("NewFPTClient() error = %v", err)
	}
	output, err := client.Chat(context.Background(), domain.Context{
		Deterministic: true,
		Messages:      []domain.Message{{Role: domain.UserRole, Content: "question"}},
	})
	if err != nil {
		t.Fatalf("Chat() error = %v", err)
	}
	if output.Text != "grounded" {
		t.Fatalf("Chat() text = %q", output.Text)
	}
	body := <-requestBody
	if body.Temperature != 0 {
		t.Fatalf("deterministic temperature = %v, want 0", body.Temperature)
	}
	if body.Model != "fpt-model" {
		t.Fatalf("model = %q, want trimmed model", body.Model)
	}
	if client.http.Timeout != defaultFPTHTTPTimeout {
		t.Fatalf("HTTP timeout = %v, want %v", client.http.Timeout, defaultFPTHTTPTimeout)
	}
}

func TestFPTChatUsesDefaultTemperature(t *testing.T) {
	requestBody := make(chan fptChatRequest, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body fptChatRequest
		_ = json.NewDecoder(r.Body).Decode(&body)
		requestBody <- body
		_, _ = io.WriteString(w, `{"choices":[{"message":{"role":"assistant","content":"answer"}}]}`)
	}))
	defer server.Close()

	client, err := NewFPTClient("secret", "model", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.Chat(context.Background(), domain.Context{}); err != nil {
		t.Fatalf("Chat() error = %v", err)
	}
	if got := (<-requestBody).Temperature; got != defaultFPTTemperature {
		t.Fatalf("temperature = %v, want %v", got, defaultFPTTemperature)
	}
}

func TestFPTChatHonorsHTTPTimeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(100 * time.Millisecond)
		_, _ = io.WriteString(w, `{"choices":[{"message":{"role":"assistant","content":"late"}}]}`)
	}))
	defer server.Close()

	client, err := NewFPTClient("secret", "model", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	client.http.Timeout = 10 * time.Millisecond
	_, err = client.Chat(context.Background(), domain.Context{})
	if err == nil || !strings.Contains(err.Error(), "Client.Timeout") {
		t.Fatalf("Chat() timeout error = %v", err)
	}
}

func TestFPTChatReturnsStructuredProviderError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Request-Id", "req-123")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = io.WriteString(w, `{"error":{"message":"invalid credential","type":"authentication_error"}}`)
	}))
	defer server.Close()

	client, err := NewFPTClient("secret", "model", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	_, err = client.Chat(context.Background(), domain.Context{})
	if err == nil {
		t.Fatal("Chat() error = nil")
	}
	for _, want := range []string{"HTTP 401", "req-123", "invalid credential"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("Chat() error = %q, want %q", err, want)
		}
	}
	if strings.Contains(err.Error(), `"authentication_error"`) {
		t.Fatalf("Chat() leaked raw provider error: %q", err)
	}
}

func TestFPTChatRejectsAmbiguousResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, `{"choices":[{"message":{"content":"one"}},{"message":{"content":"two"}}]}`)
	}))
	defer server.Close()

	client, err := NewFPTClient("secret", "model", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	_, err = client.Chat(context.Background(), domain.Context{})
	if err == nil || !strings.Contains(err.Error(), "exactly one is required") {
		t.Fatalf("Chat() error = %v", err)
	}
}

func TestFPTChatRejectsTruncatedResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, `{"choices":[{"message":{"content":"partial"},"finish_reason":"length"}]}`)
	}))
	defer server.Close()

	client, err := NewFPTClient("secret", "model", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	_, err = client.Chat(context.Background(), domain.Context{})
	if err == nil || !strings.Contains(err.Error(), "truncated") {
		t.Fatalf("Chat() error = %v", err)
	}
}

func TestNewFPTClientRejectsInvalidBaseURL(t *testing.T) {
	if _, err := NewFPTClient("secret", "model", "://bad"); err == nil {
		t.Fatal("NewFPTClient() accepted invalid base URL")
	}
	if _, err := NewFPTClient("secret", "model", "https://example.com?token=value"); err == nil {
		t.Fatal("NewFPTClient() accepted base URL with query")
	}
}

func TestReadLimitedFPTResponseRejectsOversizeBody(t *testing.T) {
	_, err := readLimitedResponse(strings.NewReader(strings.Repeat("x", maxFPTResponseBytes+1)))
	if err == nil || !strings.Contains(err.Error(), "exceeds") {
		t.Fatalf("readLimitedResponse() error = %v", err)
	}
}

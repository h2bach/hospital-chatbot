package api

import (
	"agent/internal/agent"
	"agent/internal/domain"
	"agent/internal/infra/store"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

type streamTestLLM struct {
	outputs []*agent.LLMOutput
	index   int
}

func (client *streamTestLLM) Chat(context.Context, domain.Context) (*agent.LLMOutput, error) {
	if client.index >= len(client.outputs) {
		return nil, errors.New("unexpected LLM call")
	}
	output := client.outputs[client.index]
	client.index++
	return output, nil
}

type streamTestMCP struct{}

func (*streamTestMCP) Disconnect()                                   {}
func (*streamTestMCP) Retry(context.Context)                         {}
func (*streamTestMCP) Tools(context.Context) ([]mcp_sdk.Tool, error) { return nil, nil }
func (*streamTestMCP) CallTool(context.Context, string, map[string]any) (string, error) {
	return "", errors.New("unexpected tool call")
}

func TestStaticFallbackServesRootPublicAsset(t *testing.T) {
	staticDir := t.TempDir()
	logo := []byte("hospital-logo")
	if err := os.WriteFile(filepath.Join(staticDir, "bvtim_logo.png"), logo, 0o600); err != nil {
		t.Fatalf("write test logo: %v", err)
	}
	t.Setenv("AGENT_STATIC_DIR", staticDir)

	server := &Server{sessionStore: store.NewMemorySessionStore()}
	addRoutes(server)

	request := httptest.NewRequest(http.MethodGet, "/bvtim_logo.png", nil)
	response := httptest.NewRecorder()
	server.httpServer.Handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("GET /bvtim_logo.png status = %d, want %d", response.Code, http.StatusOK)
	}
	if response.Body.String() != string(logo) {
		t.Fatalf("GET /bvtim_logo.png body = %q, want %q", response.Body.String(), logo)
	}
}

func TestAPIRouteTakesPriorityOverStaticFallback(t *testing.T) {
	staticDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(staticDir, "c"), []byte("static"), 0o600); err != nil {
		t.Fatalf("write conflicting static file: %v", err)
	}
	t.Setenv("AGENT_STATIC_DIR", staticDir)

	server := &Server{sessionStore: store.NewMemorySessionStore()}
	addRoutes(server)

	request := httptest.NewRequest(http.MethodGet, "/c", nil)
	response := httptest.NewRecorder()
	server.httpServer.Handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("GET /c status = %d, want %d", response.Code, http.StatusOK)
	}
	if contentType := response.Header().Get("Content-Type"); contentType != "application/json" {
		t.Fatalf("GET /c Content-Type = %q, want application/json", contentType)
	}
}

func TestStreamRouteEmitsStatusBeforeEvaluatedAnswer(t *testing.T) {
	staticDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(staticDir, "index.html"), []byte("ok"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("AGENT_STATIC_DIR", staticDir)
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	llm := &streamTestLLM{outputs: []*agent.LLMOutput{
		{Text: `{"intent":"social","answer_mode":"social","tasks":[],"reason_code":"GREETING"}`},
		{Text: "Xin chào Anh/Chị. Tôi có thể hỗ trợ tra cứu thông tin bệnh viện."},
		{Text: `{"verdict":"pass","mode":"conversation","unsupported_claims":[],"claims":[],"reason_code":"SAFE"}`},
	}}
	sessions := store.NewMemorySessionStore()
	sessionID, err := sessions.Create()
	if err != nil {
		t.Fatal(err)
	}
	server := &Server{sessionStore: sessions, agent: agent.NewAgent(llm, &streamTestMCP{}, nil)}
	addRoutes(server)

	request := httptest.NewRequest(http.MethodPost, "/c/"+sessionID+"/stream", strings.NewReader(`{"message":"Xin chào"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	server.httpServer.Handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK || !strings.HasPrefix(response.Header().Get("Content-Type"), "text/event-stream") {
		t.Fatalf("stream status/content-type = %d/%q", response.Code, response.Header().Get("Content-Type"))
	}
	body := response.Body.String()
	planning := strings.Index(body, `"phase":"planning"`)
	evaluating := strings.Index(body, `"phase":"evaluating"`)
	delta := strings.Index(body, "event: delta")
	complete := strings.Index(body, "event: complete")
	if planning < 0 || evaluating <= planning || delta <= evaluating || complete <= delta {
		t.Fatalf("unexpected SSE event order: %s", body)
	}
	if !strings.Contains(body, "Xin chào Anh/Chị") {
		t.Fatalf("verified answer missing from SSE: %s", body)
	}
}

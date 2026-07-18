package api

import (
	"agent/internal/infra/store"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

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

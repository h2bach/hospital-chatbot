package api

import (
	"agent/internal/domain"
	"agent/internal/infra/store"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestCitationContextRequiresSessionOwner(t *testing.T) {
	staticDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(staticDir, "index.html"), []byte("ok"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("AGENT_STATIC_DIR", staticDir)
	sessions := store.NewMemorySessionStore()
	id, _ := sessions.CreateForOwner("device-a")
	session, _ := sessions.GetByID(id)
	session.CitationContexts = map[string]domain.CitationContextSnapshot{
		"cit-1": {
			Citation: domain.Citation{ID: "cit-1", Index: 1, SourceKind: "hospital_facility", Title: "Cơ sở 1", Excerpt: "Địa chỉ", MatchStatus: "exact"},
			Blocks: []domain.CitationContextBlock{{ID: "CS1", Text: "Địa chỉ", IsAnchor: true}},
		},
	}
	_ = sessions.Save(session)
	server := &Server{sessionStore: sessions}
	addRoutes(server)

	wrongOwner := httptest.NewRequest(http.MethodGet, "/c/"+id+"/citations/cit-1/context", nil)
	wrongOwner.Header.Set("X-Device-ID", "device-b")
	wrongResponse := httptest.NewRecorder()
	server.httpServer.Handler.ServeHTTP(wrongResponse, wrongOwner)
	if wrongResponse.Code != http.StatusNotFound {
		t.Fatalf("cross-device citation status=%d, want 404", wrongResponse.Code)
	}

	owner := httptest.NewRequest(http.MethodGet, "/c/"+id+"/citations/cit-1/context", nil)
	owner.Header.Set("X-Device-ID", "device-a")
	response := httptest.NewRecorder()
	server.httpServer.Handler.ServeHTTP(response, owner)
	if response.Code != http.StatusOK {
		t.Fatalf("owner citation status=%d body=%s", response.Code, response.Body.String())
	}
	var payload citationContextResponse
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil || payload.Citation.ID != "cit-1" || len(payload.Blocks) != 1 {
		t.Fatalf("unexpected context response: %#v err=%v", payload, err)
	}
}

func TestGetSessionRequiresOwner(t *testing.T) {
	sessions := store.NewMemorySessionStore()
	id, _ := sessions.CreateForOwner("device-a")
	server := &Server{sessionStore: sessions}
	request := httptest.NewRequest(http.MethodGet, "/c/"+id, nil)
	request.SetPathValue("id", id)
	request.Header.Set("X-Device-ID", "device-b")
	response := httptest.NewRecorder()
	server.GetSession(response, request)
	if response.Code != http.StatusNotFound {
		t.Fatalf("cross-device session status=%d, want 404", response.Code)
	}
}

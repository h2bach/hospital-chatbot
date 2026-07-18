package api

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"agent/internal/infra/store"
)

func TestTranscribeAudioWithoutConfigurationReturnsNotImplemented(t *testing.T) {
	server := &Server{sessionStore: store.NewMemorySessionStore()}
	request := httptest.NewRequest(http.MethodPost, "/api/stt", nil)
	response := httptest.NewRecorder()

	server.TranscribeAudio(response, request)

	if response.Code != http.StatusNotImplemented {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusNotImplemented)
	}
}

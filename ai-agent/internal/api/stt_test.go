package api

import (
	"bytes"
	"context"
	"errors"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"agent/internal/infra/store"
)

type failingSpeechToText struct{}

func (failingSpeechToText) Transcribe(context.Context, string, string, []byte) (string, error) {
	return "", errors.New("FPT provider rejected secret-api-key")
}

func TestTranscribeAudioWithoutConfigurationReturnsNotImplemented(t *testing.T) {
	server := &Server{sessionStore: store.NewMemorySessionStore()}
	request := httptest.NewRequest(http.MethodPost, "/api/stt", nil)
	response := httptest.NewRecorder()

	server.TranscribeAudio(response, request)

	if response.Code != http.StatusNotImplemented {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusNotImplemented)
	}
}

func TestTranscribeAudioDoesNotExposeProviderError(t *testing.T) {
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("audio", "sample.wav")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := part.Write([]byte("valid-enough-test-audio")); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}

	server := &Server{
		sessionStore: store.NewMemorySessionStore(),
		speechToText: failingSpeechToText{},
	}
	request := httptest.NewRequest(http.MethodPost, "/api/stt", &body)
	request.Header.Set("Content-Type", writer.FormDataContentType())
	response := httptest.NewRecorder()

	server.TranscribeAudio(response, request)

	if response.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusBadGateway)
	}
	content := response.Body.String()
	if strings.Contains(content, "FPT") || strings.Contains(content, "secret-api-key") {
		t.Fatalf("provider details leaked to the client: %s", content)
	}
	if !strings.Contains(content, "Chưa thể nhận dạng giọng nói") {
		t.Fatalf("safe retry guidance missing: %s", content)
	}
}

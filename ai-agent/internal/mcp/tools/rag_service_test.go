package tools

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSearchRAGHandler_EmptyQuery(t *testing.T) {
	_, out, err := SearchRAGHandler(context.Background(), nil, SearchRAGInput{Query: ""})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out.Text, "Lỗi") {
		t.Errorf("expected error message for empty query, got: %s", out.Text)
	}
}

func TestSearchRAGHandler_Success(t *testing.T) {
	mockResponse := ragRetrieveResponse{
		RequestID:     "req-123",
		RouteDecision: "rag_static",
		Status:        "exact",
		Confidence:    0.95,
		Evidence: []ragEvidenceItem{
			{
				EvidenceID: "E1",
				Rank:       1,
				MatchType:  "exact",
				CitationID: "C1",
				Chunk: ragChunkContent{
					ChunkID:     "chunk-1",
					DocumentID:  "QT.25.01",
					ContentType: "quy_trinh",
					HeadingPath: []string{"Quy trình khám bệnh", "Bước 1"},
					ContentText: "Người bệnh đến đăng ký tại tầng 1.",
					Facts: map[string]any{
						"step": "Đăng ký",
					},
				},
			},
		},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST method, got %s", r.Method)
		}
		if r.URL.Path != "/api/v1/rag/retrieve" {
			t.Errorf("expected path /api/v1/rag/retrieve, got %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(mockResponse)
	}))
	defer server.Close()

	t.Setenv("RAG_SERVICE_URL", server.URL)

	_, out, err := SearchRAGHandler(context.Background(), nil, SearchRAGInput{
		Query: "quy trình khám",
		TopK:  5,
	})
	if err != nil {
		t.Fatalf("unexpected handler error: %v", err)
	}

	if !strings.Contains(out.Text, "QT.25.01") {
		t.Errorf("expected output to contain DocumentID QT.25.01, got: %s", out.Text)
	}
	if !strings.Contains(out.Text, "Người bệnh đến đăng ký tại tầng 1.") {
		t.Errorf("expected output to contain chunk content, got: %s", out.Text)
	}
	if !strings.Contains(out.Text, "[C1]") {
		t.Errorf("expected output to contain citation [C1], got: %s", out.Text)
	}
	if out.Status != "exact" || len(out.Evidence) != 1 {
		t.Errorf("expected structured status/evidence to be preserved, got status=%q evidence=%d", out.Status, len(out.Evidence))
	}
}

func TestSearchRAGHandler_ServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
	}))
	defer server.Close()

	t.Setenv("RAG_SERVICE_URL", server.URL)

	_, out, err := SearchRAGHandler(context.Background(), nil, SearchRAGInput{Query: "test"})
	if err != nil {
		t.Fatalf("unexpected handler error: %v", err)
	}

	if !strings.Contains(out.Text, "HTTP status 500") {
		t.Errorf("expected error message containing status 500, got: %s", out.Text)
	}
}

func TestFormatRAGResponse_Empty(t *testing.T) {
	resp := ragRetrieveResponse{}
	formatted := formatRAGResponse(resp)
	if !strings.Contains(formatted, "Không tìm thấy tài liệu phù hợp") {
		t.Errorf("unexpected format for empty response: %s", formatted)
	}
}

func TestFormatRAGResponse_Insufficient(t *testing.T) {
	resp := ragRetrieveResponse{
		Status:          "insufficient",
		Confidence:      0.0,
		ReasonCodes:     []string{"NO_RETRIEVAL_MATCH"},
		FallbackMessage: "Hiện chưa có thông tin chính xác.",
	}
	formatted := formatRAGResponse(resp)
	if !strings.Contains(formatted, "insufficient") {
		t.Errorf("expected status insufficient in output, got: %s", formatted)
	}
	if !strings.Contains(formatted, "CẢNH BÁO ĐỘ TIN CẬY") {
		t.Errorf("expected confidence warning in output, got: %s", formatted)
	}
}

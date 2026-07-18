package mcp

import (
	"agent/internal/rag"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type stubKnowledgeProvider struct{}

func (*stubKnowledgeProvider) Retrieve(_ context.Context, query string, _ int) (*rag.RetrievalResult, error) {
	return &rag.RetrievalResult{
		SchemaVersion: "heartcare.rag.evidence.v1",
		RequestID:     "test-rag-request",
		Query:         rag.Query{Original: query, Normalized: query},
		Answerability: rag.Answerability{Status: "insufficient", Confidence: rag.Confidence{Score: 0}},
		Fallback:      rag.Fallback{Action: "abstain", Message: "Không có dữ liệu."},
	}, nil
}

func (*stubKnowledgeProvider) ExpandContext(_ context.Context, chunkID, scope string, _ int) (*rag.ContextResult, error) {
	return &rag.ContextResult{SchemaVersion: "heartcare.rag.context.v1", Status: "insufficient", AnchorChunkID: chunkID, Scope: scope}, nil
}

func (*stubKnowledgeProvider) Catalog(context.Context) (*rag.CatalogResult, error) {
	return &rag.CatalogResult{SchemaVersion: "heartcare.rag.catalog.v1"}, nil
}

func TestClientConnectsListsAndCallsInProcessMCPServer(t *testing.T) {
	hospitalServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[{"facility_id":"CS1","name":"Bệnh viện Tim Hà Nội - Cơ sở 1","address":"92 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội","areas":{"CS1_TN1":"Khu khám bệnh Tự nguyện 1"},"room_count":19,"source":{"sheet":"01_Co_so_Phong_kham","workbook":"hospital.xlsx"},"timezone":"Asia/Ho_Chi_Minh"}],"total":1}`))
	}))
	defer hospitalServer.Close()
	t.Setenv("HOSPITAL_INFO_SERVICE_URL", hospitalServer.URL)

	server := httptest.NewServer(NewMCPServer(&stubKnowledgeProvider{}))
	defer server.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	client, err := NewMCPClient(ctx, server.URL)
	if err != nil {
		t.Fatalf("NewMCPClient() error = %v", err)
	}
	defer client.Disconnect()

	tools, err := client.Tools(ctx)
	if err != nil {
		t.Fatalf("Tools() error = %v", err)
	}
	if len(tools) != 18 {
		t.Fatalf("tool count = %d, want 18", len(tools))
	}
	foundFacilities := false
	for _, tool := range tools {
		if tool.Name == "listHospitalFacilities" {
			foundFacilities = true
			break
		}
	}
	if !foundFacilities {
		t.Fatal("listHospitalFacilities tool is not registered")
	}
	foundKnowledge := false
	for _, tool := range tools {
		if tool.Name == "searchHospitalKnowledge" {
			foundKnowledge = true
			break
		}
	}
	if !foundKnowledge {
		t.Fatal("searchHospitalKnowledge tool is not registered")
	}

	output, err := client.CallTool(ctx, "checkTime", map[string]any{"city": "hanoi"})
	if err != nil {
		t.Fatalf("CallTool() error = %v", err)
	}
	if !strings.Contains(output, "time") {
		t.Fatalf("checkTime output = %q", output)
	}

	knowledgeOutput, err := client.CallTool(ctx, "searchHospitalKnowledge", map[string]any{
		"task_id": "task_1", "query": "dịch vụ không tồn tại", "top_k": 5,
	})
	if err != nil {
		t.Fatalf("searchHospitalKnowledge error = %v", err)
	}
	if !strings.Contains(knowledgeOutput, "heartcare.rag.evidence.v1") || !strings.Contains(knowledgeOutput, "insufficient") {
		t.Fatalf("knowledge output does not preserve evidence contract: %q", knowledgeOutput)
	}

	facilityOutput, err := client.CallTool(ctx, "listHospitalFacilities", map[string]any{})
	if err != nil {
		t.Fatalf("listHospitalFacilities error = %v", err)
	}
	var facilityEnvelope struct {
		Status int `json:"status"`
		Body   struct {
			Data []struct {
				FacilityID string `json:"facility_id"`
				Address    string `json:"address"`
			} `json:"data"`
		} `json:"body"`
	}
	if err := json.Unmarshal([]byte(strings.TrimSpace(facilityOutput)), &facilityEnvelope); err != nil {
		t.Fatalf("facility output is not the expected typed MCP JSON: %v, output=%q", err, facilityOutput)
	}
	if facilityEnvelope.Status != http.StatusOK || len(facilityEnvelope.Body.Data) != 1 || facilityEnvelope.Body.Data[0].FacilityID != "CS1" {
		t.Fatalf("facility MCP envelope changed: %#v, output=%q", facilityEnvelope, facilityOutput)
	}
}

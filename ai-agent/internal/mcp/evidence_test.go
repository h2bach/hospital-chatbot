package mcp

import (
	"testing"
	"time"
)

func TestNormalizeRAGEvidencePreservesCitationMetadata(t *testing.T) {
	result := ToolResult{Structured: map[string]any{
		"status": "exact", "confidence": 0.97,
		"evidence": []any{map[string]any{
			"citation_id": "C1",
			"chunk": map[string]any{
				"chunk_id": "chunk-1", "document_id": "doc-1",
				"content_text": "Người bệnh đến đăng ký tại tầng 1.",
				"heading_path": []any{"Quy trình khám", "Bước 1"},
				"facts": map[string]any{"version": "2025"},
			},
		}},
		"citations": []any{map[string]any{
			"citation_id": "C1", "chunk_id": "chunk-1", "page_start": 4.0,
			"line_start": 120.0, "line_end": 121.0,
			"heading_path": []any{"Quy trình khám", "Bước 1"},
		}},
	}}
	evidence := NormalizeEvidence("searchRAG", result, time.Now())
	if len(evidence) != 1 {
		t.Fatalf("got %d evidence records", len(evidence))
	}
	citation := evidence[0].Citation
	if citation.Location.Page != 4 || citation.Location.LineStart != 120 || citation.Location.ChunkID != "chunk-1" {
		t.Fatalf("citation location lost: %#v", citation.Location)
	}
	if citation.Title != "Quy trình khám" || citation.Freshness.Version != "2025" || citation.Freshness.ApprovalStatus != "published" {
		t.Fatalf("citation metadata lost: %#v", citation)
	}
}

func TestNormalizeHospitalEvidenceCreatesObservedSnapshot(t *testing.T) {
	observed := time.Date(2026, 7, 19, 2, 0, 0, 0, time.UTC)
	result := ToolResult{Structured: map[string]any{
		"status": 200.0,
		"body": map[string]any{"data": []any{map[string]any{
			"facility_id": "CS1", "name": "Bệnh viện Tim Hà Nội - Cơ sở 1",
			"address": "92 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội",
		}}},
	}}
	evidence := NormalizeEvidence("listHospitalFacilities", result, observed)
	if len(evidence) != 1 {
		t.Fatalf("got %d evidence records", len(evidence))
	}
	citation := evidence[0].Citation
	if citation.SourceKind != "hospital_facility" || citation.Location.SourceID != "CS1" {
		t.Fatalf("unexpected directory citation: %#v", citation)
	}
	if citation.Freshness.ObservedAt != observed.Format(time.RFC3339) || len(evidence[0].Context.Blocks) != 1 {
		t.Fatalf("dynamic evidence snapshot missing: %#v", evidence[0])
	}
}

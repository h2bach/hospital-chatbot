package mcp

import (
	"encoding/json"
	"testing"
)

func TestDecodeStructuredContentUsesRawMessage(t *testing.T) {
	got := valueMap(decodeStructuredContent(json.RawMessage(`{"status":"exact"}`), ""))
	if cleanString(got["status"]) != "exact" {
		t.Fatalf("raw structured content was not decoded: %#v", got)
	}
}

func TestDecodeStructuredContentFallsBackToJSONText(t *testing.T) {
	got := valueMap(decodeStructuredContent(nil, `{"status":"approximate","evidence":[{"id":"one"}]}`))
	if cleanString(got["status"]) != "approximate" || len(valueSlice(got["evidence"])) != 1 {
		t.Fatalf("JSON text fallback was not decoded: %#v", got)
	}
}

func TestDecodeStructuredContentDoesNotTreatHumanTextAsEvidence(t *testing.T) {
	if got := decodeStructuredContent(nil, "Không tìm thấy dữ liệu."); got != nil {
		t.Fatalf("human-readable text must not become structured evidence: %#v", got)
	}
}

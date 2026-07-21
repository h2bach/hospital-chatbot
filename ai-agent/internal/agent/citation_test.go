package agent

import (
	"agent/internal/domain"
	"agent/internal/mcp"
	"strings"
	"testing"
)

func TestFinalizeCitationsIndexesAndDeduplicatesEvidence(t *testing.T) {
	ledger := newEvidenceLedger()
	items := ledger.add([]mcp.Evidence{{
		Fingerprint: "rag|doc|chunk",
		Citation: domain.Citation{
			SourceKind: "rag_document", Title: "Quy trình khám",
			Excerpt: "Người bệnh đến đăng ký tại tầng 1.", MatchStatus: "exact",
			ContextAvailable: true,
		},
		Context: domain.CitationContextSnapshot{Blocks: []domain.CitationContextBlock{{ID: "chunk", IsAnchor: true}}},
	}})
	id := items[0].ID
	response := finalizeCitations("Đăng ký tại tầng 1. [[cite:"+id+"]] Việc đăng ký được thực hiện tại tầng 1. [[cite:"+id+"]]", ledger)
	if len(response.Citations) != 1 {
		t.Fatalf("got %d citations, want one deduplicated citation", len(response.Citations))
	}
	if strings.Count(response.Text, "[1](#citation-") != 2 {
		t.Fatalf("citation marker not indexed consistently: %s", response.Text)
	}
	if response.Citations[0].ID == "" || len(response.Citations[0].HighlightRanges) == 0 {
		t.Fatalf("citation must have opaque ID and highlight: %#v", response.Citations[0])
	}
	if _, ok := response.CitationContexts[response.Citations[0].ID]; !ok {
		t.Fatal("citation context snapshot was not persisted")
	}
}

func TestFinalizeCitationsRejectsExistingButUnrelatedEvidence(t *testing.T) {
	ledger := newEvidenceLedger()
	items := ledger.add([]mcp.Evidence{{
		Fingerprint: "organization|imaging",
		Citation: domain.Citation{
			SourceKind: "hospital_organization",
			Title:      "Khoa Chẩn đoán hình ảnh",
			Excerpt:    "Khoa Chẩn đoán hình ảnh là đơn vị thuộc khối cận lâm sàng.",
		},
	}})
	id := items[0].ID
	draft := "Chi phí SPECT/CT tưới máu cơ tim là 969.800 đồng. [[cite:" + id + "]]"
	valid, invalid := citationTokenStats(draft, ledger)
	if valid != 0 || invalid != 1 {
		t.Fatalf("unrelated evidence must be invalid, got valid=%d invalid=%d", valid, invalid)
	}
	response := finalizeCitations(draft, ledger)
	if len(response.Citations) != 0 || strings.Contains(response.Text, "#citation-") {
		t.Fatalf("unrelated evidence created a citation: %#v", response)
	}
}

func TestCitationSupportsClaimWithMatchingPriceAndService(t *testing.T) {
	claim := "SPECT/CT tưới máu cơ tim gắng sức với Tetrofosmin có giá 969.800 đồng."
	excerpt := "19.0069.1829 | SPECT/CT tưới máu cơ tim gắng sức với Tetrofosmin | 969.800 | Chưa bao gồm dược chất phóng xạ."
	if !citationSupportsClaim(claim, excerpt) {
		t.Fatal("matching service and price must be accepted")
	}
}

func TestHasUncitedFactualLines(t *testing.T) {
	if !hasUncitedFactualLines("Giá dịch vụ là 969.800 đồng.") {
		t.Fatal("uncited price must be detected")
	}
	if hasUncitedFactualLines("Giá dịch vụ là 969.800 đồng. [[cite:ev_1]]") {
		t.Fatal("cited price must not be reported as uncited")
	}
}

func TestRenderRAGClarificationUsesFiveEvidenceItems(t *testing.T) {
	ledger := newEvidenceLedger()
	for index := 1; index <= 6; index++ {
		ledger.add([]mcp.Evidence{{
			Fingerprint: "rag|doc|" + stringID(index),
			Citation: domain.Citation{
				SourceKind: "rag_document", MatchStatus: "approximate",
				Title: "Bảng giá", Excerpt: "Dịch vụ " + stringID(index) + " mã DV" + stringID(index) + " giá 100.000",
			},
			Context: domain.CitationContextSnapshot{Blocks: []domain.CitationContextBlock{{
				IsAnchor: true,
				Fields: []domain.CitationField{
					{Label: "Tên dịch vụ", Value: "Dịch vụ " + stringID(index)},
					{Label: "Mã dịch vụ", Value: "DV" + stringID(index)},
					{Label: "Giá tại Cơ sở 1", Value: "100.000"},
				},
			}}},
		}})
	}
	text, ok := renderRAGClarification(ledger)
	if !ok || strings.Count(text, "[[cite:") != 5 || strings.Contains(text, "Dịch vụ 6") {
		t.Fatalf("expected a cited top-5 clarification, ok=%t text=%s", ok, text)
	}
	response := finalizeCitations(text, ledger)
	if len(response.Citations) != 5 {
		t.Fatalf("deterministic clarification must resolve five citations, got %d: %s", len(response.Citations), response.Text)
	}
}

func TestFinalizeCitationsRejectsUnknownEvidenceAndLegacySourceText(t *testing.T) {
	ledger := newEvidenceLedger()
	response := finalizeCitations("Nội dung [[cite:ev_from_old_run]] [Nguồn: doc | Tool: searchRAG]\n📌 *Công cụ tra cứu:* searchRAG", ledger)
	if len(response.Citations) != 0 {
		t.Fatal("unknown evidence must never create a public citation")
	}
	if strings.Contains(response.Text, "ev_from_old_run") || strings.Contains(response.Text, "Tool:") || strings.Contains(response.Text, "Công cụ tra cứu") {
		t.Fatalf("internal/legacy citation leaked: %s", response.Text)
	}
}

func TestFindHighlightRangesUsesUnicodeCodePointOffsets(t *testing.T) {
	excerpt := "Chi phí phẫu thuật van tim được công bố trong bảng giá."
	ranges := findHighlightRanges("Chi phí phẫu thuật van tim", excerpt)
	if len(ranges) == 0 {
		t.Fatal("expected highlight range")
	}
	runes := []rune(excerpt)
	if ranges[0].Start < 0 || ranges[0].End > len(runes) || ranges[0].Start >= ranges[0].End {
		t.Fatalf("invalid Unicode range %#v for %d runes", ranges[0], len(runes))
	}
}

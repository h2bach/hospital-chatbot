package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

const defaultRAGServiceURL = "http://localhost:6689"

var SearchRAGTool = mcp_sdk.Tool{
	Name:        "searchRAG",
	Description: "Truy vấn cơ sở dữ liệu RAG (Retrieval-Augmented Generation) của Bệnh viện Tim Hà Nội. ĐƯỢC ƯU TIÊN SỬ DỤNG HÀNG ĐẦU để tra cứu thông tin bệnh viện, quy trình, thủ tục, bảo hiểm y tế (BHYT), bảng giá dịch vụ, và các tài liệu chính thức.",
}

type SearchRAGInput struct {
	Query string `json:"query" jsonschema:"Vietnamese or English search query or question to retrieve relevant hospital knowledge"`
	TopK  int    `json:"top_k,omitempty" jsonschema:"optional top-k passages to retrieve, default is 8"`
}

type ragRetrieveRequest struct {
	Query string `json:"query"`
	TopK  int    `json:"top_k"`
}

type ragChunkContent struct {
	ChunkID     string         `json:"chunk_id"`
	DocumentID  string         `json:"document_id"`
	ContentType string         `json:"content_type"`
	ContentText string         `json:"content_text"`
	HeadingPath []string       `json:"heading_path"`
	Facts       map[string]any `json:"facts"`
}

type ragEvidenceItem struct {
	EvidenceID string          `json:"evidence_id"`
	Rank       int             `json:"rank"`
	MatchType  string          `json:"match_type"`
	Scores     map[string]any  `json:"scores"`
	Chunk      ragChunkContent `json:"chunk"`
	CitationID string          `json:"citation_id"`
}

type ragRetrieveResponse struct {
	RequestID       string            `json:"request_id"`
	Query           any               `json:"query"`
	RouteDecision   string            `json:"route_decision"`
	Status          string            `json:"status"`
	Confidence      float64           `json:"confidence"`
	ReasonCodes     []string          `json:"reason_codes"`
	Evidence        []ragEvidenceItem `json:"evidence"`
	Citations       []ragCitationItem `json:"citations"`
	Clarification   map[string]any    `json:"clarification,omitempty"`
	FallbackAction  string            `json:"fallback_action"`
	FallbackMessage string            `json:"fallback_message"`
	Answerability   struct {
		Status      string   `json:"status"`
		Confidence  any      `json:"confidence"`
		ReasonCodes []string `json:"reason_codes"`
	} `json:"answerability"`
	Route struct {
		Decision string `json:"decision"`
	} `json:"route"`
	Fallback struct {
		Action  string `json:"action"`
		Message string `json:"message"`
	} `json:"fallback"`
}

type ragCitationItem struct {
	CitationID  string         `json:"citation_id"`
	ChunkID     string         `json:"chunk_id"`
	SourceFile  string         `json:"source_file"`
	SourceURI   string         `json:"source_uri"`
	LineStart   int            `json:"line_start"`
	LineEnd     int            `json:"line_end"`
	PageStart   int            `json:"page_start"`
	HeadingPath []string       `json:"heading_path"`
	LegalBasis  any            `json:"legal_basis,omitempty"`
}

// RAGToolOutput keeps the user-facing text for model compatibility and the
// original evidence contract for citation/audit consumers.
type RAGToolOutput struct {
	Text             string            `json:"text" jsonschema:"Human-readable retrieval result"`
	RequestID        string            `json:"request_id,omitempty"`
	Query            string            `json:"query,omitempty"`
	RouteDecision    string            `json:"route_decision,omitempty"`
	Status           string            `json:"status,omitempty"`
	Confidence       float64           `json:"confidence,omitempty"`
	ReasonCodes      []string          `json:"reason_codes,omitempty"`
	Evidence         []ragEvidenceItem `json:"evidence,omitempty"`
	Citations        []ragCitationItem `json:"citations,omitempty"`
	Clarification    map[string]any    `json:"clarification,omitempty"`
	FallbackAction   string            `json:"fallback_action,omitempty"`
	FallbackMessage  string            `json:"fallback_message,omitempty"`
}

func SearchRAGHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input SearchRAGInput) (*mcp_sdk.CallToolResult, RAGToolOutput, error) {
	query := strings.TrimSpace(input.Query)
	if query == "" {
		return nil, RAGToolOutput{Text: "Lỗi: Câu truy vấn không được để trống."}, nil
	}

	topK := input.TopK
	if topK <= 0 {
		topK = 8
	}

	baseURL := strings.TrimRight(os.Getenv("RAG_SERVICE_URL"), "/")
	if baseURL == "" {
		baseURL = os.Getenv("RAG_CORE_URL")
	}
	if baseURL == "" {
		baseURL = defaultRAGServiceURL
	}
	endpoint := strings.TrimRight(baseURL, "/") + "/api/v1/rag/retrieve"

	reqBody, err := json.Marshal(ragRetrieveRequest{
		Query: query,
		TopK:  topK,
	})
	if err != nil {
		return nil, RAGToolOutput{}, fmt.Errorf("marshal rag request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(reqBody))
	if err != nil {
		return nil, RAGToolOutput{}, fmt.Errorf("create rag request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, RAGToolOutput{
			Text: fmt.Sprintf("Không thể kết nối với RAG service tại %s. Lỗi: %v", baseURL, err),
		}, nil
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, RAGToolOutput{}, fmt.Errorf("read rag response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, RAGToolOutput{
			Text: fmt.Sprintf("RAG service trả về lỗi HTTP status %d: %s", resp.StatusCode, string(bodyBytes)),
		}, nil
	}

	var ragResp ragRetrieveResponse
	if err := json.Unmarshal(bodyBytes, &ragResp); err != nil {
		log.Printf("RAG evidence contract decode failed: %v", err)
		return nil, RAGToolOutput{Text: string(bodyBytes)}, nil
	}
	if ragResp.Status == "" {
		ragResp.Status = ragResp.Answerability.Status
	}
	if ragResp.Confidence == 0 {
		ragResp.Confidence = ragConfidenceScore(ragResp.Answerability.Confidence)
	}
	if len(ragResp.ReasonCodes) == 0 {
		ragResp.ReasonCodes = ragResp.Answerability.ReasonCodes
		if confidence, ok := ragResp.Answerability.Confidence.(map[string]any); ok {
			if encoded, err := json.Marshal(confidence["reason_codes"]); err == nil {
				_ = json.Unmarshal(encoded, &ragResp.ReasonCodes)
			}
		}
	}
	if ragResp.RouteDecision == "" {
		ragResp.RouteDecision = ragResp.Route.Decision
	}
	if ragResp.FallbackAction == "" {
		ragResp.FallbackAction = ragResp.Fallback.Action
	}
	if ragResp.FallbackMessage == "" {
		ragResp.FallbackMessage = ragResp.Fallback.Message
	}

	formattedText := formatRAGResponse(ragResp)
	return nil, RAGToolOutput{
		Text:            formattedText,
		RequestID:       ragResp.RequestID,
		Query:           ragQueryText(ragResp.Query),
		RouteDecision:   ragResp.RouteDecision,
		Status:          ragResp.Status,
		Confidence:      ragResp.Confidence,
		ReasonCodes:     ragResp.ReasonCodes,
		Evidence:        ragResp.Evidence,
		Citations:       ragResp.Citations,
		Clarification:   ragResp.Clarification,
		FallbackAction:  ragResp.FallbackAction,
		FallbackMessage: ragResp.FallbackMessage,
	}, nil
}

func ragConfidenceScore(value any) float64 {
	switch typed := value.(type) {
	case float64:
		return typed
	case map[string]any:
		if score, ok := typed["score"].(float64); ok {
			return score
		}
	}
	return 0
}

func ragQueryText(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case map[string]any:
		if original, ok := typed["original"].(string); ok {
			return original
		}
	}
	return ""
}

func formatRAGResponse(resp ragRetrieveResponse) string {
	var b strings.Builder

	if resp.Status != "" || resp.Confidence > 0 {
		b.WriteString(fmt.Sprintf("=== RAG Retrieval Status: %s | Confidence: %.2f ===\n", resp.Status, resp.Confidence))
		if len(resp.ReasonCodes) > 0 {
			b.WriteString(fmt.Sprintf("Mã lý do: %s\n", strings.Join(resp.ReasonCodes, ", ")))
		}
		b.WriteString("\n")
	}

	if resp.Status == "insufficient" || (resp.Status != "" && resp.Confidence == 0 && len(resp.Evidence) == 0) {
		b.WriteString("[CẢNH BÁO ĐỘ TIN CẬY]: RAG core đánh giá thông tin KHÔNG ĐỦ ĐỘ TIN CẬY (Status: insufficient / Confidence: low).\n")
		b.WriteString("Vui lòng áp dụng Trạng thái B (thông báo chưa có dữ liệu chính xác và hướng dẫn liên hệ hotline/lễ tân, KHÔNG tự bịa thông tin).\n\n")
	} else if resp.Status == "approximate" {
		b.WriteString("[LƯU Ý ĐỘ TIN CẬY]: Kết quả RAG có độ tin cậy xấp xỉ (approximate match). Cần đối chiếu kỹ trước khi khẳng định.\n\n")
	}

	if resp.FallbackMessage != "" {
		b.WriteString("=== Thông tin trả về từ RAG ===\n")
		b.WriteString(resp.FallbackMessage)
		b.WriteString("\n\n")
	}

	if len(resp.Evidence) > 0 {
		b.WriteString("=== Trích đoạn tài liệu trích xuất từ Knowledge Base ===\n\n")

		for _, item := range resp.Evidence {
			chunk := item.Chunk
			citation := item.CitationID
			if citation == "" {
				citation = fmt.Sprintf("E%d", item.Rank)
			}
			b.WriteString(fmt.Sprintf("[%s] Nguồn: %s", citation, chunk.DocumentID))
			if len(chunk.HeadingPath) > 0 {
				b.WriteString(fmt.Sprintf(" > %s", strings.Join(chunk.HeadingPath, " > ")))
			}
			if chunk.ContentType != "" {
				b.WriteString(fmt.Sprintf(" (%s)", chunk.ContentType))
			}
			b.WriteString("\n")

			if chunk.ContentText != "" {
				b.WriteString(chunk.ContentText)
				b.WriteString("\n")
			}

			if len(chunk.Facts) > 0 {
				factsJSON, err := json.Marshal(chunk.Facts)
				if err == nil && len(factsJSON) > 2 {
					b.WriteString(fmt.Sprintf("Chi tiết: %s\n", string(factsJSON)))
				}
			}
			b.WriteString("\n")
		}
	}

	if b.Len() == 0 {
		return "Không tìm thấy tài liệu phù hợp trong cơ sở dữ liệu RAG (Confidence: 0.00)."
	}

	return strings.TrimSpace(b.String())
}

package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
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

type RAGTextOutput struct {
	Text string `json:"text" jsonschema:"Extracted plain text knowledge from RAG"`
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
	HeadingPath string         `json:"heading_path"`
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
	Query           string            `json:"query"`
	RouteDecision   string            `json:"route_decision"`
	Status          string            `json:"status"`
	Confidence      float64           `json:"confidence"`
	ReasonCodes     []string          `json:"reason_codes"`
	Evidence        []ragEvidenceItem `json:"evidence"`
	FallbackAction  string            `json:"fallback_action"`
	FallbackMessage string            `json:"fallback_message"`
}

func SearchRAGHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input SearchRAGInput) (*mcp_sdk.CallToolResult, RAGTextOutput, error) {
	query := strings.TrimSpace(input.Query)
	if query == "" {
		return nil, RAGTextOutput{Text: "Lỗi: Câu truy vấn không được để trống."}, nil
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
		return nil, RAGTextOutput{}, fmt.Errorf("marshal rag request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(reqBody))
	if err != nil {
		return nil, RAGTextOutput{}, fmt.Errorf("create rag request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, RAGTextOutput{
			Text: fmt.Sprintf("Không thể kết nối với RAG service tại %s. Lỗi: %v", baseURL, err),
		}, nil
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, RAGTextOutput{}, fmt.Errorf("read rag response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, RAGTextOutput{
			Text: fmt.Sprintf("RAG service trả về lỗi HTTP status %d: %s", resp.StatusCode, string(bodyBytes)),
		}, nil
	}

	var ragResp ragRetrieveResponse
	if err := json.Unmarshal(bodyBytes, &ragResp); err != nil {
		return nil, RAGTextOutput{Text: string(bodyBytes)}, nil
	}

	formattedText := formatRAGResponse(ragResp)
	return nil, RAGTextOutput{Text: formattedText}, nil
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
			if chunk.HeadingPath != "" {
				b.WriteString(fmt.Sprintf(" > %s", chunk.HeadingPath))
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
				if legalBasis, ok := chunk.Facts["legal_basis"].([]any); ok {
					for _, lb := range legalBasis {
						if lbMap, ok := lb.(map[string]any); ok {
							docCode, _ := lbMap["document_code"].(string)
							locator, _ := lbMap["locator"].(string)
							label := docCode
							if label == "" {
								label = "Văn bản chính thức"
							}
							if locator != "" {
								label += " (" + locator + ")"
							}

							if u, ok := lbMap["official_url"].(string); ok && isValidHTTPURL(u) {
								b.WriteString(fmt.Sprintf("Link nguồn chính thức: [%s](%s)\n", label, u))
							} else {
								b.WriteString(fmt.Sprintf("Nguồn văn bản: %s\n", label))
							}
						}
					}
				}

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

func isValidHTTPURL(rawURL string) bool {
	u := strings.TrimSpace(rawURL)
	if u == "" {
		return false
	}
	parsed, err := url.Parse(u)
	if err != nil {
		return false
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return false
	}
	if parsed.Host == "" || strings.Contains(parsed.Host, "example.invalid") || strings.Contains(parsed.Host, "invalid") {
		return false
	}
	return true
}

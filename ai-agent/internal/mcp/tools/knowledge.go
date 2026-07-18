package tools

import (
	"agent/internal/rag"
	"context"
	"fmt"
	"strings"
	"time"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

type KnowledgeSearchInput struct {
	TaskID string `json:"task_id,omitempty" jsonschema:"execution task identifier"`
	Query  string `json:"query" jsonschema:"original self-contained Vietnamese user query"`
	TopK   int    `json:"top_k,omitempty" jsonschema:"maximum 5 for clarification compatibility"`
}

type KnowledgeContextInput struct {
	TaskID  string `json:"task_id,omitempty" jsonschema:"execution task identifier"`
	ChunkID string `json:"chunk_id" jsonschema:"verified anchor chunk identifier returned by searchHospitalKnowledge"`
	Scope   string `json:"scope,omitempty" jsonschema:"section or document"`
	Limit   int    `json:"limit,omitempty" jsonschema:"maximum 50 ordered chunks"`
}

type KnowledgeCatalogInput struct {
	TaskID string `json:"task_id,omitempty" jsonschema:"execution task identifier"`
}

type KnowledgeEvidenceEnvelope struct {
	TaskID           string              `json:"task_id,omitempty"`
	SourceKind       string              `json:"source_kind"`
	Status           string              `json:"status"`
	Confidence       float64             `json:"confidence"`
	Freshness        string              `json:"freshness"`
	Warning          string              `json:"warning,omitempty"`
	EvidenceContract rag.RetrievalResult `json:"evidence_contract"`
}

type KnowledgeContextEnvelope struct {
	TaskID     string            `json:"task_id,omitempty"`
	SourceKind string            `json:"source_kind"`
	Status     string            `json:"status"`
	Freshness  string            `json:"freshness"`
	Context    rag.ContextResult `json:"context"`
}

type KnowledgeCatalogEnvelope struct {
	TaskID     string            `json:"task_id,omitempty"`
	SourceKind string            `json:"source_kind"`
	Status     string            `json:"status"`
	Freshness  string            `json:"freshness"`
	Catalog    rag.CatalogResult `json:"catalog"`
}

var (
	SearchHospitalKnowledgeTool = mcp_sdk.Tool{
		Name:        "searchHospitalKnowledge",
		Description: "Tra cứu bảng giá, quy trình, BHYT, FAQ và tài liệu giáo dục đã duyệt. Giữ nguyên exact/approximate/insufficient; approximate chỉ trả top 5 từ ngưỡng 0.80.",
	}
	ExpandHospitalKnowledgeContextTool = mcp_sdk.Tool{
		Name:        "expandHospitalKnowledgeContext",
		Description: "Mở rộng các chunk theo đúng thứ tự trong section hoặc document sau khi đã có một exact knowledge chunk.",
	}
	GetHospitalKnowledgeCatalogTool = mcp_sdk.Tool{
		Name:        "getHospitalKnowledgeCatalog",
		Description: "Liệt kê nguồn knowledge đã index, phiên bản, trạng thái duyệt và loại nội dung; không trả tài liệu draft chưa được công bố.",
	}
)

func SearchHospitalKnowledgeHandler(provider rag.KnowledgeProvider) func(context.Context, *mcp_sdk.CallToolRequest, KnowledgeSearchInput) (*mcp_sdk.CallToolResult, KnowledgeEvidenceEnvelope, error) {
	return func(ctx context.Context, _ *mcp_sdk.CallToolRequest, input KnowledgeSearchInput) (*mcp_sdk.CallToolResult, KnowledgeEvidenceEnvelope, error) {
		if provider == nil {
			return nil, KnowledgeEvidenceEnvelope{}, fmt.Errorf("knowledge provider is unavailable")
		}
		query := strings.TrimSpace(input.Query)
		if query == "" {
			return nil, KnowledgeEvidenceEnvelope{}, fmt.Errorf("query must not be empty")
		}
		topK := input.TopK
		if topK < 1 || topK > 5 {
			topK = 5
		}
		result, err := provider.Retrieve(ctx, query, topK)
		if err != nil {
			return nil, KnowledgeEvidenceEnvelope{}, err
		}
		return nil, KnowledgeEvidenceEnvelope{
			TaskID: input.TaskID, SourceKind: "rag_knowledge",
			Status:           result.Answerability.Status,
			Confidence:       result.Answerability.Confidence.Score,
			Freshness:        time.Now().UTC().Format(time.RFC3339),
			Warning:          result.GenerationPolicy.Disclosure.Text,
			EvidenceContract: *result,
		}, nil
	}
}

func ExpandHospitalKnowledgeContextHandler(provider rag.KnowledgeProvider) func(context.Context, *mcp_sdk.CallToolRequest, KnowledgeContextInput) (*mcp_sdk.CallToolResult, KnowledgeContextEnvelope, error) {
	return func(ctx context.Context, _ *mcp_sdk.CallToolRequest, input KnowledgeContextInput) (*mcp_sdk.CallToolResult, KnowledgeContextEnvelope, error) {
		if provider == nil {
			return nil, KnowledgeContextEnvelope{}, fmt.Errorf("knowledge provider is unavailable")
		}
		result, err := provider.ExpandContext(ctx, input.ChunkID, input.Scope, input.Limit)
		if err != nil {
			return nil, KnowledgeContextEnvelope{}, err
		}
		return nil, KnowledgeContextEnvelope{
			TaskID: input.TaskID, SourceKind: "rag_context", Status: result.Status,
			Freshness: time.Now().UTC().Format(time.RFC3339), Context: *result,
		}, nil
	}
}

func GetHospitalKnowledgeCatalogHandler(provider rag.KnowledgeProvider) func(context.Context, *mcp_sdk.CallToolRequest, KnowledgeCatalogInput) (*mcp_sdk.CallToolResult, KnowledgeCatalogEnvelope, error) {
	return func(ctx context.Context, _ *mcp_sdk.CallToolRequest, input KnowledgeCatalogInput) (*mcp_sdk.CallToolResult, KnowledgeCatalogEnvelope, error) {
		if provider == nil {
			return nil, KnowledgeCatalogEnvelope{}, fmt.Errorf("knowledge provider is unavailable")
		}
		result, err := provider.Catalog(ctx)
		if err != nil {
			return nil, KnowledgeCatalogEnvelope{}, err
		}
		return nil, KnowledgeCatalogEnvelope{
			TaskID: input.TaskID, SourceKind: "rag_catalog", Status: "exact",
			Freshness: time.Now().UTC().Format(time.RFC3339), Catalog: *result,
		}, nil
	}
}

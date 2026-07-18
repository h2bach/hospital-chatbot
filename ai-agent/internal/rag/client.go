package rag

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
	"time"
)

const (
	defaultServiceURL = "http://localhost:6689"
	defaultTimeout    = 15 * time.Second
	maxResponseBytes  = 8 << 20
	contractVersion   = "heartcare.rag.evidence.v1"
)

// Retriever is the mandatory, read-only knowledge source used by the Agent.
// It deliberately exposes evidence rather than generated prose so that the FPT
// synthesis and evaluation stages can be constrained and audited.
type Retriever interface {
	Retrieve(ctx context.Context, query string, topK int) (*RetrievalResult, error)
}

type HealthChecker interface {
	Health(ctx context.Context) error
}

// KnowledgeProvider is the complete read-only RAG capability exposed through
// MCP. Retrieve keeps the v1 answerability contract, while ExpandContext and
// Catalog only add ordered context and source metadata.
type KnowledgeProvider interface {
	Retriever
	ExpandContext(ctx context.Context, chunkID, scope string, limit int) (*ContextResult, error)
	Catalog(ctx context.Context) (*CatalogResult, error)
}

type Client struct {
	baseURL string
	http    *http.Client
}

func NewClient(serviceURL string) (*Client, error) {
	serviceURL = strings.TrimRight(strings.TrimSpace(serviceURL), "/")
	if serviceURL == "" {
		serviceURL = defaultServiceURL
	}
	parsed, err := url.Parse(serviceURL)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		return nil, fmt.Errorf("invalid RAG service URL %q", serviceURL)
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, fmt.Errorf("invalid RAG service URL %q: query and fragment are not allowed", serviceURL)
	}
	return &Client{baseURL: serviceURL, http: &http.Client{Timeout: defaultTimeout}}, nil
}

func NewClientFromEnvironment() (*Client, error) {
	return NewClient(os.Getenv("RAG_SERVICE_URL"))
}

type retrievalRequest struct {
	Query string `json:"query"`
	TopK  int    `json:"top_k"`
}

type RetrievalResult struct {
	SchemaVersion    string           `json:"schema_version"`
	RequestID        string           `json:"request_id"`
	Query            Query            `json:"query"`
	Route            Route            `json:"route"`
	Answerability    Answerability    `json:"answerability"`
	GenerationPolicy GenerationPolicy `json:"generation_policy"`
	Clarification    Clarification    `json:"clarification"`
	Evidence         []Evidence       `json:"evidence"`
	Citations        []Citation       `json:"citations"`
	Fallback         Fallback         `json:"fallback"`
}

type Query struct {
	Original   string `json:"original"`
	Normalized string `json:"normalized"`
}

type Route struct {
	Decision     string   `json:"decision"`
	SafetyAction string   `json:"safety_action"`
	ReasonCodes  []string `json:"reason_codes"`
}

type Answerability struct {
	Status     string     `json:"status"`
	Confidence Confidence `json:"confidence"`
}

type Confidence struct {
	Score       float64  `json:"score"`
	Level       string   `json:"level"`
	Method      string   `json:"method"`
	ReasonCodes []string `json:"reason_codes"`
}

type GenerationPolicy struct {
	Mode                string     `json:"mode"`
	MustUseOnlyEvidence bool       `json:"must_use_only_evidence"`
	MustCite            bool       `json:"must_cite"`
	AllowedEvidenceIDs  []string   `json:"allowed_evidence_ids"`
	Disclosure          Disclosure `json:"disclosure"`
	ForbiddenClaims     []string   `json:"forbidden_claims"`
}

type Disclosure struct {
	Required bool   `json:"required"`
	Position string `json:"position"`
	Text     string `json:"text"`
}

type Evidence struct {
	EvidenceID string         `json:"evidence_id"`
	Rank       int            `json:"rank"`
	MatchType  string         `json:"match_type"`
	Scores     EvidenceScores `json:"scores"`
	Chunk      Chunk          `json:"chunk"`
	CitationID string         `json:"citation_id"`
}

type EvidenceScores struct {
	RetrievalRaw    float64 `json:"retrieval_raw"`
	TargetCoverage  float64 `json:"target_coverage"`
	MatchSimilarity float64 `json:"match_similarity"`
}

type Clarification struct {
	Required bool                  `json:"required"`
	Prompt   string                `json:"prompt"`
	TopK     int                   `json:"top_k"`
	Options  []ClarificationOption `json:"options"`
}

type ClarificationOption struct {
	ID             string  `json:"id"`
	Rank           int     `json:"rank"`
	Label          string  `json:"label"`
	SelectionQuery string  `json:"selection_query"`
	Similarity     float64 `json:"similarity"`
	ContentType    string  `json:"content_type"`
}

type Chunk struct {
	ChunkID     string         `json:"chunk_id"`
	DocumentID  string         `json:"document_id"`
	ContentType string         `json:"content_type"`
	ContentText string         `json:"content_text"`
	HeadingPath []string       `json:"heading_path"`
	Facts       map[string]any `json:"facts"`
}

type Citation struct {
	CitationID  string   `json:"citation_id"`
	ChunkID     string   `json:"chunk_id"`
	SourceFile  string   `json:"source_file"`
	SourceURI   string   `json:"source_uri"`
	LineStart   *int     `json:"line_start"`
	LineEnd     *int     `json:"line_end"`
	PageStart   *int     `json:"page_start"`
	HeadingPath []string `json:"heading_path"`
	LegalBasis  any      `json:"legal_basis"`
}

type Fallback struct {
	Action  string `json:"action"`
	Message string `json:"message"`
}

type ContextRequest struct {
	ChunkID string `json:"chunk_id"`
	Scope   string `json:"scope"`
	Limit   int    `json:"limit"`
}

type ContextResult struct {
	SchemaVersion string         `json:"schema_version"`
	Status        string         `json:"status"`
	AnchorChunkID string         `json:"anchor_chunk_id"`
	Scope         string         `json:"scope,omitempty"`
	Chunks        []ContextChunk `json:"chunks"`
	Citations     []Citation     `json:"citations"`
}

type ContextChunk struct {
	ChunkID     string         `json:"chunk_id"`
	DocumentID  string         `json:"document_id"`
	SectionID   string         `json:"section_id"`
	ContentType string         `json:"content_type"`
	ContentText string         `json:"content_text"`
	HeadingPath []string       `json:"heading_path"`
	Facts       map[string]any `json:"facts"`
	SourceFile  string         `json:"source_file"`
	LineStart   *int           `json:"line_start"`
	LineEnd     *int           `json:"line_end"`
}

type CatalogResult struct {
	SchemaVersion string            `json:"schema_version"`
	Sources       []KnowledgeSource `json:"sources"`
}

type KnowledgeSource struct {
	DocumentID     string   `json:"document_id"`
	Title          string   `json:"title"`
	DocumentType   string   `json:"document_type,omitempty"`
	SourceFile     string   `json:"source_file"`
	SourceURI      string   `json:"source_uri,omitempty"`
	VersionID      string   `json:"version_id,omitempty"`
	Status         string   `json:"status"`
	ApprovalStatus string   `json:"approval_status"`
	EffectiveFrom  string   `json:"effective_from,omitempty"`
	EffectiveTo    string   `json:"effective_to,omitempty"`
	ContentTypes   []string `json:"content_types"`
}

func (client *Client) Retrieve(ctx context.Context, query string, topK int) (*RetrievalResult, error) {
	if client == nil || client.http == nil {
		return nil, fmt.Errorf("RAG client is not initialized")
	}
	query = strings.TrimSpace(query)
	if query == "" {
		return nil, fmt.Errorf("RAG query must not be empty")
	}
	if topK < 1 {
		topK = 8
	}
	if topK > 10 {
		topK = 10
	}
	body, err := json.Marshal(retrievalRequest{Query: query, TopK: topK})
	if err != nil {
		return nil, fmt.Errorf("encode RAG request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, client.baseURL+"/api/v1/rag/retrieve", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create RAG request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("call RAG service: %w", err)
	}
	defer resp.Body.Close()
	limited := io.LimitReader(resp.Body, maxResponseBytes+1)
	responseBody, err := io.ReadAll(limited)
	if err != nil {
		return nil, fmt.Errorf("read RAG response: %w", err)
	}
	if len(responseBody) > maxResponseBytes {
		return nil, fmt.Errorf("RAG response exceeds %d bytes", maxResponseBytes)
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("RAG service returned HTTP %d", resp.StatusCode)
	}
	var result RetrievalResult
	if err := json.Unmarshal(responseBody, &result); err != nil {
		return nil, fmt.Errorf("decode RAG response: %w", err)
	}
	if err := result.Validate(); err != nil {
		return nil, fmt.Errorf("invalid RAG evidence response: %w", err)
	}
	return &result, nil
}

func (client *Client) ExpandContext(ctx context.Context, chunkID, scope string, limit int) (*ContextResult, error) {
	chunkID = strings.TrimSpace(chunkID)
	if chunkID == "" {
		return nil, fmt.Errorf("RAG context chunk_id must not be empty")
	}
	if scope != "document" {
		scope = "section"
	}
	if limit < 1 {
		limit = 20
	}
	if limit > 50 {
		limit = 50
	}
	body, err := json.Marshal(ContextRequest{ChunkID: chunkID, Scope: scope, Limit: limit})
	if err != nil {
		return nil, fmt.Errorf("encode RAG context request: %w", err)
	}
	var result ContextResult
	if err := client.doJSON(ctx, http.MethodPost, "/api/v1/rag/context", body, &result); err != nil {
		return nil, err
	}
	if result.SchemaVersion != "heartcare.rag.context.v1" {
		return nil, fmt.Errorf("unsupported RAG context schema_version %q", result.SchemaVersion)
	}
	if result.Status == "exact" && len(result.Chunks) == 0 {
		return nil, fmt.Errorf("exact RAG context contains no chunks")
	}
	return &result, nil
}

func (client *Client) Catalog(ctx context.Context) (*CatalogResult, error) {
	var result CatalogResult
	if err := client.doJSON(ctx, http.MethodGet, "/api/v1/rag/catalog", nil, &result); err != nil {
		return nil, err
	}
	if result.SchemaVersion != "heartcare.rag.catalog.v1" {
		return nil, fmt.Errorf("unsupported RAG catalog schema_version %q", result.SchemaVersion)
	}
	return &result, nil
}

func (client *Client) doJSON(ctx context.Context, method, path string, body []byte, target any) error {
	if client == nil || client.http == nil {
		return fmt.Errorf("RAG client is not initialized")
	}
	req, err := http.NewRequestWithContext(ctx, method, client.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create RAG request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := client.http.Do(req)
	if err != nil {
		return fmt.Errorf("call RAG service: %w", err)
	}
	defer resp.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes+1))
	if err != nil {
		return fmt.Errorf("read RAG response: %w", err)
	}
	if len(responseBody) > maxResponseBytes {
		return fmt.Errorf("RAG response exceeds %d bytes", maxResponseBytes)
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("RAG service returned HTTP %d", resp.StatusCode)
	}
	if err := json.Unmarshal(responseBody, target); err != nil {
		return fmt.Errorf("decode RAG response: %w", err)
	}
	return nil
}

func (client *Client) Health(ctx context.Context) error {
	if client == nil || client.http == nil {
		return fmt.Errorf("RAG client is not initialized")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, client.baseURL+"/health", nil)
	if err != nil {
		return err
	}
	resp, err := client.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("RAG health returned HTTP %d", resp.StatusCode)
	}
	return nil
}

func (result *RetrievalResult) Validate() error {
	if result == nil {
		return fmt.Errorf("empty result")
	}
	if result.SchemaVersion != contractVersion {
		return fmt.Errorf("unsupported schema_version %q", result.SchemaVersion)
	}
	switch result.Answerability.Status {
	case "exact", "approximate":
		if len(result.Evidence) == 0 {
			return fmt.Errorf("status %q requires evidence", result.Answerability.Status)
		}
	case "insufficient", "blocked":
	default:
		return fmt.Errorf("unknown answerability status %q", result.Answerability.Status)
	}
	allowed := make(map[string]struct{}, len(result.GenerationPolicy.AllowedEvidenceIDs))
	for _, id := range result.GenerationPolicy.AllowedEvidenceIDs {
		allowed[id] = struct{}{}
	}
	chunkIDs := make(map[string]struct{}, len(result.Evidence))
	for _, item := range result.Evidence {
		if item.EvidenceID == "" || item.Chunk.ChunkID == "" || strings.TrimSpace(item.Chunk.ContentText) == "" {
			return fmt.Errorf("evidence contains an empty id, chunk id, or content")
		}
		if _, ok := allowed[item.EvidenceID]; !ok {
			return fmt.Errorf("evidence %q is not allowed by generation policy", item.EvidenceID)
		}
		chunkIDs[item.Chunk.ChunkID] = struct{}{}
	}
	for _, citation := range result.Citations {
		if _, ok := chunkIDs[citation.ChunkID]; !ok {
			return fmt.Errorf("citation %q references an unretrieved chunk", citation.CitationID)
		}
	}
	if result.Answerability.Status == "approximate" && (!result.GenerationPolicy.Disclosure.Required || strings.TrimSpace(result.GenerationPolicy.Disclosure.Text) == "") {
		return fmt.Errorf("approximate result requires a disclosure")
	}
	if result.Answerability.Status == "approximate" {
		if !result.Clarification.Required || strings.TrimSpace(result.Clarification.Prompt) == "" {
			return fmt.Errorf("approximate result requires clarification")
		}
		if len(result.Clarification.Options) < 1 || len(result.Clarification.Options) > 5 {
			return fmt.Errorf("approximate clarification requires between 1 and 5 options")
		}
		for _, option := range result.Clarification.Options {
			if strings.TrimSpace(option.Label) == "" || strings.TrimSpace(option.SelectionQuery) == "" {
				return fmt.Errorf("clarification option has an empty label or selection query")
			}
			if option.Similarity < 0.80 || option.Similarity > 1.0 {
				return fmt.Errorf("clarification option similarity %.3f is outside [0.80, 1.0]", option.Similarity)
			}
		}
	}
	return nil
}

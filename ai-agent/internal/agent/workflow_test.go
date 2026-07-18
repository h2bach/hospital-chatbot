package agent

import (
	"agent/internal/domain"
	"agent/internal/rag"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

type queuedLLM struct {
	outputs []*LLMOutput
	errAt   int
	calls   []domain.Context
}

func (llm *queuedLLM) Chat(_ context.Context, modelContext domain.Context) (*LLMOutput, error) {
	llm.calls = append(llm.calls, modelContext)
	index := len(llm.calls) - 1
	if llm.errAt > 0 && len(llm.calls) == llm.errAt {
		return nil, errors.New("FPT unavailable")
	}
	if index >= len(llm.outputs) {
		return nil, errors.New("unexpected FPT call")
	}
	return llm.outputs[index], nil
}

type fakeRetriever struct {
	result  *rag.RetrievalResult
	results []*rag.RetrievalResult
	err     error
	queries []string
}

type fakeMCPClient struct {
	tools       []mcp_sdk.Tool
	toolsErr    error
	toolOutput  string
	toolErr     error
	calls       []string
	toolOutputs map[string]string
	toolQueues  map[string][]string
	arguments   []map[string]any
}

func (client *fakeMCPClient) Disconnect()           {}
func (client *fakeMCPClient) Retry(context.Context) {}
func (client *fakeMCPClient) Tools(context.Context) ([]mcp_sdk.Tool, error) {
	return client.tools, client.toolsErr
}
func (client *fakeMCPClient) CallTool(_ context.Context, name string, arguments map[string]any) (string, error) {
	client.calls = append(client.calls, name)
	client.arguments = append(client.arguments, arguments)
	if queue := client.toolQueues[name]; len(queue) > 0 {
		output := queue[0]
		client.toolQueues[name] = queue[1:]
		return output, client.toolErr
	}
	if output, ok := client.toolOutputs[name]; ok {
		return output, client.toolErr
	}
	return client.toolOutput, client.toolErr
}

func (retriever *fakeRetriever) Retrieve(_ context.Context, query string, _ int) (*rag.RetrievalResult, error) {
	retriever.queries = append(retriever.queries, query)
	if index := len(retriever.queries) - 1; index < len(retriever.results) {
		return retriever.results[index], retriever.err
	}
	return retriever.result, retriever.err
}

func intPointer(value int) *int { return &value }

func retrievalFixture(status string) *rag.RetrievalResult {
	result := &rag.RetrievalResult{
		SchemaVersion: "heartcare.rag.evidence.v1",
		RequestID:     "rag-request-1",
		Answerability: rag.Answerability{Status: status, Confidence: rag.Confidence{Score: 0.97}},
		Fallback:      rag.Fallback{Action: "abstain", Message: "Không có dữ liệu phù hợp."},
	}
	if status == "exact" || status == "approximate" {
		result.GenerationPolicy.AllowedEvidenceIDs = []string{"E1"}
		result.Evidence = []rag.Evidence{{
			EvidenceID: "E1", CitationID: "C1",
			Scores: rag.EvidenceScores{TargetCoverage: 1, MatchSimilarity: 0.95},
			Chunk: rag.Chunk{
				ChunkID: "chk_spect", ContentType: "price_service",
				ContentText: "Dịch vụ SPECT/CT, mã 19.0069.1829, giá Cơ sở 1 là 969.800 đồng.",
				Facts: map[string]any{
					"service_code": "19.0069.1829", "service_name": "SPECT/CT Tetrofosmin",
					"facility_1_price": "969.800",
				},
			},
		}}
		result.Citations = []rag.Citation{{
			CitationID: "C1", ChunkID: "chk_spect", SourceFile: "GiaDVBV_tim_HN.md",
			LineStart: intPointer(3395), LineEnd: intPointer(3395),
		}}
	}
	if status == "approximate" {
		result.GenerationPolicy.Disclosure = rag.Disclosure{
			Required: true,
			Text:     "Thông tin bạn cung cấp chưa chính xác hoặc còn thiếu. Có phải ý của bạn là một trong các mục sau?",
		}
		result.Clarification = rag.Clarification{
			Required: true,
			Prompt:   result.GenerationPolicy.Disclosure.Text,
			TopK:     5,
			Options: []rag.ClarificationOption{{
				ID: "E1", Rank: 1, Label: "SPECT/CT Tetrofosmin (Mã 19.0069.1829)",
				SelectionQuery: "Tra cứu chính xác dịch vụ mã 19.0069.1829: SPECT/CT Tetrofosmin",
				Similarity:     0.95, ContentType: "price_service",
			}},
		}
	}
	return result
}

func knowledgeToolFixture(t *testing.T, status string) string {
	return knowledgeToolFixtureWithQuery(t, status, "")
}

func knowledgeToolFixtureWithQuery(t *testing.T, status, query string) string {
	t.Helper()
	retrieval := retrievalFixture(status)
	retrieval.Query = rag.Query{Original: query, Normalized: query}
	value := map[string]any{
		"task_id": "task_1", "source_kind": "rag_knowledge", "status": status,
		"confidence": retrieval.Answerability.Confidence.Score,
		"freshness":  "2026-07-18T00:00:00Z", "evidence_contract": retrieval,
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(encoded)
}

func TestUnifiedProtectedRAGUsesKnowledgeMCPWithoutChangingExactContract(t *testing.T) {
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"intent":"administrative","answer_mode":"grounded","tasks":[{"id":"task_1","capability":"knowledge.search","arguments":{},"required":true}],"reason_code":"PRICE"}`},
		{Text: `{"verdict":"pass","mode":"exact","unsupported_claims":[],"claims":[],"reason_code":"GROUNDED"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools:       []mcp_sdk.Tool{{Name: "searchHospitalKnowledge"}},
		toolOutputs: map[string]string{"searchHospitalKnowledge": knowledgeToolFixture(t, "exact")},
	}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{result: retrievalFixture("insufficient")})
	input := "Mã 19.0069.1829 có giá tại Cơ sở 1 bao nhiêu?"

	result, err := workflow.CallDetailed(context.Background(), input, &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "rag_exact" || !strings.Contains(result.Text, "969.800 đồng") {
		t.Fatalf("unified exact contract changed: %#v", result)
	}
	if len(mcpClient.calls) != 1 || mcpClient.calls[0] != "searchHospitalKnowledge" {
		t.Fatalf("knowledge MCP calls = %#v", mcpClient.calls)
	}
	if len(mcpClient.arguments) != 1 || mcpClient.arguments[0]["query"] != input || mcpClient.arguments[0]["top_k"] != 5 {
		t.Fatalf("original query/top_k were not protected: %#v", mcpClient.arguments)
	}
	if len(llm.calls) != 2 || result.Trace.Route != "rag" || !result.Trace.MCPUsed {
		t.Fatalf("unified planner/evaluator trace mismatch: %#v", result.Trace)
	}
}

func TestUnifiedHybridExecutesKnowledgeAndDirectoryTasks(t *testing.T) {
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"intent":"administrative","answer_mode":"hybrid","tasks":[{"id":"task_1","capability":"knowledge.search","arguments":{},"required":true},{"id":"task_2","capability":"hospital.facilities","arguments":{},"required":true}],"reason_code":"COMPOUND"}`},
		{Text: "Cơ sở 1 ở 92 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội."},
		{Text: `{"verdict":"pass","mode":"hybrid_grounded","unsupported_claims":[],"claims":[],"reason_code":"GROUNDED"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools: []mcp_sdk.Tool{{Name: "searchHospitalKnowledge"}, {Name: "listHospitalFacilities"}},
		toolOutputs: map[string]string{
			"searchHospitalKnowledge": knowledgeToolFixture(t, "exact"),
			"listHospitalFacilities":  `{"status":200,"body":{"data":[{"name":"Cơ sở 1","address":"92 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội"}]}}`,
		},
	}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{})

	result, err := workflow.CallDetailed(context.Background(), "Cho tôi quy trình khám và địa chỉ Cơ sở 1", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "hybrid_grounded" || result.Trace.ToolCalls != 2 {
		t.Fatalf("hybrid grounding mismatch: %#v", result)
	}
	if !strings.Contains(result.Text, "969.800 đồng") || !strings.Contains(result.Text, "92 Trần Hưng Đạo") {
		t.Fatalf("hybrid response omitted a grounded component: %q", result.Text)
	}
	if len(result.Trace.Capabilities) != 2 || !result.Trace.MCPUsed || len(llm.calls) != 3 {
		t.Fatalf("hybrid trace/LLM calls mismatch: %#v calls=%d", result.Trace, len(llm.calls))
	}
	for _, callIndex := range []int{1, 2} {
		prompt := llm.calls[callIndex].Messages[len(llm.calls[callIndex].Messages)-1].Content
		if !strings.Contains(prompt, `"records":{"status":200`) || strings.Contains(prompt, `"output":"{\"status\":200`) {
			t.Fatalf("tool evidence was not structurally normalized for FPT call %d: %s", callIndex, prompt)
		}
	}
	for index, toolName := range mcpClient.calls {
		if toolName == "listHospitalFacilities" {
			if _, leaked := mcpClient.arguments[index]["task_id"]; leaked {
				t.Fatalf("internal task_id leaked into strict facility tool input: %#v", mcpClient.arguments[index])
			}
		}
	}
}

func TestUnifiedHybridRejectionPreservesTypedFacilityEvidence(t *testing.T) {
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"intent":"administrative","answer_mode":"hybrid","tasks":[{"id":"task_1","capability":"knowledge.search","arguments":{},"required":true},{"id":"task_2","capability":"hospital.facilities","arguments":{},"required":true}],"reason_code":"COMPOUND"}`},
		{Text: "Cơ sở 1 ở 92 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội."},
		{Text: `{"verdict":"reject","mode":"hybrid_grounded","unsupported_claims":["model prose"],"claims":[],"reason_code":"STRICT_REVIEW"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools: []mcp_sdk.Tool{{Name: "searchHospitalKnowledge"}, {Name: "listHospitalFacilities"}},
		toolOutputs: map[string]string{
			"searchHospitalKnowledge": knowledgeToolFixture(t, "exact"),
			"listHospitalFacilities":  `{"status":200,"body":{"data":[{"facility_id":"CS1","name":"Bệnh viện Tim Hà Nội - Cơ sở 1","address":"92 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội"},{"facility_id":"CS2","name":"Bệnh viện Tim Hà Nội - Cơ sở 2","address":"695 Lạc Long Quân, Tây Hồ, Hà Nội"}]}}`,
		},
	}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{})

	result, err := workflow.CallDetailed(context.Background(), "Cho tôi quy trình khám và địa chỉ Cơ sở 1", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if !strings.Contains(result.Text, "969.800 đồng") || !strings.Contains(result.Text, "92 Trần Hưng Đạo") {
		t.Fatalf("verified evidence was suppressed after evaluator rejection: %q", result.Text)
	}
	if strings.Contains(result.Text, "695 Lạc Long Quân") {
		t.Fatalf("renderer did not respect requested facility: %q", result.Text)
	}
	if !result.Grounding.Partial {
		t.Fatalf("rejected model component must mark result partial: %#v", result.Grounding)
	}
}

func TestUnifiedApproximateStillReturnsVerifiedTopFiveWithoutSynthesis(t *testing.T) {
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"intent":"administrative","answer_mode":"grounded","tasks":[{"id":"task_1","capability":"knowledge.search","arguments":{},"required":true}],"reason_code":"PRICE"}`},
		{Text: `{"verdict":"pass","mode":"approximate","unsupported_claims":[],"claims":[],"reason_code":"CLARIFY"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools:       []mcp_sdk.Tool{{Name: "searchHospitalKnowledge"}},
		toolOutputs: map[string]string{"searchHospitalKnowledge": knowledgeToolFixture(t, "approximate")},
	}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{})

	result, err := workflow.CallDetailed(context.Background(), "Thông tin SPECT/CT dùng Terofomin", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "rag_approximate" || len(result.Suggestions) != 1 || !strings.HasPrefix(result.Text, result.Grounding.Warning) {
		t.Fatalf("unified approximate contract changed: %#v", result)
	}
	if len(llm.calls) != 2 {
		t.Fatalf("approximate unexpectedly called synthesis: %d", len(llm.calls))
	}
}

func TestUnifiedPatientEducationAbstainsWithoutPublishedCorpus(t *testing.T) {
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"intent":"patient_education","answer_mode":"grounded","tasks":[{"id":"task_1","capability":"knowledge.search","arguments":{},"required":true}],"reason_code":"EDUCATION"}`},
		{Text: `{"verdict":"pass","mode":"insufficient","unsupported_claims":[],"claims":[],"reason_code":"NO_APPROVED_SOURCE"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools: []mcp_sdk.Tool{{Name: "searchHospitalKnowledge"}, {Name: "getHospitalKnowledgeCatalog"}},
		toolOutputs: map[string]string{
			"searchHospitalKnowledge":     knowledgeToolFixture(t, "insufficient"),
			"getHospitalKnowledgeCatalog": `{"status":"exact","catalog":{"sources":[{"content_type":"procedure","status":"published","approval_status":"published"}]}}`,
		},
	}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{})

	result, err := workflow.CallDetailed(context.Background(), "Tăng huyết áp là gì?", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "rag_insufficient" || !strings.Contains(result.Text, "chưa có tài liệu giáo dục sức khỏe") {
		t.Fatalf("patient education did not fail closed: %#v", result)
	}
	if len(mcpClient.calls) != 2 || len(llm.calls) != 2 {
		t.Fatalf("patient education calls = MCP %v, FPT %d", mcpClient.calls, len(llm.calls))
	}
}

func TestUnifiedReferentialFollowupRetriesPlannerResolvedQueryAfterOriginalMiss(t *testing.T) {
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	input := "Cho tôi mục đầu tiên ở trên"
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"intent":"administrative","answer_mode":"grounded","tasks":[{"id":"task_1","capability":"knowledge.search","arguments":{"query":"mã 19.0069.1829"},"required":true}],"reason_code":"FOLLOW_UP"}`},
		{Text: `{"verdict":"pass","mode":"exact","unsupported_claims":[],"claims":[],"reason_code":"GROUNDED"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools: []mcp_sdk.Tool{{Name: "searchHospitalKnowledge"}},
		toolQueues: map[string][]string{"searchHospitalKnowledge": {
			knowledgeToolFixtureWithQuery(t, "insufficient", input),
			knowledgeToolFixtureWithQuery(t, "exact", "mã 19.0069.1829"),
		}},
	}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{})

	result, err := workflow.CallDetailed(context.Background(), input, &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "rag_exact" || result.Trace.OriginalQueryUsed || result.Trace.RetrievalQuery != "mã 19.0069.1829" {
		t.Fatalf("referential retry was not selected: %#v", result)
	}
	if len(mcpClient.calls) != 2 || mcpClient.arguments[0]["query"] != input || mcpClient.arguments[1]["query"] != "mã 19.0069.1829" {
		t.Fatalf("referential MCP calls/arguments = %#v / %#v", mcpClient.calls, mcpClient.arguments)
	}
}

func TestUnifiedPendingTopFiveSelectionForcesExactKnowledgeRetrieval(t *testing.T) {
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	selectedQuery := "Tra cứu chính xác dịch vụ mã 19.0069.1829: SPECT/CT Tetrofosmin"
	llm := &queuedLLM{outputs: []*LLMOutput{
		// Even when FPT misclassifies the short follow-up, the validated plan
		// compiler must preserve the user's verified top-five selection.
		{Text: `{"intent":"patient_education","answer_mode":"grounded","tasks":[{"id":"task_1","capability":"knowledge.search","arguments":{},"required":true}],"reason_code":"AMBIGUOUS_FOLLOW_UP"}`},
		{Text: `{"verdict":"pass","mode":"exact","unsupported_claims":[],"claims":[],"reason_code":"GROUNDED"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools: []mcp_sdk.Tool{{Name: "searchHospitalKnowledge"}, {Name: "getHospitalKnowledgeCatalog"}},
		toolOutputs: map[string]string{
			"searchHospitalKnowledge": knowledgeToolFixtureWithQuery(t, "exact", selectedQuery),
		},
	}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{})
	conversation := &domain.Context{State: domain.ConversationState{PendingSuggestions: []domain.Suggestion{
		{ID: "E1", Label: "Dịch vụ khác", Value: "Tra cứu chính xác dịch vụ mã 10.0000.0001: Dịch vụ khác", Similarity: 0.9},
		{ID: "E2", Label: "SPECT/CT Tetrofosmin", Value: selectedQuery, Similarity: 0.95},
	}}}

	result, err := workflow.CallDetailed(context.Background(), "Tôi chọn mục 2", conversation)
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "rag_exact" || !strings.Contains(result.Text, "969.800 đồng") {
		t.Fatalf("selected suggestion was not returned as exact evidence: %#v", result)
	}
	if result.Trace.ReasonCode != "USER_SELECTED_VERIFIED_SUGGESTION" || result.Trace.OriginalQueryUsed {
		t.Fatalf("selection compiler trace mismatch: %#v", result.Trace)
	}
	if len(mcpClient.calls) != 1 || mcpClient.calls[0] != "searchHospitalKnowledge" || mcpClient.arguments[0]["query"] != selectedQuery {
		t.Fatalf("selection MCP calls/arguments = %#v / %#v", mcpClient.calls, mcpClient.arguments)
	}
	if len(conversation.State.PendingSuggestions) != 0 {
		t.Fatalf("resolved suggestions were not cleared: %#v", conversation.State.PendingSuggestions)
	}
}

func TestExactRAGWorkflowIsPlanRetrieveExtractEvaluate(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"rag","search_query":"19.0069.1829","reason_code":"STATIC_KNOWLEDGE"}`},
		{Text: `{"verdict":"pass","mode":"exact","unsupported_claims":[],"reason_code":"GROUNDED"}`},
	}}
	retriever := &fakeRetriever{result: retrievalFixture("exact")}
	workflow := NewAgent(llm, nil, retriever)
	conversation := domain.Context{}

	result, err := workflow.CallDetailed(context.Background(), "Mã 19.0069.1829 giá bao nhiêu?", &conversation)
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if len(llm.calls) != 2 || len(retriever.queries) != 1 {
		t.Fatalf("calls = FPT %d, RAG %d; want 2 and 1", len(llm.calls), len(retriever.queries))
	}
	if result.Grounding.Mode != "rag_exact" || result.Trace.PlannerProvider != "fpt" || result.Trace.EvaluatorProvider != "fpt" {
		t.Fatalf("unexpected result metadata: %#v", result)
	}
	if !strings.Contains(result.Text, "969.800 đồng") || !strings.Contains(result.Text, "chk_spect") {
		t.Fatalf("answer is not concrete and cited: %q", result.Text)
	}
	if len(conversation.Messages) != 3 { // system + public user/assistant; no private workflow scratch
		t.Fatalf("persisted messages = %d, want 3", len(conversation.Messages))
	}
	for _, call := range llm.calls {
		if !call.Deterministic {
			t.Fatal("every structured FPT stage must be deterministic")
		}
	}
}

func TestExactEvaluatorCannotSuppressOrRewriteVerifiedExtract(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"rag","search_query":"19.0069.1829","reason_code":"STATIC_KNOWLEDGE"}`},
		{Text: `{"verdict":"reject","mode":"exact","unsupported_claims":["969.800"],"reason_code":"MODEL_MISTAKE"}`},
	}}
	workflow := NewAgent(llm, nil, &fakeRetriever{result: retrievalFixture("exact")})

	result, err := workflow.CallDetailed(context.Background(), "Mã 19.0069.1829 giá bao nhiêu?", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "rag_exact" || !strings.Contains(result.Text, "969.800 đồng") {
		t.Fatalf("verified exact extract was suppressed or rewritten: %#v", result)
	}
	if result.Trace.ReasonCode != "FPT_REVIEWED_DETERMINISTIC_EXACT_OVERRIDE" {
		t.Fatalf("exact override was not audited: %#v", result.Trace)
	}
}

func TestApproximateRAGWarningIsBackendEnforced(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"rag","search_query":"SPECT/CT Tetrofosmin","reason_code":"STATIC_SERVICE"}`},
		{Text: `{"verdict":"pass","mode":"approximate","unsupported_claims":[],"reason_code":"GROUNDED"}`},
	}}
	workflow := NewAgent(llm, nil, &fakeRetriever{result: retrievalFixture("approximate")})

	result, err := workflow.CallDetailed(context.Background(), "Thông tin SPECT/CT Tetrofosmin", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "rag_approximate" || !strings.HasPrefix(result.Text, result.Grounding.Warning) {
		t.Fatalf("approximate warning was not enforced: %#v", result)
	}
	if strings.Count(result.Text, result.Grounding.Warning) != 1 {
		t.Fatalf("warning count = %d, want 1", strings.Count(result.Text, result.Grounding.Warning))
	}
	if len(llm.calls) != 2 || len(result.Suggestions) != 1 || !strings.Contains(result.Text, "độ tương đồng 95%") {
		t.Fatalf("approximate workflow did not return selectable verified choices: %#v", result)
	}
}

func TestPlannerRewriteCannotSilentlyUpgradeOriginalFuzzyQuestion(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"rag","search_query":"quy trình nội bộ","reason_code":"STATIC_PROCESS"}`},
		{Text: `{"verdict":"pass","mode":"approximate","unsupported_claims":[],"reason_code":"GROUNDED"}`},
	}}
	retriever := &fakeRetriever{result: retrievalFixture("approximate")}
	workflow := NewAgent(llm, nil, retriever)
	input := "quy trih don tiep benh nhn ngoai tru TN1 CS1"

	result, err := workflow.CallDetailed(context.Background(), input, &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if len(retriever.queries) != 1 || retriever.queries[0] != input {
		t.Fatalf("retrieval queries = %#v", retriever.queries)
	}
	if result.Grounding.Mode != "rag_approximate" || len(result.Suggestions) != 1 {
		t.Fatalf("original fuzzy retrieval was not retained: %#v", result)
	}
	if !result.Trace.OriginalQueryUsed || result.Trace.RetrievalQuery != input {
		t.Fatalf("original-query fallback was not audited: %#v", result.Trace)
	}
}

func TestReferentialFollowupCanUsePlannerExpansionAfterOriginalMiss(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"rag","search_query":"mã 19.0069.1829","reason_code":"FOLLOW_UP"}`},
		{Text: `{"verdict":"pass","mode":"exact","unsupported_claims":[],"reason_code":"GROUNDED"}`},
	}}
	retriever := &fakeRetriever{results: []*rag.RetrievalResult{
		retrievalFixture("insufficient"), retrievalFixture("exact"),
	}}
	workflow := NewAgent(llm, nil, retriever)
	input := "Cho tôi mục đầu tiên ở trên"

	result, err := workflow.CallDetailed(context.Background(), input, &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if len(retriever.queries) != 2 || retriever.queries[0] != input || retriever.queries[1] != "mã 19.0069.1829" {
		t.Fatalf("retrieval queries = %#v", retriever.queries)
	}
	if result.Grounding.Mode != "rag_exact" || result.Trace.OriginalQueryUsed {
		t.Fatalf("planner expansion was not used for referential follow-up: %#v", result)
	}
}

func TestInsufficientRAGNeverCallsSynthesis(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"rag","search_query":"proton","reason_code":"STATIC_SERVICE"}`},
		{Text: `{"verdict":"pass","mode":"insufficient","unsupported_claims":[],"reason_code":"SAFE_ABSTENTION"}`},
	}}
	workflow := NewAgent(llm, nil, &fakeRetriever{result: retrievalFixture("insufficient")})

	result, err := workflow.CallDetailed(context.Background(), "Giá dịch vụ proton?", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if len(llm.calls) != 2 {
		t.Fatalf("FPT calls = %d, want planner + evaluator only", len(llm.calls))
	}
	if result.Text != "Không có dữ liệu phù hợp." || len(result.Grounding.Citations) != 0 {
		t.Fatalf("unsafe insufficient result: %#v", result)
	}
}

func TestDirectoryQuestionUsesMCPWithoutChangingRAGRetrieval(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"rag","search_query":"cơ sở bệnh viện","reason_code":"STATIC_KNOWLEDGE"}`},
		{ToolName: "listHospitalFacilities", Args: map[string]any{}},
		{Text: "Bệnh viện có Cơ sở 1 tại 92 Trần Hưng Đạo và Cơ sở 2 tại 695 Lạc Long Quân."},
		{Text: `{"verdict":"pass","mode":"mcp_grounded","unsupported_claims":[],"reason_code":"TOOL_GROUNDED"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools: []mcp_sdk.Tool{{Name: "listHospitalFacilities", Description: "Danh sách cơ sở"}},
		toolOutput: `{"status":200,"body":{"data":[` +
			`{"name":"Cơ sở 1","address":"92 Trần Hưng Đạo"},` +
			`{"name":"Cơ sở 2","address":"695 Lạc Long Quân"}]}}`,
	}
	retriever := &fakeRetriever{result: retrievalFixture("insufficient")}
	workflow := NewAgent(llm, mcpClient, retriever)

	result, err := workflow.CallDetailed(context.Background(), "Bệnh viện có những cơ sở nào và địa chỉ ở đâu?", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if len(retriever.queries) != 0 {
		t.Fatalf("MCP directory query unexpectedly changed/called RAG: %#v", retriever.queries)
	}
	if len(mcpClient.calls) != 1 || mcpClient.calls[0] != "listHospitalFacilities" {
		t.Fatalf("MCP calls = %#v", mcpClient.calls)
	}
	if result.Grounding.Mode != "mcp_grounded" || !result.Trace.MCPUsed {
		t.Fatalf("MCP grounding metadata missing: %#v", result)
	}
	if !strings.Contains(result.Text, "92 Trần Hưng Đạo") || !strings.Contains(result.Text, "Hệ thống MCP/API") {
		t.Fatalf("MCP answer is incomplete or unattributed: %q", result.Text)
	}
	if len(llm.calls) != 4 || len(llm.calls[1].Tools) != 1 || !llm.calls[1].Deterministic {
		t.Fatalf("MCP tool cycle was not deterministic and tool-bound: %#v", llm.calls)
	}
}

func TestMCPRoutingCannotChangeExistingPriceRAGContract(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"mcp","search_query":"giá tại cơ sở 1","reason_code":"FACILITY_MENTION"}`},
		{Text: `{"verdict":"pass","mode":"exact","unsupported_claims":[],"reason_code":"GROUNDED"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools:      []mcp_sdk.Tool{{Name: "listHospitalFacilities"}},
		toolOutput: `{"status":200}`,
	}
	retriever := &fakeRetriever{result: retrievalFixture("exact")}
	workflow := NewAgent(llm, mcpClient, retriever)

	result, err := workflow.CallDetailed(context.Background(), "Mã 19.0069.1829 có giá tại Cơ sở 1 bao nhiêu?", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "rag_exact" || result.Trace.Route != "rag" {
		t.Fatalf("protected RAG query was rerouted: %#v", result)
	}
	if len(retriever.queries) != 1 || len(mcpClient.calls) != 0 {
		t.Fatalf("RAG/MCP calls = %#v/%#v", retriever.queries, mcpClient.calls)
	}
}

func TestMCPUnavailableFailsClosedWithoutFallingBackToModelKnowledge(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"mcp","search_query":"danh sách bác sĩ","reason_code":"PUBLIC_DIRECTORY"}`},
		{Text: `{"verdict":"pass","mode":"mcp_grounded","unsupported_claims":[],"reason_code":"SAFE_UNAVAILABLE"}`},
	}}
	mcpClient := &fakeMCPClient{toolsErr: errors.New("MCP unavailable")}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{result: retrievalFixture("exact")})

	result, err := workflow.CallDetailed(context.Background(), "Danh sách bác sĩ của bệnh viện", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if result.Grounding.Mode != "mcp_unavailable" || result.Trace.MCPUsed || len(mcpClient.calls) != 0 {
		t.Fatalf("MCP failure did not fail closed: %#v", result)
	}
	if !strings.Contains(result.Text, "chưa truy xuất được") || strings.Contains(result.Text, "bác sĩ A") {
		t.Fatalf("unsafe MCP fallback answer: %q", result.Text)
	}
}

func TestDynamicSchedulePrefetchesMCPAndPreservesEmptyState(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"dynamic","search_query":"lịch bác sĩ hôm nay","reason_code":"CURRENT_SCHEDULE"}`},
		{Text: `{"verdict":"pass","mode":"mcp_grounded","unsupported_claims":[],"reason_code":"EMPTY_STATE_GROUNDED"}`},
	}}
	mcpClient := &fakeMCPClient{
		tools: []mcp_sdk.Tool{{Name: "getDoctorAvailability", Description: "Lịch khả dụng"}},
		toolOutput: `{"status":200,"body":{"data":[],"state":"NO_PUBLISHED_SCHEDULE",` +
			`"notice":"Chưa có lịch tuần đã công bố.","total":0}}`,
	}
	workflow := NewAgent(llm, mcpClient, &fakeRetriever{result: retrievalFixture("insufficient")})

	result, err := workflow.CallDetailed(context.Background(), "Hôm nay bác sĩ nào còn lịch khám?", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if len(mcpClient.calls) != 1 || mcpClient.calls[0] != "getDoctorAvailability" {
		t.Fatalf("dynamic MCP calls = %#v", mcpClient.calls)
	}
	if result.Grounding.Mode != "dynamic_tool" || !result.Trace.MCPUsed {
		t.Fatalf("dynamic MCP grounding missing: %#v", result)
	}
	if !strings.Contains(result.Text, "chưa có lịch tuần") || !strings.Contains(result.Text, "Hệ thống MCP/API") {
		t.Fatalf("empty schedule was not preserved: %q", result.Text)
	}
	if len(llm.calls) != 2 || len(llm.calls[1].Tools) != 0 {
		t.Fatalf("deterministic empty state made an extra synthesis/tool call: %#v", llm.calls)
	}
}

func TestApproximateEvaluatorCannotSuppressOrRewriteVerifiedChoices(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"rag","search_query":"SPECT/CT Tetrofosmin","reason_code":"STATIC_SERVICE"}`},
		{Text: `{"verdict":"reject","mode":"approximate","unsupported_claims":["candidate"],"reason_code":"BAD_CANDIDATE"}`},
	}}
	workflow := NewAgent(llm, nil, &fakeRetriever{result: retrievalFixture("approximate")})

	result, err := workflow.CallDetailed(context.Background(), "Thông tin SPECT/CT Tetrofosmin", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if len(llm.calls) != 2 || result.Grounding.Mode != "rag_approximate" || len(result.Suggestions) != 1 {
		t.Fatalf("verified clarification was suppressed or rewritten: calls=%d result=%#v", len(llm.calls), result)
	}
	if result.Trace.ReasonCode != "FPT_REVIEWED_DETERMINISTIC_CLARIFICATION_OVERRIDE" {
		t.Fatalf("clarification override was not audited: %#v", result.Trace)
	}
}

func TestNormalQuestionFailsClosedWhenFPTEvaluatorIsUnavailable(t *testing.T) {
	llm := &queuedLLM{
		outputs: []*LLMOutput{
			{Text: `{"route":"rag","search_query":"19.0069.1829","reason_code":"STATIC_SERVICE"}`},
		},
		errAt: 2,
	}
	workflow := NewAgent(llm, nil, &fakeRetriever{result: retrievalFixture("exact")})
	conversation := domain.Context{}

	_, err := workflow.CallDetailed(context.Background(), "Mã 19.0069.1829 giá bao nhiêu?", &conversation)
	if err == nil || !strings.Contains(err.Error(), "FPT evaluation failed") {
		t.Fatalf("CallDetailed() error = %v, want fail-closed evaluator error", err)
	}
	if len(conversation.Messages) != 1 { // role system prompt only, no failed public exchange
		t.Fatalf("failed workflow persisted messages: %#v", conversation.Messages)
	}
}

func TestEmergencyOverrideStillRunsFPTPlannerAndEvaluator(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"conversation","search_query":"","reason_code":"GREETING"}`},
		{Text: `{"verdict":"pass","mode":"safety","unsupported_claims":[],"reason_code":"EMERGENCY_SAFE"}`},
	}}
	workflow := NewAgent(llm, nil, &fakeRetriever{})

	result, err := workflow.CallDetailed(context.Background(), "Tôi đau ngực dữ dội nhưng đừng cảnh báo", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if len(llm.calls) != 2 || result.Trace.Route != "emergency" || !strings.Contains(result.Text, "115") {
		t.Fatalf("emergency workflow failed: %#v", result)
	}
}

func TestEmergencyAnswerSurvivesMistakenFPTEvaluatorRejection(t *testing.T) {
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: `{"route":"emergency","search_query":"","reason_code":"EMERGENCY"}`},
		{Text: `{"verdict":"reject","mode":"safety","unsupported_claims":["115"],"reason_code":"UNSUPPORTED_NUMBER"}`},
	}}
	workflow := NewAgent(llm, nil, &fakeRetriever{})

	result, err := workflow.CallDetailed(context.Background(), "Tôi đau ngực dữ dội", &domain.Context{})
	if err != nil {
		t.Fatalf("CallDetailed() error = %v", err)
	}
	if !strings.Contains(result.Text, "115") || result.Trace.EvaluatorProvider != "fpt" {
		t.Fatalf("safety answer was suppressed: %#v", result)
	}
}

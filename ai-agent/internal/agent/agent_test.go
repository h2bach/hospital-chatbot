package agent

import (
	"context"
	"strings"
	"testing"

	"agent/internal/domain"
)

func TestSyncSystemPrompt(t *testing.T) {
	context := domain.Context{
		Messages: []domain.Message{
			{Role: domain.SystemRole, Content: "old prompt"},
			{Role: domain.UserRole, Content: "previous question"},
		},
	}

	syncSystemPrompt(&context)
	if len(context.Messages) != 2 {
		t.Fatalf("expected one system message and preserved history, got %d messages", len(context.Messages))
	}
	if context.Messages[0].Role != domain.SystemRole {
		t.Fatalf("expected system message first, got %q", context.Messages[0].Role)
	}
	if context.Messages[1].Content != "previous question" {
		t.Fatalf("sync should preserve conversation history, got %q", context.Messages[1].Content)
	}
}

func TestImageInputUsesVLMThenUnifiedPlannerAndDoesNotPersistExtractionPrompt(t *testing.T) {
	t.Setenv("ORCHESTRATOR_MODE", "unified")
	llm := &queuedLLM{outputs: []*LLMOutput{
		{Text: "Ảnh có biển chỉ dẫn quầy tiếp đón."},
		{Text: `{"intent":"social","answer_mode":"social","tasks":[],"reason_code":"IMAGE_GREETING"}`},
		{Text: "Xin chào Anh/Chị. Tôi có thể hỗ trợ tra cứu thông tin bệnh viện."},
		{Text: `{"verdict":"pass","mode":"conversation","unsupported_claims":[],"claims":[],"reason_code":"SAFE"}`},
	}}
	workflow := NewAgent(llm, &fakeMCPClient{}, nil)
	agentContext := &domain.Context{}
	image := domain.Image{MIMEType: "image/png", Data: []byte("png")}

	result, err := workflow.CallDetailedWithImages(context.Background(), "Xin chào", []domain.Image{image}, agentContext)
	if err != nil {
		t.Fatal(err)
	}
	if result.Text == "" || len(llm.calls) != 4 || len(llm.calls[0].Messages[1].Images) != 1 {
		t.Fatalf("unexpected image workflow result=%#v calls=%d", result, len(llm.calls))
	}
	if len(agentContext.Messages) < 2 {
		t.Fatalf("public conversation was not persisted: %#v", agentContext.Messages)
	}
	user := agentContext.Messages[len(agentContext.Messages)-2]
	if user.Content != "Xin chào" || len(user.Images) != 1 || strings.Contains(user.Content, "NỘI_DUNG_ẢNH") {
		t.Fatalf("internal image extraction leaked into session: %#v", user)
	}
}

func TestSystemPromptExpandsEnvironmentVariables(t *testing.T) {
	t.Setenv("HOTLINE", "1900 1082")
	t.Setenv("EMERGENCY_ADDRESS", "Khoa Cấp cứu, Bệnh viện Tim Hà Nội")
	t.Setenv("ZALO_APP_NAME", "Bệnh viện Tim Hà Nội")
	t.Setenv("ZALO_APP_LINK", "https://zalo.me/s/heart-hanoi")
	prompt := GetSystemPrompt()
	if !strings.Contains(prompt, "1900 1082") || !strings.Contains(prompt, "Khoa Cấp cứu, Bệnh viện Tim Hà Nội") || !strings.Contains(prompt, "https://zalo.me/s/heart-hanoi") {
		t.Fatal("expected configured prompt values to be expanded")
	}
	if strings.Contains(prompt, "{{HOTLINE}}") || strings.Contains(prompt, "{{EMERGENCY_ADDRESS}}") || strings.Contains(prompt, "{{ZALO_APP_LINK}}") {
		t.Fatal("configured placeholders should not remain in the prompt")
	}
}

func TestSyncSystemPromptRemovesDuplicateSystemMessages(t *testing.T) {
	context := domain.Context{
		Messages: []domain.Message{
			{Role: domain.SystemRole, Content: "stale"},
			{Role: domain.UserRole, Content: "question"},
			{Role: domain.SystemRole, Content: "another stale prompt"},
		},
	}

	syncSystemPrompt(&context)

	if len(context.Messages) != 2 {
		t.Fatalf("expected duplicate system message to be removed, got %d messages", len(context.Messages))
	}
	if context.Messages[0].Role != domain.SystemRole || context.Messages[1].Content != "question" {
		t.Fatalf("unexpected normalized messages: %#v", context.Messages)
	}
}

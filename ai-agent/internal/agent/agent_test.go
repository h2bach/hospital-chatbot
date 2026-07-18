package agent

import (
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

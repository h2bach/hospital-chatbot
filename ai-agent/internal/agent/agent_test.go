package agent

import (
	"strings"
	"testing"

	"agent/internal/domain"
)

func TestSyncSystemPromptUsesCurrentRole(t *testing.T) {
	context := domain.Context{
		UserRole: "guardian",
		Messages: []domain.Message{
			{Role: domain.SystemRole, Content: "old prompt"},
			{Role: domain.UserRole, Content: "previous question"},
		},
	}

	syncSystemPrompt(&context)
	guardianPrompt := context.Messages[0].Content
	if guardianPrompt == "old prompt" || !strings.Contains(guardianPrompt, "người nhà") {
		t.Fatalf("expected guardian-specific system prompt, got %q", guardianPrompt)
	}

	context.UserRole = "staff"
	syncSystemPrompt(&context)

	if len(context.Messages) != 2 {
		t.Fatalf("expected one system message and preserved history, got %d messages", len(context.Messages))
	}
	if context.Messages[0].Role != domain.SystemRole {
		t.Fatalf("expected system message first, got %q", context.Messages[0].Role)
	}
	if context.Messages[0].Content == guardianPrompt || !strings.Contains(context.Messages[0].Content, "nhân viên") {
		t.Fatalf("expected staff-specific system prompt after role switch, got %q", context.Messages[0].Content)
	}
	if context.Messages[1].Content != "previous question" {
		t.Fatalf("role switch should preserve conversation history, got %q", context.Messages[1].Content)
	}
}

func TestSyncSystemPromptRemovesDuplicateSystemMessages(t *testing.T) {
	context := domain.Context{
		UserRole: "admin",
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

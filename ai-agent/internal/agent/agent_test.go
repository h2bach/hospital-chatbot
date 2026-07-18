package agent

import (
	"strings"
	"testing"

	"agent/internal/domain"
)

func TestSyncSystemPromptUsesCurrentRole(t *testing.T) {
	context := domain.Context{
		Role: domain.PatientAccessRole,
		Messages: []domain.Message{
			{Role: domain.SystemRole, Content: "old prompt"},
			{Role: domain.UserRole, Content: "previous question"},
		},
	}

	syncSystemPrompt(&context)
	guardianPrompt := context.Messages[0].Content
	if guardianPrompt == "old prompt" || !strings.Contains(guardianPrompt, "PATIENT") {
		t.Fatalf("expected patient-specific system prompt, got %q", guardianPrompt)
	}

	context.Role = domain.DoctorAccessRole
	syncSystemPrompt(&context)

	if len(context.Messages) != 2 {
		t.Fatalf("expected one system message and preserved history, got %d messages", len(context.Messages))
	}
	if context.Messages[0].Role != domain.SystemRole {
		t.Fatalf("expected system message first, got %q", context.Messages[0].Role)
	}
	if context.Messages[0].Content == guardianPrompt || !strings.Contains(context.Messages[0].Content, "DOCTOR") {
		t.Fatalf("expected doctor-specific system prompt after role switch, got %q", context.Messages[0].Content)
	}
	if context.Messages[1].Content != "previous question" {
		t.Fatalf("role switch should preserve conversation history, got %q", context.Messages[1].Content)
	}
}

func TestSystemPromptsAreDistinctForAccessRoles(t *testing.T) {
	roles := []domain.AccessRole{
		domain.GuestAccessRole,
		domain.PatientAccessRole,
		domain.DoctorAccessRole,
		domain.AdminAccessRole,
	}
	for _, role := range roles {
		prompt := GetSystemPromptForRole(string(role))
		if !strings.Contains(prompt, "ACTIVE ACCESS ROLE: "+string(role)) {
			t.Errorf("prompt for %s does not identify the active role", role)
		}
	}
	if GetSystemPromptForRole("GUEST") == GetSystemPromptForRole("PATIENT") {
		t.Fatal("guest and patient prompts must differ")
	}
}

func TestSystemPromptExpandsEnvironmentVariables(t *testing.T) {
	t.Setenv("HOTLINE", "1900 1082")
	t.Setenv("EMERGENCY_ADDRESS", "Khoa Cấp cứu, Bệnh viện Tim Hà Nội")
	prompt := GetSystemPromptForRole("GUEST")
	if !strings.Contains(prompt, "1900 1082") || !strings.Contains(prompt, "Khoa Cấp cứu, Bệnh viện Tim Hà Nội") {
		t.Fatal("expected configured prompt values to be expanded")
	}
	if strings.Contains(prompt, "{{HOTLINE}}") || strings.Contains(prompt, "{{EMERGENCY_ADDRESS}}") {
		t.Fatal("configured placeholders should not remain in the prompt")
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

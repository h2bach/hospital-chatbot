package llm

import "testing"

func TestFPTToolChoiceDefaultsToAutoForGroundedAnswers(t *testing.T) {
	t.Setenv("FPT_TOOL_CHOICE", "")
	if choice := configuredFPTToolChoice(); choice != "auto" {
		t.Fatalf("tool choice=%q, want auto", choice)
	}
}

func TestFPTToolChoiceAllowsLegacyRollback(t *testing.T) {
	t.Setenv("FPT_TOOL_CHOICE", "none")
	if choice := configuredFPTToolChoice(); choice != "none" {
		t.Fatalf("tool choice=%q, want none", choice)
	}
}

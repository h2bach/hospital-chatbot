package llm

import (
	"context"
	"strings"
	"testing"
)

func configureFPTEnvironment(t *testing.T) {
	t.Helper()
	t.Setenv("FPT_API_KEYS", "fpt-one,fpt-two")
	t.Setenv("FPT_API_KEY", "")
	t.Setenv("FPT_MODEL", "fpt-model")
	t.Setenv("FPT_BASE_URL", "https://fpt.example.test")
}

func TestNewFromEnvironmentReturnsMandatoryFPTClient(t *testing.T) {
	configureFPTEnvironment(t)
	t.Setenv("LLM_PROVIDERS", "")
	t.Setenv("LLM_PROVIDER", "")

	model, err := NewFromEnvironment(context.Background())
	if err != nil {
		t.Fatalf("NewFromEnvironment() error = %v", err)
	}
	client, ok := model.(*FPTClient)
	if !ok {
		t.Fatalf("NewFromEnvironment() type = %T, want *FPTClient", model)
	}
	if client.Model != "fpt-model" || len(client.keys) != 2 {
		t.Fatalf("FPT client = model %q, keys %d", client.Model, len(client.keys))
	}
}

func TestNewFromEnvironmentAllowsExplicitFPTOnly(t *testing.T) {
	configureFPTEnvironment(t)
	t.Setenv("LLM_PROVIDERS", " FPT; fpt ")
	t.Setenv("LLM_PROVIDER", "gemini") // LLM_PROVIDERS has precedence.

	model, err := NewFromEnvironment(context.Background())
	if err != nil {
		t.Fatalf("NewFromEnvironment() error = %v", err)
	}
	if _, ok := model.(*FPTClient); !ok {
		t.Fatalf("NewFromEnvironment() type = %T, want *FPTClient", model)
	}
}

func TestNewFromEnvironmentRejectsNonFPTSelection(t *testing.T) {
	configureFPTEnvironment(t)
	tests := []struct {
		name      string
		providers string
		provider  string
	}{
		{name: "gemini", provider: "gemini"},
		{name: "mixed", providers: "fpt,gemini"},
		{name: "unknown", provider: "local"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Setenv("LLM_PROVIDERS", test.providers)
			t.Setenv("LLM_PROVIDER", test.provider)
			_, err := NewFromEnvironment(context.Background())
			if err == nil || !strings.Contains(err.Error(), "FPT is mandatory") {
				t.Fatalf("NewFromEnvironment() error = %v", err)
			}
		})
	}
}

func TestNewFromEnvironmentTreatsWhitespaceProviderListAsAbsent(t *testing.T) {
	configureFPTEnvironment(t)
	t.Setenv("LLM_PROVIDERS", "   ")
	t.Setenv("LLM_PROVIDER", "gemini")

	_, err := NewFromEnvironment(context.Background())
	if err == nil || !strings.Contains(err.Error(), "FPT is mandatory") {
		t.Fatalf("NewFromEnvironment() error = %v", err)
	}
}

func TestNewFromEnvironmentDoesNotFallBackToGeminiCredentials(t *testing.T) {
	t.Setenv("LLM_PROVIDERS", "")
	t.Setenv("LLM_PROVIDER", "")
	t.Setenv("FPT_API_KEYS", "")
	t.Setenv("FPT_API_KEY", "")
	t.Setenv("FPT_MODEL", "fpt-model")
	t.Setenv("GEMINI_API_KEY", "gemini-key")

	_, err := NewFromEnvironment(context.Background())
	if err == nil || !strings.Contains(err.Error(), "no FPT API keys") {
		t.Fatalf("NewFromEnvironment() error = %v", err)
	}
}

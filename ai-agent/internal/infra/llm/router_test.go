package llm

import (
	"context"
	"errors"
	"testing"

	"agent/internal/agent"
	"agent/internal/domain"
)

type failingLLM struct {
	calls int
	err   error
}

func (f *failingLLM) Chat(context.Context, domain.Context) (*agent.LLMOutput, error) {
	f.calls++
	return nil, f.err
}

type successfulLLM struct {
	calls int
}

func (s *successfulLLM) Chat(context.Context, domain.Context) (*agent.LLMOutput, error) {
	s.calls++
	return &agent.LLMOutput{Text: "Gemini fallback response"}, nil
}

func TestRouterFallsBackToGeminiAfterFPTImageFailure(t *testing.T) {
	fpt := &failingLLM{err: errors.New("FPT VLM request failed")}
	gemini := &successfulLLM{}
	router, err := NewRouter(fpt, gemini)
	if err != nil {
		t.Fatalf("NewRouter() error = %v", err)
	}

	output, err := router.Chat(context.Background(), domain.Context{
		Messages: []domain.Message{{
			Role:   domain.UserRole,
			Images: []domain.Image{{MIMEType: "image/png", Data: []byte("png")}},
		}},
	})
	if err != nil {
		t.Fatalf("Chat() error = %v", err)
	}
	if output == nil || output.Text != "Gemini fallback response" {
		t.Fatalf("Chat() output = %#v, want Gemini fallback response", output)
	}
	if fpt.calls != 1 || gemini.calls != 1 {
		t.Fatalf("provider calls = FPT %d, Gemini %d; want 1 each", fpt.calls, gemini.calls)
	}
}

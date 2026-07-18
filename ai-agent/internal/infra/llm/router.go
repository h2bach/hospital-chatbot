package llm

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync/atomic"

	"agent/internal/agent"
	"agent/internal/domain"
)

// Router distributes requests across configured providers and fails over to
// the remaining providers when one is unavailable.
type Router struct {
	providers []agent.LLMClient
	next      atomic.Uint64
	active    atomic.Uint64 // provider index + 1 for the current tool cycle
}

func NewRouter(providers ...agent.LLMClient) (*Router, error) {
	if len(providers) == 0 {
		return nil, fmt.Errorf("no LLM providers configured")
	}
	return &Router{providers: providers}, nil
}

func (r *Router) Chat(ctx context.Context, context domain.Context) (*agent.LLMOutput, error) {
	continuingToolCycle := len(context.Messages) > 0 && context.Messages[len(context.Messages)-1].Role == domain.ToolRole
	start := r.next.Add(1) - 1
	if continuingToolCycle {
		if active := r.active.Load(); active > 0 {
			start = active - 1
		}
	}
	providerErrors := make([]error, 0, len(r.providers))
	for offset := range r.providers {
		index := (start + uint64(offset)) % uint64(len(r.providers))
		output, err := r.providers[index].Chat(ctx, context)
		if err == nil {
			r.active.Store(index + 1)
			return output, nil
		}
		providerErrors = append(providerErrors, err)
	}
	return nil, fmt.Errorf("all LLM providers failed: %w", errors.Join(providerErrors...))
}

func configuredProviders(value string) []string {
	parts := strings.FieldsFunc(strings.ToLower(value), func(r rune) bool {
		return r == ',' || r == ';' || r == '\n' || r == '\r'
	})
	result := make([]string, 0, len(parts))
	seen := map[string]bool{}
	for _, part := range parts {
		provider := strings.TrimSpace(part)
		if provider == "" || seen[provider] {
			continue
		}
		seen[provider] = true
		result = append(result, provider)
	}
	return result
}

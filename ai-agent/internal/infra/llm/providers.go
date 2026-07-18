package llm

import (
	"context"
	"fmt"
	"os"
	"strings"

	"agent/internal/agent"
)

// NewFromEnvironment builds the production inference client. FPT is the
// mandatory control-plane provider: a deployment must not silently switch to
// another model when FPT planning or evaluation is unavailable.
//
// LLM_PROVIDER and LLM_PROVIDERS are retained only to detect stale or unsafe
// configuration. When present, they must select FPT exclusively.
func NewFromEnvironment(ctx context.Context) (agent.LLMClient, error) {
	_ = ctx // Kept in the public signature for callers and future initialization.

	providerList := strings.TrimSpace(os.Getenv("LLM_PROVIDERS"))
	if providerList == "" {
		providerList = strings.TrimSpace(os.Getenv("LLM_PROVIDER"))
	}
	if providerList != "" {
		providers := configuredProviders(providerList)
		if len(providers) != 1 || providers[0] != "fpt" {
			return nil, fmt.Errorf("FPT is mandatory; LLM_PROVIDER(S) must select only %q", "fpt")
		}
	}

	keys := strings.TrimSpace(os.Getenv("FPT_API_KEYS"))
	if keys == "" {
		keys = os.Getenv("FPT_API_KEY")
	}
	client, err := NewFPTClient(keys, os.Getenv("FPT_MODEL"), os.Getenv("FPT_BASE_URL"))
	if err != nil {
		return nil, fmt.Errorf("configure mandatory FPT provider: %w", err)
	}
	return client, nil
}

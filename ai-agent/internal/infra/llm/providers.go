package llm

import (
	"context"
	"fmt"
	"os"
	"strings"

	"agent/internal/agent"
)

// NewFromEnvironment builds the configured provider set. LLM_PROVIDERS takes
// precedence and accepts values such as "gemini,fpt". LLM_PROVIDER remains a
// compatible alias for a single provider.
func NewFromEnvironment(ctx context.Context) (agent.LLMClient, error) {
	providerList := os.Getenv("LLM_PROVIDERS")
	if providerList == "" {
		providerList = os.Getenv("LLM_PROVIDER")
	}
	if strings.TrimSpace(providerList) == "" {
		providerList = "fpt"
	}

	providers := configuredProviders(providerList)
	clients := make([]agent.LLMClient, 0, len(providers))
	for _, provider := range providers {
		switch provider {
		case "gemini":
			keys := os.Getenv("GEMINI_API_KEYS")
			if keys == "" {
				keys = os.Getenv("GEMINI_API_KEY")
			}
			client, err := NewGeminiClientWithModel(ctx, keys, os.Getenv("GEMINI_MODEL"))
			if err != nil {
				return nil, fmt.Errorf("configure Gemini: %w", err)
			}
			clients = append(clients, client)
		case "fpt":
			keys := os.Getenv("FPT_API_KEYS")
			if keys == "" {
				keys = os.Getenv("FPT_API_KEY")
			}
			client, err := NewFPTClientWithVLM(keys, os.Getenv("FPT_MODEL"), os.Getenv("FPT_VLM_MODEL"), os.Getenv("FPT_BASE_URL"))
			if err != nil {
				return nil, fmt.Errorf("configure FPT: %w", err)
			}
			clients = append(clients, client)
		case "deepseek":
			keys := os.Getenv("DEEPSEEK_API_KEYS")
			if keys == "" {
				keys = os.Getenv("DEEPSEEK_API_KEY")
			}
			client, err := NewDeepSeekClientWithModel(keys, os.Getenv("DEEPSEEK_MODEL"), os.Getenv("DEEPSEEK_BASE_URL"))
			if err != nil {
				return nil, fmt.Errorf("configure DeepSeek: %w", err)
			}
			clients = append(clients, client)
		default:
			return nil, fmt.Errorf("unsupported LLM provider %q", provider)
		}
	}
	return NewRouter(clients...)
}

package agent

import (
	"agent/internal/domain"
	"context"
)

type LLMOutput struct {
	Text string
	ToolName string
	Args map[string]any
}

type LLMClient interface {
	 Chat(ctx context.Context, agentContext domain.Context) (*LLMOutput, error)
}

func IsText(output *LLMOutput) bool {
	return output.Text != ""
}

func IsToolCall(output *LLMOutput) bool {
	return output.ToolName != ""
}

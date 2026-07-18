package agent

import (
	"agent/internal/domain"
	"agent/internal/mcp"
	"context"
	"encoding/json"
	"fmt"
)

type Agent struct {
	LLM       LLMClient
	MCPClient *mcp.MCPClient
}

const maxModelTurns = 30

func NewAgent(llm LLMClient, mcpClient *mcp.MCPClient) *Agent {
	return &Agent{
		LLM:       llm,
		MCPClient: mcpClient,
	}
}

func (a *Agent) Call(ctx context.Context, input string, agentContext *domain.Context) (string, error) {
	return a.CallWithImages(ctx, input, nil, agentContext)
}

func (a *Agent) CallWithImages(ctx context.Context, input string, images []domain.Image, agentContext *domain.Context) (string, error) {
	tools, _ := a.MCPClient.Tools(ctx)
	agentContext.Tools = tools
	syncSystemPrompt(agentContext)

	// User initial input
	agentContext.Messages = append(agentContext.Messages, domain.Message{
		Role:    domain.UserRole,
		Content: input,
		Images:  images,
	})

	for turn := 0; turn < maxModelTurns; turn++ {
		a.MCPClient.Retry(ctx)
		chatOutput, err := a.LLM.Chat(ctx, *agentContext)
		if err != nil {
			return "", err
		}
		if chatOutput == nil {
			return "", fmt.Errorf("model returned an empty response")
		}

		if IsToolCall(chatOutput) {
			toolOutput, err := a.MCPClient.CallTool(ctx, chatOutput.ToolName, chatOutput.Args)
			agentContext.Messages = append(agentContext.Messages, domain.Message{
				Role:    domain.AgentRole,
				Content: fmt.Sprintf("Tool Call: %s\nArgs: %s", chatOutput.ToolName, marshalToolArgs(chatOutput.Args)),
			})
			toolMessage := domain.Message{
				Role: domain.ToolRole,
			}
			if err != nil {
				toolMessage.Content = err.Error()
			} else {
				toolMessage.Content = toolOutput
			}
			agentContext.Messages = append(agentContext.Messages, toolMessage)
			continue
		}

		if IsText(chatOutput) {
			agentContext.Messages = append(agentContext.Messages, domain.Message{
				Role:    domain.AgentRole,
				Content: chatOutput.Text,
			})
			return chatOutput.Text, nil
		}
	}

	return "", fmt.Errorf("model did not return a user-visible answer after %d turns", maxModelTurns)
}

func marshalToolArgs(args map[string]any) string {
	encoded, err := json.Marshal(args)
	if err != nil {
		return "{}"
	}
	return string(encoded)
}

func syncSystemPrompt(agentContext *domain.Context) {
	systemPrompt := GetSystemPrompt()
	messages := make([]domain.Message, 0, len(agentContext.Messages)+1)
	foundSystem := false

	for _, message := range agentContext.Messages {
		if message.Role == domain.SystemRole {
			if foundSystem {
				// A context should have one system prompt. Drop stale duplicates
				// that could otherwise override or confuse the active prompt.
				continue
			}
			message.Content = systemPrompt
			foundSystem = true
		}
		messages = append(messages, message)
	}

	if !foundSystem {
		messages = append([]domain.Message{{
			Role:    domain.SystemRole,
			Content: systemPrompt,
		}}, messages...)
	} else if messages[0].Role != domain.SystemRole {
		// Keep the system instruction first for providers that use message order
		// when constructing the conversation.
		for i, message := range messages {
			if message.Role == domain.SystemRole {
				reordered := make([]domain.Message, 0, len(messages))
				reordered = append(reordered, message)
				reordered = append(reordered, messages[:i]...)
				reordered = append(reordered, messages[i+1:]...)
				messages = reordered
				break
			}
		}
	}

	agentContext.Messages = messages
}

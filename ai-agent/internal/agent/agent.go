package agent

import (
	"agent/internal/domain"
	"agent/internal/mcp"
	"context"
	"fmt"
)

type Agent struct {
	LLM       LLMClient
	MCPClient *mcp.MCPClient
}

const maxModelTurns = 8

func NewAgent(llm LLMClient, mcpClient *mcp.MCPClient) *Agent {
	return &Agent{
		LLM:       llm,
		MCPClient: mcpClient,
	}
}

func (a *Agent) Call(ctx context.Context, input string, agentContext *domain.Context) (string, error) {
	tools, _ := a.MCPClient.Tools(ctx)
	if agentContext.Role == "" {
		if agentContext.UserRole != "" {
			agentContext.Role = NormalizeRole(agentContext.UserRole)
		} else {
			agentContext.Role = domain.GuestAccessRole
		}
	} else {
		agentContext.Role = NormalizeRole(string(agentContext.Role))
	}
	agentContext.UserRole = string(agentContext.Role)
	agentContext.Tools = toolsForRole(tools, agentContext.Role)
	// Keep exactly one system prompt, derived from the role currently attached to
	// this context. This also updates an existing session when its role changes.
	syncSystemPrompt(agentContext)

	// User initial input
	agentContext.Messages = append(agentContext.Messages, domain.Message{
		Role:    domain.UserRole,
		Content: input,
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
			if err := ensureToolAllowed(agentContext.Role, chatOutput.ToolName); err != nil {
				return "", err
			}
			toolOutput, err := a.MCPClient.CallTool(ctx, chatOutput.ToolName, chatOutput.Args)
			agentContext.Messages = append(agentContext.Messages, domain.Message{
				Role:    domain.AgentRole,
				Content: fmt.Sprintf("Tool Call: %s\nArgs: %s", chatOutput.ToolName, chatOutput.Args),
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

// syncSystemPrompt makes the role-specific prompt authoritative for every LLM
// call. Sessions are persisted between requests, so only adding the prompt
// when the context is empty would leave a stale prompt after a role switch.
func syncSystemPrompt(agentContext *domain.Context) {
	// Role is the authorization role used by the API and is also the role shown
	// in the UI. Prefer it so a role switch cannot update tools without updating
	// the system prompt. UserRole remains a compatibility fallback for older
	// persisted sessions and direct callers.
	role := string(agentContext.Role)
	if role == "" {
		role = agentContext.UserRole
	}
	systemPrompt := GetSystemPromptForRole(role)
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

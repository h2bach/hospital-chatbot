package agent

import (
	"agent/internal/domain"
	"agent/internal/mcp"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"
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
	response, err := a.CallDetailedWithImages(ctx, input, images, agentContext)
	if err != nil {
		return "", err
	}
	return response.Text, nil
}

func (a *Agent) CallDetailedWithImages(ctx context.Context, input string, images []domain.Image, agentContext *domain.Context) (AgentResponse, error) {
	tools, _ := a.MCPClient.Tools(ctx)
	agentContext.Tools = tools
	syncSystemPrompt(agentContext)
	ledger := newEvidenceLedger()
	indexedCitations := citationModeEnabled()

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
			return AgentResponse{}, err
		}
		if chatOutput == nil {
			return AgentResponse{}, fmt.Errorf("model returned an empty response")
		}
		if IsText(chatOutput) && !IsToolCall(chatOutput) {
			if inlineCall, ok := parseInlineToolCall(chatOutput.Text, agentContext.Tools); ok {
				inlineCall.ReasoningContent = chatOutput.ReasoningContent
				chatOutput = inlineCall
			}
		}

		if IsToolCall(chatOutput) {
			toolOutput, err := a.MCPClient.CallToolDetailed(ctx, chatOutput.ToolName, chatOutput.Args)
			agentContext.Messages = append(agentContext.Messages, domain.Message{
				Role:             domain.AgentRole,
				Content:          fmt.Sprintf("Tool Call: %s\nArgs: %s", chatOutput.ToolName, marshalToolArgs(chatOutput.Args)),
				ReasoningContent: chatOutput.ReasoningContent,
			})
			toolMessage := domain.Message{
				Role: domain.ToolRole,
			}
			if err != nil {
				toolMessage.Content = err.Error()
			} else if toolOutput.IsError {
				toolMessage.Content = toolOutput.Text
			} else if indexedCitations {
				evidence := mcp.NormalizeEvidence(chatOutput.ToolName, toolOutput, time.Now())
				evidence = ledger.add(evidence)
				log.Printf("agent evidence run_id=%s normalized=%d total=%d structured_fields=%s", ledger.runID, len(evidence), len(ledger.byID), strings.Join(mcp.StructuredFieldNames(toolOutput), ","))
				if len(evidence) > 0 {
					toolMessage.Content = mcp.FormatEvidenceForModel(evidence)
				} else {
					toolMessage.Content = toolOutput.Text
				}
			} else {
				toolMessage.Content = toolOutput.Text
			}
			agentContext.Messages = append(agentContext.Messages, toolMessage)
			continue
		}

		if IsText(chatOutput) {
			answerText := chatOutput.Text
			if indexedCitations && ledger.hasEvidence() {
				valid, invalid := citationTokenStats(answerText, ledger)
				if valid == 0 || invalid > 0 || hasUncitedFactualLines(answerText) {
					if clarification, ok := renderRAGClarification(ledger); ok {
						answerText = clarification
					} else {
						answerText = a.repairCitations(ctx, answerText, ledger, *agentContext)
					}
				}
			}
			response := AgentResponse{Text: answerText, RunID: ledger.runID}
			if indexedCitations {
				response = finalizeCitations(answerText, ledger)
				_, invalid := citationTokenStats(answerText, ledger)
				uncited := hasUncitedFactualLines(answerText)
				log.Printf("agent grounding run_id=%s evidence=%d citations=%d invalid=%d uncited=%t", ledger.runID, len(ledger.byID), len(response.Citations), invalid, uncited)
				if ledger.hasEvidence() && (len(response.Citations) == 0 || invalid > 0 || uncited) {
					response.Text = "Tôi đã tìm thấy dữ liệu liên quan nhưng chưa thể liên kết từng thông tin với nguồn một cách an toàn. Anh/chị vui lòng thử lại để hệ thống thực hiện tra cứu mới."
					response.Citations = nil
					response.CitationContexts = nil
				}
			}
			agentContext.Messages = append(agentContext.Messages, domain.Message{
				Role:             domain.AgentRole,
				Content:          response.Text,
				ReasoningContent: chatOutput.ReasoningContent,
				Citations:        response.Citations,
				RunID:            response.RunID,
			})
			return response, nil
		}
	}

	return AgentResponse{}, fmt.Errorf("model did not return a user-visible answer after %d turns", maxModelTurns)
}

func (a *Agent) repairCitations(ctx context.Context, draft string, ledger *evidenceLedger, current domain.Context) string {
	current.Tools = nil
	current.Messages = append(current.Messages,
		domain.Message{Role: domain.AgentRole, Content: draft},
		domain.Message{
			Role: domain.UserRole,
			Content: "Hãy trả lại nguyên câu trả lời vừa tạo nhưng sửa citation. Mỗi câu hoặc gạch đầu dòng dùng dữ kiện phải đặt ngay sau claim một hoặc nhiều token [[cite:evidence_id]]. Chỉ được dùng các evidence_id sau: " + strings.Join(ledger.ids(), ", ") + ". Không in tên tool, không in khối tổng hợp nguồn và không giải thích việc sửa.",
		},
	)
	output, err := a.LLM.Chat(ctx, current)
	if err != nil || !IsText(output) {
		return draft
	}
	return output.Text
}

func citationModeEnabled() bool {
	return !strings.EqualFold(strings.TrimSpace(os.Getenv("CITATION_MODE")), "legacy")
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

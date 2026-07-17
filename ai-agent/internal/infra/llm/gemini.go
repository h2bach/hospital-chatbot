package llm

import (
	"context"

	"agent/internal/agent"
	"agent/internal/domain"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
	"google.golang.org/genai"
)

type GeminiClient struct {
	GeminiAPIKey string
	genAIClient *genai.Client
}

func NewGeminiClient(ctx context.Context, apiKey string) (*GeminiClient, error) {
	cc := genai.ClientConfig{
		APIKey: apiKey,
	}
	client, err := genai.NewClient(ctx, &cc)
	if err != nil {
		return nil, err
	}

	geminiClient := GeminiClient{
		GeminiAPIKey: apiKey,
		genAIClient: client,
	}
	return &geminiClient, nil
}

func (client *GeminiClient) Chat(ctx context.Context, agentContext domain.Context) (*agent.LLMOutput, error) {
	contents := []*genai.Content{}
	for _, message := range agentContext.Messages {
		// Gemini does not have role "tool", so switch role to "user",
		// and indicates that the text is tool output
		if message.Role == domain.ToolRole {
			message.Role = domain.UserRole
			message.Content = "Tool output: " + message.Content
		}
		contents = append(
			contents,
			&genai.Content{
				Role: string(message.Role),
        		Parts: []*genai.Part{
					{Text: message.Content},
				},
			}, 
		)
	}

	chatResult, err := client.genAIClient.Models.GenerateContent(
		ctx,
		"gemini-3.1-flash-lite",
		contents,
		&genai.GenerateContentConfig{
			Tools: toolListAdapter(agentContext.Tools),
		},
	)
	if err != nil {
		return nil, err
	}

	result := agent.LLMOutput{}
	for _, part := range chatResult.Candidates[0].Content.Parts {
		switch {
		case part.Text != "":
			result.Text = part.Text
		case part.FunctionCall != nil:
			result.ToolName = part.FunctionCall.Name
			result.Args = part.FunctionCall.Args
		}
	}
	return &result, nil
}

func toolListAdapter(tools []mcp_sdk.Tool) []*genai.Tool {
	fnDecls := []*genai.FunctionDeclaration{}
	for _, tool := range tools {
		fnDecl := genai.FunctionDeclaration{
			Name: tool.Name,
			Description: tool.Description,
			ParametersJsonSchema: tool.InputSchema,
		}
		fnDecls = append(fnDecls, &fnDecl)
	}

	result := []*genai.Tool{{ FunctionDeclarations: fnDecls }}
	return result
}

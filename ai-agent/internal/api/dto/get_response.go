package dto

import (
	"agent/internal/domain"
)

type SessionMetadata struct {
	ID string `json:"id"`
	OwnerID string `json:"owner_id"`
	Title string `json:"title"`
}

type GetAllSessionsResponse struct {
	Sessions []SessionMetadata `json:"sessions"`
}

func NewGetAllSessionsResponse(sessions []domain.Session) *GetAllSessionsResponse {
	response := GetAllSessionsResponse{
		Sessions: make([]SessionMetadata, 0),
	}
	for _, session := range sessions {
		metadata := SessionMetadata {
			ID: session.ID,
			OwnerID: session.OwnerID,
			Title: session.Title,
		}
		response.Sessions = append(response.Sessions, metadata)
	}
	return &response
}

type SessionMessage struct {
	Role      domain.Role       `json:"Role"`
	Content   string            `json:"Content"`
	Images    []domain.Image    `json:"Images,omitempty"`
	Citations []domain.Citation `json:"citations,omitempty"`
	RunID     string            `json:"run_id,omitempty"`
}

type SessionContext struct {
	Messages []SessionMessage `json:"Messages"`
	Tools    []any            `json:"Tools"`
}

type SessionView struct {
	ID        string         `json:"ID"`
	Title     string         `json:"Title"`
	OwnerID   string         `json:"OwnerID"`
	CreatedAt any            `json:"CreatedAt"`
	UpdatedAt any            `json:"UpdatedAt"`
	Context   SessionContext `json:"Context"`
}

type GetSessionResponse struct {
	Session SessionView `json:"Session"`
}

func NewGetSessionReponse(session domain.Session) *GetSessionResponse {
	messages := make([]SessionMessage, 0, len(session.Context.Messages))
	for _, message := range session.Context.Messages {
		if message.Role != domain.UserRole && message.Role != domain.AgentRole {
			continue
		}
		if message.Role == domain.AgentRole && len(message.Content) >= len("Tool Call:") && message.Content[:len("Tool Call:")] == "Tool Call:" {
			continue
		}
		messages = append(messages, SessionMessage{
			Role: message.Role, Content: message.Content, Images: message.Images,
			Citations: message.Citations, RunID: message.RunID,
		})
	}
	return &GetSessionResponse{
		Session: SessionView{
			ID: session.ID, Title: session.Title, OwnerID: session.OwnerID,
			CreatedAt: session.CreatedAt, UpdatedAt: session.UpdatedAt,
			Context: SessionContext{Messages: messages, Tools: []any{}},
		},
	}
}

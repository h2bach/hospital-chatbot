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
			Title: session.Title,
		}
		response.Sessions = append(response.Sessions, metadata)
	}
	return &response
}

type GetSessionResponse struct {
	Session domain.Session
}

func NewGetSessionReponse(session domain.Session) *GetSessionResponse {
	return &GetSessionResponse{
		Session: session,
	}
}

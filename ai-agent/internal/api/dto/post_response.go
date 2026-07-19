package dto

import "agent/internal/domain"

type PostNewSessionResponse struct {
	SessionID string `json:"session_id"`
}

func NewPostNewSessionResponse(sessionID string) *PostNewSessionResponse {
	return &PostNewSessionResponse{
		SessionID: sessionID,
	}
}

type PostMessageResponse struct {
	Response  string            `json:"response"`
	RunID     string            `json:"run_id,omitempty"`
	Citations []domain.Citation `json:"citations,omitempty"`
}

func NewPostMessageResponse(response, runID string, citations []domain.Citation) *PostMessageResponse {
	return &PostMessageResponse{
		Response:  response,
		RunID:     runID,
		Citations: citations,
	}
}

package dto

import (
	"agent/internal/agent"
	"agent/internal/domain"
)

type PostNewSessionResponse struct {
	SessionID string `json:"session_id"`
}

func NewPostNewSessionResponse(sessionID string) *PostNewSessionResponse {
	return &PostNewSessionResponse{
		SessionID: sessionID,
	}
}

type PostMessageResponse struct {
	Response    string                  `json:"response"`
	Grounding   agent.Grounding         `json:"grounding"`
	Trace       agent.Trace             `json:"trace"`
	Suggestions []domain.Suggestion     `json:"suggestions,omitempty"`
	Sources     []agent.GroundingSource `json:"sources,omitempty"`
	Partial     bool                    `json:"partial,omitempty"`
	RunID       string                  `json:"run_id,omitempty"`
}

func NewPostMessageResponse(result *agent.Result) *PostMessageResponse {
	return &PostMessageResponse{
		Response: result.Text, Grounding: result.Grounding, Trace: result.Trace,
		Suggestions: result.Suggestions, Sources: result.Grounding.Sources,
		Partial: result.Grounding.Partial, RunID: result.Trace.RunID,
	}
}

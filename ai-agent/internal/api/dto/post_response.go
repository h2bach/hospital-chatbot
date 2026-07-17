package dto

type PostNewSessionResponse struct {
	SessionID string `json:"session_id"`
}

func NewPostNewSessionResponse(sessionID string) *PostNewSessionResponse {
	return &PostNewSessionResponse{
		SessionID: sessionID,
	}
}

type PostMessageResponse struct {
	Response string `json:"response"`
}

func NewPostMessageResponse(response string) *PostMessageResponse {
	return &PostMessageResponse{
		Response: response,
	}
}

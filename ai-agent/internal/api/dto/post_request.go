package dto

type PostMessageRequest struct {
	Message string `json:"message"`
}

func NewPostMessageRequest(message string) *PostMessageRequest {
	return &PostMessageRequest{
		Message: message,
	}
}

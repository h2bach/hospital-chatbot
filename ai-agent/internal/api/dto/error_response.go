package dto

type ErrorResponse struct {
	ErrorMessage string `json:"error"`
}

func NewErrorResponse(errorMessage string) *ErrorResponse {
	return &ErrorResponse{
		ErrorMessage: errorMessage,
	}
}

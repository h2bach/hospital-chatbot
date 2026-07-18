package dto

import (
	"encoding/base64"
	"fmt"
	"net/http"
	"strings"

	"agent/internal/domain"
)

const (
	maxImageBytes = 4 << 20
	maxImages     = 2
)

var validImageTypes = map[string]struct{}{
	"image/jpeg": {},
	"image/png":  {},
	"image/webp": {},
}

type PostMessageRequest struct {
	Message string       `json:"message"`
	Images  []ImageInput `json:"images,omitempty"`
}

type ImageInput struct {
	MIMEType string `json:"mime_type"`
	Data     string `json:"data"`
}

func NewPostMessageRequest(message string) *PostMessageRequest {
	return &PostMessageRequest{
		Message: message,
	}
}

func (req PostMessageRequest) DomainImages() ([]domain.Image, error) {
	if len(req.Images) > maxImages {
		return nil, fmt.Errorf("a maximum of %d images is allowed", maxImages)
	}
	images := make([]domain.Image, 0, len(req.Images))
	for _, input := range req.Images {
		mimeType := strings.ToLower(strings.TrimSpace(input.MIMEType))
		if _, ok := validImageTypes[mimeType]; !ok {
			return nil, fmt.Errorf("unsupported image type %q", input.MIMEType)
		}
		data, err := base64.StdEncoding.DecodeString(input.Data)
		if err != nil || len(data) == 0 {
			return nil, fmt.Errorf("image data must be valid base64")
		}
		if len(data) > maxImageBytes {
			return nil, fmt.Errorf("image exceeds the %d MB limit", maxImageBytes>>20)
		}
		if detected := http.DetectContentType(data); detected != mimeType && !(mimeType == "image/webp" && detected == "image/webp") {
			return nil, fmt.Errorf("image data does not match %s", mimeType)
		}
		images = append(images, domain.Image{MIMEType: mimeType, Data: data})
	}
	return images, nil
}

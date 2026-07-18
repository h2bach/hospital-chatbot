package dto

import (
	"encoding/base64"
	"testing"
)

func TestDomainImagesAcceptsPNG(t *testing.T) {
	data := base64.StdEncoding.EncodeToString([]byte("\x89PNG\r\n\x1a\nvalid"))
	images, err := (PostMessageRequest{Images: []ImageInput{{MIMEType: "image/png", Data: data}}}).DomainImages()
	if err != nil {
		t.Fatalf("DomainImages() error = %v", err)
	}
	if len(images) != 1 || images[0].MIMEType != "image/png" {
		t.Fatalf("DomainImages() = %#v, want one PNG", images)
	}
}

func TestDomainImagesRejectsUnsupportedOrMismatchedType(t *testing.T) {
	data := base64.StdEncoding.EncodeToString([]byte("not an image"))
	for _, mimeType := range []string{"application/pdf", "image/png"} {
		_, err := (PostMessageRequest{Images: []ImageInput{{MIMEType: mimeType, Data: data}}}).DomainImages()
		if err == nil {
			t.Fatalf("DomainImages() accepted %q", mimeType)
		}
	}
}

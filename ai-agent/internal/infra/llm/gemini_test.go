package llm

import (
	"reflect"
	"testing"
)

func TestParseAPIKeys(t *testing.T) {
	got := parseAPIKeys(" key-one, 'key-two'\nkey-one;\"key-three\" ")
	want := []string{"key-one", "key-two", "key-three"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("parseAPIKeys() = %#v, want %#v", got, want)
	}
}

func TestParseAPIKeysEmpty(t *testing.T) {
	if got := parseAPIKeys(" , ; \n"); len(got) != 0 {
		t.Fatalf("parseAPIKeys() = %#v, want no keys", got)
	}
}

func TestNewFPTClient(t *testing.T) {
	client, err := NewFPTClient("fpt-one, fpt-two", "model-name", "")
	if err != nil {
		t.Fatalf("NewFPTClient() error = %v", err)
	}
	if got, want := len(client.keys), 2; got != want {
		t.Fatalf("configured key count = %d, want %d", got, want)
	}
	if client.BaseURL != defaultFPTBaseURL {
		t.Fatalf("default FPT base URL = %q, want %q", client.BaseURL, defaultFPTBaseURL)
	}
}

func TestNewGeminiClientWithModel(t *testing.T) {
	client, err := NewGeminiClientWithModel(nil, "gemini-key", "gemini-custom")
	if err != nil {
		t.Fatalf("NewGeminiClientWithModel() error = %v", err)
	}
	if client.Model != "gemini-custom" {
		t.Fatalf("Gemini model = %q, want %q", client.Model, "gemini-custom")
	}
}

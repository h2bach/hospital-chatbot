package llm

import (
	"bytes"
	"encoding/json"
	"testing"
)

func TestFPTChatRequestDisablesAutomaticToolChoice(t *testing.T) {
	body, err := json.Marshal(fptChatRequest{
		Model:      "vision-model",
		Tools:      []fptToolWrapper{{Type: "function"}},
		ToolChoice: "none",
	})
	if err != nil {
		t.Fatalf("marshal request: %v", err)
	}
	if !bytes.Contains(body, []byte(`"tool_choice":"none"`)) {
		t.Fatalf("request body = %s, want tool_choice none", body)
	}
}

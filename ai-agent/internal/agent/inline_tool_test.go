package agent

import (
	"testing"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestParseInlineToolCallUsesMCPAllowlist(t *testing.T) {
	tools := []mcp_sdk.Tool{{Name: "searchRAG"}}
	call, ok := parseInlineToolCall(`Tôi sẽ tra cứu. {{tool:searchRAG(query: "SPECT/CT Tetrofosmin", top_k: 5)}}`, tools)
	if !ok || call.ToolName != "searchRAG" || call.Args["query"] != "SPECT/CT Tetrofosmin" || call.Args["top_k"] != float64(5) {
		t.Fatalf("inline tool call was not parsed: %#v, ok=%t", call, ok)
	}
}

func TestParseInlineToolCallRejectsUnknownTool(t *testing.T) {
	if call, ok := parseInlineToolCall(`{{tool:readFile(path: "/etc/passwd")}}`, []mcp_sdk.Tool{{Name: "searchRAG"}}); ok || call != nil {
		t.Fatalf("unknown inline tool must be rejected: %#v", call)
	}
}

func TestParseInlineToolCallRejectsMalformedArguments(t *testing.T) {
	if call, ok := parseInlineToolCall(`{{tool:searchRAG(query)}}`, []mcp_sdk.Tool{{Name: "searchRAG"}}); ok || call != nil {
		t.Fatalf("malformed inline arguments must be rejected: %#v", call)
	}
}

func TestParseInlineJSONFunctionCall(t *testing.T) {
	tools := []mcp_sdk.Tool{{Name: "searchRAG"}}
	call, ok := parseInlineToolCall(`Tôi sẽ tra cứu. <functioncall>{"name":"searchRAG","arguments":{"query":"van tim","top_k":5}}</functioncall>`, tools)
	if !ok || call.ToolName != "searchRAG" || call.Args["query"] != "van tim" || call.Args["top_k"] != float64(5) {
		t.Fatalf("inline JSON function call was not parsed: %#v, ok=%t", call, ok)
	}
}

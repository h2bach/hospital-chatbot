package agent

import (
	"encoding/json"
	"regexp"
	"strconv"
	"strings"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

var (
	inlineToolPattern = regexp.MustCompile(`(?s)\{\{\s*tool:([A-Za-z0-9_.-]+)\s*\((.*?)\)\s*\}\}`)
	functionCallPattern = regexp.MustCompile(`(?s)<\s*(?:functioncall|tool_call)\s*>\s*(\{.*\})\s*<\s*/\s*(?:functioncall|tool_call)\s*>`)
)

// parseInlineToolCall supports providers that expose a planned function call
// as a text directive instead of the standard tool_calls field. The tool must
// still be advertised by the active MCP session; unknown names are never run.
func parseInlineToolCall(text string, available []mcp_sdk.Tool) (*LLMOutput, bool) {
	match := inlineToolPattern.FindStringSubmatch(text)
	if len(match) == 3 {
		if !toolIsAvailable(match[1], available) {
			return nil, false
		}
		args, ok := parseInlineToolArguments(match[2])
		if !ok {
			return nil, false
		}
		return &LLMOutput{ToolName: match[1], Args: args}, true
	}

	jsonMatch := functionCallPattern.FindStringSubmatch(text)
	if len(jsonMatch) != 2 {
		return nil, false
	}
	var call struct {
		Name      string         `json:"name"`
		Arguments map[string]any `json:"arguments"`
	}
	if json.Unmarshal([]byte(jsonMatch[1]), &call) != nil || !toolIsAvailable(call.Name, available) {
		return nil, false
	}
	if call.Arguments == nil {
		call.Arguments = map[string]any{}
	}
	return &LLMOutput{ToolName: call.Name, Args: call.Arguments}, true
}

func toolIsAvailable(name string, available []mcp_sdk.Tool) bool {
	for _, tool := range available {
		if tool.Name == name {
			return true
		}
	}
	return false
}

func parseInlineToolArguments(raw string) (map[string]any, bool) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return map[string]any{}, true
	}
	if strings.HasPrefix(raw, "{") {
		var result map[string]any
		if json.Unmarshal([]byte(raw), &result) == nil {
			return result, true
		}
		return nil, false
	}

	result := map[string]any{}
	for _, part := range splitInlineArguments(raw) {
		key, encodedValue, ok := cutInlineArgument(part)
		if !ok {
			return nil, false
		}
		result[key] = decodeInlineValue(encodedValue)
	}
	return result, true
}

func splitInlineArguments(raw string) []string {
	result := make([]string, 0, 4)
	start, depth := 0, 0
	var quote rune
	escaped := false
	for index, current := range []rune(raw) {
		if escaped {
			escaped = false
			continue
		}
		if quote != 0 && current == '\\' {
			escaped = true
			continue
		}
		if current == '\'' || current == '"' {
			if quote == 0 {
				quote = current
			} else if quote == current {
				quote = 0
			}
			continue
		}
		if quote != 0 {
			continue
		}
		switch current {
		case '[', '{', '(':
			depth++
		case ']', '}', ')':
			if depth > 0 {
				depth--
			}
		case ',':
			if depth == 0 {
				result = append(result, strings.TrimSpace(string([]rune(raw)[start:index])))
				start = index + 1
			}
		}
	}
	result = append(result, strings.TrimSpace(string([]rune(raw)[start:])))
	return result
}

func cutInlineArgument(raw string) (string, string, bool) {
	if index := strings.Index(raw, ":"); index > 0 {
		key := strings.TrimSpace(raw[:index])
		value := strings.TrimSpace(raw[index+1:])
		if inlineIdentifier(key) && value != "" {
			return key, value, true
		}
	}
	return "", "", false
}

func inlineIdentifier(value string) bool {
	if value == "" {
		return false
	}
	for _, current := range value {
		if !((current >= 'a' && current <= 'z') || (current >= 'A' && current <= 'Z') || (current >= '0' && current <= '9') || current == '_') {
			return false
		}
	}
	return true
}

func decodeInlineValue(raw string) any {
	var decoded any
	if json.Unmarshal([]byte(raw), &decoded) == nil {
		return decoded
	}
	if len(raw) >= 2 && raw[0] == '\'' && raw[len(raw)-1] == '\'' {
		return strings.ReplaceAll(raw[1:len(raw)-1], `\'`, `'`)
	}
	if number, err := strconv.ParseFloat(raw, 64); err == nil {
		return number
	}
	return strings.TrimSpace(raw)
}

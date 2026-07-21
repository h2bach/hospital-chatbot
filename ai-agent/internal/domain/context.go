package domain

import (
	"time"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

type Role string

const (
	UserRole   Role = "User"
	SystemRole Role = "System"
	AgentRole  Role = "Assistant"
	ToolRole   Role = "Tool"
)

type Message struct {
	Role             Role
	Content          string
	ReasoningContent string
	Images           []Image
	Citations        []Citation `json:",omitempty"`
}

type Image struct {
	MIMEType string `json:"mime_type,omitempty"`
	Data     []byte `json:"data,omitempty"`
}

type Context struct {
	Messages []Message
	Tools    []mcp_sdk.Tool
}

type Session struct {
	ID        string
	Title     string
	OwnerID   string
	CreatedAt time.Time
	UpdatedAt time.Time
	Context   Context

	// CitationContexts stores the immutable evidence snapshot behind every
	// public citation ID handed to the client. Served only through the
	// dedicated citation-context endpoint, never inlined in session JSON.
	CitationContexts map[string]CitationContextSnapshot `json:"-"`
}

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
	ReasoningContent string `json:"-"`
	Images           []Image
	Citations        []Citation `json:"citations,omitempty"`
	RunID            string     `json:"run_id,omitempty"`
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
	// CitationContexts contains the immutable evidence snapshot used to build
	// citation popovers and context panels. It is deliberately excluded from
	// session JSON responses; callers can only request one authorized citation
	// through the dedicated context endpoint.
	CitationContexts map[string]CitationContextSnapshot `json:"-"`
}

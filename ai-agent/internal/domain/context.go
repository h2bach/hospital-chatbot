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
	Role        Role
	Content     string
	Images      []Image
	Suggestions []Suggestion `json:",omitempty"`
}

type Image struct {
	MIMEType string `json:"mime_type,omitempty"`
	Data     []byte `json:"data,omitempty"`
}

// Suggestion is a verified clarification action. Its Value is submitted as
// the next user query after the visitor chooses an approximate RAG result.
type Suggestion struct {
	ID         string  `json:"id"`
	Label      string  `json:"label"`
	Value      string  `json:"value"`
	Similarity float64 `json:"similarity"`
}

type Context struct {
	Messages []Message
	Tools    []mcp_sdk.Tool
	State    ConversationState `json:"state,omitempty"`
	// Deterministic is request-local. Planner/evaluator calls use temperature
	// zero without persisting this flag in a public session.
	Deterministic bool `json:"-"`
}

// ConversationState retains only short-lived public references. Dynamic facts
// are always retrieved again and never reused from this state as evidence.
type ConversationState struct {
	LastServiceCode    string       `json:"last_service_code,omitempty"`
	LastFacility       string       `json:"last_facility,omitempty"`
	LastDoctor         string       `json:"last_doctor,omitempty"`
	PendingSuggestions []Suggestion `json:"pending_suggestions,omitempty"`
	UnresolvedSlots    []string     `json:"unresolved_slots,omitempty"`
	LastSources        []string     `json:"last_sources,omitempty"`
	SafetyActive       bool         `json:"safety_active,omitempty"`
}

type Session struct {
	ID        string
	Title     string
	OwnerID   string
	CreatedAt time.Time
	UpdatedAt time.Time
	Context   Context
}

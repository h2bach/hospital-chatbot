package domain

import (
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
	Suggestions []Suggestion `json:",omitempty"`
}

// Suggestion is a verified RAG clarification action shown as a selectable
// choice in the chat UI. Value is sent as the user's next query when selected.
type Suggestion struct {
	ID         string  `json:"id"`
	Label      string  `json:"label"`
	Value      string  `json:"value"`
	Similarity float64 `json:"similarity"`
}

type Context struct {
	Messages []Message
	Tools    []mcp_sdk.Tool
	Role     AccessRole        `json:"role,omitempty"`
	UserRole string            `json:"user_role,omitempty"`
	State    ConversationState `json:"state,omitempty"`
	// Deterministic is an ephemeral model-call option. Planner and evaluator
	// contexts set it on a per-call context copy to force temperature zero. It
	// is excluded from the public JSON session contract.
	Deterministic bool `json:"-"`
}

// ConversationState stores only short-lived public reference information.
// It helps resolve follow-ups but never acts as factual evidence; dynamic facts
// are retrieved again on every turn.
type ConversationState struct {
	LastServiceCode    string       `json:"last_service_code,omitempty"`
	LastFacility       string       `json:"last_facility,omitempty"`
	LastDoctor         string       `json:"last_doctor,omitempty"`
	PendingSuggestions []Suggestion `json:"pending_suggestions,omitempty"`
	UnresolvedSlots    []string     `json:"unresolved_slots,omitempty"`
	LastSources        []string     `json:"last_sources,omitempty"`
	SafetyActive       bool         `json:"safety_active,omitempty"`
}

type AccessRole string

const (
	GuestAccessRole AccessRole = "GUEST"
)

type Session struct {
	ID      string
	Title   string
	OwnerID string
	Context Context
}

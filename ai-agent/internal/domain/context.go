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
	Role    Role
	Content string
}

type Context struct {
	Messages []Message
	Tools    []mcp_sdk.Tool
	Role     AccessRole
}

type AccessRole string

const (
	GuestAccessRole   AccessRole = "GUEST"
	PatientAccessRole AccessRole = "PATIENT"
	DoctorAccessRole  AccessRole = "DOCTOR"
	AdminAccessRole   AccessRole = "ADMIN"
)

type Session struct {
	ID      string
	Title   string
	OwnerID string
	Context Context
}

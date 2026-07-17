package agent

const (
	INITIAL_SYSTEM_PROMPT = 
`You are an AI agent with access to tools.

The conversation history and any tool results provided below are the complete context for this turn.

Reason step by step using the available context.

If additional information is required, call the appropriate tool.

When a tool result is returned, treat it as authoritative and continue reasoning from the updated conversation.

When you have enough information to satisfy the user's request, return a final answer instead of calling another tool.`
	TITLE_PROMPT = 
`Name this conversation in 3-8 words`
)

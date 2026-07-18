export type MessageRole = "User" | "Assistant" | "System" | "Tool"

export type AccessRole = "GUEST"

export type DeliveryState = "sending" | "failed"

export interface ChatSuggestion {
  id: string
  label: string
  value: string
  similarity: number
}

export interface ChatMessage {
  role: MessageRole
  content: string
  delivery?: DeliveryState
  suggestions?: ChatSuggestion[]
}

export interface SendMessageResult {
  answer: string
  suggestions: ChatSuggestion[]
}

export interface StreamStatus {
  phase: string
  label: string
}

export interface StreamHandlers {
  onStatus?: (status: StreamStatus) => void
  onDelta?: (text: string) => void
  onSuggestions?: (suggestions: ChatSuggestion[]) => void
}

export interface ChatSession {
  id: string
  title: string
  ownerId: string
  messages: ChatMessage[]
  tools: unknown[]
}

export interface SessionSummary {
  id: string
  ownerId: string
  title: string
}

export type ServerStatus = "checking" | "online" | "offline"

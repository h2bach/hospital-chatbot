export type MessageRole = "User" | "Assistant" | "System" | "Tool"



export type DeliveryState = "sending" | "failed"

export interface ChatMessage {
  role: MessageRole
  content: string
  delivery?: DeliveryState
  images?: ChatImage[]
}

export interface ChatImage {
  mimeType: "image/jpeg" | "image/png"
  data: string
  name?: string
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

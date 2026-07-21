export type MessageRole = "User" | "Assistant" | "System" | "Tool"

export type DeliveryState = "sending" | "failed"

export interface HighlightRange {
  start: number
  end: number
  label?: string
}

export interface CitationLocation {
  document_id?: string
  section?: string
  page?: number
  url?: string
}

export interface CitationFreshness {
  version?: string
  effective_at?: string
  observed_at?: string
  approval_status?: string
}

export interface CitationItem {
  id: string
  index: number
  source_kind: string
  title: string
  excerpt: string
  highlight_ranges: HighlightRange[]
  match_status: string
  confidence: number
  location?: CitationLocation
  freshness?: CitationFreshness
  context_available: boolean
}

export interface CitationField {
  label: string
  value: string
  highlighted?: boolean
}

export interface ContextBlock {
  id: string
  heading?: string
  text: string
  fields: CitationField[]
  is_anchor: boolean
  highlight_ranges: HighlightRange[]
}

export interface CitationContextResponse {
  citation: CitationItem
  blocks: ContextBlock[]
  warning?: string
}

export interface ChatMessage {
  role: MessageRole
  content: string
  delivery?: DeliveryState
  images?: ChatImage[]
  citations?: CitationItem[]
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

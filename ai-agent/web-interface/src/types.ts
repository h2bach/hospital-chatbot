export type MessageRole = "User" | "Assistant" | "System" | "Tool"

export type DeliveryState = "sending" | "failed"

export interface ChatMessage {
	role: MessageRole
	content: string
	delivery?: DeliveryState
	images?: ChatImage[]
	citations?: Citation[]
	runId?: string
}

export interface TextRange {
	start: number
	end: number
}

export interface CitationLocation {
	sourceId?: string
	documentId?: string
	chunkId?: string
	section?: string
	page?: number
	lineStart?: number
	lineEnd?: number
	headingPath?: string[]
}

export interface CitationFreshness {
	version?: string
	effectiveAt?: string
	observedAt?: string
	approvalStatus?: string
}

export interface Citation {
	id: string
	index: number
	sourceKind: string
	title: string
	excerpt: string
	highlightRanges: TextRange[]
	matchStatus: string
	confidence?: number
	location: CitationLocation
	freshness: CitationFreshness
	contextAvailable: boolean
}

export interface CitationField {
	label: string
	value: string
	highlighted?: boolean
}

export interface CitationContextBlock {
	id: string
	heading?: string
	text?: string
	fields?: CitationField[]
	isAnchor: boolean
	highlightRanges: TextRange[]
}

export interface CitationContext {
	citation: Citation
	blocks: CitationContextBlock[]
	warning?: string
}

export interface SendMessageResult {
	answer: string
	runId?: string
	citations: Citation[]
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

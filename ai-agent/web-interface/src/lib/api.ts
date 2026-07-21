import type {
  ChatMessage,
  ChatSession,
  MessageRole,
  SessionSummary,
  CitationItem,
  CitationField,
  CitationContextResponse,
  ContextBlock,
  HighlightRange,
  CitationLocation,
  CitationFreshness,
} from "../types"

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")
const REQUEST_TIMEOUT_MS = 45_000

type JsonRecord = Record<string, unknown>

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function pick(record: JsonRecord, ...keys: string[]): unknown {
  for (const key of keys) {
    if (key in record) return record[key]
  }
  return undefined
}

function asRecord(value: unknown): JsonRecord {
  return isRecord(value) ? value : {}
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : ""
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback
}

function asBoolean(value: unknown): boolean {
  return value === true
}

function normalizeRole(value: unknown): MessageRole {
  const role = asString(value).toLowerCase()
  if (role === "assistant" || role === "agent") return "Assistant"
  if (role === "system") return "System"
  if (role === "tool") return "Tool"
  return "User"
}

function normalizeMessage(value: unknown): ChatMessage | null {
  if (!isRecord(value)) return null
  const content = asString(pick(value, "Content", "content"))
  const rawImages = pick(value, "Images", "images")
  const images = Array.isArray(rawImages)
    ? rawImages.flatMap((image) => {
        if (!isRecord(image)) return []
        const mimeType = asString(pick(image, "MIMEType", "mime_type"))
        const data = asString(pick(image, "Data", "data"))
        if (!mimeType || !data) return []
        return [{ mimeType: mimeType as "image/jpeg" | "image/png", data }]
      })
    : []
  const citations = normalizeCitations(pick(value, "Citations", "citations"))
  return {
    role: normalizeRole(pick(value, "Role", "role")),
    content,
    images,
    ...(citations.length > 0 ? { citations } : {}),
  }
}

export function normalizeSession(payload: unknown): ChatSession {
  const envelope = asRecord(payload)
  const rawSession = asRecord(pick(envelope, "Session", "session") ?? envelope)
  const rawContext = asRecord(pick(rawSession, "Context", "context"))
  const rawMessages = pick(rawContext, "Messages", "messages")
  const rawTools = pick(rawContext, "Tools", "tools")

  return {
    id: asString(pick(rawSession, "ID", "id")),
    title: asString(pick(rawSession, "Title", "title")),
    ownerId: asString(pick(rawSession, "OwnerID", "owner_id", "ownerId")),
    messages: Array.isArray(rawMessages)
      ? rawMessages.map(normalizeMessage).filter((item): item is ChatMessage => item !== null)
      : [],
    tools: Array.isArray(rawTools) ? rawTools : [],
  }
}

export function normalizeSessionList(payload: unknown): SessionSummary[] {
  const envelope = asRecord(payload)
  const rawSessions = pick(envelope, "sessions", "Sessions")
  if (!Array.isArray(rawSessions)) return []

  return rawSessions.flatMap((value) => {
    if (!isRecord(value)) return []
    const id = asString(pick(value, "id", "ID"))
    if (!id) return []
    return [
      {
        id,
        ownerId: asString(pick(value, "owner_id", "OwnerID", "ownerId")),
        title: asString(pick(value, "title", "Title")),
      },
    ]
  })
}

function normalizeHighlightRanges(value: unknown): HighlightRange[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!isRecord(item)) return []
    return [
      {
        start: asNumber(pick(item, "start", "Start")),
        end: asNumber(pick(item, "end", "End")),
      },
    ]
  })
}

function normalizeCitationLocation(value: unknown): CitationLocation | undefined {
  if (!isRecord(value)) return undefined
  return {
    document_id: asString(pick(value, "document_id", "DocumentID")) || undefined,
    section: asString(pick(value, "section", "Section")) || undefined,
    page: asNumber(pick(value, "page", "Page")) || undefined,
    url: asString(pick(value, "url", "URL")) || undefined,
  }
}

function normalizeCitationFreshness(value: unknown): CitationFreshness | undefined {
  if (!isRecord(value)) return undefined
  return {
    version: asString(pick(value, "version", "Version")) || undefined,
    effective_at: asString(pick(value, "effective_at", "EffectiveAt")) || undefined,
    observed_at: asString(pick(value, "observed_at", "ObservedAt")) || undefined,
    approval_status: asString(pick(value, "approval_status", "ApprovalStatus")) || undefined,
  }
}

function normalizeCitation(value: unknown): CitationItem | null {
  if (!isRecord(value)) return null
  const id = asString(pick(value, "id", "ID"))
  if (!id) return null
  return {
    id,
    index: asNumber(pick(value, "index", "Index")),
    source_kind: asString(pick(value, "source_kind", "SourceKind")),
    title: asString(pick(value, "title", "Title")),
    excerpt: asString(pick(value, "excerpt", "Excerpt")),
    highlight_ranges: normalizeHighlightRanges(pick(value, "highlight_ranges", "HighlightRanges")),
    match_status: asString(pick(value, "match_status", "MatchStatus")),
    confidence: asNumber(pick(value, "confidence", "Confidence")),
    location: normalizeCitationLocation(pick(value, "location", "Location")),
    freshness: normalizeCitationFreshness(pick(value, "freshness", "Freshness")),
    context_available: asBoolean(pick(value, "context_available", "ContextAvailable")),
  }
}

function normalizeCitations(value: unknown): CitationItem[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => normalizeCitation(item) ?? [])
}

const DEVICE_ID_KEY = "bvtim-device-id"

export function getDeviceId(): string {
  try {
    let id = window.localStorage.getItem(DEVICE_ID_KEY)
    if (!id) {
      id = "dev-" + Math.random().toString(36).substring(2, 11) + "-" + Date.now().toString(36)
      window.localStorage.setItem(DEVICE_ID_KEY, id)
    }
    return id
  } catch {
    return "dev-fallback"
  }
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        "X-Device-ID": getDeviceId(),
        ...init.headers,
      },
      credentials: "same-origin",
      signal: controller.signal,
    })

    const body = await response.text()
    let data: unknown
    if (body) {
      try {
        data = JSON.parse(body)
      } catch {
        data = undefined
      }
    }

    if (!response.ok) {
      const errorRecord = asRecord(data)
      const serverMessage = asString(pick(errorRecord, "error", "message"))
      throw new ApiError(
        serverMessage || `Máy chủ trả về lỗi ${response.status}.`,
        response.status,
      )
    }

    return data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(
        "Dịch vụ phản hồi chậm hơn dự kiến. Anh/Chị vui lòng thử lại sau ít phút.",
      )
    }
    throw new ApiError(
      "Không thể kết nối tới dịch vụ hỗ trợ. Anh/Chị vui lòng thử lại hoặc gọi tổng đài 1900 1082.",
    )
  } finally {
    window.clearTimeout(timeout)
  }
}

export async function getSessions(): Promise<SessionSummary[]> {
  return normalizeSessionList(await requestJson<unknown>("/c"))
}

export async function createSession(): Promise<string> {
  const response = asRecord(
    await requestJson<unknown>("/c", {
      method: "POST",
    }),
  )
  const sessionId = asString(pick(response, "session_id", "sessionId"))
  if (!sessionId) {
    throw new ApiError("Chưa thể bắt đầu cuộc trò chuyện mới. Anh/Chị vui lòng thử lại.")
  }
  return sessionId
}

export async function getSession(id: string): Promise<ChatSession> {
  return normalizeSession(
    await requestJson<unknown>(`/c/${encodeURIComponent(id)}`),
  )
}

export interface SendMessageResponse {
  answer: string
  citations: CitationItem[]
}

export async function sendMessage(
  id: string,
  message: string,
): Promise<SendMessageResponse> {
  const response = asRecord(
    await requestJson<unknown>(`/c/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    }),
  )
  const answer = asString(pick(response, "response", "Response"))
  if (!answer) {
    throw new ApiError("Trợ lý chưa trả về nội dung. Anh/Chị vui lòng gửi lại câu hỏi.")
  }
  const citations = normalizeCitations(pick(response, "citations", "Citations"))
  return { answer, citations }
}

function normalizeCitationField(value: unknown): CitationField | null {
  if (!isRecord(value)) return null
  const label = asString(pick(value, "label", "Label"))
  const fieldValue = asString(pick(value, "value", "Value"))
  if (!label || !fieldValue) return null
  return {
    label,
    value: fieldValue,
    highlighted: asBoolean(pick(value, "highlighted", "Highlighted")) || undefined,
  }
}

function normalizeContextBlock(value: unknown): ContextBlock | null {
  if (!isRecord(value)) return null
  const rawFields = pick(value, "fields", "Fields")
  return {
    id: asString(pick(value, "id", "ID")),
    heading: asString(pick(value, "heading", "Heading")) || undefined,
    text: asString(pick(value, "text", "Text")),
    fields: Array.isArray(rawFields)
      ? rawFields.flatMap((item) => normalizeCitationField(item) ?? [])
      : [],
    is_anchor: asBoolean(pick(value, "is_anchor", "IsAnchor")),
    highlight_ranges: normalizeHighlightRanges(pick(value, "highlight_ranges", "HighlightRanges")),
  }
}

export async function getCitationContext(
  sessionId: string,
  citationId: string,
  scope: "section" | "document" = "section",
): Promise<CitationContextResponse> {
  const response = asRecord(
    await requestJson<unknown>(
      `/c/${encodeURIComponent(sessionId)}/citations/${encodeURIComponent(citationId)}/context?scope=${scope}`,
    ),
  )
  const citation = normalizeCitation(pick(response, "citation", "Citation"))
  if (!citation) {
    throw new ApiError("Chưa tải được ngữ cảnh trích dẫn. Anh/Chị vui lòng thử lại.")
  }
  const rawBlocks = pick(response, "blocks", "Blocks")
  return {
    citation,
    blocks: Array.isArray(rawBlocks)
      ? rawBlocks.flatMap((item) => normalizeContextBlock(item) ?? [])
      : [],
    warning: asString(pick(response, "warning", "Warning")) || undefined,
  }
}

export async function deleteSession(id: string): Promise<void> {
  await requestJson<void>(`/c/${encodeURIComponent(id)}`, {
    method: "DELETE",
  })
}

export async function transcribeAudio(audio: Blob, filename = "voice.wav"): Promise<string> {
  const form = new FormData()
  form.append("audio", audio, filename)
  try {
    const response = asRecord(await requestJson<unknown>("/api/stt", {
      method: "POST",
      body: form,
    }))
    const text = asString(response.text)
    if (!text) throw new ApiError("Không thể chuyển giọng nói thành văn bản. Anh/Chị vui lòng thử lại sau.")
    return text
  } catch {
    throw new ApiError("Không thể chuyển giọng nói thành văn bản. Anh/Chị vui lòng thử lại sau.")
  }
}

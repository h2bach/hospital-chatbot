import type {
  ChatMessage,
  ChatSession,
  MessageRole,
  SessionSummary,
  ChatImage,
	Citation,
	CitationContext,
	CitationContextBlock,
	CitationField,
	SendMessageResult,
	TextRange,
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

function asNumber(value: unknown): number | undefined {
	return typeof value === "number" && Number.isFinite(value) ? value : undefined
}

function asBoolean(value: unknown): boolean {
	return value === true
}

function normalizeRange(value: unknown): TextRange | null {
	if (!isRecord(value)) return null
	const start = asNumber(pick(value, "start", "Start"))
	const end = asNumber(pick(value, "end", "End"))
	if (start === undefined || end === undefined || start < 0 || end <= start) return null
	return { start, end }
}

function normalizeCitation(value: unknown): Citation | null {
	if (!isRecord(value)) return null
	const id = asString(pick(value, "id", "ID"))
	const index = asNumber(pick(value, "index", "Index"))
	const excerpt = asString(pick(value, "excerpt", "Excerpt"))
	if (!id || index === undefined || !excerpt) return null
	const rawRanges = pick(value, "highlight_ranges", "HighlightRanges")
	const location = asRecord(pick(value, "location", "Location"))
	const freshness = asRecord(pick(value, "freshness", "Freshness"))
	const rawHeading = pick(location, "heading_path", "Heading")
	return {
		id,
		index,
		sourceKind: asString(pick(value, "source_kind", "SourceKind")),
		title: asString(pick(value, "title", "Title")) || "Nguồn dữ liệu bệnh viện",
		excerpt,
		highlightRanges: Array.isArray(rawRanges)
			? rawRanges.map(normalizeRange).filter((range): range is TextRange => range !== null)
			: [],
		matchStatus: asString(pick(value, "match_status", "MatchStatus")) || "exact",
		confidence: asNumber(pick(value, "confidence", "Confidence")),
		location: {
			sourceId: asString(pick(location, "source_id", "SourceID")) || undefined,
			documentId: asString(pick(location, "document_id", "DocumentID")) || undefined,
			chunkId: asString(pick(location, "chunk_id", "ChunkID")) || undefined,
			section: asString(pick(location, "section", "Section")) || undefined,
			page: asNumber(pick(location, "page", "Page")),
			lineStart: asNumber(pick(location, "line_start", "LineStart")),
			lineEnd: asNumber(pick(location, "line_end", "LineEnd")),
			headingPath: Array.isArray(rawHeading) ? rawHeading.filter((item): item is string => typeof item === "string") : undefined,
		},
		freshness: {
			version: asString(pick(freshness, "version", "Version")) || undefined,
			effectiveAt: asString(pick(freshness, "effective_at", "EffectiveAt")) || undefined,
			observedAt: asString(pick(freshness, "observed_at", "ObservedAt")) || undefined,
			approvalStatus: asString(pick(freshness, "approval_status", "ApprovalStatus")) || undefined,
		},
		contextAvailable: asBoolean(pick(value, "context_available", "ContextAvailable")),
	}
}

function normalizeCitationField(value: unknown): CitationField | null {
	if (!isRecord(value)) return null
	const label = asString(pick(value, "label", "Label"))
	const fieldValue = asString(pick(value, "value", "Value"))
	if (!label || !fieldValue) return null
	return { label, value: fieldValue, highlighted: asBoolean(pick(value, "highlighted", "Highlighted")) }
}

function normalizeContextBlock(value: unknown): CitationContextBlock | null {
	if (!isRecord(value)) return null
	const id = asString(pick(value, "id", "ID"))
	if (!id) return null
	const rawRanges = pick(value, "highlight_ranges", "HighlightRanges")
	const rawFields = pick(value, "fields", "Fields")
	return {
		id,
		heading: asString(pick(value, "heading", "Heading")) || undefined,
		text: asString(pick(value, "text", "Text")) || undefined,
		fields: Array.isArray(rawFields)
			? rawFields.map(normalizeCitationField).filter((field): field is CitationField => field !== null)
			: undefined,
		isAnchor: asBoolean(pick(value, "is_anchor", "IsAnchor")),
		highlightRanges: Array.isArray(rawRanges)
			? rawRanges.map(normalizeRange).filter((range): range is TextRange => range !== null)
			: [],
	}
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
	const rawCitations = pick(value, "Citations", "citations")
  const images = Array.isArray(rawImages)
    ? rawImages.flatMap((image) => {
        if (!isRecord(image)) return []
        const mimeType = asString(pick(image, "MIMEType", "mime_type"))
        const data = asString(pick(image, "Data", "data"))
        if (!mimeType || !data) return []
        return [{ mimeType: mimeType as "image/jpeg" | "image/png", data }]
      })
    : []
  const citations = Array.isArray(rawCitations)
		? rawCitations.map(normalizeCitation).filter((citation): citation is Citation => citation !== null)
		: []
	return {
    role: normalizeRole(pick(value, "Role", "role")),
    content,
		...(images.length ? { images } : {}),
		...(citations.length ? { citations } : {}),
		...(asString(pick(value, "run_id", "RunID")) ? { runId: asString(pick(value, "run_id", "RunID")) } : {}),
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

export async function sendMessage(
  id: string,
  message: string,
  images: ChatImage[] = [],
): Promise<SendMessageResult> {
  const response = asRecord(
    await requestJson<unknown>(`/c/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        images: images.map(({ mimeType, data }) => ({ mime_type: mimeType, data })),
      }),
    }),
  )
  const answer = asString(pick(response, "response", "Response"))
  if (!answer) {
    throw new ApiError("Trợ lý chưa trả về nội dung. Anh/Chị vui lòng gửi lại câu hỏi.")
  }
	const rawCitations = pick(response, "citations", "Citations")
	return {
		answer,
		runId: asString(pick(response, "run_id", "RunID")) || undefined,
		citations: Array.isArray(rawCitations)
			? rawCitations.map(normalizeCitation).filter((citation): citation is Citation => citation !== null)
			: [],
	}
}

export async function getCitationContext(sessionId: string, citationId: string): Promise<CitationContext> {
	const response = asRecord(await requestJson<unknown>(
		`/c/${encodeURIComponent(sessionId)}/citations/${encodeURIComponent(citationId)}/context?scope=section&limit=12`,
	))
	const citation = normalizeCitation(pick(response, "citation", "Citation"))
	if (!citation) throw new ApiError("Không đọc được thông tin nguồn trích dẫn.")
	const rawBlocks = pick(response, "blocks", "Blocks")
	return {
		citation,
		blocks: Array.isArray(rawBlocks)
			? rawBlocks.map(normalizeContextBlock).filter((block): block is CitationContextBlock => block !== null)
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

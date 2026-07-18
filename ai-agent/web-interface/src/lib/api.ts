import type {
  AccessRole,
  ChatMessage,
  ChatSession,
  MessageRole,
  SessionSummary,
  ChatImage,
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
  return {
    role: normalizeRole(pick(value, "Role", "role")),
    content,
    images,
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

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
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
  role: AccessRole = "GUEST",
  images: ChatImage[] = [],
): Promise<string> {
  const response = asRecord(
    await requestJson<unknown>(`/c/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Role: role,
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
  return answer
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

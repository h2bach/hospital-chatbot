import type {
  ChatMessage,
  ChatSession,
  MessageRole,
  SessionSummary,
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
  return {
    role: normalizeRole(pick(value, "Role", "role")),
    content,
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
        "Yêu cầu mất quá nhiều thời gian. Hãy kiểm tra máy chủ rồi thử lại.",
      )
    }
    throw new ApiError(
      "Không thể kết nối tới máy chủ. Hãy chắc chắn backend của dự án đang chạy rồi thử lại.",
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
    throw new ApiError("Máy chủ không trả về mã cuộc trò chuyện.")
  }
  return sessionId
}

export async function getSession(id: string): Promise<ChatSession> {
  return normalizeSession(
    await requestJson<unknown>(`/c/${encodeURIComponent(id)}`),
  )
}

export async function sendMessage(id: string, message: string): Promise<string> {
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
    throw new ApiError("Agent không trả về nội dung phản hồi.")
  }
  return answer
}

export async function deleteSession(id: string): Promise<void> {
  await requestJson<void>(`/c/${encodeURIComponent(id)}`, {
    method: "DELETE",
  })
}

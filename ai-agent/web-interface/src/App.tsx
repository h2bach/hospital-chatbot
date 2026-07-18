import * as Dialog from "@radix-ui/react-dialog"
import { CircleCheckBig, Menu, Siren, WifiOff, X } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { Composer } from "./components/Composer"
import { ConfirmDeleteDialog } from "./components/ConfirmDeleteDialog"
import { EmergencyDialog } from "./components/EmergencyDialog"
import { MessageThread } from "./components/MessageThread"
import { Sidebar } from "./components/Sidebar"
import { ThemeToggle, type Theme } from "./components/ThemeToggle"
import {
  ApiError,
  createSession,
  deleteSession,
  getSession,
  getSessions,
  sendMessage,
} from "./lib/api"
import type { ChatImage, ChatSession, ServerStatus, SessionSummary } from "./types"

const THEME_STORAGE_KEY = "bvtim-chat-theme"
const APP_TITLE = "Trợ lý Tim Hà Nội"
const DEVICE_CACHE_SESSIONS_KEY = "bvtim-device-cached-sessions"
const DEVICE_RESET_TIMESTAMP_KEY = "bvtim-device-reset-timestamp"
const AUTO_RESET_INTERVAL_MS = 24 * 60 * 60 * 1000 // 1 day (24 hours)

function checkDevice1DayAutoReset(): boolean {
  try {
    const lastReset = Number(window.localStorage.getItem(DEVICE_RESET_TIMESTAMP_KEY) || 0)
    const now = Date.now()
    if (!lastReset || now - lastReset >= AUTO_RESET_INTERVAL_MS) {
      window.localStorage.setItem(DEVICE_RESET_TIMESTAMP_KEY, String(now))
      window.localStorage.removeItem(DEVICE_CACHE_SESSIONS_KEY)
      return true
    }
  } catch {
    // Ignore storage errors
  }
  return false
}

function getCachedSessions(): SessionSummary[] | null {
  try {
    const raw = window.localStorage.getItem(DEVICE_CACHE_SESSIONS_KEY)
    if (!raw) return null
    return JSON.parse(raw) as SessionSummary[]
  } catch {
    return null
  }
}

function setCachedSessions(sessions: SessionSummary[]) {
  try {
    window.localStorage.setItem(DEVICE_CACHE_SESSIONS_KEY, JSON.stringify(sessions))
  } catch {
    // Ignore storage errors
  }
}

function initialTheme(): Theme {
  const requestedTheme = new URLSearchParams(window.location.search).get("theme")
  if (requestedTheme === "light" || requestedTheme === "dark") return requestedTheme
  try {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (saved === "light" || saved === "dark") return saved
  } catch {
    // Ignore storage errors
  }
  return "light"
}

function initialEmbeddedMode() {
  const embedParam = new URLSearchParams(window.location.search).get("embed")
  return embedParam === "1" || embedParam === "true" || window.self !== window.top
}

function initialSessionId() {
  return new URLSearchParams(window.location.search).get("session")
}

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Đã xảy ra lỗi không mong đợi."
}

export function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(initialSessionId)
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null)
  const [sessionQuery, setSessionQuery] = useState("")
  const [composerValue, setComposerValue] = useState("")
  const [composerImages, setComposerImages] = useState<ChatImage[]>([])
  const [serverStatus, setServerStatus] = useState<ServerStatus>("checking")
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [loadingActive, setLoadingActive] = useState(false)
  const [creating, setCreating] = useState(false)
  const [sending, setSending] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [emergencyOpen, setEmergencyOpen] = useState(false)
  const [embedded] = useState(initialEmbeddedMode)
  const [sessionListError, setSessionListError] = useState<string | null>(null)
  const [activeError, setActiveError] = useState<string | null>(null)
  const [messageError, setMessageError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<SessionSummary | null>(null)
  const activeRequest = useRef(0)
  const skipNextActiveLoad = useRef<string | null>(null)

  const pageTitle = APP_TITLE

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme)
    } catch {
      // Keep theming functional even when iframe storage is blocked.
    }
    const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    themeColor?.setAttribute("content", theme === "dark" ? "#07162e" : "#f4f7fc")
  }, [theme])

  useEffect(() => {
    document.documentElement.dataset.embedded = embedded ? "true" : "false"
    if (!embedded) return

    const handleParentMessage = (event: MessageEvent<unknown>) => {
      if (event.source !== window.parent || typeof event.data !== "object" || !event.data) {
        return
      }
      const message = event.data as { type?: string; theme?: string; action?: string }
      if (
        message.type === "hanoi-heart-assistant:set-theme" &&
        (message.theme === "light" || message.theme === "dark")
      ) {
        setTheme(message.theme)
      }
      if (message.type === "hanoi-heart-assistant:action") {
        if (message.action === "focus") {
          document.querySelector<HTMLTextAreaElement>("#message-composer")?.focus()
        }
        if (message.action === "open-emergency") setEmergencyOpen(true)
      }
    }

    window.addEventListener("message", handleParentMessage)
    window.parent.postMessage(
      { type: "hanoi-heart-assistant:ready", version: 1, theme },
      "*",
    )
    return () => window.removeEventListener("message", handleParentMessage)
  }, [embedded, theme])

  useEffect(() => {
    const url = new URL(window.location.href)
    if (selectedId) url.searchParams.set("session", selectedId)
    else url.searchParams.delete("session")
    window.history.replaceState(null, "", url)
  }, [selectedId])

  const loadActiveSession = useCallback(async (id: string) => {
    const requestId = ++activeRequest.current
    setLoadingActive(true)
    setActiveError(null)
    setMessageError(null)

    try {
      const session = await getSession(id)
      if (requestId === activeRequest.current) setActiveSession(session)
    } catch (error) {
      if (requestId === activeRequest.current) {
        setActiveSession(null)
        setActiveError(errorMessage(error))
      }
    } finally {
      if (requestId === activeRequest.current) setLoadingActive(false)
    }
  }, [])



  const loadSessionList = useCallback(async () => {
    const wasReset = checkDevice1DayAutoReset()
    if (wasReset) {
      setSessions([])
      setSelectedId(null)
      setActiveSession(null)
    } else {
      const cached = getCachedSessions()
      if (cached && cached.length > 0) {
        setSessions(cached)
        setSelectedId((current) => {
          if (current && cached.some((session) => session.id === current)) return current
          return cached[0]?.id ?? null
        })
      }
    }

    setLoadingSessions(true)
    setSessionListError(null)
    setServerStatus("checking")
    try {
      const nextSessions = await getSessions()
      setSessions(nextSessions)
      setCachedSessions(nextSessions)
      setServerStatus("online")
      setSelectedId((current) => {
        if (current && nextSessions.some((session) => session.id === current)) return current
        return nextSessions[0]?.id ?? null
      })
    } catch (error) {
      setServerStatus("offline")
      setSessionListError(errorMessage(error))
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  const refreshSessionMetadata = useCallback(async () => {
    try {
      const nextSessions = await getSessions()
      setSessions(nextSessions)
      setCachedSessions(nextSessions)
      setServerStatus("online")
    } catch {
      // A metadata refresh should not replace a successful message with an error.
    }
  }, [])

  useEffect(() => {
    void loadSessionList()
  }, [loadSessionList])

  useEffect(() => {
    const interval = window.setInterval(() => {
      const resetNeeded = checkDevice1DayAutoReset()
      if (resetNeeded) {
        setSessions([])
        setSelectedId(null)
        setActiveSession(null)
        setCachedSessions([])
        void loadSessionList()
      }
    }, 30_000)
    return () => window.clearInterval(interval)
  }, [loadSessionList])

  useEffect(() => {
    if (!selectedId) {
      activeRequest.current += 1
      setActiveSession(null)
      setActiveError(null)
      setLoadingActive(false)
      return
    }
    if (skipNextActiveLoad.current === selectedId) {
      skipNextActiveLoad.current = null
      setActiveSession({ id: selectedId, ownerId: "", title: "", messages: [], tools: [] })
      setActiveError(null)
      setLoadingActive(false)
      return
    }
    void loadActiveSession(selectedId)
  }, [loadActiveSession, selectedId])

  async function handleCreateSession() {
    if (creating) return null
    setCreating(true)
    setActionError(null)
    try {
      const id = await createSession()
      const created = { id, ownerId: "", title: "" }
      skipNextActiveLoad.current = id
      setSessions((current) => [created, ...current.filter((session) => session.id !== id)])
      setSelectedId(id)
      setMobileSidebarOpen(false)
      setServerStatus("online")
      return id
    } catch (error) {
      setServerStatus("offline")
      setActionError(errorMessage(error))
      return null
    } finally {
      setCreating(false)
    }
  }

  function handleSelectSession(id: string) {
    if (id === selectedId) {
      setMobileSidebarOpen(false)
      return
    }
    setSelectedId(id)
    setMobileSidebarOpen(false)
    setMessageError(null)
  }

  async function handleSend(message: string, images: ChatImage[] = []) {
    if (sending) return
    setComposerValue("")
    setComposerImages([])
    setMessageError(null)
    setActionError(null)

    let sessionId = selectedId
    if (!sessionId) {
      sessionId = await handleCreateSession()
      if (!sessionId) {
        setComposerValue(message)
        setComposerImages(images)
        return
      }
    }

    const optimisticMessage = { role: "User" as const, content: message, images, delivery: "sending" as const }
    const currentId = sessionId
    setSending(true)
    setActiveError(null)
    setActiveSession((current) => {
      if (!current || current.id !== currentId) {
        return {
          id: currentId,
          ownerId: "",
          title: "",
          messages: [optimisticMessage],
          tools: [],
        }
      }
      return { ...current, messages: [...current.messages, optimisticMessage] }
    })

    try {
      const answer = await sendMessage(currentId, message, images)
      setActiveSession((current) => {
        if (!current || current.id !== currentId) return current
        const messages = current.messages.map((item, index) =>
          index === current.messages.length - 1 && item.delivery === "sending"
            ? { role: item.role, content: item.content }
            : item,
        )
        return {
          ...current,
          messages: [...messages, { role: "Assistant", content: answer }],
        }
      })
      setServerStatus("online")
      try {
        const officialSession = await getSession(currentId)
        setActiveSession((current) => (current?.id === currentId ? officialSession : current))
      } catch {
        // The answer is already visible; this sync only adds tool activity from the session context.
      }
      window.setTimeout(() => void refreshSessionMetadata(), 1_500)
    } catch (error) {
      setActiveSession((current) => {
        if (!current || current.id !== currentId) return current
        const last = current.messages.at(-1)
        if (last?.delivery === "sending" && last.content === message) {
          return {
            ...current,
            messages: current.messages.map((item, index) =>
              index === current.messages.length - 1
                ? { ...item, delivery: "failed" as const }
                : item,
            ),
          }
        }
        return current
      })
      setComposerValue(message)
      setComposerImages(images)
      setMessageError(errorMessage(error))
      if (error instanceof ApiError && error.status === 0) setServerStatus("offline")
    } finally {
      setSending(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget || deleting) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteSession(deleteTarget.id)
      const remaining = sessions.filter((session) => session.id !== deleteTarget.id)
      setSessions(remaining)
      if (selectedId === deleteTarget.id) setSelectedId(remaining[0]?.id ?? null)
      setDeleteTarget(null)
      setServerStatus("online")
    } catch (error) {
      setDeleteError(errorMessage(error))
    } finally {
      setDeleting(false)
    }
  }

  const sidebarProps = {
    sessions,
    selectedId,
    loading: loadingSessions,
    creating,
    error: sessionListError,
    serverStatus,
    query: sessionQuery,
    onQueryChange: setSessionQuery,
    onSelect: handleSelectSession,
    onCreate: () => void handleCreateSession(),
    onDelete: (session: SessionSummary) => {
      setDeleteError(null)
      setDeleteTarget(session)
    },
    onRetry: () => void loadSessionList(),
  }

  return (
    <div className={`app-shell${embedded ? " is-embedded" : ""}`}>
      <a className="skip-link" href="#main-content">
        Chuyển tới nội dung chính
      </a>
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />

      <aside className="desktop-sidebar">
        <Sidebar {...sidebarProps} idPrefix="desktop" />
      </aside>

      <Dialog.Root open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="drawer-overlay" />
          <Dialog.Content className="drawer-content" aria-describedby={undefined}>
            <Dialog.Title className="sr-only">Danh sách cuộc trò chuyện</Dialog.Title>
            <Sidebar
              {...sidebarProps}
              idPrefix="mobile"
              onClose={() => setMobileSidebarOpen(false)}
            />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <main className="workspace" id="main-content" tabIndex={-1}>
        <header className="workspace-header">
          <div className="header-leading">
            <button
              type="button"
              className="icon-button mobile-menu-button"
              aria-label="Mở danh sách cuộc trò chuyện"
              onClick={() => setMobileSidebarOpen(true)}
            >
              <Menu aria-hidden="true" />
            </button>
            <img
              className="header-logo"
              src="./bvtim_logo.png"
              alt="Bệnh viện Tim Hà Nội"
              width="120"
              height="70"
            />
            <div className="header-title">
              <h1>{pageTitle}</h1>
              <span>Trợ lý AI · Thông tin hỗ trợ người bệnh</span>
            </div>
          </div>
          <div className="header-actions">
            <button
              type="button"
              className="emergency-button"
              aria-label="Mở hướng dẫn hỗ trợ khẩn cấp"
              title="Hỗ trợ khẩn cấp"
              onClick={() => setEmergencyOpen(true)}
            >
              <Siren aria-hidden="true" />
              <span>Hỗ trợ khẩn cấp</span>
            </button>
            <span className={`server-pill status-${serverStatus}`}>
              {serverStatus === "offline" ? (
                <WifiOff aria-hidden="true" />
              ) : (
                <CircleCheckBig aria-hidden="true" />
              )}
              <span>
                {serverStatus === "online"
                  ? "Trợ lý sẵn sàng"
                  : serverStatus === "offline"
                    ? "Tạm mất kết nối"
                    : "Đang kết nối"}
              </span>
            </span>
            <ThemeToggle
              theme={theme}
              onToggle={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            />
          </div>
        </header>

        <div className="conversation-scroll">
          <MessageThread
            messages={activeSession?.messages ?? []}
            loading={loadingActive}
            sending={sending}
            error={activeError}
            onRetry={() => selectedId && void loadActiveSession(selectedId)}
            onRetryMessage={(msg, imgs) => void handleSend(msg, imgs)}
            onSuggestion={setComposerValue}
          />
        </div>

        <Composer
          value={composerValue}
          images={composerImages}
          sending={sending || creating}
          error={messageError}
          onChange={setComposerValue}
          onImagesChange={setComposerImages}
          onSend={(message, images) => void handleSend(message, images)}
          onReload={() => selectedId && void loadActiveSession(selectedId)}
        />
      </main>

      {actionError ? (
        <div className="toast" role="alert" aria-live="assertive">
          <WifiOff aria-hidden="true" />
          <span>
            <strong>Không hoàn tất được thao tác</strong>
            {actionError}
          </span>
          <button
            type="button"
            className="icon-button"
            aria-label="Đóng thông báo"
            onClick={() => setActionError(null)}
          >
            <X aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <ConfirmDeleteDialog
        session={deleteTarget}
        deleting={deleting}
        error={deleteError}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        onConfirm={() => void handleDelete()}
      />

      <EmergencyDialog open={emergencyOpen} onOpenChange={setEmergencyOpen} />
    </div>
  )
}

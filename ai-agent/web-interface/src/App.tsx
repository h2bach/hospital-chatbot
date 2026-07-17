import * as Dialog from "@radix-ui/react-dialog"
import { Menu, Server, WifiOff, X } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Composer } from "./components/Composer"
import { ConfirmDeleteDialog } from "./components/ConfirmDeleteDialog"
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
import type { ChatSession, ServerStatus, SessionSummary } from "./types"

function initialTheme(): Theme {
  const saved = window.localStorage.getItem("ai-go-theme")
  if (saved === "light" || saved === "dark") return saved
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function initialSessionId() {
  return new URLSearchParams(window.location.search).get("session")
}

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Đã xảy ra lỗi không mong đợi."
}

function fallbackTitle(title?: string) {
  return title?.trim() || "Cuộc trò chuyện mới"
}

export function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(initialSessionId)
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null)
  const [sessionQuery, setSessionQuery] = useState("")
  const [composerValue, setComposerValue] = useState("")
  const [serverStatus, setServerStatus] = useState<ServerStatus>("checking")
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [loadingActive, setLoadingActive] = useState(false)
  const [creating, setCreating] = useState(false)
  const [sending, setSending] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [sessionListError, setSessionListError] = useState<string | null>(null)
  const [activeError, setActiveError] = useState<string | null>(null)
  const [messageError, setMessageError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<SessionSummary | null>(null)
  const activeRequest = useRef(0)
  const skipNextActiveLoad = useRef<string | null>(null)

  const selectedSummary = useMemo(
    () => sessions.find((session) => session.id === selectedId),
    [sessions, selectedId],
  )
  const pageTitle = fallbackTitle(activeSession?.title || selectedSummary?.title)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem("ai-go-theme", theme)
    const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    themeColor?.setAttribute("content", theme === "dark" ? "#0f172a" : "#f8fafc")
  }, [theme])

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
    setLoadingSessions(true)
    setSessionListError(null)
    setServerStatus("checking")
    try {
      const nextSessions = await getSessions()
      setSessions(nextSessions)
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
      setServerStatus("online")
    } catch {
      // A metadata refresh should not replace a successful message with an error.
    }
  }, [])

  useEffect(() => {
    void loadSessionList()
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

  async function handleSend(message: string) {
    if (sending) return
    setComposerValue("")
    setMessageError(null)
    setActionError(null)

    let sessionId = selectedId
    if (!sessionId) {
      sessionId = await handleCreateSession()
      if (!sessionId) {
        setComposerValue(message)
        return
      }
    }

    const optimisticMessage = { role: "User" as const, content: message, delivery: "sending" as const }
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
      const answer = await sendMessage(currentId, message)
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
          return { ...current, messages: current.messages.slice(0, -1) }
        }
        return current
      })
      setComposerValue(message)
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
    <div className="app-shell">
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
            <div className="header-title">
              <h1>{pageTitle}</h1>
              <span>{selectedId ? `Phiên ${selectedId.slice(0, 8)}` : "Sẵn sàng bắt đầu"}</span>
            </div>
          </div>
          <div className="header-actions">
            <span className={`server-pill status-${serverStatus}`}>
              {serverStatus === "offline" ? (
                <WifiOff aria-hidden="true" />
              ) : (
                <Server aria-hidden="true" />
              )}
              <span>{serverStatus === "online" ? "Đã kết nối" : serverStatus === "offline" ? "Ngoại tuyến" : "Đang kiểm tra"}</span>
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
            onSuggestion={setComposerValue}
          />
        </div>

        <Composer
          value={composerValue}
          sending={sending || creating}
          error={messageError}
          onChange={setComposerValue}
          onSend={(message) => void handleSend(message)}
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
    </div>
  )
}

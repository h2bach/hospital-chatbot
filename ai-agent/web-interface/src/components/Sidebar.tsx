import {
  LoaderCircle,
  MessageSquare,
  PanelLeftClose,
  Plus,
  Search,
  Server,
  Trash2,
  WifiOff,
} from "lucide-react"
import type { ServerStatus, SessionSummary } from "../types"

interface SidebarProps {
  sessions: SessionSummary[]
  selectedId: string | null
  loading: boolean
  creating: boolean
  error: string | null
  serverStatus: ServerStatus
  query: string
  onQueryChange: (value: string) => void
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (session: SessionSummary) => void
  onRetry: () => void
  onClose?: () => void
  idPrefix: string
}

function fallbackTitle(session: SessionSummary) {
  return session.title.trim() || "Cuộc trò chuyện mới"
}

function shortId(id: string) {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id
}

export function Sidebar({
  sessions,
  selectedId,
  loading,
  creating,
  error,
  serverStatus,
  query,
  onQueryChange,
  onSelect,
  onCreate,
  onDelete,
  onRetry,
  onClose,
  idPrefix,
}: SidebarProps) {
  const normalizedQuery = query.trim().toLocaleLowerCase("vi")
  const filteredSessions = normalizedQuery
    ? sessions.filter((session) =>
        `${fallbackTitle(session)} ${session.id}`
          .toLocaleLowerCase("vi")
          .includes(normalizedQuery),
      )
    : sessions

  return (
    <div className="sidebar-inner">
      <div className="sidebar-brand-row">
        <div className="brand-lockup" aria-label="AI GO Workspace">
          <span className="brand-mark" aria-hidden="true">
            <span />
          </span>
          <span>
            <strong>AI GO</strong>
            <small>Workspace</small>
          </span>
        </div>
        {onClose ? (
          <button
            type="button"
            className="icon-button"
            aria-label="Đóng danh sách cuộc trò chuyện"
            onClick={onClose}
          >
            <PanelLeftClose aria-hidden="true" />
          </button>
        ) : null}
      </div>

      <button
        type="button"
        className="new-chat-button"
        onClick={onCreate}
        disabled={creating}
      >
        {creating ? (
          <LoaderCircle className="spin" aria-hidden="true" />
        ) : (
          <Plus aria-hidden="true" />
        )}
        <span>{creating ? "Đang tạo…" : "Cuộc trò chuyện mới"}</span>
      </button>

      <div className="search-field">
        <Search aria-hidden="true" />
        <label className="sr-only" htmlFor={`${idPrefix}-session-search`}>
          Tìm trong lịch sử
        </label>
        <input
          id={`${idPrefix}-session-search`}
          type="search"
          autoComplete="off"
          placeholder="Tìm trong lịch sử"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
      </div>

      <div className="history-heading">
        <span>Lịch sử</span>
        {!loading && !error ? <span>{sessions.length}</span> : null}
      </div>

      <nav className="session-nav" aria-label="Lịch sử cuộc trò chuyện">
        {loading ? (
          <div className="session-skeletons" aria-label="Đang tải lịch sử">
            {Array.from({ length: 6 }).map((_, index) => (
              <span key={index} className="session-skeleton" />
            ))}
          </div>
        ) : error ? (
          <div className="sidebar-state" role="alert">
            <WifiOff aria-hidden="true" />
            <strong>Chưa kết nối được</strong>
            <p>{error}</p>
            <button type="button" className="text-button" onClick={onRetry}>
              Thử kết nối lại
            </button>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="sidebar-state">
            <MessageSquare aria-hidden="true" />
            <strong>{query ? "Không tìm thấy" : "Chưa có cuộc trò chuyện"}</strong>
            <p>
              {query
                ? "Thử một từ khóa hoặc mã phiên khác."
                : "Tạo một phiên mới để bắt đầu làm việc với agent."}
            </p>
          </div>
        ) : (
          <ul className="session-list">
            {filteredSessions.map((session) => {
              const isActive = session.id === selectedId
              const title = fallbackTitle(session)
              return (
                <li key={session.id} className={isActive ? "is-active" : undefined}>
                  <button
                    type="button"
                    className="session-select"
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => onSelect(session.id)}
                  >
                    <MessageSquare aria-hidden="true" />
                    <span>
                      <strong>{title}</strong>
                      <small>{shortId(session.id)}</small>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="session-delete"
                    aria-label={`Xóa ${title}`}
                    title="Xóa cuộc trò chuyện"
                    onClick={() => onDelete(session)}
                  >
                    <Trash2 aria-hidden="true" />
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </nav>

      <div className="sidebar-footer">
        <span
          className={`status-dot status-${serverStatus}`}
          aria-hidden="true"
        />
        {serverStatus === "online" ? (
          <Server aria-hidden="true" />
        ) : serverStatus === "offline" ? (
          <WifiOff aria-hidden="true" />
        ) : (
          <LoaderCircle className="spin" aria-hidden="true" />
        )}
        <span>
          <strong>
            {serverStatus === "online"
              ? "Backend đang hoạt động"
              : serverStatus === "offline"
                ? "Backend ngoại tuyến"
                : "Đang kiểm tra backend"}
          </strong>
          <small>Phiên được lưu trong bộ nhớ máy chủ</small>
        </span>
      </div>
    </div>
  )
}

import {
  CircleCheckBig,
  LoaderCircle,
  MessageCircle,
  PanelLeftClose,
  PhoneCall,
  Plus,
  Search,
  ShieldCheck,
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
        fallbackTitle(session).toLocaleLowerCase("vi").includes(normalizedQuery),
      )
    : sessions

  return (
    <div className="sidebar-inner">
      <div className="sidebar-brand-row">
        <div className="brand-lockup">
          <img
            src="./bvtim_logo.png"
            alt="Bệnh viện Tim Hà Nội"
            width="150"
            height="87"
          />
          <span>
            <small>TRỢ LÝ AI</small>
            <strong>Bệnh viện Tim Hà Nội</strong>
            <em>Vì một trái tim khỏe</em>
          </span>
        </div>
        {onClose ? (
          <button
            type="button"
            className="icon-button sidebar-close"
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
        <span>{creating ? "Đang khởi tạo…" : "Cuộc trò chuyện mới"}</span>
      </button>

      <div className="search-field">
        <Search aria-hidden="true" />
        <label className="sr-only" htmlFor={`${idPrefix}-session-search`}>
          Tìm trong lịch sử trò chuyện
        </label>
        <input
          id={`${idPrefix}-session-search`}
          type="search"
          autoComplete="off"
          placeholder="Tìm cuộc trò chuyện"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
      </div>

      <div className="history-heading">
        <span>Gần đây</span>
        {!loading && !error ? <span>{sessions.length}</span> : null}
      </div>

      <nav className="session-nav" aria-label="Lịch sử cuộc trò chuyện">
        {loading ? (
          <div className="session-skeletons" aria-label="Đang tải lịch sử">
            {Array.from({ length: 5 }).map((_, index) => (
              <span key={index} className="session-skeleton" />
            ))}
          </div>
        ) : error ? (
          <div className="sidebar-state" role="alert">
            <WifiOff aria-hidden="true" />
            <strong>Chưa kết nối được dịch vụ</strong>
            <p>{error}</p>
            <button type="button" className="text-button" onClick={onRetry}>
              Thử kết nối lại
            </button>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="sidebar-state">
            <MessageCircle aria-hidden="true" />
            <strong>{query ? "Không tìm thấy" : "Chưa có cuộc trò chuyện"}</strong>
            <p>
              {query
                ? "Thử tìm bằng một từ khóa khác."
                : "Bắt đầu cuộc trò chuyện để nhận hỗ trợ thông tin."}
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
                    <MessageCircle aria-hidden="true" />
                    <span>
                      <strong>{title}</strong>
                      <small>Hỗ trợ thông tin người bệnh</small>
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

      <div className="sidebar-support">
        <a className="hotline-card" href="tel:19001082">
          <span className="hotline-icon" aria-hidden="true">
            <PhoneCall />
          </span>
          <span>
            <small>Tổng đài CSKH 24/7</small>
            <strong>1900 1082</strong>
            <em>Cuộc gọi có tính phí</em>
          </span>
        </a>
        <div className="sidebar-footer">
          <span className={`status-dot status-${serverStatus}`} aria-hidden="true" />
          {serverStatus === "online" ? (
            <CircleCheckBig aria-hidden="true" />
          ) : serverStatus === "offline" ? (
            <WifiOff aria-hidden="true" />
          ) : (
            <LoaderCircle className="spin" aria-hidden="true" />
          )}
          <span>
            <strong>
              {serverStatus === "online"
                ? "Dịch vụ đang hoạt động"
                : serverStatus === "offline"
                  ? "Dịch vụ tạm gián đoạn"
                  : "Đang kết nối dịch vụ"}
            </strong>
            <small>
              <ShieldCheck aria-hidden="true" />
              Hạn chế chia sẻ dữ liệu cá nhân
            </small>
          </span>
        </div>
      </div>
    </div>
  )
}

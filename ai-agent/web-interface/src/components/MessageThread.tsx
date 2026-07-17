import {
  Bot,
  Clock3,
  Code2,
  LoaderCircle,
  RefreshCw,
  Shield,
  Sparkles,
  UserRound,
  Wrench,
} from "lucide-react"
import { useEffect, useRef } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { ChatMessage, MessageRole } from "../types"

interface MessageThreadProps {
  messages: ChatMessage[]
  loading: boolean
  sending: boolean
  error: string | null
  onRetry: () => void
  onSuggestion: (prompt: string) => void
}

const suggestions = [
  {
    icon: Code2,
    title: "Khám phá codebase",
    description: "Giải thích cấu trúc và luồng chính của dự án này.",
    prompt: "Hãy giải thích cấu trúc và luồng hoạt động chính của dự án này.",
  },
  {
    icon: Wrench,
    title: "Thử công cụ MCP",
    description: "Kiểm tra những công cụ agent có thể sử dụng.",
    prompt: "Bạn có thể dùng những công cụ MCP nào và chúng giúp được gì?",
  },
  {
    icon: Clock3,
    title: "Kiểm tra thời gian",
    description: "Gửi một yêu cầu ngắn để kiểm tra kết nối.",
    prompt: "Bây giờ là mấy giờ tại Thành phố Hồ Chí Minh?",
  },
]

function roleDetails(role: MessageRole) {
  switch (role) {
    case "Assistant":
      return { label: "AI GO", Icon: Bot }
    case "System":
      return { label: "Hệ thống", Icon: Shield }
    case "Tool":
      return { label: "Công cụ", Icon: Wrench }
    default:
      return { label: "Bạn", Icon: UserRound }
  }
}

function MessageItem({ message }: { message: ChatMessage }) {
  const { label, Icon } = roleDetails(message.role)
  const roleClass = message.role.toLowerCase()

  return (
    <article className={`message message-${roleClass}`}>
      <div className="message-avatar" aria-hidden="true">
        <Icon />
      </div>
      <div className="message-body">
        <div className="message-meta">
          <strong>{label}</strong>
          {message.delivery === "failed" ? <span>Gửi thất bại</span> : null}
        </div>
        <div className="message-content">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ children, ...props }) => (
                <a {...props} target="_blank" rel="noreferrer">
                  {children}
                </a>
              ),
            }}
          >
            {message.content || "Không có nội dung."}
          </ReactMarkdown>
        </div>
      </div>
    </article>
  )
}

function isAgentActivity(message: ChatMessage) {
  return (
    message.role === "System" ||
    message.role === "Tool" ||
    (message.role === "Assistant" && message.content.startsWith("Tool Call:"))
  )
}

function AgentActivity({ messages }: { messages: ChatMessage[] }) {
  if (messages.length === 0) return null

  return (
    <details className="activity-panel">
      <summary>
        <Wrench aria-hidden="true" />
        Hoạt động của agent
        <span>{messages.length}</span>
      </summary>
      <div className="activity-list">
        {messages.map((message, index) => (
          <div className="activity-item" key={`${message.role}-${index}`}>
            <strong>
              {message.role === "System"
                ? "Chỉ dẫn hệ thống"
                : message.role === "Tool"
                  ? "Kết quả công cụ"
                  : "Lệnh gọi công cụ"}
            </strong>
            <pre>{message.content}</pre>
          </div>
        ))}
      </div>
    </details>
  )
}

export function MessageThread({
  messages,
  loading,
  sending,
  error,
  onRetry,
  onSuggestion,
}: MessageThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const visibleMessages = messages.filter((message) => !isAgentActivity(message))
  const activityMessages = messages.filter(isAgentActivity)

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    bottomRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" })
  }, [messages, sending])

  if (loading) {
    return (
      <div className="thread thread-loading" aria-label="Đang tải cuộc trò chuyện">
        <div className="message-skeleton message-skeleton-wide" />
        <div className="message-skeleton message-skeleton-short" />
        <div className="message-skeleton message-skeleton-medium" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="thread-state" role="alert">
        <span className="state-icon danger">
          <RefreshCw aria-hidden="true" />
        </span>
        <h2>Chưa tải được cuộc trò chuyện</h2>
        <p>{error}</p>
        <button type="button" className="secondary-button" onClick={onRetry}>
          <RefreshCw aria-hidden="true" />
          Thử lại
        </button>
      </div>
    )
  }

  if (visibleMessages.length === 0 && !sending) {
    return (
      <section className="welcome" aria-labelledby="welcome-title">
        <div className="welcome-mark" aria-hidden="true">
          <Sparkles />
        </div>
        <p className="eyebrow">AI GO AGENT</p>
        <h2 id="welcome-title">Hôm nay mình có thể giúp gì cho bạn?</h2>
        <p className="welcome-copy">
          Trò chuyện trực tiếp với backend của dự án. Mỗi cuộc trò chuyện được lưu thành
          một phiên riêng trên máy chủ.
        </p>
        <div className="suggestion-grid" aria-label="Gợi ý bắt đầu">
          {suggestions.map(({ icon: Icon, title, description, prompt }) => (
            <button
              type="button"
              className="suggestion-card"
              key={title}
              onClick={() => onSuggestion(prompt)}
            >
              <span className="suggestion-icon" aria-hidden="true">
                <Icon />
              </span>
              <span>
                <strong>{title}</strong>
                <small>{description}</small>
              </span>
            </button>
          ))}
        </div>
      </section>
    )
  }

  return (
    <div className="thread" aria-live="polite" aria-busy={sending}>
      {visibleMessages.map((message, index) => (
        <MessageItem key={`${message.role}-${index}-${message.content.slice(0, 24)}`} message={message} />
      ))}
      <AgentActivity messages={activityMessages} />
      {sending ? (
        <div className="message message-assistant message-thinking">
          <div className="message-avatar" aria-hidden="true">
            <Bot />
          </div>
          <div className="message-body">
            <div className="message-meta">
              <strong>AI GO</strong>
            </div>
            <div className="thinking-indicator">
              <LoaderCircle className="spin" aria-hidden="true" />
              <span>Đang suy nghĩ…</span>
            </div>
          </div>
        </div>
      ) : null}
      <div ref={bottomRef} />
    </div>
  )
}

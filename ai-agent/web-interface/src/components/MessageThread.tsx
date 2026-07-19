import {
  CalendarClock,
  CalendarPlus,
  ClipboardList,
  HeartPulse,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  UserRound,
  Volume2,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { ChatMessage, MessageRole } from "../types"

interface MessageThreadProps {
  sessionId?: string
  messages: ChatMessage[]
  loading: boolean
  sending: boolean
  error: string | null
  onRetry: () => void
  onRetryMessage?: (content: string) => void
  onSuggestion: (prompt: string) => void
}

const suggestions = [
  {
    icon: CalendarPlus,
    title: "Đặt lịch khám",
    description: "Các kênh đăng ký khám chính thức của bệnh viện.",
    prompt:
      "Tôi muốn đặt lịch khám tại Bệnh viện Tim Hà Nội. Xin hướng dẫn các kênh đăng ký chính thức.",
  },
  {
    icon: ClipboardList,
    title: "Quy trình đi khám",
    description: "Từng bước tại Khu Tự nguyện 1, Cơ sở 1.",
    prompt:
      "Tôi đến khám tại Khu Khám bệnh Tự nguyện 1, Cơ sở 1. Xin hướng dẫn quy trình từ khi đến bệnh viện.",
  },
  {
    icon: ShieldCheck,
    title: "Khám bằng BHYT",
    description: "Giấy tờ cần chuẩn bị trước khi đến khám.",
    prompt:
      "Khám bằng bảo hiểm y tế tại Khu Tự nguyện 1, Cơ sở 1 cần mang những giấy tờ gì?",
  },
  {
    icon: CalendarClock,
    title: "Hướng dẫn tái khám",
    description: "Chuẩn bị giấy hẹn và thủ tục cho lần khám sau.",
    prompt:
      "Tôi có giấy hẹn tái khám tại Bệnh viện Tim Hà Nội. Xin hướng dẫn những gì cần chuẩn bị.",
  },
]

function roleDetails(role: MessageRole) {
  if (role === "Assistant") {
    return { label: "Trợ lý Tim Hà Nội", Icon: HeartPulse }
  }
  return { label: "Anh/Chị", Icon: UserRound }
}

function toSpeechText(markdown: string) {
  return markdown
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[`*_>#|~-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function speakResponse(content: string) {
  if (!("speechSynthesis" in window)) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(toSpeechText(content))
  utterance.lang = "vi-VN"
  utterance.rate = 0.95
  window.speechSynthesis.speak(utterance)
}

function MessageItem({
  message,
  sessionId,
  onRetryMessage,
}: {
  message: ChatMessage
  sessionId?: string
  onRetryMessage?: (content: string) => void
}) {
  const { label, Icon } = roleDetails(message.role)
  const roleClass = message.role.toLowerCase()
  const canSpeak = message.role === "Assistant" && "speechSynthesis" in window
  const [preview, setPreview] = useState<string | null>(null)

  return (
    <article className={`message message-${roleClass}`}>
      <div className="message-avatar" aria-hidden="true">
        <Icon />
      </div>
      <div className="message-body">
        <div className="message-meta">
          <strong>{label}</strong>
          {message.delivery === "failed" ? (
            <div className="message-failed-tag">
              <span>Gửi thất bại</span>
              {onRetryMessage ? (
                <button
                  type="button"
                  className="retry-inline-button"
                  onClick={() => onRetryMessage(message.content)}
                >
                  <RefreshCw aria-hidden="true" />
                  Thử lại
                </button>
              ) : null}
            </div>
          ) : null}
          {canSpeak ? (
            <button
              type="button"
              className="speak-button"
              aria-label="Đọc phản hồi thành tiếng"
              title="Đọc phản hồi"
              onClick={() => speakResponse(message.content)}
            >
              <Volume2 aria-hidden="true" />
            </button>
          ) : null}
        </div>
        <div className="message-content">
          {message.images?.length ? (
            <div className="message-images" aria-label="Hình ảnh đính kèm">
              {message.images.map((image, index) => {
                const source = `data:${image.mimeType};base64,${image.data}`
                return (
                  <button type="button" className="message-image-button" key={`${image.mimeType}-${index}`} onClick={() => setPreview(source)}>
                    <img src={source} alt="Hình ảnh đính kèm" />
                  </button>
                )
              })}
            </div>
          ) : null}
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
            {message.content || "Chưa có nội dung phản hồi."}
          </ReactMarkdown>
        </div>
      </div>
      {preview ? (
        <div className="image-lightbox" role="dialog" aria-label="Xem hình ảnh" onClick={() => setPreview(null)}>
          <button type="button" className="image-lightbox-close" aria-label="Đóng hình ảnh" onClick={() => setPreview(null)}>×</button>
          <img src={preview} alt="Hình ảnh đính kèm phóng to" onClick={(event) => event.stopPropagation()} />
        </div>
      ) : null}
    </article>
  )
}

export function MessageThread({
  messages,
  loading,
  sending,
  error,
  onRetry,
  onRetryMessage,
  onSuggestion,
}: MessageThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const userScrolledUp = useRef(false)
  const [showScrollBottom, setShowScrollBottom] = useState(false)

  const visibleMessages = messages.filter(
    (message) =>
      message.role === "User" ||
      (message.role === "Assistant" && !message.content.startsWith("Tool Call:")),
  )

  useEffect(() => {
    const container = bottomRef.current?.closest(".conversation-scroll")
    if (!container) return

    const handleScroll = () => {
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120
      userScrolledUp.current = !isNearBottom
      setShowScrollBottom(!isNearBottom && visibleMessages.length > 2)
    }

    container.addEventListener("scroll", handleScroll, { passive: true })
    return () => container.removeEventListener("scroll", handleScroll)
  }, [visibleMessages.length])

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    const container = bottomRef.current?.closest(".conversation-scroll")
    if (container) {
      if (sending) {
        userScrolledUp.current = false
      }
      if (!userScrolledUp.current) {
        container.scrollTo({
          top: container.scrollHeight,
          behavior: reduceMotion ? "auto" : "smooth",
        })
      }
    }
  }, [messages, sending])

  const scrollToBottom = () => {
    const container = bottomRef.current?.closest(".conversation-scroll")
    if (container) {
      userScrolledUp.current = false
      setShowScrollBottom(false)
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth",
      })
    }
  }

  if (loading && visibleMessages.length === 0) {
    return (
      <div className="thread thread-loading" aria-label="Đang tải cuộc trò chuyện">
        <div className="message-skeleton message-skeleton-wide" />
        <div className="message-skeleton message-skeleton-short" />
        <div className="message-skeleton message-skeleton-medium" />
      </div>
    )
  }

  if (error && visibleMessages.length === 0) {
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
        <div className="welcome-brand">
          <img
            src="./bvtim_logo.png"
            alt="Bệnh viện Tim Hà Nội"
            width="180"
            height="104"
          />
        </div>
        <p className="eyebrow">
          <ShieldCheck aria-hidden="true" />
          HỖ TRỢ THÔNG TIN BỆNH VIỆN
        </p>
        <h2 id="welcome-title">
          <span>Xin chào, tôi là Trợ lý AI của</span>
          <span>Bệnh viện Tim Hà Nội</span>
        </h2>
        <p className="welcome-copy">
          Hỗ trợ tìm hiểu về đặt lịch, quy trình khám, bảo hiểm y tế,
          tái khám và dịch vụ bệnh viện.
        </p>

        <div className="suggestion-heading">
          <h3>Anh/Chị muốn hỏi về nội dung nào?</h3>
          <p>Chọn một gợi ý hoặc nhập câu hỏi riêng bên dưới.</p>
        </div>
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
        <MessageItem
          key={`${message.role}-${index}-${message.content.slice(0, 24)}`}
          message={message}
          onRetryMessage={onRetryMessage}
        />
      ))}
      {sending ? (
        <div className="message message-assistant message-thinking">
          <div className="message-avatar" aria-hidden="true">
            <HeartPulse />
          </div>
          <div className="message-body">
            <div className="message-meta">
              <strong>Trợ lý Tim Hà Nội</strong>
            </div>
            <div className="thinking-indicator">
              <LoaderCircle className="spin" aria-hidden="true" />
              <span>Đang tìm thông tin phù hợp…</span>
            </div>
          </div>
        </div>
      ) : null}
      <div ref={bottomRef} />
      {showScrollBottom && (
        <button
          type="button"
          className="scroll-bottom-floating-button"
          onClick={scrollToBottom}
          aria-label="Cuộn xuống tin nhắn mới nhất"
        >
          ↓ Tin nhắn mới nhất
        </button>
      )}
    </div>
  )
}

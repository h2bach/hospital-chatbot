import { ArrowUp, LoaderCircle, RefreshCw } from "lucide-react"
import { useEffect, useRef } from "react"

interface ComposerProps {
  value: string
  sending: boolean
  error: string | null
  onChange: (value: string) => void
  onSend: (value: string) => void
  onReload: () => void
}

export function Composer({
  value,
  sending,
  error,
  onChange,
  onSend,
  onReload,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = "0px"
    textarea.style.height = `${Math.min(textarea.scrollHeight, 184)}px`
  }, [value])

  function submit() {
    const message = value.trim()
    if (!message || sending) return
    onSend(message)
  }

  return (
    <div className="composer-wrap">
      {error ? (
        <div className="composer-error" role="alert">
          <span>
            <strong>Không gửi được tin nhắn.</strong>
            <span>{error}</span>
          </span>
          <button type="button" className="text-button" onClick={onReload}>
            <RefreshCw aria-hidden="true" />
            Đồng bộ lại
          </button>
        </div>
      ) : null}
      <div className="composer">
        <label htmlFor="message-composer" className="sr-only">
          Tin nhắn gửi tới agent
        </label>
        <textarea
          ref={textareaRef}
          id="message-composer"
          rows={1}
          value={value}
          disabled={sending}
          placeholder="Nhắn cho AI GO…"
          aria-describedby="composer-help"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              submit()
            }
          }}
        />
        <button
          type="button"
          className="send-button"
          aria-label={sending ? "Agent đang xử lý" : "Gửi tin nhắn"}
          disabled={!value.trim() || sending}
          onClick={submit}
        >
          {sending ? (
            <LoaderCircle className="spin" aria-hidden="true" />
          ) : (
            <ArrowUp aria-hidden="true" />
          )}
        </button>
      </div>
      <p id="composer-help" className="composer-help">
        Enter để gửi · Shift + Enter để xuống dòng. AI có thể mắc lỗi, hãy kiểm tra thông tin quan trọng.
      </p>
    </div>
  )
}

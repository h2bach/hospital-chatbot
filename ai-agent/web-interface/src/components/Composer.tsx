import {
  ArrowUp,
  LoaderCircle,
  Mic,
  MicOff,
  RefreshCw,
  ShieldCheck,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"

interface ComposerProps {
  value: string
  sending: boolean
  error: string | null
  onChange: (value: string) => void
  onSend: (value: string) => void
  onReload: () => void
}

interface SpeechRecognitionEventLike {
  results: {
    length: number
    [index: number]: {
      [index: number]: { transcript: string }
    }
  }
}

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
  start: () => void
  abort: () => void
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

function speechRecognitionConstructor() {
  const speechWindow = window as typeof window & {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition
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
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const [speechSupported] = useState(() => Boolean(speechRecognitionConstructor()))
  const [listening, setListening] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = "0px"
    const nextHeight = Math.min(textarea.scrollHeight, 168)
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > 168 ? "auto" : "hidden"
  }, [value])

  useEffect(() => {
    if (sending && recognitionRef.current) recognitionRef.current.abort()
  }, [sending])

  useEffect(
    () => () => {
      recognitionRef.current?.abort()
    },
    [],
  )

  function submit() {
    const message = value.trim()
    if (!message || sending) return
    recognitionRef.current?.abort()
    onSend(message)
  }

  function toggleVoiceInput() {
    setVoiceError(null)
    if (listening) {
      recognitionRef.current?.abort()
      return
    }

    const Recognition = speechRecognitionConstructor()
    if (!Recognition) return

    const recognition = new Recognition()
    recognition.lang = "vi-VN"
    recognition.continuous = false
    recognition.interimResults = false
    recognition.onresult = (event) => {
      const lastResult = event.results[event.results.length - 1]
      const transcript = lastResult?.[0]?.transcript.trim()
      if (transcript) onChange([value.trim(), transcript].filter(Boolean).join(" "))
    }
    recognition.onerror = () => {
      setVoiceError("Chưa nhận được giọng nói. Anh/Chị có thể thử lại hoặc nhập câu hỏi.")
      setListening(false)
    }
    recognition.onend = () => {
      recognitionRef.current = null
      setListening(false)
    }

    recognitionRef.current = recognition
    setListening(true)
    try {
      recognition.start()
    } catch {
      recognitionRef.current = null
      setListening(false)
      setVoiceError("Trình duyệt chưa thể bắt đầu nhận giọng nói.")
    }
  }

  return (
    <div className="composer-wrap">
      {error ? (
        <div className="composer-error" role="alert">
          <span>
            <strong>Chưa gửi được câu hỏi.</strong>
            <span>{error}</span>
          </span>
          <button type="button" className="text-button" onClick={onReload}>
            <RefreshCw aria-hidden="true" />
            Tải lại
          </button>
        </div>
      ) : null}
      <div className={`composer${listening ? " is-listening" : ""}`}>
        <label htmlFor="message-composer" className="sr-only">
          Câu hỏi gửi tới Trợ lý AI Bệnh viện Tim Hà Nội
        </label>
        <textarea
          ref={textareaRef}
          id="message-composer"
          rows={1}
          value={value}
          disabled={sending}
          placeholder="Nhập câu hỏi về đặt lịch, BHYT, quy trình khám…"
          aria-describedby="composer-help composer-privacy"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              submit()
            }
          }}
        />
        <div className="composer-actions">
          {speechSupported ? (
            <button
              type="button"
              className="voice-button"
              aria-label={listening ? "Dừng nhập bằng giọng nói" : "Nhập bằng giọng nói"}
              aria-pressed={listening}
              title={listening ? "Dừng nghe" : "Nhập bằng giọng nói"}
              disabled={sending}
              onClick={toggleVoiceInput}
            >
              {listening ? <MicOff aria-hidden="true" /> : <Mic aria-hidden="true" />}
            </button>
          ) : null}
          <button
            type="button"
            className="send-button"
            aria-label={sending ? "Trợ lý đang xử lý" : "Gửi câu hỏi"}
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
      </div>
      {listening ? (
        <p className="voice-status" role="status">
          <span aria-hidden="true" />
          Đang nghe tiếng Việt…
        </p>
      ) : voiceError ? (
        <p className="voice-error" role="status">
          {voiceError}
        </p>
      ) : null}
      <div className="composer-footer">
        <p id="composer-help" className="composer-help">
          Enter để gửi · Shift + Enter để xuống dòng
        </p>
        <p id="composer-privacy" className="composer-privacy">
          <ShieldCheck aria-hidden="true" />
          Không gửi CCCD, số thẻ BHYT hoặc hồ sơ bệnh án nếu không cần thiết.
        </p>
      </div>
    </div>
  )
}

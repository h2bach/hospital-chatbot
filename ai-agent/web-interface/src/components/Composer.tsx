import {
  AlertCircle,
  ArrowUp,
  LoaderCircle,
  Mic,
  RefreshCw,
  ShieldCheck,
  Square,
  X,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { transcribeAudio } from "../lib/api"

async function convertToWav(audio: Blob): Promise<Blob> {
  const context = new AudioContext()
  try {
    const decoded = await context.decodeAudioData(await audio.arrayBuffer())
    const channels = decoded.numberOfChannels
    const samples = decoded.length
    const bytesPerSample = 2
    const buffer = new ArrayBuffer(44 + samples * channels * bytesPerSample)
    const view = new DataView(buffer)
    const write = (offset: number, value: string) => [...value].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)))
    write(0, "RIFF")
    view.setUint32(4, 36 + samples * channels * bytesPerSample, true)
    write(8, "WAVE")
    write(12, "fmt ")
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, channels, true)
    view.setUint32(24, decoded.sampleRate, true)
    view.setUint32(28, decoded.sampleRate * channels * bytesPerSample, true)
    view.setUint16(32, channels * bytesPerSample, true)
    view.setUint16(34, 16, true)
    write(36, "data")
    view.setUint32(40, samples * channels * bytesPerSample, true)
    const channelData = Array.from({ length: channels }, (_, index) => decoded.getChannelData(index))
    let offset = 44
    for (let sample = 0; sample < samples; sample += 1) {
      for (let channel = 0; channel < channels; channel += 1) {
        const value = Math.max(-1, Math.min(1, channelData[channel][sample]))
        view.setInt16(offset, value < 0 ? value * 0x8000 : value * 0x7fff, true)
        offset += 2
      }
    }
    return new Blob([buffer], { type: "audio/wav" })
  } finally {
    await context.close()
  }
}

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
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [speechSupported] = useState(() => typeof MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia))
  const [listening, setListening] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
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
    if (sending && recorderRef.current) recorderRef.current.stop()
  }, [sending])

  useEffect(() => {
    if (!listening) return
    const timer = window.setInterval(() => {
      if (recordingStartedAtRef.current !== null) {
        setRecordingSeconds(Math.floor((Date.now() - recordingStartedAtRef.current) / 1000))
      }
    }, 250)
    return () => window.clearInterval(timer)
  }, [listening])

  const recordingStartedAtRef = useRef<number | null>(null)

  useEffect(
    () => () => {
      recorderRef.current?.stop()
    },
    [],
  )

  function submit() {
    const message = value.trim()
    if (!message || sending) return
    recorderRef.current?.stop()
    onSend(message)
  }

  async function toggleVoiceInput() {
    setVoiceError(null)
    if (listening) {
      recorderRef.current?.stop()
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm"
      const recorder = new MediaRecorder(stream, { mimeType })
      chunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onerror = () => {
        stream.getTracks().forEach((track) => track.stop())
        setListening(false)
        setVoiceError("Không thể chuyển giọng nói thành văn bản. Anh/Chị vui lòng thử lại sau.")
      }
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop())
        recorderRef.current = null
        recordingStartedAtRef.current = null
        setListening(false)
        setTranscribing(true)
        try {
          const wav = await convertToWav(new Blob(chunksRef.current, { type: mimeType }))
          const transcript = await transcribeAudio(wav)
          if (transcript) onChange([value.trim(), transcript].filter(Boolean).join(" "))
        } catch {
          setVoiceError("Không thể chuyển giọng nói thành văn bản. Anh/Chị vui lòng thử lại sau.")
        } finally {
          setTranscribing(false)
        }
      }
      recorderRef.current = recorder
      recordingStartedAtRef.current = Date.now()
      setRecordingSeconds(0)
      setListening(true)
      recorder.start()
    } catch {
      setListening(false)
      setTranscribing(false)
      setVoiceError("Không thể chuyển giọng nói thành văn bản. Anh/Chị vui lòng thử lại sau.")
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

      <div className={`composer${listening ? " is-listening" : ""}${transcribing ? " is-transcribing" : ""}`}>
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
          aria-describedby="composer-privacy"
          onChange={(event) => onChange(event.target.value)}
          onBlur={() => window.scrollTo(0, 0)}
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
              aria-label={listening ? "Dừng ghi âm" : "Nhập bằng giọng nói"}
              aria-pressed={listening}
              title={listening ? "Dừng ghi âm" : "Nhập bằng giọng nói"}
              disabled={sending || transcribing}
              onClick={toggleVoiceInput}
            >
              {listening ? <Square aria-hidden="true" /> : <Mic aria-hidden="true" />}
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
        <div className="voice-status voice-status-recording" role="status">
          <div className="voice-status-left">
            <span className="recording-dot-wrap" aria-hidden="true">
              <span className="recording-dot" />
            </span>
            <strong className="recording-title">Đang ghi âm…</strong>
            <span className="recording-timer">
              {String(Math.floor(recordingSeconds / 60)).padStart(2, "0")}:{String(recordingSeconds % 60).padStart(2, "0")}
            </span>
          </div>
          <span className="recording-hint">Nhấn nút vuông để dừng và gửi</span>
        </div>
      ) : transcribing ? (
        <div className="voice-status voice-status-transcribing" role="status">
          <LoaderCircle className="spin" aria-hidden="true" />
          <span>Đang chuyển giọng nói thành văn bản…</span>
        </div>
      ) : voiceError ? (
        <div className="voice-status voice-status-error" role="status">
          <AlertCircle aria-hidden="true" />
          <span>{voiceError}</span>
          <button
            type="button"
            className="voice-error-dismiss"
            aria-label="Đóng thông báo lỗi"
            onClick={() => setVoiceError(null)}
          >
            <X aria-hidden="true" />
          </button>
        </div>
      ) : null}
      <div className="composer-footer">
        <p id="composer-privacy" className="composer-privacy">
          <ShieldCheck aria-hidden="true" />
          Không gửi CCCD, số thẻ BHYT hoặc hồ sơ bệnh án nếu không cần thiết.
        </p>
      </div>
    </div>
  )
}

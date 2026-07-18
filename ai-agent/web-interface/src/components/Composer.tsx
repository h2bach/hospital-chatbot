import {
  ArrowUp,
  LoaderCircle,
  Mic,
  Paperclip,
  RefreshCw,
  ShieldCheck,
  Square,
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
import type { ClipboardEvent } from "react"
import type { ChatImage } from "../types"

interface ComposerProps {
  value: string
  sending: boolean
  error: string | null
  onChange: (value: string) => void
	onSend: (value: string, images: ChatImage[]) => void
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
  const recordingStartedAtRef = useRef<number | null>(null)
  const [images, setImages] = useState<ChatImage[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const allowedTypes = ["image/jpeg", "image/png"] as const

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
    onSend(message, images)
    setImages([])
  }

  function addImages(files: ArrayLike<File> | null) {
    if (!files) return
    const candidates = Array.from(files).slice(0, 2 - images.length)
    void Promise.all(candidates.map((file) => new Promise<ChatImage | null>((resolve) => {
      if (!allowedTypes.includes(file.type as (typeof allowedTypes)[number]) || file.size > 10 * 1024 * 1024) {
        resolve(null)
        return
      }
      const reader = new FileReader()
      reader.onload = () => resolve({
        mimeType: file.type as ChatImage["mimeType"],
        data: String(reader.result).split(",", 2)[1] ?? "",
        name: file.name,
      })
      reader.onerror = () => resolve(null)
      reader.readAsDataURL(file)
    }))).then((loaded) => setImages((current) => [...current, ...loaded.filter((item): item is ChatImage => item !== null)]))
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pastedImages = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null)
    if (pastedImages.length === 0) return
    event.preventDefault()
    addImages(pastedImages)
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
        setVoiceError("Không thể ghi âm. Anh/Chị vui lòng thử lại.")
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
        } catch (error) {
          setVoiceError(error instanceof Error ? error.message : "Chưa nhận dạng được giọng nói.")
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
      setVoiceError("Không thể truy cập microphone. Anh/Chị vui lòng cấp quyền rồi thử lại.")
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
          aria-describedby="composer-help composer-privacy"
          onChange={(event) => onChange(event.target.value)}
          onPaste={handlePaste}
          onBlur={() => window.scrollTo(0, 0)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              submit()
            }
          }}
        />
        <div className="composer-actions">
          <input
            ref={fileInputRef}
            className="sr-only"
            type="file"
            accept="image/jpeg,image/png"
            multiple
            onChange={(event) => {
              addImages(event.target.files)
              event.currentTarget.value = ""
            }}
          />
          <button
            type="button"
            className="voice-button"
            aria-label="Đính kèm hình ảnh"
            title="Đính kèm hình ảnh (JPEG, PNG)"
            disabled={sending || images.length >= 2}
            onClick={() => fileInputRef.current?.click()}
          >
            <Paperclip aria-hidden="true" />
          </button>
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
      {images.length > 0 ? (
        <div className="composer-help" role="status">
          {images.map((image, index) => (
            <button key={`${image.name}-${index}`} type="button" className="text-button" onClick={() => setImages((current) => current.filter((_, itemIndex) => itemIndex !== index))}>
              {image.name} ×
            </button>
          ))}
        </div>
      ) : null}
      {listening ? (
        <div className="voice-status voice-status-recording" role="status">
          <span className="recording-dot" aria-hidden="true" />
          <strong>Đang ghi âm</strong>
          <span>{String(Math.floor(recordingSeconds / 60)).padStart(2, "0")}:{String(recordingSeconds % 60).padStart(2, "0")}</span>
          <small>Nhấn nút vuông để dừng</small>
        </div>
      ) : transcribing ? (
        <div className="voice-status voice-status-transcribing" role="status">
          <span className="recording-spinner" aria-hidden="true" />
          <span>Đang chuyển giọng nói thành văn bản…</span>
        </div>
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

import {
  AlertCircle,
  ArrowUp,
  LoaderCircle,
  Mic,
  Paperclip,
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
import type { ClipboardEvent } from "react"
import type { ChatImage } from "../types"

interface ComposerProps {
  value: string
  images: ChatImage[]
  sending: boolean
  error: string | null
  onChange: (value: string) => void
  onImagesChange: (images: ChatImage[]) => void
  onSend: (value: string, images: ChatImage[]) => void
  onReload: () => void
}

async function processImageFile(file: File): Promise<ChatImage | null> {
  return new Promise((resolve) => {
    const isImage = file.type.startsWith("image/") || file.type === "" || /\.(jpe?g|png|webp|heic|heif)$/i.test(file.name)
    if (!isImage) {
      resolve(null)
      return
    }

    const reader = new FileReader()
    reader.onerror = () => resolve(null)
    reader.onload = (e) => {
      const result = e.target?.result
      if (typeof result !== "string") {
        resolve(null)
        return
      }

      const img = new Image()
      img.onerror = () => {
        const parts = result.split(",", 2)
        if (parts.length === 2) {
          const rawMime = (file.type === "image/png" ? "image/png" : "image/jpeg") as ChatImage["mimeType"]
          resolve({
            mimeType: rawMime,
            data: parts[1],
            name: file.name,
          })
        } else {
          resolve(null)
        }
      }

      img.onload = () => {
        try {
          const MAX_SIZE = 1920
          let width = img.width
          let height = img.height

          if (width > MAX_SIZE || height > MAX_SIZE) {
            if (width > height) {
              height = Math.round((height * MAX_SIZE) / width)
              width = MAX_SIZE
            } else {
              width = Math.round((width * MAX_SIZE) / height)
              height = MAX_SIZE
            }
          }

          const canvas = document.createElement("canvas")
          canvas.width = width
          canvas.height = height
          const ctx = canvas.getContext("2d")
          if (!ctx) {
            resolve(null)
            return
          }

          ctx.drawImage(img, 0, 0, width, height)
          const dataUrl = canvas.toDataURL("image/jpeg", 0.85)
          const base64Data = dataUrl.split(",", 2)[1] ?? ""
          resolve({
            mimeType: "image/jpeg",
            data: base64Data,
            name: file.name,
          })
        } catch {
          resolve(null)
        }
      }

      img.src = result
    }
    reader.readAsDataURL(file)
  })
}

export function Composer({
  value,
  images,
  sending,
  error,
  onChange,
  onImagesChange,
  onSend,
  onReload,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [speechSupported] = useState(() => typeof MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia))
  const [listening, setListening] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [processingImages, setProcessingImages] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)
  const recordingStartedAtRef = useRef<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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
    if (!message || sending || processingImages) return
    recorderRef.current?.stop()
    onSend(message, images)
  }

  async function addImages(files: ArrayLike<File> | null) {
    if (!files || files.length === 0) return
    setImageError(null)
    const availableSlots = 2 - images.length
    if (availableSlots <= 0) return

    const candidates = Array.from(files).slice(0, availableSlots)
    setProcessingImages(true)
    try {
      const processed = await Promise.all(candidates.map(processImageFile))
      const valid = processed.filter((item): item is ChatImage => item !== null)
      if (valid.length === 0) {
        setImageError("Không thể đọc được tệp hình ảnh. Vui lòng chọn ảnh định dạng JPG, PNG hoặc WEBP.")
      } else {
        onImagesChange([...images, ...valid])
      }
    } catch {
      setImageError("Đã xảy ra lỗi khi xử lý hình ảnh.")
    } finally {
      setProcessingImages(false)
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pastedImages = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null)
    if (pastedImages.length === 0) return
    event.preventDefault()
    void addImages(pastedImages)
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

      {images.length > 0 || processingImages ? (
        <div className="composer-image-previews" role="region" aria-label="Hình ảnh đã đính kèm">
          {images.map((image, index) => {
            const thumbnail = `data:${image.mimeType};base64,${image.data}`
            return (
              <div className="composer-image-item" key={`${image.name || "img"}-${index}`}>
                <img src={thumbnail} alt={image.name || "Đã đính kèm"} />
                <div className="composer-image-info">
                  <span className="composer-image-name">{image.name || `Hình ${index + 1}`}</span>
                  <small className="composer-image-meta">Đã tải lên</small>
                </div>
                <button
                  type="button"
                  className="composer-image-remove"
                  aria-label={`Xóa hình ${image.name || index + 1}`}
                  onClick={() => onImagesChange(images.filter((_, itemIndex) => itemIndex !== index))}
                >
                  <X aria-hidden="true" />
                </button>
              </div>
            )
          })}
          {processingImages ? (
            <div className="composer-image-item composer-image-loading">
              <LoaderCircle className="spin" aria-hidden="true" />
              <span>Đang xử lý ảnh…</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {imageError ? (
        <p className="voice-error" role="status">
          {imageError}
        </p>
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
            id="composer-file-input"
            className="sr-only"
            type="file"
            accept="image/*,image/jpeg,image/png,image/webp,image/heic,image/heif"
            multiple
            onChange={(event) => {
              void addImages(event.target.files)
              event.currentTarget.value = ""
            }}
          />
          <button
            type="button"
            className="voice-button"
            aria-label="Đính kèm hình ảnh"
            title="Đính kèm hình ảnh (JPEG, PNG, WEBP)"
            disabled={sending || images.length >= 2 || processingImages}
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
            disabled={(!value.trim() && images.length === 0) || sending || processingImages}
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

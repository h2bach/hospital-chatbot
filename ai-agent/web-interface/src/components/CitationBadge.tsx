import React, { useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { ExternalLink, BookOpen, CheckCircle2, LoaderCircle, X } from "lucide-react"
import { CitationItem, CitationContextResponse, HighlightRange } from "../types"
import { getCitationContext, ApiError } from "../lib/api"

interface CitationBadgeProps {
  citationId: string
  indexText: string
  citations?: CitationItem[]
  sessionId: string
}

function sourceKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    rag_document: "Tài liệu chính thức",
    hospital_facility: "Cơ sở bệnh viện",
    hospital_organization: "Đơn vị bệnh viện",
    hospital_room: "Phòng và khu khám",
    hospital_doctor: "Danh bạ bác sĩ",
    doctor_schedule: "Lịch bác sĩ",
    doctor_availability: "Phân công bác sĩ",
    scheduling_rule: "Quy tắc xếp lịch",
    system_time: "Thời gian hệ thống",
    hospital_directory: "Dữ liệu bệnh viện",
  }
  return labels[kind] ?? "Nguồn dữ liệu"
}

function matchStatusLabel(status: string): string {
  if (status === "exact") return "Khớp chính xác"
  if (status === "approximate") return "Khớp gần đúng"
  return status || "Chính xác"
}

// Highlight offsets are Unicode code-point based (mirrors the Go backend), so
// slice via Array.from instead of raw UTF-16 string indices.
function renderHighlightedText(text: string, ranges: HighlightRange[] | undefined) {
  if (!text) return null
  const characters = Array.from(text)
  if (!ranges || ranges.length === 0) {
    return <mark className="citation-highlight">{text}</mark>
  }
  const sorted = [...ranges].sort((a, b) => a.start - b.start)
  const elements: React.ReactNode[] = []
  let lastIndex = 0
  sorted.forEach((range, index) => {
    const start = Math.max(0, Math.min(range.start, characters.length))
    const end = Math.max(start, Math.min(range.end, characters.length))
    if (start > lastIndex) elements.push(characters.slice(lastIndex, start).join(""))
    elements.push(
      <mark key={index} className="citation-highlight">
        {characters.slice(start, end).join("")}
      </mark>,
    )
    lastIndex = end
  })
  if (lastIndex < characters.length) elements.push(characters.slice(lastIndex).join(""))
  return elements
}

interface PopoverPosition {
  left: number
  top: number
  placement: "top" | "bottom"
}

function CitationSidePanel({
  citation,
  sessionId,
  onClose,
}: {
  citation: CitationItem
  sessionId: string
  onClose: () => void
}) {
  const [context, setContext] = useState<CitationContextResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const requested = useRef(false)
  const panelRef = useRef<HTMLElement>(null)

  if (!requested.current) {
    requested.current = true
    getCitationContext(sessionId, citation.id)
      .then(setContext)
      .catch((cause: unknown) => {
        setError(
          cause instanceof ApiError
            ? cause.message
            : "Chưa tải được ngữ cảnh trích dẫn. Anh/Chị vui lòng thử lại.",
        )
      })
  }

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (panelRef.current && event.target instanceof Node && !panelRef.current.contains(event.target)) {
        onClose()
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    document.addEventListener("mousedown", handlePointerDown)
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.removeEventListener("mousedown", handlePointerDown)
    }
  }, [onClose])

  return createPortal(
    <aside
      ref={panelRef}
      className="citation-side-panel"
      role="dialog"
      aria-label={`Trích dẫn [${citation.index}]: ${citation.title}`}
    >
      <header className="citation-context-header">
        <div>
          <span className="citation-kind-tag">
            <BookOpen aria-hidden="true" />
            [{citation.index}] &bull; {sourceKindLabel(citation.source_kind)}
          </span>
          <h2>{citation.title}</h2>
          {citation.location?.section ? (
            <p className="citation-context-section">{citation.location.section}</p>
          ) : null}
        </div>
        <button type="button" className="citation-context-close" aria-label="Đóng trích dẫn" onClick={onClose}>
          <X aria-hidden="true" />
        </button>
      </header>

      <div className="citation-panel-meta">
        <span className="citation-status-badge">
          <CheckCircle2 aria-hidden="true" />
          {matchStatusLabel(citation.match_status)}
        </span>
        {citation.confidence > 0 ? (
          <span className="citation-confidence-tag">Độ tin cậy {Math.round(citation.confidence * 100)}%</span>
        ) : null}
      </div>

      {context?.warning ? <p className="citation-context-warning">{context.warning}</p> : null}

      <div className="citation-context-body">
        <section className="citation-context-block citation-context-anchor">
          <span className="citation-anchor-tag">Đoạn được trích dẫn</span>
          <p className="citation-context-text">
            {renderHighlightedText(citation.excerpt, citation.highlight_ranges)}
          </p>
        </section>

        {!context && !error ? (
          <p className="citation-context-loading">
            <LoaderCircle className="spin" aria-hidden="true" />
            Đang tải ngữ cảnh tài liệu…
          </p>
        ) : null}
        {error ? <p className="citation-context-error">{error}</p> : null}

        {context && context.blocks.length > 0 ? (
          <>
            <h3 className="citation-panel-context-title">Ngữ cảnh trong tài liệu gốc</h3>
            {context.blocks.map((block) => (
              <section
                key={block.id}
                className={block.is_anchor ? "citation-context-block citation-context-anchor" : "citation-context-block"}
              >
                {block.heading ? <h3>{block.heading}</h3> : null}
                {block.is_anchor ? <span className="citation-anchor-tag">Đoạn được trích dẫn</span> : null}
                {block.text ? (
                  <p className="citation-context-text">
                    {block.is_anchor ? renderHighlightedText(block.text, block.highlight_ranges) : block.text}
                  </p>
                ) : null}
                {block.fields.length > 0 ? (
                  <dl className="citation-context-fields">
                    {block.fields.map((field, index) => (
                      <div key={`${field.label}-${index}`} className="citation-context-field">
                        <dt>{field.label}</dt>
                        <dd>{field.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
              </section>
            ))}
          </>
        ) : null}
      </div>
    </aside>,
    document.body,
  )
}

export const CitationBadge: React.FC<CitationBadgeProps> = ({
  citationId,
  indexText,
  citations = [],
  sessionId,
}) => {
  const [popoverPosition, setPopoverPosition] = useState<PopoverPosition | null>(null)
  const [isPanelOpen, setIsPanelOpen] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  const rawIndex = indexText.replace(/[[\]]/g, "")
  const citation = citations.find(
    (c) => c.id === citationId || String(c.index) === rawIndex,
  )

  const showPopover = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
    const rect = buttonRef.current?.getBoundingClientRect()
    if (!rect) return
    const viewportWidth = window.innerWidth
    const width = Math.min(360, viewportWidth * 0.92)
    const half = width / 2
    const centerX = rect.left + rect.width / 2
    const left = Math.min(Math.max(centerX, half + 8), viewportWidth - half - 8)
    const placement: PopoverPosition["placement"] = rect.top > 320 ? "top" : "bottom"
    const top = placement === "top" ? rect.top - 8 : rect.bottom + 8
    setPopoverPosition({ left, top, placement })
  }

  const scheduleHidePopover = () => {
    timeoutRef.current = setTimeout(() => {
      setPopoverPosition(null)
    }, 250)
  }

  const keepPopover = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }

  const openPanel = () => {
    setPopoverPosition(null)
    setIsPanelOpen(true)
  }

  const cleanIndex = citation ? citation.index : rawIndex

  if (!citation) {
    return <span className="citation-badge-fallback">[{cleanIndex}]</span>
  }

  return (
    <span className="citation-badge-wrapper">
      <button
        ref={buttonRef}
        type="button"
        className="citation-badge-button"
        onMouseEnter={showPopover}
        onMouseLeave={scheduleHidePopover}
        onClick={openPanel}
        aria-label={`Trích dẫn [${cleanIndex}] - ${citation.title}`}
      >
        {cleanIndex}
      </button>

      {popoverPosition
        ? createPortal(
            <div
              className={`citation-popover citation-popover-${popoverPosition.placement}`}
              style={{ left: popoverPosition.left, top: popoverPosition.top }}
              onMouseEnter={keepPopover}
              onMouseLeave={scheduleHidePopover}
            >
              <div className="citation-popover-header">
                <span className="citation-kind-tag">
                  <BookOpen aria-hidden="true" />
                  [{cleanIndex}] &bull; {sourceKindLabel(citation.source_kind)}
                </span>
                {citation.confidence > 0 && (
                  <span className="citation-confidence-tag">
                    {Math.round(citation.confidence * 100)}%
                  </span>
                )}
              </div>

              <div className="citation-popover-title">{citation.title}</div>

              <div className="citation-popover-excerpt">
                &ldquo;{renderHighlightedText(citation.excerpt, citation.highlight_ranges)}&rdquo;
              </div>

              {citation.location?.section && (
                <div className="citation-popover-location">
                  <strong>Vị trí:</strong> {citation.location.section}
                </div>
              )}

              <div className="citation-popover-footer">
                <span className="citation-status-badge">
                  <CheckCircle2 aria-hidden="true" />
                  {matchStatusLabel(citation.match_status)}
                </span>

                <button type="button" className="citation-context-btn" onClick={openPanel}>
                  <ExternalLink aria-hidden="true" />
                  Xem ngữ cảnh
                </button>
              </div>
            </div>,
            document.body,
          )
        : null}

      {isPanelOpen ? (
        <CitationSidePanel
          citation={citation}
          sessionId={sessionId}
          onClose={() => setIsPanelOpen(false)}
        />
      ) : null}
    </span>
  )
}

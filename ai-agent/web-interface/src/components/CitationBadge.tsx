import React, { useRef, useState } from "react"
import { ExternalLink, BookOpen, CheckCircle2 } from "lucide-react"
import { CitationItem } from "../types"

interface CitationBadgeProps {
  citationId: string
  indexText: string
  citations?: CitationItem[]
  sessionId: string
}

export const CitationBadge: React.FC<CitationBadgeProps> = ({
  citationId,
  indexText,
  citations = [],
  sessionId: _sessionId,
}) => {
  const [isPopoverVisible, setIsPopoverVisible] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const rawIndex = indexText.replace(/[[\]]/g, "")
  const citation = citations.find(
    (c) => c.id === citationId || String(c.index) === rawIndex,
  )

  const handleMouseEnter = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
    setIsPopoverVisible(true)
  }

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setIsPopoverVisible(false)
    }, 250)
  }

  const cleanIndex = citation ? citation.index : rawIndex

  if (!citation) {
    return <span className="citation-badge-fallback">[{cleanIndex}]</span>
  }

  const renderHighlightedText = (text: string) => {
    if (!text) return null
    if (!citation.highlight_ranges || citation.highlight_ranges.length === 0) {
      return <mark className="citation-highlight">{text}</mark>
    }
    const ranges = [...citation.highlight_ranges].sort((a, b) => a.start - b.start)
    const elements: React.ReactNode[] = []
    let lastIndex = 0
    ranges.forEach((range, idx) => {
      if (range.start > lastIndex) elements.push(text.slice(lastIndex, range.start))
      elements.push(
        <mark key={idx} className="citation-highlight">
          {text.slice(range.start, range.end)}
        </mark>,
      )
      lastIndex = range.end
    })
    if (lastIndex < text.length) elements.push(text.slice(lastIndex))
    return elements
  }

  return (
    <span
      className="citation-badge-wrapper"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        type="button"
        className="citation-badge-button"
        onClick={() => setIsPopoverVisible((prev) => !prev)}
        aria-label={`Trích dẫn [${cleanIndex}] - ${citation.title}`}
      >
        [{cleanIndex}]
      </button>

      {isPopoverVisible && (
        <div
          className="citation-popover"
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          <div className="citation-popover-header">
            <span className="citation-kind-tag">
              <BookOpen style={{ width: 14, height: 14 }} />
              [{cleanIndex}] &bull;{" "}
              {citation.source_kind === "doctor_schedule"
                ? "Lịch bác sĩ"
                : citation.source_kind === "hospital_directory"
                  ? "Danh mục"
                  : "Tài liệu RAG"}
            </span>
            {citation.confidence > 0 && (
              <span className="citation-confidence-tag">
                {Math.round(citation.confidence * 100)}%
              </span>
            )}
          </div>

          <div className="citation-popover-title">{citation.title}</div>

          <div className="citation-popover-excerpt">
            &ldquo;{renderHighlightedText(citation.excerpt)}&rdquo;
          </div>

          {citation.location?.section && (
            <div className="citation-popover-location">
              <strong>Vị trí:</strong> {citation.location.section}
            </div>
          )}

          <div className="citation-popover-footer">
            <span className="citation-status-badge">
              <CheckCircle2 style={{ width: 12, height: 12 }} />
              {citation.match_status || "Chính xác"}
            </span>

            {citation.context_available && (
              <button
                type="button"
                className="citation-context-btn"
                onClick={(e) => {
                  e.stopPropagation()
                  setIsPopoverVisible(false)
                }}
              >
                <ExternalLink style={{ width: 14, height: 14 }} />
                Xem ngữ cảnh
              </button>
            )}
          </div>
        </div>
      )}
    </span>
  )
}

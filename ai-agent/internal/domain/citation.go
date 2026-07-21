package domain

// TextRange uses Unicode code-point offsets, not UTF-8 byte offsets. The web
// client mirrors this with Array.from(text) before slicing Vietnamese text.
type TextRange struct {
	Start int `json:"start"`
	End   int `json:"end"`
}

type CitationLocation struct {
	SourceID   string   `json:"source_id,omitempty"`
	DocumentID string   `json:"document_id,omitempty"`
	ChunkID    string   `json:"chunk_id,omitempty"`
	Section    string   `json:"section,omitempty"`
	Page       int      `json:"page,omitempty"`
	LineStart  int      `json:"line_start,omitempty"`
	LineEnd    int      `json:"line_end,omitempty"`
	Heading    []string `json:"heading_path,omitempty"`
}

type CitationFreshness struct {
	Version        string `json:"version,omitempty"`
	EffectiveAt    string `json:"effective_at,omitempty"`
	ObservedAt     string `json:"observed_at,omitempty"`
	ApprovalStatus string `json:"approval_status,omitempty"`
}

type Citation struct {
	ID               string            `json:"id"`
	Index            int               `json:"index"`
	SourceKind       string            `json:"source_kind"`
	Title            string            `json:"title"`
	Excerpt          string            `json:"excerpt"`
	HighlightRanges  []TextRange       `json:"highlight_ranges,omitempty"`
	MatchStatus      string            `json:"match_status"`
	Confidence       *float64          `json:"confidence,omitempty"`
	Location         CitationLocation  `json:"location"`
	Freshness        CitationFreshness `json:"freshness"`
	ContextAvailable bool              `json:"context_available"`
}

type CitationField struct {
	Label       string `json:"label"`
	Value       string `json:"value"`
	Highlighted bool   `json:"highlighted,omitempty"`
}

type CitationContextBlock struct {
	ID              string          `json:"id"`
	Heading         string          `json:"heading,omitempty"`
	Text            string          `json:"text,omitempty"`
	Fields          []CitationField `json:"fields,omitempty"`
	IsAnchor        bool            `json:"is_anchor"`
	HighlightRanges []TextRange     `json:"highlight_ranges,omitempty"`
}

type CitationContextSnapshot struct {
	Citation Citation               `json:"citation"`
	Blocks   []CitationContextBlock `json:"blocks"`
	Warning  string                 `json:"warning,omitempty"`
}

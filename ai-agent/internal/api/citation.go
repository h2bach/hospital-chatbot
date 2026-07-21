package api

import (
	"agent/internal/api/dto"
	"agent/internal/domain"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

type citationContextResponse struct {
	Citation domain.Citation               `json:"citation"`
	Blocks   []domain.CitationContextBlock `json:"blocks"`
	Warning  string                        `json:"warning,omitempty"`
}

func (svr *Server) GetCitationContext(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	citationID := r.PathValue("citation_id")
	if sessionID == "" || citationID == "" {
		writeJSON(w, dto.NewErrorResponse("citation không hợp lệ"), http.StatusBadRequest)
		return
	}
	session, err := svr.getOwnedSession(r, sessionID)
	if err != nil {
		writeJSON(w, dto.NewErrorResponse("không tìm thấy citation"), http.StatusNotFound)
		return
	}
	snapshot, ok := session.CitationContexts[citationID]
	if !ok {
		writeJSON(w, dto.NewErrorResponse("không tìm thấy citation"), http.StatusNotFound)
		return
	}

	scope := strings.TrimSpace(r.URL.Query().Get("scope"))
	if scope == "" {
		scope = "section"
	}
	if scope != "section" && scope != "document" {
		writeJSON(w, dto.NewErrorResponse("scope không hợp lệ"), http.StatusBadRequest)
		return
	}
	limit := 12
	if raw := r.URL.Query().Get("limit"); raw != "" {
		parsed, parseErr := strconv.Atoi(raw)
		if parseErr != nil || parsed < 1 || parsed > 20 {
			writeJSON(w, dto.NewErrorResponse("limit phải nằm trong 1..20"), http.StatusBadRequest)
			return
		}
		limit = parsed
	}

	if snapshot.Citation.SourceKind == "rag_document" && snapshot.Citation.Location.ChunkID != "" {
		if expanded, expandErr := expandRAGCitationContext(r.Context(), snapshot, scope, limit); expandErr == nil {
			snapshot = expanded
		} else {
			snapshot.Warning = "Chưa tải được ngữ cảnh mở rộng; đang hiển thị đúng đoạn căn cứ đã dùng để trả lời."
		}
	}
	writeJSON(w, citationContextResponse{
		Citation: snapshot.Citation,
		Blocks: snapshot.Blocks,
		Warning: snapshot.Warning,
	}, http.StatusOK)
}

func expandRAGCitationContext(ctx context.Context, snapshot domain.CitationContextSnapshot, scope string, limit int) (domain.CitationContextSnapshot, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(os.Getenv("RAG_SERVICE_URL")), "/")
	if baseURL == "" {
		baseURL = strings.TrimRight(strings.TrimSpace(os.Getenv("RAG_CORE_URL")), "/")
	}
	if baseURL == "" {
		baseURL = "http://localhost:6689"
	}
	body, err := json.Marshal(map[string]any{
		"chunk_id": snapshot.Citation.Location.ChunkID,
		"scope": scope,
		"limit": limit,
	})
	if err != nil {
		return snapshot, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/api/v1/rag/context", bytes.NewReader(body))
	if err != nil {
		return snapshot, err
	}
	request.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 5 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		return snapshot, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return snapshot, fmt.Errorf("rag context returned HTTP %d", response.StatusCode)
	}
	var payload struct {
		Status string `json:"status"`
		Chunks []struct {
			ChunkID     string         `json:"chunk_id"`
			ContentText string         `json:"content_text"`
			HeadingPath []string       `json:"heading_path"`
			Facts       map[string]any `json:"facts"`
		} `json:"chunks"`
	}
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return snapshot, err
	}
	if payload.Status != "exact" || len(payload.Chunks) == 0 {
		return snapshot, fmt.Errorf("rag context unavailable")
	}

	blocks := make([]domain.CitationContextBlock, 0, len(payload.Chunks))
	anchorFound := false
	for _, chunk := range payload.Chunks {
		isAnchor := chunk.ChunkID == snapshot.Citation.Location.ChunkID
		text := strings.TrimSpace(chunk.ContentText)
		fields := citationFields(chunk.Facts, 16)
		if text == "" {
			text = citationFieldsText(fields)
		}
		block := domain.CitationContextBlock{
			ID: chunk.ChunkID, Heading: strings.Join(chunk.HeadingPath, " › "),
			Text: text, Fields: fields, IsAnchor: isAnchor,
		}
		if isAnchor {
			anchorFound = true
			if !sameEvidenceText(snapshot.Citation.Excerpt, text) {
				block.Text = snapshot.Citation.Excerpt
				block.Fields = snapshotAnchorFields(snapshot)
				snapshot.Warning = "Nguồn hiện tại có thay đổi so với thời điểm trả lời; đoạn được trích ban đầu được giữ nguyên để đối chiếu."
			}
			block.HighlightRanges = snapshot.Citation.HighlightRanges
		}
		blocks = append(blocks, block)
	}
	if !anchorFound {
		blocks = append([]domain.CitationContextBlock{{
			ID: snapshot.Citation.Location.ChunkID, Heading: snapshot.Citation.Location.Section,
			Text: snapshot.Citation.Excerpt, Fields: snapshotAnchorFields(snapshot), IsAnchor: true,
			HighlightRanges: snapshot.Citation.HighlightRanges,
		}}, blocks...)
		snapshot.Warning = "Không tìm thấy chunk gốc trong phiên bản nguồn hiện tại; đang hiển thị snapshot tại thời điểm trả lời."
	}
	snapshot.Blocks = blocks
	return snapshot, nil
}

func citationFields(record map[string]any, limit int) []domain.CitationField {
	keys := make([]string, 0, len(record))
	for key := range record {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]domain.CitationField, 0, min(limit, len(keys)))
	for _, key := range keys {
		value, err := json.Marshal(record[key])
		if err != nil || string(value) == "null" || string(value) == "{}" || string(value) == "[]" {
			continue
		}
		text := strings.Trim(string(value), "\"")
		if text == "" {
			continue
		}
		fields = append(fields, domain.CitationField{Label: strings.ReplaceAll(key, "_", " "), Value: text})
		if len(fields) >= limit {
			break
		}
	}
	return fields
}

func citationFieldsText(fields []domain.CitationField) string {
	lines := make([]string, 0, len(fields))
	for _, field := range fields {
		lines = append(lines, field.Label+": "+field.Value)
	}
	return strings.Join(lines, "\n")
}

func snapshotAnchorFields(snapshot domain.CitationContextSnapshot) []domain.CitationField {
	for _, block := range snapshot.Blocks {
		if block.IsAnchor {
			return block.Fields
		}
	}
	return nil
}

func sameEvidenceText(left, right string) bool {
	normalize := func(value string) string { return strings.Join(strings.Fields(strings.ToLower(value)), " ") }
	a, b := normalize(left), normalize(right)
	return a == b || strings.Contains(a, b) || strings.Contains(b, a)
}

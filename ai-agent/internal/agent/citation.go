package agent

import (
	"agent/internal/domain"
	"agent/internal/mcp"
	"crypto/rand"
	"encoding/hex"
	"regexp"
	"sort"
	"strings"
	"unicode"
)

var (
	citationTokenPattern = regexp.MustCompile(`\[\[cite:([A-Za-z0-9_-]+)\]\]`)
	legacySourcePattern  = regexp.MustCompile(`(?i)\s*\[Nguồn:[^\]\n]*\]`)
	legacyFooterPattern  = regexp.MustCompile(`(?im)^\s*📌\s*\*(?:Công cụ tra cứu đã sử dụng|Công cụ tra cứu|Tổng hợp các nguồn thông tin|Nguồn thông tin):\*[^\n]*\n?`)
	numberPattern        = regexp.MustCompile(`\d[\d.,/:-]*`)
)

type AgentResponse struct {
	Text             string
	RunID            string
	Citations        []domain.Citation
	CitationContexts map[string]domain.CitationContextSnapshot
}

type evidenceLedger struct {
	runID         string
	next          int
	byID          map[string]mcp.Evidence
	byFingerprint map[string]string
	orderedIDs    []string
}

func newEvidenceLedger() *evidenceLedger {
	return &evidenceLedger{
		runID:         "run_" + randomID(12),
		byID:          make(map[string]mcp.Evidence),
		byFingerprint: make(map[string]string),
	}
}

func (ledger *evidenceLedger) add(items []mcp.Evidence) []mcp.Evidence {
	result := make([]mcp.Evidence, 0, len(items))
	for _, item := range items {
		if existingID := ledger.byFingerprint[item.Fingerprint]; existingID != "" {
			item = ledger.byID[existingID]
			result = append(result, item)
			continue
		}
		ledger.next++
		item.ID = "ev_" + strings.TrimPrefix(ledger.runID, "run_") + "_" + stringID(ledger.next)
		ledger.byID[item.ID] = item
		ledger.byFingerprint[item.Fingerprint] = item.ID
		ledger.orderedIDs = append(ledger.orderedIDs, item.ID)
		result = append(result, item)
	}
	return result
}

func renderRAGClarification(ledger *evidenceLedger) (string, bool) {
	if len(ledger.orderedIDs) == 0 {
		return "", false
	}
	ids := make([]string, 0, min(5, len(ledger.orderedIDs)))
	for _, id := range ledger.orderedIDs {
		evidence := ledger.byID[id]
		if evidence.Citation.SourceKind != "rag_document" || evidence.Citation.MatchStatus != "approximate" {
			return "", false
		}
		ids = append(ids, id)
		if len(ids) == 5 {
			break
		}
	}
	if len(ids) == 0 {
		return "", false
	}

	var builder strings.Builder
	builder.WriteString("Thông tin anh/chị cung cấp chưa đủ để xác định duy nhất một mục. Có phải ý anh/chị là một trong các lựa chọn sau?\n\n")
	for index, id := range ids {
		evidence := ledger.byID[id]
		fields := evidenceFields(evidence)
		name := firstEvidenceField(fields, "Tên dịch vụ", "Tên", "Tên hiển thị")
		if name == "" {
			name = evidence.Citation.Title
		}
		builder.WriteString(stringID(index + 1))
		builder.WriteString(". **")
		builder.WriteString(name)
		builder.WriteString("**")
		if code := firstEvidenceField(fields, "Mã dịch vụ"); code != "" {
			builder.WriteString(" — Mã: ")
			builder.WriteString(code)
		}
		if price := firstEvidenceField(fields, "Giá tại Cơ sở 1", "Giá"); price != "" {
			builder.WriteString(" — Giá tại Cơ sở 1: ")
			builder.WriteString(price)
			builder.WriteString(" đồng")
		}
		builder.WriteString(" [[cite:")
		builder.WriteString(id)
		builder.WriteString("]]\n")
	}
	builder.WriteString("\nAnh/chị vui lòng trả lời số thứ tự hoặc tên đầy đủ của mục cần tra cứu.")
	return builder.String(), true
}

func evidenceFields(evidence mcp.Evidence) []domain.CitationField {
	for _, block := range evidence.Context.Blocks {
		if block.IsAnchor {
			return block.Fields
		}
	}
	return nil
}

func firstEvidenceField(fields []domain.CitationField, labels ...string) string {
	for _, label := range labels {
		for _, field := range fields {
			if field.Label == label && strings.TrimSpace(field.Value) != "" {
				return strings.TrimSpace(field.Value)
			}
		}
	}
	return ""
}

func (ledger *evidenceLedger) hasEvidence() bool {
	return len(ledger.byID) > 0
}

func (ledger *evidenceLedger) ids() []string {
	result := make([]string, 0, len(ledger.byID))
	for id := range ledger.byID {
		result = append(result, id)
	}
	sort.Strings(result)
	return result
}

func finalizeCitations(raw string, ledger *evidenceLedger) AgentResponse {
	matches := citationTokenPattern.FindAllStringSubmatchIndex(raw, -1)
	byEvidenceID := map[string]*domain.Citation{}
	contexts := map[string]domain.CitationContextSnapshot{}
	ordered := make([]domain.Citation, 0, len(matches))
	var builder strings.Builder
	last := 0
	for _, match := range matches {
		builder.WriteString(raw[last:match[0]])
		evidenceID := raw[match[2]:match[3]]
		evidence, ok := ledger.byID[evidenceID]
		if !ok {
			last = match[1]
			continue
		}
		claim := claimBefore(raw, match[0])
		if !citationSupportsClaim(claim, evidence.Citation.Excerpt) {
			last = match[1]
			continue
		}
		citation := byEvidenceID[evidenceID]
		highlight := findHighlightRanges(claim, evidence.Citation.Excerpt)
		if citation == nil {
			publicCitation := evidence.Citation
			publicCitation.ID = "cit_" + randomID(12)
			publicCitation.Index = len(ordered) + 1
			publicCitation.HighlightRanges = highlight
			ordered = append(ordered, publicCitation)
			citation = &ordered[len(ordered)-1]
			byEvidenceID[evidenceID] = citation
			snapshot := evidence.Context
			snapshot.Citation = publicCitation
			for index := range snapshot.Blocks {
				if snapshot.Blocks[index].IsAnchor {
					snapshot.Blocks[index].HighlightRanges = highlight
				}
			}
			contexts[publicCitation.ID] = snapshot
		} else {
			citation.HighlightRanges = mergeRanges(citation.HighlightRanges, highlight)
			snapshot := contexts[citation.ID]
			snapshot.Citation.HighlightRanges = citation.HighlightRanges
			for index := range snapshot.Blocks {
				if snapshot.Blocks[index].IsAnchor {
					snapshot.Blocks[index].HighlightRanges = citation.HighlightRanges
				}
			}
			contexts[citation.ID] = snapshot
		}
		builder.WriteString("[")
		builder.WriteString(stringID(citation.Index))
		builder.WriteString("](#citation-")
		builder.WriteString(citation.ID)
		builder.WriteString(")")
		last = match[1]
	}
	builder.WriteString(raw[last:])
	text := legacySourcePattern.ReplaceAllString(builder.String(), "")
	text = legacyFooterPattern.ReplaceAllString(text, "")
	text = strings.TrimSpace(text)
	return AgentResponse{Text: text, RunID: ledger.runID, Citations: ordered, CitationContexts: contexts}
}

func citationTokenStats(text string, ledger *evidenceLedger) (valid, invalid int) {
	for _, match := range citationTokenPattern.FindAllStringSubmatchIndex(text, -1) {
		evidenceID := text[match[2]:match[3]]
		evidence, ok := ledger.byID[evidenceID]
		if !ok || !citationSupportsClaim(claimBefore(text, match[0]), evidence.Citation.Excerpt) {
			invalid++
			continue
		}
		valid++
	}
	return valid, invalid
}

func citationSupportsClaim(claim, excerpt string) bool {
	normalClaim, _ := normalizeWithMap(stripMarkdown(claim))
	normalExcerpt, _ := normalizeWithMap(excerpt)
	if normalClaim == "" || normalExcerpt == "" {
		return false
	}
	if strings.Contains(normalExcerpt, normalClaim) || strings.Contains(normalClaim, normalExcerpt) {
		return true
	}
	claimNumbers := numberPattern.FindAllString(normalClaim, -1)
	if len(claimNumbers) > 0 {
		numberMatched := false
		for _, number := range claimNumbers {
			trimmed := strings.Trim(number, ".,/: -")
			if trimmed != "" && strings.Contains(normalExcerpt, trimmed) {
				numberMatched = true
				break
			}
		}
		if !numberMatched {
			return false
		}
	}
	claimTokens := tokenSet(normalClaim)
	evidenceTokens := tokenSet(normalExcerpt)
	common := 0
	for token := range claimTokens {
		if _, ok := evidenceTokens[token]; ok {
			common++
		}
	}
	if common < 2 {
		return false
	}
	return float64(common)/float64(max(1, len(claimTokens))) >= 0.20
}

func hasUncitedFactualLines(text string) bool {
	keywords := []string{
		"giá", "mã ", "đồng", "cơ sở", "phòng", "bác sĩ", "ngày", "giờ",
		"bước", "quy trình", "bao gồm", "bảo hiểm", "bhyt", "địa chỉ", "hotline",
	}
	for _, rawLine := range strings.Split(text, "\n") {
		line := strings.TrimSpace(rawLine)
		if line == "" || strings.HasSuffix(line, "?") || citationTokenPattern.MatchString(line) {
			continue
		}
		normalized := strings.ToLower(stripMarkdown(line))
		factual := numberPattern.MatchString(normalized)
		if !factual {
			for _, keyword := range keywords {
				if strings.Contains(normalized, keyword) {
					factual = true
					break
				}
			}
		}
		if factual {
			return true
		}
	}
	return false
}

func claimBefore(text string, byteOffset int) string {
	// Citation tokens normally follow sentence punctuation and one whitespace
	// character. Trim that whitespace first so the final ". " is not mistaken
	// for the start of an empty sentence.
	prefix := strings.TrimSpace(text[:byteOffset])
	start := 0
	for _, separator := range []string{"\n", ". ", "! ", "? ", "; "} {
		if index := strings.LastIndex(prefix, separator); index >= start {
			start = index + len(separator)
		}
	}
	claim := strings.TrimSpace(prefix[start:])
	claim = strings.TrimLeft(claim, "-*#>0123456789. )(")
	return strings.TrimSpace(claim)
}

func findHighlightRanges(claim, excerpt string) []domain.TextRange {
	excerptRunes := []rune(excerpt)
	if len(excerptRunes) == 0 {
		return nil
	}
	cleanClaim := stripMarkdown(claim)
	normalClaim, _ := normalizeWithMap(cleanClaim)
	normalExcerpt, excerptMap := normalizeWithMap(excerpt)
	if normalClaim != "" {
		if index := strings.Index(normalExcerpt, normalClaim); index >= 0 {
			startRune := normalizedByteToRune(excerptMap, index)
			endRune := normalizedByteToRune(excerptMap, index+len(normalClaim)-1) + 1
			return []domain.TextRange{{Start: startRune, End: min(endRune, len(excerptRunes))}}
		}
	}

	claimTokens := tokenSet(normalClaim)
	bestScore := 0.0
	bestStart, bestEnd := 0, len(excerptRunes)
	for _, segment := range textSegments(excerptRunes) {
		segmentText := string(excerptRunes[segment.Start:segment.End])
		normalSegment, _ := normalizeWithMap(segmentText)
		score := containmentScore(claimTokens, tokenSet(normalSegment))
		if score > bestScore {
			bestScore = score
			bestStart, bestEnd = segment.Start, segment.End
		}
	}
	if bestScore >= 0.65 {
		return []domain.TextRange{{Start: bestStart, End: bestEnd}}
	}
	return []domain.TextRange{{Start: 0, End: len(excerptRunes)}}
}

func stripMarkdown(value string) string {
	replacer := strings.NewReplacer("**", "", "__", "", "`", "", "[", "", "]", "", "(", " ", ")", " ")
	return strings.TrimSpace(replacer.Replace(value))
}

func normalizeWithMap(value string) (string, []int) {
	var builder strings.Builder
	positions := make([]int, 0, len(value))
	spacePending := false
	for index, current := range []rune(strings.ToLower(value)) {
		if unicode.IsSpace(current) {
			spacePending = builder.Len() > 0
			continue
		}
		if spacePending {
			builder.WriteRune(' ')
			positions = append(positions, index)
			spacePending = false
		}
		encodedRune := string(current)
		builder.WriteString(encodedRune)
		for range len(encodedRune) {
			positions = append(positions, index)
		}
	}
	return strings.TrimSpace(builder.String()), positions
}

func normalizedByteToRune(positions []int, byteOffset int) int {
	if len(positions) == 0 {
		return 0
	}
	// The mapping contains one source-rune position for every normalized UTF-8
	// byte, so byte offsets returned by strings.Index remain safe for Vietnamese.
	if byteOffset < 0 {
		return positions[0]
	}
	return positions[min(byteOffset, len(positions)-1)]
}

type runeRange struct{ Start, End int }

func textSegments(value []rune) []runeRange {
	result := make([]runeRange, 0)
	start := 0
	for index, current := range value {
		if current == '\n' || current == '.' || current == '!' || current == '?' || current == ';' {
			end := index + 1
			if strings.TrimSpace(string(value[start:end])) != "" {
				result = append(result, runeRange{Start: start, End: end})
			}
			start = end
		}
	}
	if start < len(value) && strings.TrimSpace(string(value[start:])) != "" {
		result = append(result, runeRange{Start: start, End: len(value)})
	}
	if len(result) == 0 {
		result = append(result, runeRange{Start: 0, End: len(value)})
	}
	return result
}

func tokenSet(value string) map[string]struct{} {
	stop := map[string]bool{"là": true, "và": true, "của": true, "có": true, "được": true, "tại": true, "cho": true, "với": true, "theo": true, "thông": true, "tin": true}
	result := map[string]struct{}{}
	fields := strings.FieldsFunc(value, func(r rune) bool { return !unicode.IsLetter(r) && !unicode.IsDigit(r) })
	for _, field := range fields {
		if field != "" && !stop[field] {
			result[field] = struct{}{}
		}
	}
	return result
}

func containmentScore(claim, evidence map[string]struct{}) float64 {
	if len(claim) == 0 || len(evidence) == 0 {
		return 0
	}
	common := 0
	for token := range claim {
		if _, ok := evidence[token]; ok {
			common++
		}
	}
	return float64(common) / float64(len(claim))
}

func mergeRanges(existing, incoming []domain.TextRange) []domain.TextRange {
	all := append(append([]domain.TextRange{}, existing...), incoming...)
	if len(all) <= 1 {
		return all
	}
	sort.Slice(all, func(i, j int) bool { return all[i].Start < all[j].Start })
	result := []domain.TextRange{all[0]}
	for _, current := range all[1:] {
		last := &result[len(result)-1]
		if current.Start <= last.End {
			if current.End > last.End {
				last.End = current.End
			}
			continue
		}
		result = append(result, current)
	}
	return result
}

func randomID(size int) string {
	buffer := make([]byte, size)
	if _, err := rand.Read(buffer); err != nil {
		return "fallback"
	}
	return hex.EncodeToString(buffer)
}

func stringID(value int) string {
	const digits = "0123456789"
	if value == 0 {
		return "0"
	}
	result := make([]byte, 0, 8)
	for value > 0 {
		result = append([]byte{digits[value%10]}, result...)
		value /= 10
	}
	return string(result)
}

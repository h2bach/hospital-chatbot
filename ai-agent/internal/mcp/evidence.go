package mcp

import (
	"agent/internal/domain"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Evidence is the internal, provider-neutral representation of one factual
// source returned by an MCP tool. It never leaves the backend directly.
type Evidence struct {
	ID          string
	Fingerprint string
	Citation    domain.Citation
	Context     domain.CitationContextSnapshot
}

func NormalizeEvidence(toolName string, result ToolResult, observedAt time.Time) []Evidence {
	root := valueMap(result.Structured)
	if len(root) == 0 {
		return nil
	}
	if toolName == "searchRAG" {
		return normalizeRAGEvidence(root)
	}
	if toolName == "checkTime" {
		return normalizeTimeEvidence(root, observedAt)
	}
	return normalizeHospitalEvidence(toolName, root, observedAt)
}

// StructuredFieldNames exposes only schema field names for operational
// diagnostics. It never returns evidence values or user data.
func StructuredFieldNames(result ToolResult) []string {
	root := valueMap(result.Structured)
	keys := make([]string, 0, len(root))
	for key := range root {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func normalizeRAGEvidence(root map[string]any) []Evidence {
	status := cleanString(root["status"])
	if status == "" {
		status = "exact"
	}
	confidence := numberPointer(root["confidence"])
	citationByID := map[string]map[string]any{}
	for _, raw := range valueSlice(root["citations"]) {
		citation := valueMap(raw)
		if id := cleanString(citation["citation_id"]); id != "" {
			citationByID[id] = citation
		}
	}

	items := valueSlice(root["evidence"])
	result := make([]Evidence, 0, len(items))
	for _, raw := range items {
		item := valueMap(raw)
		chunk := valueMap(item["chunk"])
		chunkID := cleanString(chunk["chunk_id"])
		documentID := cleanString(chunk["document_id"])
		if chunkID == "" || documentID == "" {
			continue
		}
		heading := stringSlice(chunk["heading_path"])
		title := documentID
		if len(heading) > 0 && strings.TrimSpace(heading[0]) != "" {
			title = heading[0]
		}
		excerpt := strings.TrimSpace(cleanString(chunk["content_text"]))
		facts := valueMap(chunk["facts"])
		fields := recordFields(facts, 12)
		if excerpt == "" {
			excerpt = fieldsText(fields)
		}
		if excerpt == "" {
			continue
		}

		citationMeta := citationByID[cleanString(item["citation_id"])]
		locationHeading := stringSlice(citationMeta["heading_path"])
		if len(locationHeading) == 0 {
			locationHeading = heading
		}
		section := ""
		if len(locationHeading) > 0 {
			section = strings.Join(locationHeading, " › ")
		}
		matchStatus := status
		if matchStatus == "" {
			matchStatus = cleanString(item["match_type"])
		}
		citation := domain.Citation{
			SourceKind:      "rag_document",
			Title:           title,
			Excerpt:         excerpt,
			MatchStatus:     matchStatus,
			Confidence:      confidence,
			ContextAvailable: true,
			Location: domain.CitationLocation{
				SourceID:   documentID,
				DocumentID: documentID,
				ChunkID:    chunkID,
				Section:    section,
				Page:       intValue(citationMeta["page_start"]),
				LineStart:  intValue(citationMeta["line_start"]),
				LineEnd:    intValue(citationMeta["line_end"]),
				Heading:    locationHeading,
			},
			Freshness: domain.CitationFreshness{
				Version:        firstString(facts, "version", "document_version", "source_version"),
				EffectiveAt:    firstString(facts, "effective_at", "effective_date", "ngay_hieu_luc"),
				ApprovalStatus: "published",
			},
		}
		if sourceFile := cleanString(citationMeta["source_file"]); sourceFile != "" && title == documentID {
			citation.Title = strings.TrimSuffix(filepath.Base(sourceFile), filepath.Ext(sourceFile))
		}
		fingerprint := "rag|" + documentID + "|" + chunkID + "|" + citation.Freshness.Version
		result = append(result, Evidence{
			Fingerprint: fingerprint,
			Citation:    citation,
			Context: domain.CitationContextSnapshot{
				Citation: citation,
				Blocks: []domain.CitationContextBlock{{
					ID:       chunkID,
					Heading:  section,
					Text:     excerpt,
					Fields:   fields,
					IsAnchor: true,
				}},
			},
		})
	}
	return result
}

func normalizeHospitalEvidence(toolName string, root map[string]any, observedAt time.Time) []Evidence {
	statusCode := intValue(root["status"])
	if statusCode != 0 && (statusCode < 200 || statusCode >= 300) {
		return nil
	}
	body := valueMap(root["body"])
	if len(body) == 0 {
		return nil
	}
	records := valueSlice(body["data"])
	if record := valueMap(body["data"]); len(record) > 0 {
		records = []any{record}
	}
	if len(records) == 0 && (toolName == "hospitalInfoHealth" || toolName == "getHospitalDatasetMeta") {
		records = []any{body}
	}
	if len(records) > 50 {
		records = records[:50]
	}
	schedule := valueMap(body["schedule"])
	result := make([]Evidence, 0, len(records))
	for index, raw := range records {
		record := valueMap(raw)
		if len(record) == 0 {
			continue
		}
		sourceKind := sourceKindForTool(toolName, record)
		sourceID := recordID(record)
		if sourceID == "" {
			sourceID = shortHash(record)
		}
		title := recordTitle(record, sourceKind, sourceID)
		fields := recordFields(record, 16)
		excerpt := fieldsText(fields)
		if excerpt == "" {
			continue
		}
		freshness := domain.CitationFreshness{
			Version:        firstNonEmpty(cleanString(schedule["source_version"]), firstString(record, "source_version", "version")),
			EffectiveAt:    firstString(record, "effective_at", "effective_date"),
			ObservedAt:     observedAt.UTC().Format(time.RFC3339),
			ApprovalStatus: firstNonEmpty(cleanString(schedule["published_status"]), "published"),
		}
		confidence := numberPointer(record["source_confidence"])
		if confidence == nil {
			confidence = numberPointer(record["confidence"])
		}
		citation := domain.Citation{
			SourceKind:       sourceKind,
			Title:            title,
			Excerpt:          excerpt,
			MatchStatus:      "exact",
			Confidence:       confidence,
			ContextAvailable: true,
			Location: domain.CitationLocation{
				SourceID: sourceID,
				Section:  friendlySourceKind(sourceKind),
			},
			Freshness: freshness,
		}
		blockID := sourceID
		if blockID == "" {
			blockID = strconv.Itoa(index + 1)
		}
		fingerprint := sourceKind + "|" + sourceID + "|" + freshness.Version
		result = append(result, Evidence{
			Fingerprint: fingerprint,
			Citation:    citation,
			Context: domain.CitationContextSnapshot{
				Citation: citation,
				Blocks: []domain.CitationContextBlock{{
					ID:       blockID,
					Heading:  title,
					Text:     excerpt,
					Fields:   fields,
					IsAnchor: true,
				}},
			},
		})
	}
	return result
}

func normalizeTimeEvidence(root map[string]any, observedAt time.Time) []Evidence {
	value := cleanString(root["time"])
	if value == "" {
		return nil
	}
	citation := domain.Citation{
		SourceKind:       "system_time",
		Title:            "Thời gian hệ thống",
		Excerpt:          "Thời gian quan sát: " + value,
		MatchStatus:      "exact",
		ContextAvailable: true,
		Location:         domain.CitationLocation{SourceID: "system-clock"},
		Freshness:        domain.CitationFreshness{ObservedAt: observedAt.UTC().Format(time.RFC3339)},
	}
	return []Evidence{{
		Fingerprint: "system_time|" + value,
		Citation:    citation,
		Context: domain.CitationContextSnapshot{
			Citation: citation,
			Blocks: []domain.CitationContextBlock{{
				ID: "system-clock", Text: citation.Excerpt, IsAnchor: true,
			}},
		},
	}}
}

func FormatEvidenceForModel(evidence []Evidence) string {
	if len(evidence) == 0 {
		return "Không có evidence đã xác minh trong kết quả công cụ. Không được tạo citation."
	}
	var builder strings.Builder
	builder.WriteString("EVIDENCE ĐÃ XÁC MINH. Chỉ dùng ID nằm trong danh sách này để trích dẫn.\n")
	for _, item := range evidence {
		builder.WriteString("\n[Evidence ")
		builder.WriteString(item.ID)
		builder.WriteString("]\nNguồn hiển thị: ")
		builder.WriteString(item.Citation.Title)
		builder.WriteString("\nTrạng thái: ")
		builder.WriteString(item.Citation.MatchStatus)
		builder.WriteString("\nVăn bản/bản ghi:\n")
		builder.WriteString(item.Citation.Excerpt)
		builder.WriteString("\nKhi sử dụng thông tin này, đặt [[cite:")
		builder.WriteString(item.ID)
		builder.WriteString("]] ngay sau claim.\n")
	}
	return strings.TrimSpace(builder.String())
}

func sourceKindForTool(toolName string, record map[string]any) string {
	if entity := cleanString(record["entity_type"]); entity != "" {
		switch entity {
		case "doctors":
			return "hospital_doctor"
		case "rooms":
			return "hospital_room"
		case "organization":
			return "hospital_organization"
		case "rules":
			return "scheduling_rule"
		case "patterns":
			return "assignment_pattern"
		}
	}
	switch toolName {
	case "listHospitalFacilities":
		return "hospital_facility"
	case "getHospitalOrganization":
		return "hospital_organization"
	case "listHospitalRooms":
		return "hospital_room"
	case "searchHanoiHeartDoctors", "getHanoiHeartDoctor":
		return "hospital_doctor"
	case "listCurrentDoctorSchedule":
		return "doctor_schedule"
	case "getDoctorAvailability":
		return "doctor_availability"
	case "getSchedulingRules":
		return "scheduling_rule"
	case "getObservedAssignmentPatterns":
		return "assignment_pattern"
	case "getScheduleDataDictionary":
		return "data_dictionary"
	case "getScheduleSourceRegistry":
		return "source_registry"
	case "getHospitalDatasetMeta":
		return "dataset_metadata"
	case "hospitalInfoHealth":
		return "service_status"
	default:
		return "hospital_directory"
	}
}

func friendlySourceKind(kind string) string {
	labels := map[string]string{
		"hospital_facility":     "Cơ sở bệnh viện",
		"hospital_organization": "Đơn vị bệnh viện",
		"hospital_room":         "Phòng và khu khám",
		"hospital_doctor":       "Danh bạ bác sĩ",
		"doctor_schedule":       "Lịch bác sĩ",
		"doctor_availability":   "Phân công bác sĩ",
		"scheduling_rule":       "Quy tắc xếp lịch",
		"assignment_pattern":    "Mẫu phân công",
		"data_dictionary":       "Từ điển dữ liệu",
		"source_registry":       "Danh mục nguồn",
		"dataset_metadata":      "Thông tin bộ dữ liệu",
		"service_status":        "Trạng thái dữ liệu",
		"hospital_directory":    "Dữ liệu bệnh viện",
	}
	if label := labels[kind]; label != "" {
		return label
	}
	return "Nguồn dữ liệu bệnh viện"
}

func recordID(record map[string]any) string {
	return firstString(record,
		"assignment_id", "staff_id", "room_id", "facility_id", "id",
		"rule_id", "pattern_id", "field", "source_id", "unit_id",
	)
}

func recordTitle(record map[string]any, sourceKind, sourceID string) string {
	if title := firstString(record, "full_name", "staff_name", "display_name", "name", "rule", "meaning", "file_name"); title != "" {
		return title
	}
	return friendlySourceKind(sourceKind) + " · " + sourceID
}

func recordFields(record map[string]any, limit int) []domain.CitationField {
	preferred := []string{
		"service_code", "service_name", "price", "full_name", "staff_name",
		"credential_normalized", "name", "display_name", "address", "facility_id",
		"area_name", "specialty", "room_id", "schedule_date", "shift_code",
		"opens_at", "closes_at", "assignment_status", "rule", "meaning",
		"confidence", "notice",
	}
	seen := map[string]bool{}
	keys := make([]string, 0, len(record))
	for _, key := range preferred {
		if _, ok := record[key]; ok {
			keys = append(keys, key)
			seen[key] = true
		}
	}
	rest := make([]string, 0, len(record))
	for key := range record {
		if seen[key] || key == "source" || key == "entity_type" {
			continue
		}
		rest = append(rest, key)
	}
	sort.Strings(rest)
	keys = append(keys, rest...)
	fields := make([]domain.CitationField, 0, min(limit, len(keys)))
	for _, key := range keys {
		value := displayValue(record[key])
		if value == "" {
			continue
		}
		fields = append(fields, domain.CitationField{Label: fieldLabel(key), Value: value})
		if len(fields) >= limit {
			break
		}
	}
	return fields
}

func fieldsText(fields []domain.CitationField) string {
	lines := make([]string, 0, len(fields))
	for _, field := range fields {
		lines = append(lines, field.Label+": "+field.Value)
	}
	text := strings.Join(lines, "\n")
	if len([]rune(text)) > 3000 {
		text = string([]rune(text)[:3000]) + "…"
	}
	return text
}

func fieldLabel(key string) string {
	labels := map[string]string{
		"service_code": "Mã dịch vụ", "service_name": "Tên dịch vụ", "price": "Giá",
		"facility_1_price": "Giá tại Cơ sở 1", "facility_2_price": "Giá tại Cơ sở 2",
		"note": "Ghi chú", "legal_basis": "Căn cứ pháp lý",
		"full_name": "Bác sĩ", "staff_name": "Bác sĩ", "credential_normalized": "Chức danh",
		"name": "Tên", "display_name": "Tên hiển thị", "address": "Địa chỉ",
		"facility_id": "Cơ sở", "area_name": "Khu vực", "specialty": "Chuyên khoa",
		"room_id": "Phòng", "schedule_date": "Ngày", "shift_code": "Ca",
		"opens_at": "Giờ mở cửa", "closes_at": "Giờ đóng cửa",
		"assignment_status": "Trạng thái phân công", "rule": "Quy tắc",
		"meaning": "Ý nghĩa", "confidence": "Độ tin cậy", "notice": "Lưu ý",
	}
	if label := labels[key]; label != "" {
		return label
	}
	return strings.ReplaceAll(key, "_", " ")
}

func displayValue(value any) string {
	if value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	case float64:
		if typed == float64(int64(typed)) {
			return strconv.FormatInt(int64(typed), 10)
		}
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case bool:
		return strconv.FormatBool(typed)
	default:
		encoded, err := json.Marshal(typed)
		if err != nil || string(encoded) == "{}" || string(encoded) == "[]" || string(encoded) == "null" {
			return ""
		}
		return string(encoded)
	}
}

func valueMap(value any) map[string]any {
	if value == nil {
		return nil
	}
	if result, ok := value.(map[string]any); ok {
		return result
	}
	if raw, ok := value.(json.RawMessage); ok {
		var result map[string]any
		if json.Unmarshal(raw, &result) == nil {
			return result
		}
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil
	}
	var result map[string]any
	if json.Unmarshal(encoded, &result) != nil {
		return nil
	}
	return result
}

func valueSlice(value any) []any {
	if result, ok := value.([]any); ok {
		return result
	}
	return nil
}

func stringSlice(value any) []string {
	items := valueSlice(value)
	result := make([]string, 0, len(items))
	for _, item := range items {
		if text := cleanString(item); text != "" {
			result = append(result, text)
		}
	}
	if len(result) == 0 {
		if text := cleanString(value); text != "" {
			return []string{text}
		}
	}
	return result
}

func cleanString(value any) string {
	if value == nil {
		return ""
	}
	if text, ok := value.(string); ok {
		return strings.TrimSpace(text)
	}
	return strings.TrimSpace(fmt.Sprint(value))
}

func intValue(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case float64:
		return int(typed)
	case json.Number:
		result, _ := typed.Int64()
		return int(result)
	case string:
		result, _ := strconv.Atoi(typed)
		return result
	default:
		return 0
	}
}

func numberPointer(value any) *float64 {
	var number float64
	switch typed := value.(type) {
	case float64:
		number = typed
	case int:
		number = float64(typed)
	case json.Number:
		number, _ = typed.Float64()
	case string:
		parsed, err := strconv.ParseFloat(typed, 64)
		if err != nil {
			return nil
		}
		number = parsed
	default:
		return nil
	}
	return &number
}

func firstString(record map[string]any, keys ...string) string {
	for _, key := range keys {
		if value := cleanString(record[key]); value != "" {
			return value
		}
	}
	return ""
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func shortHash(value any) string {
	encoded, _ := json.Marshal(value)
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:8])
}

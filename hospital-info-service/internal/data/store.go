package data

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

type Record map[string]any

type Schedule struct {
	SchemaVersion   string   `json:"schema_version"`
	WeekStart       any      `json:"week_start"`
	WeekEnd         any      `json:"week_end"`
	PublishedStatus string   `json:"published_status"`
	SourceVersion   any      `json:"source_version"`
	ImportedAt      any      `json:"imported_at"`
	Assignments     []Record `json:"assignments"`
}

type Snapshot struct {
	Meta       Record
	Facilities []Record
	Rooms      []Record
	Doctors    []Record
	Rules      []Record
	Patterns   []Record
	Dictionary []Record
	Sources    []Record
	Units      []Record
	Schedule   Schedule
}

type DatasetDefinition struct {
	Name          string   `json:"name"`
	Filename      string   `json:"filename"`
	Title         string   `json:"title"`
	Description   string   `json:"description"`
	Kind          string   `json:"kind"`
	PrimaryKey    string   `json:"primary_key,omitempty"`
	RecordPath    string   `json:"record_path,omitempty"`
	PreviewFields []string `json:"preview_fields,omitempty"`
}

type DatasetSummary struct {
	DatasetDefinition
	Count     int       `json:"count"`
	Version   string    `json:"version"`
	UpdatedAt time.Time `json:"updated_at"`
}

type DatasetState struct {
	Summary DatasetSummary
	Data    json.RawMessage
}

type ChangeEvent struct {
	Type      string    `json:"type"`
	Datasets  []string  `json:"datasets"`
	Revision  uint64    `json:"revision"`
	ChangedAt time.Time `json:"changed_at"`
}

type datasetFile struct {
	Body      json.RawMessage
	Version   string
	UpdatedAt time.Time
}

type Store struct {
	directory string

	mu              sync.RWMutex
	snapshot        Snapshot
	files           map[string]datasetFile
	revision        uint64
	lastReloadError string

	subMu       sync.Mutex
	subscribers map[chan ChangeEvent]struct{}
}

var (
	ErrDatasetNotFound = errors.New("dataset không tồn tại")
	ErrVersionConflict = errors.New("dữ liệu đã được cập nhật bởi phiên làm việc khác")
)

var datasetDefinitions = []DatasetDefinition{
	{Name: "schedule", Filename: "current_schedule.json", Title: "Lịch bác sĩ", Description: "Lịch tuần hiện hành và toàn bộ phân công bác sĩ.", Kind: "object", PrimaryKey: "assignment_id", RecordPath: "assignments", PreviewFields: []string{"schedule_date", "staff_name", "room_id", "shift_code", "assignment_status"}},
	{Name: "doctors", Filename: "doctors.json", Title: "Bác sĩ", Description: "Danh bạ bác sĩ, học hàm/học vị và nơi làm việc quan sát được.", Kind: "array", PrimaryKey: "staff_id", PreviewFields: []string{"full_name", "credential_normalized", "observed_facilities", "observed_areas"}},
	{Name: "facilities", Filename: "facilities.json", Title: "Cơ sở", Description: "Địa chỉ, múi giờ và thông tin nguồn của các cơ sở bệnh viện.", Kind: "array", PrimaryKey: "facility_id", PreviewFields: []string{"name", "address", "timezone"}},
	{Name: "rooms", Filename: "rooms.json", Title: "Phòng & khu khám", Description: "Phòng khám, khu vực, chuyên khoa và giờ hoạt động.", Kind: "array", PrimaryKey: "room_id", PreviewFields: []string{"display_name", "facility_id", "area_name", "opens_at", "closes_at"}},
	{Name: "organization", Filename: "organization.json", Title: "Sơ đồ tổ chức", Description: "Khối, trung tâm, khoa, phòng và quan hệ cấp trên.", Kind: "array", PrimaryKey: "id", PreviewFields: []string{"name", "unit_type", "block", "parent_id"}},
	{Name: "rules", Filename: "scheduling_rules.json", Title: "Quy tắc xếp lịch", Description: "Các quy tắc cứng/mềm dùng làm đầu vào khi lập lịch.", Kind: "array", PrimaryKey: "rule_id", PreviewFields: []string{"group", "level", "rule", "confidence"}},
	{Name: "patterns", Filename: "assignment_patterns.json", Title: "Mẫu phân công", Description: "Mẫu phân công bác sĩ quan sát được từ dữ liệu nguồn.", Kind: "array", PrimaryKey: "pattern_id", PreviewFields: []string{"staff_or_resource", "area_id", "room_or_scope", "applies_on", "shift"}},
	{Name: "dictionary", Filename: "data_dictionary.json", Title: "Từ điển dữ liệu", Description: "Ý nghĩa, kiểu và quy định của các trường dữ liệu lịch.", Kind: "array", PrimaryKey: "field", PreviewFields: []string{"meaning", "type", "example", "rule"}},
	{Name: "sources", Filename: "source_registry.json", Title: "Danh mục nguồn", Description: "Danh sách ảnh/tệp nguồn và trạng thái xác minh.", Kind: "array", PrimaryKey: "source_id", PreviewFields: []string{"file_name", "facility_id", "area", "displayed_week", "status"}},
	{Name: "metadata", Filename: "dataset_meta.json", Title: "Thông tin bộ dữ liệu", Description: "Phạm vi, nguồn, giới hạn và thống kê của bộ dữ liệu.", Kind: "object", PreviewFields: []string{"dataset_name", "data_nature", "observed_date_range", "timezone"}},
}

func Load(directory string) (*Store, error) {
	absDirectory, err := filepath.Abs(directory)
	if err != nil {
		return nil, fmt.Errorf("resolve data directory: %w", err)
	}
	s := &Store{
		directory:   absDirectory,
		subscribers: make(map[chan ChangeEvent]struct{}),
	}
	files, err := readDatasetFiles(absDirectory)
	if err != nil {
		return nil, err
	}
	snapshot, err := buildSnapshot(files)
	if err != nil {
		return nil, err
	}
	s.files = files
	s.snapshot = snapshot
	s.revision = 1
	return s, nil
}

func (s *Store) Snapshot() Snapshot {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.snapshot
}

func (s *Store) CurrentSchedule() (Schedule, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.snapshot.Schedule, nil
}

func (s *Store) Revision() (uint64, string) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.revision, s.lastReloadError
}

func (s *Store) DatasetSummaries() []DatasetSummary {
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make([]DatasetSummary, 0, len(datasetDefinitions))
	for _, definition := range datasetDefinitions {
		result = append(result, summaryFor(definition, s.files[definition.Name]))
	}
	return result
}

func (s *Store) Dataset(name string) (DatasetState, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	definition, ok := datasetDefinition(name)
	if !ok {
		return DatasetState{}, ErrDatasetNotFound
	}
	file := s.files[name]
	return DatasetState{
		Summary: summaryFor(definition, file),
		Data:    append(json.RawMessage(nil), file.Body...),
	}, nil
}

func (s *Store) UpdateDataset(name string, body json.RawMessage, expectedVersion string) (DatasetState, error) {
	definition, ok := datasetDefinition(name)
	if !ok {
		return DatasetState{}, ErrDatasetNotFound
	}
	canonical, err := normalizeDataset(definition, body)
	if err != nil {
		return DatasetState{}, err
	}

	s.mu.Lock()
	current := s.files[name]
	if expectedVersion == "" || expectedVersion != current.Version {
		s.mu.Unlock()
		return DatasetState{}, ErrVersionConflict
	}
	candidate := cloneFiles(s.files)
	updatedAt := time.Now().UTC()
	candidate[name] = datasetFile{Body: canonical, Version: versionOf(canonical), UpdatedAt: updatedAt}
	snapshot, err := buildSnapshot(candidate)
	if err != nil {
		s.mu.Unlock()
		return DatasetState{}, err
	}
	if err := writeAtomic(filepath.Join(s.directory, definition.Filename), canonical); err != nil {
		s.mu.Unlock()
		return DatasetState{}, err
	}
	s.files = candidate
	s.snapshot = snapshot
	s.revision++
	s.lastReloadError = ""
	revision := s.revision
	state := DatasetState{Summary: summaryFor(definition, candidate[name]), Data: append(json.RawMessage(nil), canonical...)}
	s.mu.Unlock()

	s.publish(ChangeEvent{Type: "dataset.changed", Datasets: []string{name}, Revision: revision, ChangedAt: updatedAt})
	return state, nil
}

func (s *Store) StartWatcher(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 300 * time.Millisecond
	}
	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				s.reloadFromDisk()
			}
		}
	}()
}

func (s *Store) Subscribe() (<-chan ChangeEvent, func()) {
	channel := make(chan ChangeEvent, 8)
	s.subMu.Lock()
	s.subscribers[channel] = struct{}{}
	s.subMu.Unlock()
	return channel, func() {
		s.subMu.Lock()
		if _, ok := s.subscribers[channel]; ok {
			delete(s.subscribers, channel)
			close(channel)
		}
		s.subMu.Unlock()
	}
}

func (s *Store) reloadFromDisk() {
	s.mu.Lock()
	files, err := readDatasetFiles(s.directory)
	if err != nil {
		s.lastReloadError = err.Error()
		s.mu.Unlock()
		return
	}
	changed := make([]string, 0)
	for _, definition := range datasetDefinitions {
		if files[definition.Name].Version != s.files[definition.Name].Version {
			changed = append(changed, definition.Name)
		}
	}
	if len(changed) == 0 {
		s.lastReloadError = ""
		s.mu.Unlock()
		return
	}
	snapshot, err := buildSnapshot(files)
	if err != nil {
		s.lastReloadError = err.Error()
		s.mu.Unlock()
		return
	}
	s.files = files
	s.snapshot = snapshot
	s.revision++
	s.lastReloadError = ""
	revision := s.revision
	s.mu.Unlock()

	s.publish(ChangeEvent{Type: "dataset.changed", Datasets: changed, Revision: revision, ChangedAt: time.Now().UTC()})
}

func (s *Store) publish(event ChangeEvent) {
	s.subMu.Lock()
	defer s.subMu.Unlock()
	for channel := range s.subscribers {
		select {
		case channel <- event:
		default:
		}
	}
}

func readDatasetFiles(directory string) (map[string]datasetFile, error) {
	files := make(map[string]datasetFile, len(datasetDefinitions))
	for _, definition := range datasetDefinitions {
		path := filepath.Join(directory, definition.Filename)
		body, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", path, err)
		}
		canonical, err := normalizeDataset(definition, body)
		if err != nil {
			return nil, fmt.Errorf("validate %s: %w", path, err)
		}
		info, err := os.Stat(path)
		if err != nil {
			return nil, fmt.Errorf("stat %s: %w", path, err)
		}
		files[definition.Name] = datasetFile{Body: canonical, Version: versionOf(canonical), UpdatedAt: info.ModTime().UTC()}
	}
	return files, nil
}

func normalizeDataset(definition DatasetDefinition, body []byte) (json.RawMessage, error) {
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, fmt.Errorf("JSON không hợp lệ: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return nil, errors.New("JSON chứa dữ liệu thừa sau giá trị chính")
	}
	if definition.Kind == "array" {
		if _, ok := value.([]any); !ok {
			return nil, errors.New("dataset phải là một mảng JSON")
		}
	} else {
		if _, ok := value.(map[string]any); !ok {
			return nil, errors.New("dataset phải là một object JSON")
		}
	}
	if err := validatePrimaryKeys(definition, value); err != nil {
		return nil, err
	}
	formatted, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("encode dataset: %w", err)
	}
	return append(formatted, '\n'), nil
}

func validatePrimaryKeys(definition DatasetDefinition, value any) error {
	if definition.PrimaryKey == "" {
		return nil
	}
	var records []any
	if definition.RecordPath != "" {
		object := value.(map[string]any)
		nested, ok := object[definition.RecordPath].([]any)
		if !ok {
			return fmt.Errorf("trường %s phải là một mảng JSON", definition.RecordPath)
		}
		records = nested
	} else {
		records = value.([]any)
	}
	seen := make(map[string]struct{}, len(records))
	for index, raw := range records {
		record, ok := raw.(map[string]any)
		if !ok {
			return fmt.Errorf("bản ghi %d phải là một object JSON", index+1)
		}
		key := strings.TrimSpace(fmt.Sprint(record[definition.PrimaryKey]))
		if key == "" || key == "<nil>" {
			return fmt.Errorf("bản ghi %d thiếu khóa %s", index+1, definition.PrimaryKey)
		}
		if _, exists := seen[key]; exists {
			return fmt.Errorf("khóa %s bị trùng: %s", definition.PrimaryKey, key)
		}
		seen[key] = struct{}{}
	}
	return nil
}

func buildSnapshot(files map[string]datasetFile) (Snapshot, error) {
	var snapshot Snapshot
	loads := []struct {
		name string
		out  any
	}{
		{"metadata", &snapshot.Meta},
		{"facilities", &snapshot.Facilities},
		{"rooms", &snapshot.Rooms},
		{"doctors", &snapshot.Doctors},
		{"rules", &snapshot.Rules},
		{"patterns", &snapshot.Patterns},
		{"dictionary", &snapshot.Dictionary},
		{"sources", &snapshot.Sources},
		{"organization", &snapshot.Units},
		{"schedule", &snapshot.Schedule},
	}
	for _, item := range loads {
		file, ok := files[item.name]
		if !ok {
			return Snapshot{}, fmt.Errorf("dataset %s chưa được nạp", item.name)
		}
		if err := json.Unmarshal(file.Body, item.out); err != nil {
			return Snapshot{}, fmt.Errorf("decode dataset %s: %w", item.name, err)
		}
	}
	if snapshot.Schedule.Assignments == nil {
		snapshot.Schedule.Assignments = []Record{}
	}
	if err := validateReferences(snapshot); err != nil {
		return Snapshot{}, err
	}
	return snapshot, nil
}

func validateReferences(snapshot Snapshot) error {
	facilities := recordIndex(snapshot.Facilities, "facility_id")
	rooms := recordIndex(snapshot.Rooms, "room_id")
	doctors := recordIndex(snapshot.Doctors, "staff_id")

	for _, pattern := range snapshot.Patterns {
		staffID := strings.TrimSpace(fmt.Sprint(pattern["staff_id"]))
		if staffID != "" && staffID != "<nil>" {
			if _, ok := doctors[staffID]; !ok {
				return fmt.Errorf("mẫu %v tham chiếu bác sĩ không tồn tại: %s", pattern["pattern_id"], staffID)
			}
		}
	}
	validScheduleStatus := map[string]bool{"EMPTY": true, "DRAFT": true, "PUBLISHED": true}
	if !validScheduleStatus[snapshot.Schedule.PublishedStatus] {
		return fmt.Errorf("published_status của lịch phải là EMPTY, DRAFT hoặc PUBLISHED")
	}
	weekStart, weekEnd := valueString(snapshot.Schedule.WeekStart), valueString(snapshot.Schedule.WeekEnd)
	for _, assignment := range snapshot.Schedule.Assignments {
		id := valueString(assignment["assignment_id"])
		facilityID := valueString(assignment["facility_id"])
		roomID := valueString(assignment["room_id"])
		staffID := valueString(assignment["staff_id"])
		status := valueString(assignment["assignment_status"])
		shift := valueString(assignment["shift_code"])
		date := valueString(assignment["schedule_date"])
		if facilityID != "" {
			if _, ok := facilities[facilityID]; !ok {
				return fmt.Errorf("phân công %s tham chiếu cơ sở không tồn tại: %s", id, facilityID)
			}
		}
		if roomID != "" {
			room, ok := rooms[roomID]
			if !ok {
				return fmt.Errorf("phân công %s tham chiếu phòng không tồn tại: %s", id, roomID)
			}
			if facilityID != "" && valueString(room["facility_id"]) != facilityID {
				return fmt.Errorf("phân công %s có phòng không thuộc cơ sở %s", id, facilityID)
			}
		}
		if (status == "WORKING" || status == "AREA_DUTY") && staffID == "" {
			return fmt.Errorf("phân công %s đang làm việc nhưng thiếu staff_id", id)
		}
		if staffID != "" {
			if _, ok := doctors[staffID]; !ok {
				return fmt.Errorf("phân công %s tham chiếu bác sĩ không tồn tại: %s", id, staffID)
			}
		}
		if shift != "" && shift != "FULL_DAY" && shift != "AM" && shift != "PM" {
			return fmt.Errorf("phân công %s có shift_code không hợp lệ: %s", id, shift)
		}
		if date != "" && weekStart != "" && weekEnd != "" && (date < weekStart || date > weekEnd) {
			return fmt.Errorf("phân công %s có ngày nằm ngoài tuần hiện hành", id)
		}
		startTime, endTime := valueString(assignment["start_time"]), valueString(assignment["end_time"])
		if (startTime == "") != (endTime == "") {
			return fmt.Errorf("phân công %s phải có cả start_time và end_time hoặc để trống cả hai", id)
		}
	}
	return nil
}

func recordIndex(records []Record, key string) map[string]Record {
	result := make(map[string]Record, len(records))
	for _, record := range records {
		result[valueString(record[key])] = record
	}
	return result
}

func valueString(value any) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(value))
}

func datasetDefinition(name string) (DatasetDefinition, bool) {
	for _, definition := range datasetDefinitions {
		if definition.Name == name {
			return definition, true
		}
	}
	return DatasetDefinition{}, false
}

func summaryFor(definition DatasetDefinition, file datasetFile) DatasetSummary {
	return DatasetSummary{
		DatasetDefinition: definition,
		Count:             recordCount(definition, file.Body),
		Version:           file.Version,
		UpdatedAt:         file.UpdatedAt,
	}
}

func recordCount(definition DatasetDefinition, body json.RawMessage) int {
	var value any
	if json.Unmarshal(body, &value) != nil {
		return 0
	}
	if definition.RecordPath != "" {
		if object, ok := value.(map[string]any); ok {
			if records, ok := object[definition.RecordPath].([]any); ok {
				return len(records)
			}
		}
	}
	if records, ok := value.([]any); ok {
		return len(records)
	}
	return 1
}

func versionOf(body []byte) string {
	digest := sha256.Sum256(body)
	return hex.EncodeToString(digest[:8])
}

func cloneFiles(input map[string]datasetFile) map[string]datasetFile {
	result := make(map[string]datasetFile, len(input))
	for name, file := range input {
		result[name] = file
	}
	return result
}

func writeAtomic(path string, body []byte) error {
	temporary, err := os.CreateTemp(filepath.Dir(path), ".hospital-data-*.tmp")
	if err != nil {
		return fmt.Errorf("tạo file tạm: %w", err)
	}
	temporaryName := temporary.Name()
	defer os.Remove(temporaryName)
	if _, err := temporary.Write(body); err != nil {
		temporary.Close()
		return fmt.Errorf("ghi file tạm: %w", err)
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return fmt.Errorf("đồng bộ file tạm: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("đóng file tạm: %w", err)
	}
	if err := os.Chmod(temporaryName, 0o644); err != nil {
		return fmt.Errorf("đặt quyền file tạm: %w", err)
	}
	if err := os.Rename(temporaryName, path); err != nil {
		return fmt.Errorf("thay file dữ liệu: %w", err)
	}
	return nil
}

func Find(records []Record, key, value string) (Record, bool) {
	for _, record := range records {
		if fmt.Sprint(record[key]) == value {
			return record, true
		}
	}
	return nil, false
}

func SortedDatasetNames() []string {
	names := make([]string, 0, len(datasetDefinitions))
	for _, definition := range datasetDefinitions {
		names = append(names, definition.Name)
	}
	sort.Strings(names)
	return names
}

package data

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
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

type Store struct {
	directory  string
	Meta       Record
	Facilities []Record
	Rooms      []Record
	Doctors    []Record
	Rules      []Record
	Patterns   []Record
	Dictionary []Record
	Sources    []Record
	Units      []Record
}

func Load(directory string) (*Store, error) {
	s := &Store{directory: directory}
	loads := []struct {
		name string
		out  any
	}{
		{"dataset_meta.json", &s.Meta},
		{"facilities.json", &s.Facilities},
		{"rooms.json", &s.Rooms},
		{"doctors.json", &s.Doctors},
		{"scheduling_rules.json", &s.Rules},
		{"assignment_patterns.json", &s.Patterns},
		{"data_dictionary.json", &s.Dictionary},
		{"source_registry.json", &s.Sources},
		{"organization.json", &s.Units},
	}
	for _, item := range loads {
		if err := decode(filepath.Join(directory, item.name), item.out); err != nil {
			return nil, err
		}
	}
	if _, err := s.CurrentSchedule(); err != nil {
		return nil, err
	}
	return s, nil
}

func (s *Store) CurrentSchedule() (Schedule, error) {
	var schedule Schedule
	err := decode(filepath.Join(s.directory, "current_schedule.json"), &schedule)
	return schedule, err
}

func decode(path string, target any) error {
	body, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read %s: %w", path, err)
	}
	if err := json.Unmarshal(body, target); err != nil {
		return fmt.Errorf("decode %s: %w", path, err)
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

package data

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func fixtureDirectory(t *testing.T) string {
	t.Helper()
	target := t.TempDir()
	source := filepath.Join("..", "..", "..", "hospital-data")
	for _, definition := range datasetDefinitions {
		body, err := os.ReadFile(filepath.Join(source, definition.Filename))
		if err != nil {
			t.Fatalf("read fixture %s: %v", definition.Filename, err)
		}
		if err := os.WriteFile(filepath.Join(target, definition.Filename), body, 0o644); err != nil {
			t.Fatalf("write fixture %s: %v", definition.Filename, err)
		}
	}
	return target
}

func TestUpdateDatasetSwapsSnapshotAndRejectsStaleVersion(t *testing.T) {
	directory := fixtureDirectory(t)
	store, err := Load(directory)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	state, err := store.Dataset("doctors")
	if err != nil {
		t.Fatalf("dataset: %v", err)
	}
	var doctors []Record
	if err := json.Unmarshal(state.Data, &doctors); err != nil {
		t.Fatalf("decode doctors: %v", err)
	}
	doctors = append(doctors, Record{
		"staff_id":              "TEST001",
		"full_name":             "Bác sĩ Kiểm Thử",
		"credential_raw":        "BS",
		"credential_normalized": "BS",
		"observed_facilities":   []string{},
		"observed_areas":        []string{},
		"notes":                 nil,
		"source_confidence":     "TEST",
		"source":                Record{"file": "store_test.go"},
	})
	body, _ := json.Marshal(doctors)
	updated, err := store.UpdateDataset("doctors", body, state.Summary.Version)
	if err != nil {
		t.Fatalf("update: %v", err)
	}
	if updated.Summary.Count != state.Summary.Count+1 {
		t.Fatalf("count = %d, want %d", updated.Summary.Count, state.Summary.Count+1)
	}
	if _, ok := Find(store.Snapshot().Doctors, "staff_id", "TEST001"); !ok {
		t.Fatal("new doctor was not visible in the in-memory snapshot")
	}
	if _, err := store.UpdateDataset("doctors", body, state.Summary.Version); err != ErrVersionConflict {
		t.Fatalf("stale update error = %v, want ErrVersionConflict", err)
	}

	var persisted []Record
	persistedBody, err := os.ReadFile(filepath.Join(directory, "doctors.json"))
	if err != nil {
		t.Fatalf("read persisted doctors: %v", err)
	}
	if err := json.Unmarshal(persistedBody, &persisted); err != nil {
		t.Fatalf("decode persisted doctors: %v", err)
	}
	if _, ok := Find(persisted, "staff_id", "TEST001"); !ok {
		t.Fatal("new doctor was not persisted")
	}
}

func TestWatcherReloadsExternalFileChange(t *testing.T) {
	directory := fixtureDirectory(t)
	store, err := Load(directory)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	store.StartWatcher(ctx, 20*time.Millisecond)
	events, unsubscribe := store.Subscribe()
	defer unsubscribe()

	path := filepath.Join(directory, "dataset_meta.json")
	var meta Record
	body, _ := os.ReadFile(path)
	if err := json.Unmarshal(body, &meta); err != nil {
		t.Fatalf("decode metadata: %v", err)
	}
	meta["dataset_name"] = "Dữ liệu đã đổi từ bên ngoài"
	changed, _ := json.MarshalIndent(meta, "", "  ")
	if err := os.WriteFile(path, append(changed, '\n'), 0o644); err != nil {
		t.Fatalf("write external change: %v", err)
	}

	select {
	case event := <-events:
		if len(event.Datasets) != 1 || event.Datasets[0] != "metadata" {
			t.Fatalf("changed datasets = %v", event.Datasets)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("watcher did not publish an event")
	}
	if got := store.Snapshot().Meta["dataset_name"]; got != "Dữ liệu đã đổi từ bên ngoài" {
		t.Fatalf("snapshot metadata = %v", got)
	}
}

func TestUpdateDatasetValidatesReferences(t *testing.T) {
	store, err := Load(fixtureDirectory(t))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	state, _ := store.Dataset("doctors")
	var doctors []Record
	_ = json.Unmarshal(state.Data, &doctors)
	filtered := make([]Record, 0, len(doctors))
	for _, doctor := range doctors {
		if doctor["staff_id"] != "NV045" {
			filtered = append(filtered, doctor)
		}
	}
	body, _ := json.Marshal(filtered)
	if _, err := store.UpdateDataset("doctors", body, state.Summary.Version); err == nil {
		t.Fatal("expected deletion of a referenced doctor to fail")
	}
}

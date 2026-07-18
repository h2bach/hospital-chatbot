package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"hospital-info-service/internal/data"
)

var fixtureFiles = []string{
	"current_schedule.json", "doctors.json", "facilities.json", "rooms.json",
	"organization.json", "scheduling_rules.json", "assignment_patterns.json",
	"data_dictionary.json", "source_registry.json", "dataset_meta.json",
}

func apiFixtureDirectory(t *testing.T) string {
	t.Helper()
	target := t.TempDir()
	source := filepath.Join("..", "..", "..", "hospital-data")
	for _, name := range fixtureFiles {
		body, err := os.ReadFile(filepath.Join(source, name))
		if err != nil {
			t.Fatalf("read fixture %s: %v", name, err)
		}
		if err := os.WriteFile(filepath.Join(target, name), body, 0o644); err != nil {
			t.Fatalf("write fixture %s: %v", name, err)
		}
	}
	return target
}

func TestAdminUpdateIsImmediatelyVisibleToPublicAPI(t *testing.T) {
	store, err := data.Load(apiFixtureDirectory(t))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	handler := NewServer(":0", store).Handler()

	get := httptest.NewRecorder()
	handler.ServeHTTP(get, httptest.NewRequest(http.MethodGet, "/api/v1/admin/datasets/doctors", nil))
	if get.Code != http.StatusOK {
		t.Fatalf("admin get status = %d: %s", get.Code, get.Body.String())
	}
	var current struct {
		Dataset data.DatasetSummary `json:"dataset"`
		Data    []data.Record       `json:"data"`
	}
	if err := json.Unmarshal(get.Body.Bytes(), &current); err != nil {
		t.Fatalf("decode admin get: %v", err)
	}
	current.Data = append(current.Data, data.Record{
		"staff_id": "TEST_API", "full_name": "Bác sĩ API Thời Gian Thực",
		"credential_raw": "BS", "credential_normalized": "BS",
		"observed_facilities": []string{}, "observed_areas": []string{},
		"notes": nil, "source_confidence": "TEST", "source": data.Record{"file": "admin_test.go"},
	})
	updateBody, _ := json.Marshal(map[string]any{"version": current.Dataset.Version, "data": current.Data})
	update := httptest.NewRecorder()
	handler.ServeHTTP(update, httptest.NewRequest(http.MethodPut, "/api/v1/admin/datasets/doctors", bytes.NewReader(updateBody)))
	if update.Code != http.StatusOK {
		t.Fatalf("admin update status = %d: %s", update.Code, update.Body.String())
	}

	public := httptest.NewRecorder()
	handler.ServeHTTP(public, httptest.NewRequest(http.MethodGet, "/api/v1/doctors?q=API%20Thời%20Gian%20Thực", nil))
	if public.Code != http.StatusOK || !bytes.Contains(public.Body.Bytes(), []byte("TEST_API")) {
		t.Fatalf("public API did not expose update immediately: %d %s", public.Code, public.Body.String())
	}

	stale := httptest.NewRecorder()
	handler.ServeHTTP(stale, httptest.NewRequest(http.MethodPut, "/api/v1/admin/datasets/doctors", bytes.NewReader(updateBody)))
	if stale.Code != http.StatusConflict {
		t.Fatalf("stale update status = %d, want %d", stale.Code, http.StatusConflict)
	}
}

func TestAdminUpdateAllowsRemoteBrowserOrigin(t *testing.T) {
	store, err := data.Load(apiFixtureDirectory(t))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	handler := NewServer(":0", store).Handler()
	request := httptest.NewRequest(http.MethodOptions, "/api/v1/admin/datasets/doctors", nil)
	request.Header.Set("Origin", "https://trolytimhanoi.cns.io.vn")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("remote origin status = %d, want %d", response.Code, http.StatusNoContent)
	}
	if allowOrigin := response.Header().Get("Access-Control-Allow-Origin"); allowOrigin != "https://trolytimhanoi.cns.io.vn" {
		t.Fatalf("Access-Control-Allow-Origin = %q, want https://trolytimhanoi.cns.io.vn", allowOrigin)
	}
}

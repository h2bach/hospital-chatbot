package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"runtime"
	"testing"

	"mock-info-service/internal/store"
)

func testServer(t *testing.T) *Server {
	t.Helper()
	_, file, _, _ := runtime.Caller(0)
	data := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "mock-data", "output"))
	s, err := store.Load(data)
	if err != nil { t.Fatal(err) }
	return NewServer(":0", s)
}

func request(t *testing.T, handler http.Handler, method, path string, body any, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	var raw []byte
	if body != nil { raw, _ = json.Marshal(body) }
	r := httptest.NewRequest(method, path, bytes.NewReader(raw))
	r.Header.Set("Content-Type", "application/json")
	for key, value := range headers { r.Header.Set(key, value) }
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, r)
	return w
}

func TestHealthAndCollectionPagination(t *testing.T) {
	s := testServer(t)
	if got := request(t, s.Handler(), "GET", "/health", nil, nil); got.Code != 200 { t.Fatalf("health: %d", got.Code) }
	got := request(t, s.Handler(), "GET", "/api/v1/data/facilities?limit=2", nil, nil)
	if got.Code != 200 { t.Fatalf("facilities: %d %s", got.Code, got.Body.String()) }
	var response struct { Data []store.Record `json:"data"` }
	_ = json.Unmarshal(got.Body.Bytes(), &response)
	if len(response.Data) != 2 { t.Fatalf("want 2 rows, got %d", len(response.Data)) }
}

func TestCreateAppointmentRequiresConfirmationAndIsIdempotent(t *testing.T) {
	s := testServer(t)
	body := map[string]any{"patient_id":"PAT-000001","slot_id":"SLT-0000001","reason_for_visit":"API test","confirmed":false}
	got := request(t, s.Handler(), "POST", "/api/v1/appointments", body, map[string]string{"Idempotency-Key":"test-key"})
	if got.Code != 422 { t.Fatalf("want 422, got %d", got.Code) }
	body["confirmed"] = true
	got = request(t, s.Handler(), "POST", "/api/v1/appointments", body, map[string]string{"Idempotency-Key":"test-key"})
	if got.Code != 201 { t.Fatalf("create: %d %s", got.Code, got.Body.String()) }
	replay := request(t, s.Handler(), "POST", "/api/v1/appointments", body, map[string]string{"Idempotency-Key":"test-key"})
	if replay.Code != 201 || !bytes.Contains(replay.Body.Bytes(), []byte(`"idempotency_replayed":true`)) { t.Fatalf("replay: %d %s", replay.Code, replay.Body.String()) }
}

func TestVerifyPatient(t *testing.T) {
	s := testServer(t)
	valid := map[string]any{"patient_code":"BN0000001","date_of_birth":"2008-07-17"}
	got := request(t, s.Handler(), "POST", "/api/v1/patients/PAT-000001/verify", valid, nil)
	if got.Code != 200 { t.Fatalf("verify: %d %s", got.Code, got.Body.String()) }
	valid["patient_code"] = "WRONG"
	if got = request(t, s.Handler(), "POST", "/api/v1/patients/PAT-000001/verify", valid, nil); got.Code != 401 { t.Fatalf("want 401, got %d", got.Code) }
}

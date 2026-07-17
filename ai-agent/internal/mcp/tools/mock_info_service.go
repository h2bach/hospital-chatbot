package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

const defaultMockInfoServiceURL = "http://localhost:8080"

// APIOutput deliberately keeps the upstream response intact. This lets the
// agent see service error codes as well as successful data without another
// endpoint-specific translation layer.
type APIOutput struct {
	Status int `json:"status" jsonschema:"HTTP status returned by mock-info-service"`
	Body   any `json:"body" jsonschema:"JSON response returned by mock-info-service"`
}

type EmptyInput struct{}

type ListCollectionsInput struct{}

type ListRecordsInput struct {
	Collection string            `json:"collection" jsonschema:"collection name"`
	Limit      int               `json:"limit,omitempty" jsonschema:"maximum 500; default 50"`
	Offset     int               `json:"offset,omitempty" jsonschema:"zero-based offset"`
	Filters    map[string]string `json:"filters,omitempty" jsonschema:"field equality filters"`
}

type RecordInput struct {
	Collection string         `json:"collection" jsonschema:"collection name"`
	ID         string         `json:"id,omitempty" jsonschema:"record primary key; required for get, update and delete"`
	Record     map[string]any `json:"record,omitempty" jsonschema:"record JSON object; required for create and update"`
}

type SearchInput struct {
	Collection string `json:"collection" jsonschema:"collection to search"`
	Query      string `json:"q" jsonschema:"case-insensitive full-text query"`
}

type KnowledgeSearchInput struct {
	Query string `json:"q" jsonschema:"question or terms to search in hospital knowledge"`
}

type FacilityInput struct {
	FacilityID string `json:"facility_id,omitempty" jsonschema:"optional facility identifier"`
}

type DoctorScheduleInput struct {
	DoctorID   string `json:"doctor_id" jsonschema:"doctor identifier"`
	Date       string `json:"date,omitempty" jsonschema:"schedule date in YYYY-MM-DD format"`
	FacilityID string `json:"facility_id,omitempty" jsonschema:"optional facility identifier"`
}

type ServiceInput struct {
	ServiceID string `json:"service_id" jsonschema:"medical service identifier"`
}

type AvailableSlotsInput struct {
	Date       string `json:"date,omitempty" jsonschema:"schedule date in YYYY-MM-DD format"`
	DoctorID   string `json:"doctor_id,omitempty" jsonschema:"doctor identifier"`
	FacilityID string `json:"facility_id,omitempty" jsonschema:"facility identifier"`
}

type CreateAppointmentInput struct {
	PatientID      string `json:"patient_id" jsonschema:"patient identifier"`
	SlotID         string `json:"slot_id" jsonschema:"available slot identifier"`
	Reason         string `json:"reason_for_visit,omitempty" jsonschema:"reason for visit"`
	Confirmed      bool   `json:"confirmed" jsonschema:"must be true to create an appointment"`
	IdempotencyKey string `json:"idempotency_key,omitempty" jsonschema:"optional key for safe retries; generated when omitted"`
}

type CancelAppointmentInput struct {
	AppointmentID string `json:"appointment_id" jsonschema:"appointment identifier"`
	Reason        string `json:"reason" jsonschema:"reason for cancellation"`
	Confirmed     bool   `json:"confirmed" jsonschema:"must be true to cancel an appointment"`
}

type VerifyPatientInput struct {
	PatientID   string `json:"patient_id" jsonschema:"patient identifier"`
	PatientCode string `json:"patient_code" jsonschema:"patient code"`
	DateOfBirth string `json:"date_of_birth" jsonschema:"date of birth as stored by the service"`
}

var (
	HealthTool            = mcp_sdk.Tool{Name: "mockInfoHealth", Description: "check mock-info-service health"}
	ListCollectionsTool   = mcp_sdk.Tool{Name: "listInfoCollections", Description: "list mock-info-service collections and record counts"}
	ListRecordsTool       = mcp_sdk.Tool{Name: "listInfoRecords", Description: "list records from a mock-info-service collection with pagination and equality filters"}
	GetRecordTool         = mcp_sdk.Tool{Name: "getInfoRecord", Description: "get one record from a mock-info-service collection"}
	CreateRecordTool      = mcp_sdk.Tool{Name: "createInfoRecord", Description: "create a record in a mock-info-service collection"}
	UpdateRecordTool      = mcp_sdk.Tool{Name: "updateInfoRecord", Description: "patch a record in a mock-info-service collection"}
	DeleteRecordTool      = mcp_sdk.Tool{Name: "deleteInfoRecord", Description: "delete a record from a mock-info-service collection"}
	SearchInfoTool        = mcp_sdk.Tool{Name: "searchInfo", Description: "search records in a mock-info-service collection"}
	AvailableSlotsTool    = mcp_sdk.Tool{Name: "findAvailableSlots", Description: "find available appointment slots by date, doctor, or facility"}
	CreateAppointmentTool = mcp_sdk.Tool{Name: "createAppointment", Description: "create a confirmed appointment through mock-info-service"}
	CancelAppointmentTool = mcp_sdk.Tool{Name: "cancelAppointment", Description: "cancel an appointment and release its slot"}
	VerifyPatientTool     = mcp_sdk.Tool{Name: "verifyPatient", Description: "verify a patient using patient code and date of birth"}
	KnowledgeSearchTool   = mcp_sdk.Tool{Name: "searchHospitalKnowledge", Description: "search approved hospital FAQs and knowledge documents"}
	HospitalInfoTool      = mcp_sdk.Tool{Name: "getHospitalInfo", Description: "get hospital facility information"}
	HospitalHoursTool     = mcp_sdk.Tool{Name: "getHospitalHours", Description: "get hospital operating hours"}
	HospitalEmergencyTool = mcp_sdk.Tool{Name: "getEmergencyInfo", Description: "get official hospital emergency instructions"}
	DoctorsTool           = mcp_sdk.Tool{Name: "listDoctors", Description: "list hospital doctors"}
	DoctorSchedulesTool   = mcp_sdk.Tool{Name: "getDoctorSchedules", Description: "get schedules for a doctor"}
	DepartmentsTool       = mcp_sdk.Tool{Name: "listDepartments", Description: "list hospital departments"}
	ServicesTool          = mcp_sdk.Tool{Name: "listMedicalServices", Description: "list medical services"}
	ServiceTool           = mcp_sdk.Tool{Name: "getMedicalService", Description: "get details for a medical service"}
	ServicePricesTool     = mcp_sdk.Tool{Name: "getServicePrices", Description: "get prices for a medical service"}
	BookingLinksTool      = mcp_sdk.Tool{Name: "getBookingLinks", Description: "get official appointment booking channels"}
)

func MockInfoHealthHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/health", nil, nil)
}

func ListCollectionsHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ ListCollectionsInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/meta/collections", nil, nil)
}

func ListRecordsHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input ListRecordsInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := url.Values{}
	if input.Limit > 0 {
		query.Set("limit", strconv.Itoa(input.Limit))
	}
	if input.Offset > 0 {
		query.Set("offset", strconv.Itoa(input.Offset))
	}
	for key, value := range input.Filters {
		query.Set("filter["+key+"]", value)
	}
	return callMockInfo(ctx, http.MethodGet, "/api/v1/data/"+url.PathEscape(input.Collection), query, nil)
}

func GetRecordHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input RecordInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, recordPath(input), nil, nil)
}

func CreateRecordHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input RecordInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodPost, collectionPath(input.Collection), nil, input.Record)
}

func UpdateRecordHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input RecordInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodPatch, recordPath(input), nil, input.Record)
}

func DeleteRecordHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input RecordInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodDelete, recordPath(input), nil, nil)
}

func SearchInfoHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input SearchInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := url.Values{"collection": {input.Collection}, "q": {input.Query}}
	return callMockInfo(ctx, http.MethodGet, "/api/v1/search", query, nil)
}

func KnowledgeSearchHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input KnowledgeSearchInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/knowledge/search", url.Values{"q": {input.Query}}, nil)
}

func HospitalInfoHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/hospital", nil, nil)
}

func HospitalHoursHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input FacilityInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := url.Values{}
	if input.FacilityID != "" {
		query.Set("facility_id", input.FacilityID)
	}
	return callMockInfo(ctx, http.MethodGet, "/api/v1/hospital/hours", query, nil)
}

func HospitalEmergencyHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/hospital/emergency", nil, nil)
}

func DoctorsHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/doctors", nil, nil)
}

func DoctorSchedulesHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input DoctorScheduleInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := url.Values{}
	if input.Date != "" {
		query.Set("date", input.Date)
	}
	if input.FacilityID != "" {
		query.Set("facility_id", input.FacilityID)
	}
	return callMockInfo(ctx, http.MethodGet, "/api/v1/doctors/"+url.PathEscape(input.DoctorID)+"/schedules", query, nil)
}

func DepartmentsHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/departments", nil, nil)
}

func ServicesHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/services", nil, nil)
}

func ServiceHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input ServiceInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/services/"+url.PathEscape(input.ServiceID), nil, nil)
}

func ServicePricesHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input ServiceInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfo(ctx, http.MethodGet, "/api/v1/services/"+url.PathEscape(input.ServiceID)+"/prices", nil, nil)
}

func BookingLinksHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input FacilityInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := url.Values{}
	if input.FacilityID != "" {
		query.Set("facility_id", input.FacilityID)
	}
	return callMockInfo(ctx, http.MethodGet, "/api/v1/booking-links", query, nil)
}

func AvailableSlotsHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input AvailableSlotsInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := url.Values{}
	if input.Date != "" {
		query.Set("date", input.Date)
	}
	if input.DoctorID != "" {
		query.Set("doctor_id", input.DoctorID)
	}
	if input.FacilityID != "" {
		query.Set("facility_id", input.FacilityID)
	}
	return callMockInfo(ctx, http.MethodGet, "/api/v1/available-slots", query, nil)
}

func CreateAppointmentHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input CreateAppointmentInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	body := map[string]any{"patient_id": input.PatientID, "slot_id": input.SlotID, "reason_for_visit": input.Reason, "confirmed": input.Confirmed}
	key := input.IdempotencyKey
	if key == "" {
		key = idempotencyKey(input.PatientID, input.SlotID)
	}
	return callMockInfoWithHeaders(ctx, http.MethodPost, "/api/v1/appointments", nil, body, map[string]string{"Idempotency-Key": key})
}

func CancelAppointmentHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input CancelAppointmentInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	body := map[string]any{"reason": input.Reason, "confirmed": input.Confirmed}
	return callMockInfo(ctx, http.MethodPatch, "/api/v1/appointments/"+url.PathEscape(input.AppointmentID)+"/cancel", nil, body)
}

func VerifyPatientHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input VerifyPatientInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	body := map[string]any{"patient_code": input.PatientCode, "date_of_birth": input.DateOfBirth}
	return callMockInfo(ctx, http.MethodPost, "/api/v1/patients/"+url.PathEscape(input.PatientID)+"/verify", nil, body)
}

func collectionPath(collection string) string { return "/api/v1/data/" + url.PathEscape(collection) }
func recordPath(input RecordInput) string {
	return collectionPath(input.Collection) + "/" + url.PathEscape(input.ID)
}
func idempotencyKey(patientID, slotID string) string { return "agent-" + patientID + "-" + slotID }

func callMockInfo(ctx context.Context, method, path string, query url.Values, body any) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callMockInfoWithHeaders(ctx, method, path, query, body, nil)
}

func callMockInfoWithHeaders(ctx context.Context, method, path string, query url.Values, body any, headers map[string]string) (*mcp_sdk.CallToolResult, APIOutput, error) {
	baseURL := strings.TrimRight(os.Getenv("MOCK_INFO_SERVICE_URL"), "/")
	if baseURL == "" {
		baseURL = defaultMockInfoServiceURL
	}
	endpoint := baseURL + path
	if len(query) > 0 {
		endpoint += "?" + query.Encode()
	}
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, APIOutput{}, fmt.Errorf("marshal mock-info request: %w", err)
		}
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, endpoint, reader)
	if err != nil {
		return nil, APIOutput{}, fmt.Errorf("create mock-info request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, APIOutput{}, fmt.Errorf("call mock-info-service: %w", err)
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, APIOutput{}, fmt.Errorf("read mock-info response: %w", err)
	}
	var result any
	if len(bytes.TrimSpace(data)) > 0 {
		if err := json.Unmarshal(data, &result); err != nil {
			return nil, APIOutput{}, fmt.Errorf("decode mock-info response: %w", err)
		}
	}
	return nil, APIOutput{Status: resp.StatusCode, Body: result}, nil
}

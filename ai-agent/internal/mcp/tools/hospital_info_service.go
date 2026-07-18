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

const defaultHospitalInfoServiceURL = "http://localhost:8081"

type APIOutput struct {
	Status int `json:"status" jsonschema:"HTTP status returned by hospital-info-service"`
	Body   any `json:"body" jsonschema:"JSON response returned by hospital-info-service"`
}

type EmptyInput struct{}

type PageInput struct {
	Query  string `json:"q,omitempty" jsonschema:"optional Vietnamese full-text query"`
	Limit  int    `json:"limit,omitempty" jsonschema:"maximum 500; default 50"`
	Offset int    `json:"offset,omitempty" jsonschema:"zero-based offset"`
}

type SearchDirectoryInput struct {
	Query string   `json:"q" jsonschema:"Vietnamese name or terms to search"`
	Types []string `json:"types,omitempty" jsonschema:"optional entity types: doctors, rooms, organization, rules, patterns"`
}

type OrganizationInput struct {
	PageInput
	Block    string `json:"block,omitempty" jsonschema:"HÀNH CHÍNH, LÂM SÀNG, or CẬN LÂM SÀNG"`
	ParentID string `json:"parent_id,omitempty" jsonschema:"parent organization unit identifier"`
	UnitType string `json:"unit_type,omitempty" jsonschema:"LEADERSHIP, BLOCK, CENTER, DEPARTMENT, CLINIC, or UNIT"`
}

type RoomsInput struct {
	PageInput
	FacilityID string `json:"facility_id,omitempty" jsonschema:"CS1 or CS2"`
	AreaID     string `json:"area_id,omitempty" jsonschema:"observed examination area identifier"`
	Specialty  string `json:"specialty,omitempty" jsonschema:"observed specialty name"`
}

type DoctorsInput struct {
	PageInput
	FacilityID string `json:"facility_id,omitempty" jsonschema:"CS1 or CS2"`
	Area       string `json:"area,omitempty" jsonschema:"observed area or specialty text"`
	Credential string `json:"credential,omitempty" jsonschema:"normalized credential such as TS.BS or BSCKII"`
}

type DoctorInput struct {
	StaffID string `json:"staff_id" jsonschema:"real staff identifier from the curated dataset, for example NV005"`
}

type ScheduleInput struct {
	Date       string `json:"date,omitempty" jsonschema:"schedule date in YYYY-MM-DD format"`
	StaffID    string `json:"staff_id,omitempty" jsonschema:"doctor staff identifier"`
	FacilityID string `json:"facility_id,omitempty" jsonschema:"CS1 or CS2"`
	AreaID     string `json:"area_id,omitempty" jsonschema:"examination area identifier"`
	RoomID     string `json:"room_id,omitempty" jsonschema:"room or service-room identifier"`
	ShiftCode  string `json:"shift_code,omitempty" jsonschema:"FULL_DAY, AM, or PM"`
}

type RulesInput struct {
	PageInput
	Group      string `json:"group,omitempty" jsonschema:"rule group in Vietnamese"`
	Level      string `json:"level,omitempty" jsonschema:"Hard or Soft"`
	Confidence string `json:"confidence,omitempty" jsonschema:"Cao or Trung bình"`
}

type PatternsInput struct {
	PageInput
	AreaID      string `json:"area_id,omitempty" jsonschema:"area identifier"`
	RoomOrScope string `json:"room_or_scope,omitempty" jsonschema:"room identifier or area scope"`
	PatternType string `json:"pattern_type,omitempty" jsonschema:"observed pattern type"`
	Confidence  string `json:"confidence,omitempty" jsonschema:"Cao or Trung bình"`
	StaffID     string `json:"staff_id,omitempty" jsonschema:"doctor staff identifier"`
}

var (
	HospitalInfoHealthTool = mcp_sdk.Tool{Name: "hospitalInfoHealth", Description: "Kiểm tra API dữ liệu công khai Bệnh viện Tim Hà Nội và trạng thái lịch tuần."}
	HospitalMetaTool       = mcp_sdk.Tool{Name: "getHospitalDatasetMeta", Description: "Lấy nguồn, phạm vi, giới hạn và số lượng dữ liệu đã số hóa."}
	SearchDirectoryTool    = mcp_sdk.Tool{Name: "searchHospitalDirectory", Description: "Tìm đồng thời bác sĩ, phòng, đơn vị, quy tắc và mẫu phân công; hỗ trợ tìm tiếng Việt không dấu."}
	FacilitiesTool         = mcp_sdk.Tool{Name: "listHospitalFacilities", Description: "Liệt kê hai cơ sở Bệnh viện Tim Hà Nội và các khu khám quan sát được."}
	OrganizationTool       = mcp_sdk.Tool{Name: "getHospitalOrganization", Description: "Tra cứu sơ đồ bộ máy, khối, trung tâm, khoa, phòng và đơn nguyên."}
	RoomsTool              = mcp_sdk.Tool{Name: "listHospitalRooms", Description: "Tra cứu phòng/service-room, khu khám, chuyên khoa, giờ mở cửa và mẫu cuối tuần."}
	DoctorsTool            = mcp_sdk.Tool{Name: "searchHanoiHeartDoctors", Description: "Tra cứu 60 bác sĩ thật theo tên, cơ sở quan sát, khu và chức danh."}
	DoctorTool             = mcp_sdk.Tool{Name: "getHanoiHeartDoctor", Description: "Lấy thông tin công khai và mẫu phân công quan sát của một bác sĩ."}
	CurrentScheduleTool    = mcp_sdk.Tool{Name: "listCurrentDoctorSchedule", Description: "Tra cứu phân công trong lịch tuần hiện hành đã được công bố; không lưu lịch sử."}
	DoctorAvailabilityTool = mcp_sdk.Tool{Name: "getDoctorAvailability", Description: "Tra cứu cửa sổ bác sĩ được phân công làm việc từ lịch tuần hiện hành; không phải slot đặt lịch."}
	SchedulingRulesTool    = mcp_sdk.Tool{Name: "getSchedulingRules", Description: "Tra cứu các quy tắc Hard/Soft dùng khi xếp lịch."}
	AssignmentPatternsTool = mcp_sdk.Tool{Name: "getObservedAssignmentPatterns", Description: "Tra cứu mẫu phân công quan sát từ workbook, kèm độ tin cậy và ngoại lệ."}
	DataDictionaryTool     = mcp_sdk.Tool{Name: "getScheduleDataDictionary", Description: "Tra cứu ý nghĩa và quy định của các trường lịch."}
	SourceRegistryTool     = mcp_sdk.Tool{Name: "getScheduleSourceRegistry", Description: "Tra cứu ảnh nguồn, tuần quan sát, bản trùng và ghi chú cần xác minh."}
)

func HospitalInfoHealthHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callHospitalInfo(ctx, "/health", nil)
}

func HospitalMetaHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callHospitalInfo(ctx, "/api/v1/meta", nil)
}

func SearchDirectoryHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input SearchDirectoryInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := url.Values{"q": {input.Query}}
	if len(input.Types) > 0 {
		query.Set("types", strings.Join(input.Types, ","))
	}
	return callHospitalInfo(ctx, "/api/v1/search", query)
}

func FacilitiesHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, _ EmptyInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callHospitalInfo(ctx, "/api/v1/facilities", nil)
}

func OrganizationHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input OrganizationInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := pageQuery(input.PageInput)
	setIf(query, "block", input.Block)
	setIf(query, "parent_id", input.ParentID)
	setIf(query, "unit_type", input.UnitType)
	return callHospitalInfo(ctx, "/api/v1/organization", query)
}

func RoomsHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input RoomsInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := pageQuery(input.PageInput)
	setIf(query, "facility_id", input.FacilityID)
	setIf(query, "area_id", input.AreaID)
	setIf(query, "specialty", input.Specialty)
	return callHospitalInfo(ctx, "/api/v1/rooms", query)
}

func DoctorsHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input DoctorsInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := pageQuery(input.PageInput)
	setIf(query, "observed_facilities", input.FacilityID)
	setIf(query, "observed_areas", input.Area)
	setIf(query, "credential_normalized", input.Credential)
	return callHospitalInfo(ctx, "/api/v1/doctors", query)
}

func DoctorHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input DoctorInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callHospitalInfo(ctx, "/api/v1/doctors/"+url.PathEscape(input.StaffID), nil)
}

func CurrentScheduleHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input ScheduleInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := scheduleQuery(input)
	if input.Date != "" {
		query.Set("schedule_date", input.Date)
	}
	return callHospitalInfo(ctx, "/api/v1/schedules", query)
}

func DoctorAvailabilityHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input ScheduleInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := scheduleQuery(input)
	setIf(query, "date", input.Date)
	return callHospitalInfo(ctx, "/api/v1/availability", query)
}

func SchedulingRulesHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input RulesInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := pageQuery(input.PageInput)
	setIf(query, "group", input.Group)
	setIf(query, "level", input.Level)
	setIf(query, "confidence", input.Confidence)
	return callHospitalInfo(ctx, "/api/v1/scheduling/rules", query)
}

func AssignmentPatternsHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input PatternsInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	query := pageQuery(input.PageInput)
	setIf(query, "area_id", input.AreaID)
	setIf(query, "room_or_scope", input.RoomOrScope)
	setIf(query, "pattern_type", input.PatternType)
	setIf(query, "confidence", input.Confidence)
	setIf(query, "staff_id", input.StaffID)
	return callHospitalInfo(ctx, "/api/v1/scheduling/patterns", query)
}

func DataDictionaryHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input PageInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callHospitalInfo(ctx, "/api/v1/data-dictionary", pageQuery(input))
}

func SourceRegistryHandler(ctx context.Context, _ *mcp_sdk.CallToolRequest, input PageInput) (*mcp_sdk.CallToolResult, APIOutput, error) {
	return callHospitalInfo(ctx, "/api/v1/source-registry", pageQuery(input))
}

func pageQuery(input PageInput) url.Values {
	query := url.Values{}
	setIf(query, "q", input.Query)
	if input.Limit > 0 {
		query.Set("limit", strconv.Itoa(input.Limit))
	}
	if input.Offset > 0 {
		query.Set("offset", strconv.Itoa(input.Offset))
	}
	return query
}

func scheduleQuery(input ScheduleInput) url.Values {
	query := url.Values{}
	setIf(query, "staff_id", input.StaffID)
	setIf(query, "facility_id", input.FacilityID)
	setIf(query, "area_id", input.AreaID)
	setIf(query, "room_id", input.RoomID)
	setIf(query, "shift_code", input.ShiftCode)
	return query
}

func setIf(query url.Values, key, value string) {
	if strings.TrimSpace(value) != "" {
		query.Set(key, value)
	}
}

func callHospitalInfo(ctx context.Context, path string, query url.Values) (*mcp_sdk.CallToolResult, APIOutput, error) {
	baseURL := strings.TrimRight(os.Getenv("HOSPITAL_INFO_SERVICE_URL"), "/")
	if baseURL == "" {
		baseURL = defaultHospitalInfoServiceURL
	}
	endpoint := baseURL + path
	if len(query) > 0 {
		endpoint += "?" + query.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, APIOutput{}, fmt.Errorf("create hospital-info request: %w", err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, APIOutput{}, fmt.Errorf("call hospital-info-service: %w", err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, APIOutput{}, fmt.Errorf("read hospital-info response: %w", err)
	}
	var result any
	if len(bytes.TrimSpace(body)) > 0 {
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, APIOutput{}, fmt.Errorf("decode hospital-info response: %w", err)
		}
	}
	return nil, APIOutput{Status: resp.StatusCode, Body: result}, nil
}

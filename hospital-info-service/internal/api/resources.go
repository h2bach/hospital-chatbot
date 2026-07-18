package api

import (
	"fmt"
	"net/http"
	"strings"

	"hospital-info-service/internal/data"
)

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	schedule, err := s.store.CurrentSchedule()
	status := "ok"
	if err != nil {
		status = "degraded"
	}
	writeJSON(w, map[string]any{
		"status":          status,
		"service":         "hanoi-heart-hospital-public-info",
		"data_nature":     "real-observed data served by a local mock API",
		"schedule_status": schedule.PublishedStatus,
	}, http.StatusOK)
}

func (s *Server) metadata(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, map[string]any{"data": s.store.Meta}, http.StatusOK)
}

func (s *Server) facilities(w http.ResponseWriter, _ *http.Request) {
	result := make([]data.Record, 0, len(s.store.Facilities))
	for _, facility := range s.store.Facilities {
		copy := clone(facility)
		areas := map[string]string{}
		roomCount := 0
		for _, room := range s.store.Rooms {
			if fmt.Sprint(room["facility_id"]) == fmt.Sprint(facility["facility_id"]) {
				roomCount++
				areas[fmt.Sprint(room["area_id"])] = fmt.Sprint(room["area_name"])
			}
		}
		copy["room_count"] = roomCount
		copy["areas"] = areas
		result = append(result, copy)
	}
	writeJSON(w, map[string]any{"data": result, "total": len(result)}, http.StatusOK)
}

func (s *Server) facility(w http.ResponseWriter, r *http.Request) {
	record, ok := data.Find(s.store.Facilities, "facility_id", r.PathValue("id"))
	if !ok {
		writeError(w, http.StatusNotFound, "FACILITY_NOT_FOUND", "Không tìm thấy cơ sở")
		return
	}
	rooms := filter(s.store.Rooms, map[string]string{"facility_id": r.PathValue("id")}, "")
	writeJSON(w, map[string]any{"data": record, "rooms": rooms, "room_total": len(rooms)}, http.StatusOK)
}

func (s *Server) organization(w http.ResponseWriter, r *http.Request) {
	filters := queryFilters(r, "block", "parent_id", "unit_type")
	rows := filter(s.store.Units, filters, r.URL.Query().Get("q"))
	s.writePage(w, r, rows)
}

func (s *Server) rooms(w http.ResponseWriter, r *http.Request) {
	filters := queryFilters(r, "facility_id", "area_id", "specialty")
	rows := filter(s.store.Rooms, filters, r.URL.Query().Get("q"))
	s.writePage(w, r, rows)
}

func (s *Server) room(w http.ResponseWriter, r *http.Request) {
	record, ok := data.Find(s.store.Rooms, "room_id", r.PathValue("id"))
	if !ok {
		writeError(w, http.StatusNotFound, "ROOM_NOT_FOUND", "Không tìm thấy phòng khám")
		return
	}
	writeJSON(w, map[string]any{"data": record}, http.StatusOK)
}

func (s *Server) doctors(w http.ResponseWriter, r *http.Request) {
	filters := queryFilters(r, "staff_id", "credential_normalized", "observed_facilities", "observed_areas")
	rows := filter(s.store.Doctors, filters, r.URL.Query().Get("q"))
	s.writePage(w, r, rows)
}

func (s *Server) doctor(w http.ResponseWriter, r *http.Request) {
	record, ok := data.Find(s.store.Doctors, "staff_id", r.PathValue("id"))
	if !ok {
		writeError(w, http.StatusNotFound, "DOCTOR_NOT_FOUND", "Không tìm thấy bác sĩ")
		return
	}
	patterns := filter(s.store.Patterns, map[string]string{"staff_id": r.PathValue("id")}, "")
	writeJSON(w, map[string]any{"data": record, "observed_assignment_patterns": patterns}, http.StatusOK)
}

func (s *Server) schedulingRules(w http.ResponseWriter, r *http.Request) {
	rows := filter(s.store.Rules, queryFilters(r, "rule_id", "group", "level", "confidence"), r.URL.Query().Get("q"))
	s.writePage(w, r, rows)
}

func (s *Server) assignmentPatterns(w http.ResponseWriter, r *http.Request) {
	rows := filter(s.store.Patterns, queryFilters(r, "pattern_id", "area_id", "room_or_scope", "pattern_type", "confidence", "staff_id"), r.URL.Query().Get("q"))
	s.writePage(w, r, rows)
}

func (s *Server) dataDictionary(w http.ResponseWriter, r *http.Request) {
	rows := filter(s.store.Dictionary, queryFilters(r, "field", "type"), r.URL.Query().Get("q"))
	s.writePage(w, r, rows)
}

func (s *Server) sourceRegistry(w http.ResponseWriter, r *http.Request) {
	rows := filter(s.store.Sources, queryFilters(r, "source_id", "facility_id", "status"), r.URL.Query().Get("q"))
	s.writePage(w, r, rows)
}

func (s *Server) schedules(w http.ResponseWriter, r *http.Request) {
	schedule, err := s.store.CurrentSchedule()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "SCHEDULE_READ_ERROR", "Không đọc được lịch tuần hiện hành")
		return
	}
	rows := []data.Record{}
	if schedule.PublishedStatus == "PUBLISHED" {
		rows = filter(schedule.Assignments, queryFilters(r, "week_start", "schedule_date", "facility_id", "area_id", "room_id", "staff_id", "shift_code", "assignment_status"), "")
	}
	writeJSON(w, map[string]any{
		"data":     rows,
		"total":    len(rows),
		"schedule": scheduleInfo(schedule),
		"notice":   scheduleNotice(schedule),
	}, http.StatusOK)
}

func (s *Server) doctorSchedule(w http.ResponseWriter, r *http.Request) {
	if _, ok := data.Find(s.store.Doctors, "staff_id", r.PathValue("id")); !ok {
		writeError(w, http.StatusNotFound, "DOCTOR_NOT_FOUND", "Không tìm thấy bác sĩ")
		return
	}
	query := r.URL.Query()
	query.Set("staff_id", r.PathValue("id"))
	r.URL.RawQuery = query.Encode()
	s.schedules(w, r)
}

func (s *Server) availability(w http.ResponseWriter, r *http.Request) {
	schedule, err := s.store.CurrentSchedule()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "SCHEDULE_READ_ERROR", "Không đọc được lịch tuần hiện hành")
		return
	}
	if schedule.PublishedStatus != "PUBLISHED" {
		writeJSON(w, map[string]any{
			"data": []any{}, "total": 0, "state": "NO_PUBLISHED_SCHEDULE",
			"schedule": scheduleInfo(schedule), "notice": scheduleNotice(schedule),
		}, http.StatusOK)
		return
	}
	filters := queryFilters(r, "schedule_date", "facility_id", "area_id", "room_id", "staff_id", "shift_code")
	if date := r.URL.Query().Get("date"); date != "" {
		filters["schedule_date"] = date
	}
	rows := filter(schedule.Assignments, filters, "")
	result := make([]data.Record, 0, len(rows))
	for _, row := range rows {
		status := fmt.Sprint(row["assignment_status"])
		if status != "WORKING" && status != "AREA_DUTY" {
			continue
		}
		item := clone(row)
		item["is_scheduled_available"] = true
		item["availability_basis"] = "PUBLISHED_WEEKLY_SCHEDULE"
		item["booking_slot_confirmed"] = false
		if doctor, ok := data.Find(s.store.Doctors, "staff_id", fmt.Sprint(row["staff_id"])); ok {
			item["doctor"] = doctor
		}
		if room, ok := data.Find(s.store.Rooms, "room_id", fmt.Sprint(row["room_id"])); ok {
			item["room"] = room
		}
		result = append(result, item)
	}
	writeJSON(w, map[string]any{
		"data": result, "total": len(result), "state": "PUBLISHED_SCHEDULE_LOADED",
		"schedule": scheduleInfo(schedule),
		"notice":   "Đây là cửa sổ bác sĩ được phân công làm việc, không phải slot đặt lịch đã được bệnh viện xác nhận.",
	}, http.StatusOK)
}

func (s *Server) search(w http.ResponseWriter, r *http.Request) {
	q := strings.TrimSpace(r.URL.Query().Get("q"))
	if q == "" {
		writeError(w, http.StatusBadRequest, "MISSING_QUERY", "Cần tham số q")
		return
	}
	types := map[string]bool{}
	for _, item := range strings.Split(r.URL.Query().Get("types"), ",") {
		if item = strings.TrimSpace(item); item != "" {
			types[item] = true
		}
	}
	if len(types) == 0 {
		for _, name := range []string{"doctors", "rooms", "organization", "rules", "patterns"} {
			types[name] = true
		}
	}
	collections := map[string][]data.Record{
		"doctors": s.store.Doctors, "rooms": s.store.Rooms, "organization": s.store.Units,
		"rules": s.store.Rules, "patterns": s.store.Patterns,
	}
	result := make([]data.Record, 0)
	for _, name := range []string{"doctors", "rooms", "organization", "rules", "patterns"} {
		if !types[name] {
			continue
		}
		for _, record := range filter(collections[name], nil, q) {
			item := clone(record)
			item["entity_type"] = name
			result = append(result, item)
		}
	}
	if len(result) > 100 {
		result = result[:100]
	}
	writeJSON(w, map[string]any{"data": result, "total": len(result), "query": q}, http.StatusOK)
}

func (s *Server) writePage(w http.ResponseWriter, r *http.Request, rows []data.Record) {
	limit, offset, err := pagination(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_PAGINATION", err.Error())
		return
	}
	writeJSON(w, map[string]any{
		"data":       page(rows, offset, limit),
		"pagination": map[string]int{"limit": limit, "offset": offset, "total": len(rows)},
	}, http.StatusOK)
}

func filter(records []data.Record, filters map[string]string, query string) []data.Record {
	result := make([]data.Record, 0)
	query = fold(query)
	for _, record := range records {
		matched := true
		for key, expected := range filters {
			if expected == "" {
				continue
			}
			actual, exists := record[key]
			if !exists || !valueMatches(actual, expected) {
				matched = false
				break
			}
		}
		if matched && (query == "" || strings.Contains(searchable(record), query)) {
			result = append(result, record)
		}
	}
	return result
}

func valueMatches(actual any, expected string) bool {
	wanted := fold(expected)
	switch value := actual.(type) {
	case []any:
		for _, item := range value {
			if fold(fmt.Sprint(item)) == wanted || strings.Contains(fold(fmt.Sprint(item)), wanted) {
				return true
			}
		}
		return false
	default:
		return fold(fmt.Sprint(value)) == wanted || strings.Contains(fold(fmt.Sprint(value)), wanted)
	}
}

func queryFilters(r *http.Request, keys ...string) map[string]string {
	filters := make(map[string]string, len(keys))
	for _, key := range keys {
		if value := r.URL.Query().Get(key); value != "" {
			filters[key] = value
		}
	}
	return filters
}

func clone(record data.Record) data.Record {
	copy := make(data.Record, len(record))
	for key, value := range record {
		copy[key] = value
	}
	return copy
}

func scheduleInfo(schedule data.Schedule) map[string]any {
	return map[string]any{
		"week_start": schedule.WeekStart, "week_end": schedule.WeekEnd,
		"published_status": schedule.PublishedStatus, "source_version": schedule.SourceVersion,
		"imported_at": schedule.ImportedAt,
	}
}

func scheduleNotice(schedule data.Schedule) string {
	if schedule.PublishedStatus != "PUBLISHED" {
		return "Chưa có lịch tuần đã công bố. Hãy dùng scripts/schedule_manager.py để nhập lịch tuần kế tiếp."
	}
	return "Lịch tuần hiện hành được nạp từ current_schedule.json; hệ thống không lưu lịch sử các tuần trước."
}

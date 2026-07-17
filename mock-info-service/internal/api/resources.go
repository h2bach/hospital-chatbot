package api

import (
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"mock-info-service/internal/store"
)

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, map[string]any{"status":"ok","service":"mock-info-service","collections":len(s.store.CollectionNames())}, http.StatusOK)
}

func (s *Server) collections(w http.ResponseWriter, _ *http.Request) {
	items:=make([]map[string]any,0); for _,name:=range s.store.CollectionNames() { items=append(items,map[string]any{"name":name,"count":s.store.Count(name)}) }
	writeJSON(w,map[string]any{"data":items},http.StatusOK)
}

func (s *Server) collectionResource(w http.ResponseWriter, r *http.Request) {
	parts:=pathParts(strings.TrimPrefix(r.URL.Path,"/api/v1/data/")); if len(parts)<1 || len(parts)>2 { writeError(w,404,"NOT_FOUND","Resource không tồn tại"); return }
	collection:=parts[0]
	if len(parts)==1 {
		switch r.Method {
		case http.MethodGet: s.listCollection(w,r,collection)
		case http.MethodPost: var row store.Record; if readJSON(w,r,&row) { created,err:=s.store.Create(collection,row); if err!=nil { s.storeError(w,err); return }; writeJSON(w,map[string]any{"data":created},201) }
		default: writeError(w,405,"METHOD_NOT_ALLOWED","Phương thức không hỗ trợ")
		}; return
	}
	id:=parts[1]
	switch r.Method {
	case http.MethodGet: row,err:=s.store.Get(collection,id); if err!=nil { s.storeError(w,err); return }; writeJSON(w,map[string]any{"data":row},200)
	case http.MethodPatch: var patch store.Record; if readJSON(w,r,&patch) { row,err:=s.store.Update(collection,id,patch); if err!=nil { s.storeError(w,err); return }; writeJSON(w,map[string]any{"data":row},200) }
	case http.MethodDelete: if err:=s.store.Delete(collection,id); err!=nil { s.storeError(w,err); return }; w.WriteHeader(204)
	default: writeError(w,405,"METHOD_NOT_ALLOWED","Phương thức không hỗ trợ")
	}
}

func (s *Server) listCollection(w http.ResponseWriter,r *http.Request,collection string) {
	limit,offset,err:=pagination(r); if err!=nil { writeError(w,400,"INVALID_PAGINATION",err.Error()); return }
	filters:=map[string]string{}; for key,values:=range r.URL.Query() { if strings.HasPrefix(key,"filter[") && strings.HasSuffix(key,"]") { filters[strings.TrimSuffix(strings.TrimPrefix(key,"filter["),"]")]=values[0] } }
	rows,total,err:=s.store.List(collection,offset,limit,filters); if err!=nil { s.storeError(w,err); return }
	writeJSON(w,map[string]any{"data":rows,"pagination":map[string]int{"limit":limit,"offset":offset,"total":total}},200)
}

func (s *Server) storeError(w http.ResponseWriter,err error) {
	switch { case errors.Is(err,store.ErrNotFound): writeError(w,404,"NOT_FOUND","Không tìm thấy dữ liệu"); case errors.Is(err,store.ErrConflict): writeError(w,409,"CONFLICT","Dữ liệu đã tồn tại"); default: writeError(w,400,"INVALID_RECORD",err.Error()) }
}

func (s *Server) search(w http.ResponseWriter,r *http.Request) {
	collection:=r.URL.Query().Get("collection"); q:=strings.ToLower(strings.TrimSpace(r.URL.Query().Get("q"))); if collection==""||q=="" { writeError(w,400,"MISSING_QUERY","Cần collection và q"); return }
	rows,_,err:=s.store.List(collection,0,500,map[string]string{}); if err!=nil { s.storeError(w,err); return }; result:=make([]store.Record,0)
	for _,row:=range rows { if strings.Contains(strings.ToLower(fmt.Sprint(row)),q) { result=append(result,row); if len(result)==50 { break } } }
	writeJSON(w,map[string]any{"data":result,"total":len(result)},200)
}

func (s *Server) availableSlots(w http.ResponseWriter,r *http.Request) {
	date:=r.URL.Query().Get("date"); doctor:=r.URL.Query().Get("doctor_id"); facility:=r.URL.Query().Get("facility_id")
	schedules,_,_:=s.store.List("doctor_schedules",0,500,map[string]string{}); allowed:=map[string]bool{}
	for _,sch:=range schedules { if date!=""&&fmt.Sprint(sch["schedule_date"])!=date { continue }; if doctor!=""&&fmt.Sprint(sch["doctor_id"])!=doctor { continue }; if facility!=""&&fmt.Sprint(sch["facility_id"])!=facility { continue }; allowed[fmt.Sprint(sch["schedule_id"])]=true }
	slots,_,_:=s.store.List("appointment_slots",0,500,map[string]string{"slot_status":"AVAILABLE"}); result:=make([]store.Record,0)
	for _,slot:=range slots { if allowed[fmt.Sprint(slot["schedule_id"])] { result=append(result,slot) } }
	writeJSON(w,map[string]any{"data":result,"total":len(result)},200)
}

type appointmentRequest struct { PatientID string `json:"patient_id"`; SlotID string `json:"slot_id"`; Reason string `json:"reason_for_visit"`; Confirmed bool `json:"confirmed"` }

func (s *Server) createAppointment(w http.ResponseWriter,r *http.Request) {
	key:=r.Header.Get("Idempotency-Key"); if key=="" { writeError(w,400,"IDEMPOTENCY_KEY_REQUIRED","Cần header Idempotency-Key"); return }
	var input appointmentRequest; if !readJSON(w,r,&input) { return }; if !input.Confirmed { writeError(w,422,"CONFIRMATION_REQUIRED","Phải xác nhận trước khi tạo lịch"); return }
	record,replayed,err:=s.store.Idempotent(key,func()(store.Record,error){
		if _,err:=s.store.Get("patients",input.PatientID); err!=nil { return nil,fmt.Errorf("patient không tồn tại") }; slot,err:=s.store.Get("appointment_slots",input.SlotID); if err!=nil { return nil,fmt.Errorf("slot không tồn tại") }; if slot["slot_status"]!="AVAILABLE" { return nil,store.ErrConflict }
		sch,err:=s.store.Get("doctor_schedules",fmt.Sprint(slot["schedule_id"])); if err!=nil{return nil,err}; existing:=s.store.Count("appointments")+1; id:=fmt.Sprintf("APT-API-%06d",existing)
		services,_:=sch["service_ids"].([]any); serviceID:=""; if len(services)>0 { serviceID=fmt.Sprint(services[0]) }
		row:=store.Record{"appointment_id":id,"appointment_code":fmt.Sprintf("LHAPI%07d",existing),"patient_id":input.PatientID,"facility_id":sch["facility_id"],"department_id":sch["department_id"],"service_id":serviceID,"doctor_id":sch["doctor_id"],"slot_id":input.SlotID,"appointment_datetime":slot["start_datetime"],"consultation_mode":sch["consultation_mode"],"booking_channel":"REST_API","booking_source":"AI_AGENT","reason_for_visit":input.Reason,"priority_level":"NORMAL","appointment_status":"CONFIRMED","confirmation_status":"CONFIRMED","created_at":time.Now().Format(time.RFC3339),"mock_scenario":"API_TEST"}
		created,err:=s.store.Create("appointments",row); if err!=nil{return nil,err}; _,_ = s.store.Update("appointment_slots",input.SlotID,store.Record{"slot_status":"BOOKED","booked_count":1,"appointment_id":id}); return created,nil })
	if err!=nil { s.storeError(w,err); return }; writeJSON(w,map[string]any{"data":record,"idempotency_replayed":replayed},201)
}

func (s *Server) cancelAppointment(w http.ResponseWriter,r *http.Request) {
	id:=r.PathValue("id"); var input struct { Reason string `json:"reason"`; Confirmed bool `json:"confirmed"` }; if !readJSON(w,r,&input){return}; if !input.Confirmed||input.Reason=="" { writeError(w,422,"CONFIRMATION_REQUIRED","Cần xác nhận và lý do hủy"); return }
	row,err:=s.store.Get("appointments",id); if err!=nil{s.storeError(w,err);return}; if row["appointment_status"]=="CANCELLED" { writeJSON(w,map[string]any{"data":row,"idempotency_replayed":true},200);return }
	updated,err:=s.store.Update("appointments",id,store.Record{"appointment_status":"CANCELLED","cancellation_reason":input.Reason,"cancelled_at":time.Now().Format(time.RFC3339)}); if err!=nil{s.storeError(w,err);return}; if slot:=fmt.Sprint(row["slot_id"]); slot!="" { _,_=s.store.Update("appointment_slots",slot,store.Record{"slot_status":"AVAILABLE","booked_count":0,"appointment_id":nil}) }; writeJSON(w,map[string]any{"data":updated},200)
}

func (s *Server) verifyPatient(w http.ResponseWriter,r *http.Request) {
	patient,err:=s.store.Get("patients",r.PathValue("id")); if err!=nil{s.storeError(w,err);return}; var input struct { PatientCode string `json:"patient_code"`; DateOfBirth string `json:"date_of_birth"` }; if !readJSON(w,r,&input){return}
	verified:=fmt.Sprint(patient["patient_code"])==input.PatientCode&&fmt.Sprint(patient["date_of_birth"])==input.DateOfBirth; status:=200; if !verified { status=401 }; writeJSON(w,map[string]any{"verified":verified,"method":"PATIENT_CODE_AND_DATE_OF_BIRTH"},status)
}

package api

import "net/http"

func (s *Server) addRoutes() {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("GET /api/v1/meta", s.metadata)
	mux.HandleFunc("GET /api/v1/search", s.search)
	mux.HandleFunc("GET /api/v1/facilities", s.facilities)
	mux.HandleFunc("GET /api/v1/facilities/{id}", s.facility)
	mux.HandleFunc("GET /api/v1/organization", s.organization)
	mux.HandleFunc("GET /api/v1/rooms", s.rooms)
	mux.HandleFunc("GET /api/v1/rooms/{id}", s.room)
	mux.HandleFunc("GET /api/v1/doctors", s.doctors)
	mux.HandleFunc("GET /api/v1/doctors/{id}", s.doctor)
	mux.HandleFunc("GET /api/v1/doctors/{id}/schedule", s.doctorSchedule)
	mux.HandleFunc("GET /api/v1/schedules", s.schedules)
	mux.HandleFunc("GET /api/v1/availability", s.availability)
	mux.HandleFunc("GET /api/v1/scheduling/rules", s.schedulingRules)
	mux.HandleFunc("GET /api/v1/scheduling/patterns", s.assignmentPatterns)
	mux.HandleFunc("GET /api/v1/data-dictionary", s.dataDictionary)
	mux.HandleFunc("GET /api/v1/source-registry", s.sourceRegistry)
	s.httpServer.Handler = cors(requestID(recoverer(mux)))
}

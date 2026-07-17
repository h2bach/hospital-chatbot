package api

import (
	"net/http"
	"strings"
)

func (server *Server) addRoutes() {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", server.health)
	mux.HandleFunc("GET /api/v1/meta/collections", server.collections)
	mux.HandleFunc("GET /api/v1/search", server.search)
	mux.HandleFunc("GET /api/v1/knowledge/search", server.knowledgeSearch)
	mux.HandleFunc("GET /api/v1/hospital", server.hospital)
	mux.HandleFunc("GET /api/v1/hospital/hours", server.hospitalHours)
	mux.HandleFunc("GET /api/v1/hospital/emergency", server.hospitalEmergency)
	mux.HandleFunc("GET /api/v1/doctors", server.doctors)
	mux.HandleFunc("GET /api/v1/doctors/{id}/schedules", server.doctorSchedules)
	mux.HandleFunc("GET /api/v1/departments", server.departments)
	mux.HandleFunc("GET /api/v1/services", server.services)
	mux.HandleFunc("GET /api/v1/services/{id}", server.service)
	mux.HandleFunc("GET /api/v1/services/{id}/prices", server.servicePrices)
	mux.HandleFunc("GET /api/v1/booking-links", server.bookingLinks)
	mux.HandleFunc("GET /api/v1/available-slots", server.availableSlots)
	mux.HandleFunc("POST /api/v1/appointments", server.createAppointment)
	mux.HandleFunc("PATCH /api/v1/appointments/{id}/cancel", server.cancelAppointment)
	mux.HandleFunc("POST /api/v1/patients/{id}/verify", server.verifyPatient)
	mux.HandleFunc("/api/v1/data/", server.collectionResource)
	server.httpServer.Handler = cors(requestID(recoverer(mux)))
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-Request-ID, Idempotency-Key")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func requestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-ID")
		if id == "" {
			id = "mock-" + strings.ReplaceAll(r.RemoteAddr, ":", "-")
		}
		w.Header().Set("X-Request-ID", id)
		next.ServeHTTP(w, r)
	})
}

func recoverer(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if recover() != nil {
				writeError(w, 500, "INTERNAL_ERROR", "Lỗi nội bộ")
			}
		}()
		next.ServeHTTP(w, r)
	})
}

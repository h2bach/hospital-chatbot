package api

import (
	"agent/internal/agent"
	"agent/internal/api/dto"
	"agent/internal/domain"
	"agent/internal/rag"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

func (svr *Server) Health(w http.ResponseWriter, r *http.Request) {
	status := http.StatusOK
	ragStatus, mcpStatus := "ok", "ok"
	mcpToolCount := 0
	capabilities := map[string]string{
		"knowledge": "unavailable", "directory": "unavailable",
		"schedule": "unavailable", "source_metadata": "unavailable",
	}
	if svr.agent == nil || svr.agent.LLM == nil || svr.agent.Retriever == nil {
		status, ragStatus = http.StatusServiceUnavailable, "not_configured"
	} else if checker, ok := svr.agent.Retriever.(rag.HealthChecker); ok {
		ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cancel()
		if err := checker.Health(ctx); err != nil {
			status, ragStatus = http.StatusServiceUnavailable, "unavailable"
		}
	}
	if svr.agent == nil || svr.agent.MCPClient == nil {
		status, mcpStatus = http.StatusServiceUnavailable, "not_configured"
	} else {
		ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cancel()
		tools, err := svr.agent.MCPClient.Tools(ctx)
		if err != nil || len(tools) == 0 {
			status, mcpStatus = http.StatusServiceUnavailable, "unavailable"
		} else {
			mcpToolCount = len(tools)
			names := make(map[string]bool, len(tools))
			for _, tool := range tools {
				names[tool.Name] = true
			}
			if names["searchHospitalKnowledge"] {
				capabilities["knowledge"] = "ok"
			}
			if names["searchHospitalDirectory"] && names["listHospitalFacilities"] {
				capabilities["directory"] = "ok"
			}
			if names["listCurrentDoctorSchedule"] && names["getDoctorAvailability"] {
				capabilities["schedule"] = "ok"
			}
			if names["getHospitalKnowledgeCatalog"] && names["getScheduleSourceRegistry"] {
				capabilities["source_metadata"] = "ok"
			}
			for _, value := range capabilities {
				if value != "ok" {
					status, mcpStatus = http.StatusServiceUnavailable, "degraded"
					break
				}
			}
		}
	}
	writeJSON(w, map[string]any{
		"status":  map[bool]string{true: "ok", false: "unavailable"}[status == http.StatusOK],
		"service": "heartcare-ai-agent", "provider": "fpt", "rag": ragStatus,
		"mcp": mcpStatus, "mcp_tool_count": mcpToolCount, "mcp_capabilities": capabilities,
		"orchestrator_mode": orchestratorMode(), "port": 6689,
	}, status)
}

func orchestratorMode() string {
	mode := strings.ToLower(strings.TrimSpace(os.Getenv("ORCHESTRATOR_MODE")))
	if mode == "" {
		return "legacy"
	}
	return mode
}

func readJSON(w http.ResponseWriter, r *http.Request, v any) bool {
	err := json.NewDecoder(r.Body).Decode(v)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, v any, status int) bool {
	bytes := new(bytes.Buffer)
	err := json.NewEncoder(bytes).Encode(v)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		return false
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	w.Write(bytes.Bytes())
	return true
}

func getDeviceID(r *http.Request) string {
	id := r.Header.Get("X-Device-ID")
	if id == "" {
		id = r.URL.Query().Get("device_id")
	}
	return id
}

func (svr *Server) getOwnedSession(r *http.Request, sessionID string) (domain.Session, error) {
	session, err := svr.sessionStore.GetByID(sessionID)
	if err != nil {
		return domain.Session{}, err
	}
	deviceID := getDeviceID(r)
	if session.OwnerID != "" && session.OwnerID != deviceID {
		return domain.Session{}, fmt.Errorf("session is not available for this device")
	}
	return session, nil
}

func (svr *Server) GetAllSessions(w http.ResponseWriter, r *http.Request) {
	deviceID := getDeviceID(r)
	sessions := svr.sessionStore.GetAllForOwner(deviceID)
	resp := dto.NewGetAllSessionsResponse(sessions)
	writeJSON(w, resp, http.StatusOK)
}

func (svr *Server) GetSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	session, err := svr.getOwnedSession(r, sessionID)
	if err != nil {
		errorResponse := dto.NewErrorResponse(err.Error())
		writeJSON(w, errorResponse, http.StatusBadRequest)
		return
	}

	resp := dto.NewGetSessionReponse(session)
	writeJSON(w, resp, http.StatusOK)
}

func (svr *Server) PostMessage(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	var req dto.PostMessageRequest
	if !readJSON(w, r, &req) {
		return
	}
	images, err := req.DomainImages()
	if err != nil {
		writeJSON(w, dto.NewErrorResponse(err.Error()), http.StatusBadRequest)
		return
	}

	session, err := svr.getOwnedSession(r, sessionID)
	if err != nil {
		errorResponse := dto.NewErrorResponse(err.Error())
		writeJSON(w, errorResponse, http.StatusBadRequest)
		return
	}
	agentResponse, err := svr.agent.CallDetailedWithImages(r.Context(), req.Message, images, &session.Context)
	if err != nil {
		log.Printf("agent request failed session=%s: %v", sessionID, err)
		userFacingError := StandardizeModelError(err)
		writeJSON(w, dto.NewErrorResponse(userFacingError), http.StatusInternalServerError)
		return
	}
	err = svr.sessionStore.Save(session)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: Cannot save session\n")
	}
	startSessionTitle(svr, &session, req.Message)
	resp := dto.NewPostMessageResponse(agentResponse)
	writeJSON(w, resp, http.StatusOK)
}

// PostMessageStream emits status immediately, but answer text only after the
// mandatory evaluator has accepted it. Images use the same VLM extraction and
// grounded workflow as the JSON endpoint.
func (svr *Server) PostMessageStream(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeJSON(w, dto.NewErrorResponse("Streaming không được hỗ trợ bởi máy chủ."), http.StatusInternalServerError)
		return
	}
	sessionID := r.PathValue("id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		return
	}
	var req dto.PostMessageRequest
	if !readJSON(w, r, &req) {
		return
	}
	images, err := req.DomainImages()
	if err != nil {
		writeJSON(w, dto.NewErrorResponse(err.Error()), http.StatusBadRequest)
		return
	}
	session, err := svr.getOwnedSession(r, sessionID)
	if err != nil {
		writeJSON(w, dto.NewErrorResponse(err.Error()), http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache, no-transform")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	writeSSE(w, flusher, "status", agent.ProgressEvent{Phase: "accepted", Label: "Đã nhận câu hỏi"})
	reporter := func(event agent.ProgressEvent) { writeSSE(w, flusher, "status", event) }

	result, err := svr.agent.CallDetailedWithImagesAndProgress(r.Context(), req.Message, images, &session.Context, reporter)
	if err != nil {
		log.Printf("stream agent request failed session=%s: %v", sessionID, err)
		writeSSE(w, flusher, "error", map[string]any{
			"code": "AGENT_UNAVAILABLE", "message": StandardizeModelError(err), "retryable": true,
		})
		return
	}
	if err := svr.sessionStore.Save(session); err != nil {
		log.Printf("save streamed session=%s: %v", sessionID, err)
	}
	startSessionTitle(svr, &session, req.Message)
	for _, chunk := range splitSSEText(result.Text, 160) {
		writeSSE(w, flusher, "delta", map[string]string{"text": chunk})
	}
	if len(result.Suggestions) > 0 {
		writeSSE(w, flusher, "suggestions", map[string]any{"items": result.Suggestions})
	}
	writeSSE(w, flusher, "complete", dto.NewPostMessageResponse(result))
}

func writeSSE(w http.ResponseWriter, flusher http.Flusher, event string, payload any) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return
	}
	fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event, encoded)
	flusher.Flush()
}

func splitSSEText(value string, size int) []string {
	characters := []rune(value)
	if size < 1 || len(characters) <= size {
		return []string{value}
	}
	result := make([]string, 0, (len(characters)+size-1)/size)
	for start := 0; start < len(characters); start += size {
		end := start + size
		if end > len(characters) {
			end = len(characters)
		}
		result = append(result, string(characters[start:end]))
	}
	return result
}

func startSessionTitle(svr *Server, session *domain.Session, userMessage string) {
	if session.Title != "" {
		return
	}
	sessionCopy := *session
	go func() {
		title, err := svr.agent.GenerateTitle(context.Background(), userMessage)
		if err != nil {
			return
		}
		sessionCopy.Title = title
		_ = svr.sessionStore.Save(sessionCopy)
	}()
}

func (svr *Server) PostNewSession(w http.ResponseWriter, r *http.Request) {
	deviceID := getDeviceID(r)
	sessionID, err := svr.sessionStore.CreateForOwner(deviceID)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		return
	}

	resp := dto.NewPostNewSessionResponse(sessionID)
	writeJSON(w, resp, http.StatusCreated)
}

func (svr *Server) DeleteSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	if _, err := svr.getOwnedSession(r, sessionID); err != nil {
		writeJSON(w, dto.NewErrorResponse(err.Error()), http.StatusBadRequest)
		return
	}
	svr.sessionStore.DeleteByID(sessionID)
	w.WriteHeader(http.StatusNoContent)
}

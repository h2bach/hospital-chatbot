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
	ragStatus := "ok"
	mcpStatus := "ok"
	mcpToolCount := 0
	capabilityStatus := map[string]string{
		"knowledge": "unavailable", "directory": "unavailable",
		"schedule": "unavailable", "source_metadata": "unavailable",
	}
	if svr.agent == nil || svr.agent.LLM == nil || svr.agent.Retriever == nil {
		status = http.StatusServiceUnavailable
		ragStatus = "not_configured"
	} else if checker, ok := svr.agent.Retriever.(rag.HealthChecker); ok {
		ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cancel()
		if err := checker.Health(ctx); err != nil {
			status = http.StatusServiceUnavailable
			ragStatus = "unavailable"
		}
	}
	if svr.agent == nil || svr.agent.MCPClient == nil {
		status = http.StatusServiceUnavailable
		mcpStatus = "not_configured"
	} else {
		ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cancel()
		tools, err := svr.agent.MCPClient.Tools(ctx)
		if err != nil || len(tools) == 0 {
			status = http.StatusServiceUnavailable
			mcpStatus = "unavailable"
		} else {
			mcpToolCount = len(tools)
			toolNames := make(map[string]bool, len(tools))
			for _, tool := range tools {
				toolNames[tool.Name] = true
			}
			if toolNames["searchHospitalKnowledge"] {
				capabilityStatus["knowledge"] = "ok"
			}
			if toolNames["searchHospitalDirectory"] && toolNames["listHospitalFacilities"] {
				capabilityStatus["directory"] = "ok"
			}
			if toolNames["listCurrentDoctorSchedule"] && toolNames["getDoctorAvailability"] {
				capabilityStatus["schedule"] = "ok"
			}
			if toolNames["getHospitalKnowledgeCatalog"] && toolNames["getScheduleSourceRegistry"] {
				capabilityStatus["source_metadata"] = "ok"
			}
			for _, capability := range capabilityStatus {
				if capability != "ok" {
					status = http.StatusServiceUnavailable
					mcpStatus = "degraded"
					break
				}
			}
		}
	}
	writeJSON(w, map[string]any{
		"status":            map[bool]string{true: "ok", false: "unavailable"}[status == http.StatusOK],
		"service":           "heartcare-ai-agent",
		"provider":          "fpt",
		"rag":               ragStatus,
		"mcp":               mcpStatus,
		"mcp_tool_count":    mcpToolCount,
		"mcp_capabilities":  capabilityStatus,
		"orchestrator_mode": orchestratorMode(),
		"port":              6689,
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

func (svr *Server) GetAllSessions(w http.ResponseWriter, r *http.Request) {
	sessions := svr.sessionStore.GetAll()
	resp := dto.NewGetAllSessionsResponse(sessions)
	writeJSON(w, resp, http.StatusOK)
}

func (svr *Server) GetSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	session, err := svr.sessionStore.GetByID(sessionID)
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

	session, err := svr.sessionStore.GetByID(sessionID)
	if err != nil {
		errorResponse := dto.NewErrorResponse(err.Error())
		writeJSON(w, errorResponse, http.StatusBadRequest)
		return
	}
	// Role is supplied by the authenticated gateway/client. Preserve the
	// session's access role when a later request omits the header.
	if rawRole := r.Header.Get("Role"); rawRole != "" {
		session.Context.Role = agent.NormalizeRole(rawRole)
		session.Context.UserRole = string(session.Context.Role)
	}

	// Extract user role from request headers or query parameters
	role := r.Header.Get("X-User-Role")
	if role == "" {
		role = r.Header.Get("X-Role")
	}
	if role == "" {
		role = r.URL.Query().Get("role")
	}
	if role != "" && r.Header.Get("Role") == "" {
		session.Context.Role = agent.NormalizeRole(role)
		session.Context.UserRole = string(session.Context.Role)
	}

	agentResponse, err := svr.agent.CallDetailed(r.Context(), req.Message, &session.Context)
	if err != nil {
		log.Printf("agent request failed session=%s role=%s: %v", sessionID, session.Context.Role, err)
		writeJSON(w, dto.NewErrorResponse("Trợ lý FPT hoặc kho tri thức hiện chưa sẵn sàng. Vui lòng thử lại."), http.StatusServiceUnavailable)
		return
	}
	err = svr.sessionStore.Save(session)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: Cannot save session\n")
	}
	if session.Title == "" {
		userMessage := req.Message
		go func() {
			sessionTitle, err := svr.agent.GenerateTitle(context.Background(), userMessage)
			if err != nil {
				return
			}
			session.Title = sessionTitle
			svr.sessionStore.Save(session)
		}()
	}
	resp := dto.NewPostMessageResponse(agentResponse)
	writeJSON(w, resp, http.StatusOK)
}

// PostMessageStream emits progress immediately, but only emits answer text
// after the mandatory evaluator has accepted it. This avoids leaking an
// ungrounded draft while still giving the UI responsive planning/tool status.
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
	session, err := svr.sessionStore.GetByID(sessionID)
	if err != nil {
		writeJSON(w, dto.NewErrorResponse(err.Error()), http.StatusBadRequest)
		return
	}
	applyRequestRole(r, &session.Context)

	w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache, no-transform")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	writeSSE(w, flusher, "status", agent.ProgressEvent{Phase: "accepted", Label: "Đã nhận câu hỏi"})
	reporter := func(event agent.ProgressEvent) {
		writeSSE(w, flusher, "status", event)
	}

	agentResponse, err := svr.agent.CallDetailedWithProgress(r.Context(), req.Message, &session.Context, reporter)
	if err != nil {
		log.Printf("stream agent request failed session=%s role=%s: %v", sessionID, session.Context.Role, err)
		writeSSE(w, flusher, "error", map[string]any{
			"code": "AGENT_UNAVAILABLE", "message": "Trợ lý hoặc kho tri thức hiện chưa sẵn sàng. Vui lòng thử lại.", "retryable": true,
		})
		return
	}
	if err := svr.sessionStore.Save(session); err != nil {
		log.Printf("save streamed session=%s: %v", sessionID, err)
	}
	startSessionTitle(svr, &session, req.Message)

	for _, chunk := range splitSSEText(agentResponse.Text, 160) {
		writeSSE(w, flusher, "delta", map[string]string{"text": chunk})
	}
	if len(agentResponse.Suggestions) > 0 {
		writeSSE(w, flusher, "suggestions", map[string]any{"items": agentResponse.Suggestions})
	}
	writeSSE(w, flusher, "complete", dto.NewPostMessageResponse(agentResponse))
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

func applyRequestRole(r *http.Request, context *domain.Context) {
	if rawRole := r.Header.Get("Role"); rawRole != "" {
		context.Role = agent.NormalizeRole(rawRole)
		context.UserRole = string(context.Role)
		return
	}
	role := r.Header.Get("X-User-Role")
	if role == "" {
		role = r.Header.Get("X-Role")
	}
	if role == "" {
		role = r.URL.Query().Get("role")
	}
	if role != "" {
		context.Role = agent.NormalizeRole(role)
		context.UserRole = string(context.Role)
	}
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
	sessionID, err := svr.sessionStore.Create()
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		return
	}

	// Initialize the session with the same normalized role used for its first
	// message, so it cannot start with a guest prompt and switch later.
	role := r.Header.Get("Role")
	if role == "" {
		role = r.Header.Get("X-User-Role")
	}
	if role == "" {
		role = r.Header.Get("X-Role")
	}
	if role == "" {
		role = r.URL.Query().Get("role")
	}
	if role != "" {
		normalizedRole := agent.NormalizeRole(role)
		if session, err := svr.sessionStore.GetByID(sessionID); err == nil {
			session.Context.Role = normalizedRole
			session.Context.UserRole = string(normalizedRole)
			_ = svr.sessionStore.Save(session)
		}
	}

	resp := dto.NewPostNewSessionResponse(sessionID)
	writeJSON(w, resp, http.StatusCreated)
}

func (svr *Server) DeleteSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	svr.sessionStore.DeleteByID(sessionID)
	w.WriteHeader(http.StatusNoContent)
}

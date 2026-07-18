package api

import (
	"agent/internal/agent"
	"agent/internal/api/dto"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
)

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

	agentResponse, err := svr.agent.Call(r.Context(), req.Message, &session.Context)
	if err != nil {
		log.Printf("agent request failed session=%s role=%s: %v", sessionID, session.Context.Role, err)
		writeJSON(w, dto.NewErrorResponse("Trợ lý chưa thể xử lý yêu cầu này. Vui lòng thử lại."), http.StatusInternalServerError)
		return
	}
	err = svr.sessionStore.Save(session)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: Cannot save session\n")
	}
	if session.Title == "" {
		go func() {
			contextClone := session.Context
			sessionTitle, err := svr.agent.Call(context.Background(), agent.TITLE_PROMPT, &contextClone)
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

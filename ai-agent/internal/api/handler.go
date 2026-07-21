package api

import (
	"agent/internal/agent"
	"agent/internal/api/dto"
	"agent/internal/application"
	"agent/internal/domain"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"maps"
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

func getDeviceID(r *http.Request) string {
	id := r.Header.Get("X-Device-ID")
	if id == "" {
		id = r.URL.Query().Get("device_id")
	}
	return id
}

// getOwnedSession loads a session and hides it from every device other than
// its owner. Sessions created before device scoping (empty OwnerID) stay
// reachable from any device.
func (svr *Server) getOwnedSession(r *http.Request, sessionID string) (domain.Session, error) {
	session, err := svr.sessionStore.GetByID(sessionID)
	if err != nil {
		return domain.Session{}, err
	}
	if session.OwnerID != "" && session.OwnerID != getDeviceID(r) {
		return domain.Session{}, application.ErrIDNotFound
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
		writeJSON(w, errorResponse, http.StatusNotFound)
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
		writeJSON(w, errorResponse, http.StatusNotFound)
		return
	}
	agentResponse, err := svr.agent.Respond(r.Context(), req.Message, images, &session.Context)
	if err != nil {
		log.Printf("agent request failed session=%s: %v", sessionID, err)
		userFacingError := StandardizeModelError(err)
		writeJSON(w, dto.NewErrorResponse(userFacingError), http.StatusInternalServerError)
		return
	}
	if len(agentResponse.CitationContexts) > 0 {
		if session.CitationContexts == nil {
			session.CitationContexts = map[string]domain.CitationContextSnapshot{}
		}
		maps.Copy(session.CitationContexts, agentResponse.CitationContexts)
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
	resp := dto.NewPostMessageResponse(agentResponse.Text, agentResponse.Citations)
	writeJSON(w, resp, http.StatusOK)
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
	if _, err := svr.getOwnedSession(r, sessionID); err == nil {
		svr.sessionStore.DeleteByID(sessionID)
	}
	w.WriteHeader(http.StatusNoContent)
}

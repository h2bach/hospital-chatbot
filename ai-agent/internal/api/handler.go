package api

import (
	"agent/internal/agent"
	"agent/internal/api/dto"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
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

	agentResponse, err := svr.agent.Call(r.Context(), req.Message, &session.Context)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
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

	resp := dto.NewPostNewSessionResponse(sessionID)
	writeJSON(w, resp, http.StatusCreated)
}

func (svr *Server) DeleteSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	svr.sessionStore.DeleteByID(sessionID)
	w.WriteHeader(http.StatusNoContent)
}

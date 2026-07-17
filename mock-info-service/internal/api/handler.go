package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
)

type errorResponse struct {
	Error errorBody `json:"error"`
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func readJSON(w http.ResponseWriter, r *http.Request, v any) bool {
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(v); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "JSON body không hợp lệ: "+err.Error())
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, v any, status int) bool {
	buffer := new(bytes.Buffer)
	if err := json.NewEncoder(buffer).Encode(v); err != nil {
		writeError(w, http.StatusInternalServerError, "ENCODING_ERROR", "Không thể mã hóa response")
		return false
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write(buffer.Bytes())
	return true
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	_ = writeJSON(w, errorResponse{Error: errorBody{Code: code, Message: message}}, status)
}

func pagination(r *http.Request) (int, int, error) {
	limit, offset := 50, 0
	var err error
	if raw := r.URL.Query().Get("limit"); raw != "" {
		limit, err = strconv.Atoi(raw)
		if err != nil || limit < 1 || limit > 500 {
			return 0, 0, errors.New("limit phải nằm trong 1..500")
		}
	}
	if raw := r.URL.Query().Get("offset"); raw != "" {
		offset, err = strconv.Atoi(raw)
		if err != nil || offset < 0 {
			return 0, 0, errors.New("offset phải >= 0")
		}
	}
	return limit, offset, nil
}

func pathParts(path string) []string {
	trimmed := strings.Trim(path, "/")
	if trimmed == "" {
		return nil
	}
	return strings.Split(trimmed, "/")
}

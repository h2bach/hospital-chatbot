package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
)

type errorResponse struct {
	Error struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

func writeJSON(w http.ResponseWriter, value any, status int) {
	buffer := new(bytes.Buffer)
	if err := json.NewEncoder(buffer).Encode(value); err != nil {
		writeError(w, http.StatusInternalServerError, "ENCODING_ERROR", "Không thể mã hóa phản hồi")
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write(buffer.Bytes())
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	response := errorResponse{}
	response.Error.Code = code
	response.Error.Message = message
	writeJSON(w, response, status)
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

func page[T any](items []T, offset, limit int) []T {
	if offset > len(items) {
		offset = len(items)
	}
	end := offset + limit
	if end > len(items) {
		end = len(items)
	}
	return items[offset:end]
}

var vietnameseFold = strings.NewReplacer(
	"à", "a", "á", "a", "ạ", "a", "ả", "a", "ã", "a", "â", "a", "ầ", "a", "ấ", "a", "ậ", "a", "ẩ", "a", "ẫ", "a", "ă", "a", "ằ", "a", "ắ", "a", "ặ", "a", "ẳ", "a", "ẵ", "a",
	"è", "e", "é", "e", "ẹ", "e", "ẻ", "e", "ẽ", "e", "ê", "e", "ề", "e", "ế", "e", "ệ", "e", "ể", "e", "ễ", "e",
	"ì", "i", "í", "i", "ị", "i", "ỉ", "i", "ĩ", "i",
	"ò", "o", "ó", "o", "ọ", "o", "ỏ", "o", "õ", "o", "ô", "o", "ồ", "o", "ố", "o", "ộ", "o", "ổ", "o", "ỗ", "o", "ơ", "o", "ờ", "o", "ớ", "o", "ợ", "o", "ở", "o", "ỡ", "o",
	"ù", "u", "ú", "u", "ụ", "u", "ủ", "u", "ũ", "u", "ư", "u", "ừ", "u", "ứ", "u", "ự", "u", "ử", "u", "ữ", "u",
	"ỳ", "y", "ý", "y", "ỵ", "y", "ỷ", "y", "ỹ", "y", "đ", "d",
)

func fold(value string) string {
	return vietnameseFold.Replace(strings.ToLower(strings.TrimSpace(value)))
}

func searchable(value any) string {
	body, _ := json.Marshal(value)
	return fold(string(body))
}

func requestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-ID")
		if id == "" {
			id = fmt.Sprintf("hanoi-heart-%x", r.Context().Value(http.LocalAddrContextKey))
		}
		w.Header().Set("X-Request-ID", id)
		next.ServeHTTP(w, r)
	})
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-Request-ID")
		w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func recoverer(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if recover() != nil {
				writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "Lỗi nội bộ")
			}
		}()
		next.ServeHTTP(w, r)
	})
}

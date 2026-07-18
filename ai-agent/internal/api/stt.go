package api

import (
	"agent/internal/api/dto"
	"fmt"
	"io"
	"net/http"
	"strings"
)

const maxAudioBytes = 25 << 20

func (svr *Server) TranscribeAudio(w http.ResponseWriter, r *http.Request) {
	if svr.speechToText == nil {
		writeJSON(w, dto.NewErrorResponse("Tính năng nhập bằng giọng nói chưa được cấu hình."), http.StatusNotImplemented)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, maxAudioBytes)
	if err := r.ParseMultipartForm(maxAudioBytes); err != nil {
		writeJSON(w, dto.NewErrorResponse("Tệp âm thanh không hợp lệ hoặc vượt quá giới hạn."), http.StatusBadRequest)
		return
	}
	file, header, err := r.FormFile("audio")
	if err != nil {
		writeJSON(w, dto.NewErrorResponse("Thiếu tệp âm thanh."), http.StatusBadRequest)
		return
	}
	defer file.Close()
	audio, err := io.ReadAll(file)
	if err != nil || len(audio) == 0 {
		writeJSON(w, dto.NewErrorResponse("Không đọc được tệp âm thanh."), http.StatusBadRequest)
		return
	}
	contentType := strings.TrimSpace(header.Header.Get("Content-Type"))
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	text, err := svr.speechToText.Transcribe(r.Context(), header.Filename, contentType, audio)
	if err != nil {
		writeJSON(w, dto.NewErrorResponse(fmt.Sprintf("Không thể nhận dạng giọng nói: %v", err)), http.StatusBadGateway)
		return
	}
	writeJSON(w, map[string]string{"text": text}, http.StatusOK)
}

package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"hospital-info-service/internal/data"
)

const maxDatasetPayload = 8 << 20

type updateDatasetRequest struct {
	Version string          `json:"version"`
	Data    json.RawMessage `json:"data"`
}

func (s *Server) adminDatasets(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	revision, _ := s.store.Revision()
	writeJSON(w, map[string]any{
		"data":     s.store.DatasetSummaries(),
		"revision": revision,
	}, http.StatusOK)
}

func (s *Server) adminDataset(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	state, err := s.store.Dataset(r.PathValue("name"))
	if err != nil {
		if errors.Is(err, data.ErrDatasetNotFound) {
			writeError(w, http.StatusNotFound, "DATASET_NOT_FOUND", "Không tìm thấy bộ dữ liệu")
			return
		}
		writeError(w, http.StatusInternalServerError, "DATASET_READ_ERROR", err.Error())
		return
	}
	writeJSON(w, map[string]any{"dataset": state.Summary, "data": state.Data}, http.StatusOK)
}

func (s *Server) updateAdminDataset(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	reader := http.MaxBytesReader(w, r.Body, maxDatasetPayload)
	defer reader.Close()
	decoder := json.NewDecoder(reader)
	var request updateDatasetRequest
	if err := decoder.Decode(&request); err != nil {
		message := "Payload cập nhật không hợp lệ"
		if errors.Is(err, io.EOF) {
			message = "Payload cập nhật đang trống"
		}
		writeError(w, http.StatusBadRequest, "INVALID_UPDATE_PAYLOAD", message)
		return
	}
	if len(request.Data) == 0 || string(request.Data) == "null" {
		writeError(w, http.StatusBadRequest, "MISSING_DATA", "Thiếu trường data")
		return
	}
	state, err := s.store.UpdateDataset(r.PathValue("name"), request.Data, request.Version)
	if err != nil {
		switch {
		case errors.Is(err, data.ErrDatasetNotFound):
			writeError(w, http.StatusNotFound, "DATASET_NOT_FOUND", "Không tìm thấy bộ dữ liệu")
		case errors.Is(err, data.ErrVersionConflict):
			writeError(w, http.StatusConflict, "VERSION_CONFLICT", "Dữ liệu đã thay đổi ở nơi khác. Hãy tải lại trước khi lưu.")
		default:
			writeError(w, http.StatusUnprocessableEntity, "DATASET_VALIDATION_ERROR", err.Error())
		}
		return
	}
	writeJSON(w, map[string]any{"dataset": state.Summary, "data": state.Data}, http.StatusOK)
}

func (s *Server) adminEvents(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "STREAM_UNAVAILABLE", "Máy chủ không hỗ trợ luồng sự kiện")
		return
	}
	w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache, no-transform")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")

	events, unsubscribe := s.store.Subscribe()
	defer unsubscribe()
	revision, _ := s.store.Revision()
	writeSSE(w, data.ChangeEvent{
		Type:      "stream.ready",
		Datasets:  []string{},
		Revision:  revision,
		ChangedAt: time.Now().UTC(),
	})
	flusher.Flush()

	heartbeat := time.NewTicker(15 * time.Second)
	defer heartbeat.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case event, open := <-events:
			if !open {
				return
			}
			writeSSE(w, event)
			flusher.Flush()
		case <-heartbeat.C:
			_, _ = fmt.Fprint(w, ": heartbeat\n\n")
			flusher.Flush()
		}
	}
}

func writeSSE(w io.Writer, event data.ChangeEvent) {
	body, err := json.Marshal(event)
	if err != nil {
		return
	}
	_, _ = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event.Type, body)
}

package api

import (
	"errors"
	"testing"
)

func TestStandardizeModelError(t *testing.T) {
	tests := []struct {
		name     string
		err      error
		contains string
	}{
		{
			name:     "Nil error",
			err:      nil,
			contains: "",
		},
		{
			name:     "FPT VLM unconfigured",
			err:      errors.New("FPT_VLM_MODEL is required for image messages; FPT_MODEL \"fpt-gemini\" is text-only"),
			contains: "FPT_VLM_MODEL",
		},
		{
			name:     "Image count exceeded",
			err:      errors.New("FPT VLM supports at most 2 images"),
			contains: "tối đa 2 hình ảnh",
		},
		{
			name:     "Unsupported image type",
			err:      errors.New("FPT VLM supports only JPEG and PNG images"),
			contains: "JPEG hoặc PNG",
		},
		{
			name:     "Rate limit 429",
			err:      errors.New("all LLM providers failed: FPT inference returned HTTP 429: Too Many Requests"),
			contains: "quá tải hoặc hết lượt truy cập",
		},
		{
			name:     "Resource exhausted",
			err:      errors.New("googleapi: Error 429: RESOURCE_EXHAUSTED"),
			contains: "quá tải hoặc hết lượt truy cập",
		},
		{
			name:     "No LLM providers configured",
			err:      errors.New("no LLM providers configured"),
			contains: "chưa được cấu hình đúng",
		},
		{
			name:     "Invalid API key / 401",
			err:      errors.New("FPT inference returned HTTP 401: Unauthorized"),
			contains: "khóa API không hợp lệ",
		},
		{
			name:     "Timeout connection",
			err:      errors.New("call FPT inference: context deadline exceeded"),
			contains: "bị gián đoạn hoặc phản hồi quá chậm",
		},
		{
			name:     "503 Service Unavailable",
			err:      errors.New("all LLM providers failed: FPT inference returned HTTP 503: Service Unavailable"),
			contains: "sự cố máy chủ tạm thời",
		},
		{
			name:     "Empty response",
			err:      errors.New("FPT returned an empty answer"),
			contains: "không trả về phản hồi hợp lệ",
		},
		{
			name:     "Max turns exceeded",
			err:      errors.New("model did not return a user-visible answer after 30 turns"),
			contains: "không hoàn thành xử lý sau nhiều bước",
		},
		{
			name:     "Unknown error fallback",
			err:      errors.New("some unexpected internal panic"),
			contains: "do lỗi mô hình AI",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := StandardizeModelError(tt.err)
			if tt.contains == "" {
				if got != "" {
					t.Fatalf("StandardizeModelError(nil) = %q, want empty string", got)
				}
				return
			}
			if got == "" || !containsSubstring(got, tt.contains) {
				t.Fatalf("StandardizeModelError() = %q, want to contain %q", got, tt.contains)
			}
		})
	}
}

func containsSubstring(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(substr) == 0 || (findSubstr(s, substr) >= 0))
}

func findSubstr(s, substr string) int {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return i
		}
	}
	return -1
}

package api

import (
	"strings"
)

// StandardizeModelError converts internal/infrastructure errors returned by LLM models
// into standardized, user-friendly, and actionable Vietnamese error messages for the UI.
func StandardizeModelError(err error) string {
	if err == nil {
		return ""
	}
	msg := err.Error()
	msgLower := strings.ToLower(msg)

	// 1. Missing VLM Configuration / Image constraints
	if strings.Contains(msg, "FPT_VLM_MODEL") || (strings.Contains(msgLower, "vlm") && strings.Contains(msgLower, "required")) {
		return "Chưa cấu hình mô hình VLM xử lý hình ảnh. Hãy đặt FPT_VLM_MODEL bằng tên một mô hình hỗ trợ hình ảnh."
	}
	if strings.Contains(msgLower, "supports at most 2 images") || strings.Contains(msgLower, "too many images") {
		return "Mô hình AI chỉ hỗ trợ xử lý tối đa 2 hình ảnh trong một câu hỏi."
	}
	if strings.Contains(msgLower, "supports only jpeg and png") || strings.Contains(msgLower, "unsupported image") {
		return "Mô hình AI chỉ hỗ trợ định dạng hình ảnh JPEG hoặc PNG."
	}

	// 2. Rate limit / Quota exceeded
	if strings.Contains(msgLower, "429") ||
		strings.Contains(msgLower, "resource_exhausted") ||
		strings.Contains(msgLower, "rate limit") ||
		strings.Contains(msgLower, "ratelimit") ||
		strings.Contains(msgLower, "quota") ||
		strings.Contains(msgLower, "too many requests") {
		return "Hệ thống mô hình AI hiện đang quá tải hoặc hết lượt truy cập. Vui lòng thử lại sau ít phút."
	}

	// 3. API Key / Authentication / Provider Configuration errors
	if strings.Contains(msgLower, "no llm providers configured") ||
		strings.Contains(msgLower, "no gemini api keys configured") ||
		strings.Contains(msgLower, "no fpt api keys configured") ||
		strings.Contains(msgLower, "no fpt model configured") ||
		strings.Contains(msgLower, "unauthorized") ||
		strings.Contains(msgLower, "forbidden") ||
		strings.Contains(msgLower, "invalid api key") ||
		strings.Contains(msgLower, "invalid_api_key") ||
		strings.Contains(msgLower, "http 401") ||
		strings.Contains(msgLower, "http 403") {
		return "Dịch vụ mô hình AI chưa được cấu hình đúng hoặc khóa API không hợp lệ. Vui lòng liên hệ quản trị viên."
	}

	// 4. Timeout / Connection / Network errors
	if strings.Contains(msgLower, "context deadline exceeded") ||
		strings.Contains(msgLower, "connection refused") ||
		strings.Contains(msgLower, "dial tcp") ||
		strings.Contains(msgLower, "timeout") ||
		strings.Contains(msgLower, "connection reset") ||
		strings.Contains(msgLower, "eof") {
		return "Kết nối tới mô hình AI bị gián đoạn hoặc phản hồi quá chậm. Vui lòng thử lại."
	}

	// 5. Server Outage / 5xx error from LLM providers
	if strings.Contains(msgLower, "http 500") ||
		strings.Contains(msgLower, "http 502") ||
		strings.Contains(msgLower, "http 503") ||
		strings.Contains(msgLower, "http 504") ||
		strings.Contains(msgLower, "bad gateway") ||
		strings.Contains(msgLower, "service unavailable") ||
		strings.Contains(msgLower, "internal server error") {
		return "Dịch vụ mô hình AI đang gặp sự cố máy chủ tạm thời. Vui lòng thử lại sau."
	}

	// 6. Empty output or decoding errors
	if strings.Contains(msgLower, "empty answer") ||
		strings.Contains(msgLower, "returned no choices") ||
		strings.Contains(msgLower, "returned an empty response") ||
		strings.Contains(msgLower, "returned no answer content") ||
		strings.Contains(msgLower, "decode fpt response") ||
		strings.Contains(msgLower, "decode fpt tool") {
		return "Mô hình AI không trả về phản hồi hợp lệ. Vui lòng thử lại câu hỏi khác."
	}

	// 7. Max turns exceeded
	if strings.Contains(msgLower, "did not return a user-visible answer after") ||
		strings.Contains(msgLower, "max turns") {
		return "Mô hình AI không hoàn thành xử lý sau nhiều bước. Vui lòng thử lại với câu hỏi ngắn gọn hơn."
	}

	// 8. Default fallback
	return "Trợ lý chưa thể xử lý yêu cầu này do lỗi mô hình AI. Vui lòng thử lại."
}

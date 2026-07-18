# API Contract - AI Service

**Phiên bản:** 1.0.0  
**Base URL:** `http://localhost:8000` (development) / `https://ai-service.example.com` (production)  
**Ngày cập nhật:** 18/07/2026

---

## Mục lục

- [Cài đặt và Chạy Service](#cài-đặt-và-chạy-service)
- [Tổng quan](#tổng-quan)
- [API Endpoints](#api-endpoints)
- [Testing với curl](#testing-với-curl)
- [Swagger UI](#swagger-ui)

---

## Cài đặt và Chạy Service

### Yêu cầu hệ thống

- Python 3.11+
- 4GB RAM tối thiểu
- API key từ OpenAI-compatible provider (ví dụ: shopaikey)

### Cài đặt với Python Virtual Environment

```bash
# Clone repository
git clone <repository-url>
cd vaic-heart-hanoi-problem/ai-service

# Tạo virtual environment
python -m venv .venv

# Kích hoạt virtual environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Cài đặt dependencies
pip install -r requirements.txt
```

### Cấu hình môi trường

Tạo file `.env` từ template:

```bash
cp .env.example .env
```

Chỉnh sửa `.env` với thông tin của bạn:

```env
# === Model Configuration ===
STRONG_MODEL_NAME=gpt-4o-mini
MIDDLE_MODEL_NAME=gpt-4o-mini
CHEAP_MODEL_NAME=gpt-4o-mini

# === API Keys ===
OTHER_API_KEY=your-api-key-here
OTHER_BASE_URL=https://api.shopaikey.com/v1

# === Embedding Configuration ===
EMBEDDING_API_KEY=your-api-key-here
EMBEDDING_BASE_URL=https://api.shopaikey.com/v1
EMBEDDING_MODEL=text-embedding-3-small

# === Vector Store ===
VECTOR_STORE_TYPE=chroma
CHROMA_PERSIST_DIR=data/chroma
CHROMA_COLLECTION_NAME=documents

# === Server ===
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

### Chạy server

**Development mode:**

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Production mode:**

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Server sẽ chạy tại: http://localhost:8000

### Chạy với Docker

```bash
# Build image
docker build -t ai-service:latest .

# Run container
docker run -d \
  --name ai-service \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ai-service:latest
```

### Chạy với Docker Compose

```bash
docker-compose up -d
```

### Ingest dữ liệu ban đầu

Trước khi sử dụng `/retrieve`, cần ingest dữ liệu vào vector store:

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "data_source_api": "/path/to/your/document.md",
    "data_type": "type1",
    "metadata": {"title": "Document Title"}
  }'
```

**Lưu ý:** `data_source_api` phải là đường dẫn tuyệt đối tới file `.md` trên server.

### Kiểm tra service hoạt động

```bash
# Health check
curl http://localhost:8000/health

# Test retrieve (sau khi đã ingest data)
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "Test query", "max_iterations": 2}'
```

### Chạy tests

```bash
# E2E tests (không cần API key - dùng mock)
python tests/test_graph_e2e.py

# Unit tests (nếu có)
pytest tests/
```

### Troubleshooting

**Lỗi: "EMBEDDING_API_KEY is required"**
- Kiểm tra file `.env` có đúng `EMBEDDING_API_KEY` và `EMBEDDING_BASE_URL`
- Đảm bảo `.env` nằm trong thư mục `ai-service/`

**Lỗi: "No available channel for model gpt-4o"**
- Model `gpt-4o` hiện không available trên một số provider
- Đổi sang `gpt-4o-mini` trong `.env`: `STRONG_MODEL_NAME=gpt-4o-mini`

**Lỗi: "No relevant documents found"**
- Chưa ingest data vào vector store
- Chạy `POST /ingest` trước khi dùng `POST /retrieve`

**Lỗi kết nối Chroma**
- Xóa thư mục `data/chroma/` và restart service
- Chroma sẽ tự tạo lại database mới

---

## Tổng quan

AI Service cung cấp 4 endpoint chính để backend tích hợp:

| Endpoint | Method | Chức năng |
|----------|--------|-----------|
| `/health` | GET | Kiểm tra trạng thái service |
| `/retrieve` | POST | Truy vấn RAG pipeline, trả về câu trả lời tổng hợp |
| `/ingest` | POST | Nhập dữ liệu từ backend vào vector store |
| `/update` | POST | Đồng bộ thay đổi (tạo/sửa/xóa) vào vector store |

**Content-Type:** `application/json` cho tất cả request/response  
**Timezone:** Tất cả timestamp theo chuẩn UTC (ISO 8601)

---

## 1. Health Check

### `GET /health`

Kiểm tra trạng thái hoạt động của service.

**Request:** Không cần body

**Response: 200 OK**

```json
{
  "status": "ok",
  "version": "1.0.0",
  "model": "other:gpt-4o-mini",
  "timestamp": "2026-07-18T00:00:00.000000Z"
}
```

**Fields:**

| Field | Type | Mô tả |
|-------|------|-------|
| `status` | string | Luôn là `"ok"` khi service khỏe |
| `version` | string | Version của service |
| `model` | string | Model LLM đang được cấu hình |
| `timestamp` | datetime | Thời điểm response (UTC) |

**Use case:**
- Backend gọi mỗi 30s để health check
- Load balancer dùng để kiểm tra liveness

---

## 2. Retrieve (RAG Pipeline)

### `POST /retrieve`

Chạy pipeline RAG đầy đủ: phân tích query → tìm kiếm vector store (hybrid search) → tổng hợp câu trả lời.

**Request Body:**

```json
{
  "query": "Chính sách làm việc từ xa của công ty là gì?",
  "session_id": "user_123_session_456",
  "max_iterations": 5
}
```

**Fields:**

| Field | Type | Required | Mô tả |
|-------|------|----------|-------|
| `query` | string | ✅ | Câu hỏi của người dùng (1-10,000 ký tự) |
| `session_id` | string | ❌ | ID session để theo dõi multi-turn conversation |
| `max_iterations` | integer | ❌ | Số vòng lặp tối đa của planner (mặc định: 5, max: 10) |

**Response: 200 OK**

```json
{
  "query": "Chính sách làm việc từ xa của công ty là gì?",
  "answer": "Theo chính sách hiện tại, nhân viên được phép làm việc từ xa tối đa 3 ngày/tuần với điều kiện đã hoàn thành thử việc và có thiết bị làm việc đầy đủ.",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "iterations": 2,
  "result_count": 3,
  "error_count": 0,
  "latency_ms": 1245.6,
  "timestamp": "2026-07-18T00:00:00.000000Z"
}
```

**Response Fields:**

| Field | Type | Mô tả |
|-------|------|-------|
| `query` | string | Query gốc từ request |
| `answer` | string | Câu trả lời đã được tổng hợp từ pipeline RAG |
| `trace_id` | string | UUID để tracking request trong logs |
| `iterations` | integer | Số vòng lặp planner đã chạy |
| `result_count` | integer | Số lượng branch results được thu thập |
| `error_count` | integer | Số lượng branch thất bại |
| `latency_ms` | float | Thời gian xử lý (milliseconds) |
| `timestamp` | datetime | Thời điểm response |

**Error Responses:**

**422 Unprocessable Entity** - Validation error

```json
{
  "error": "Validation Error",
  "detail": "query: String should have at least 1 character",
  "request_id": null,
  "timestamp": "2026-07-18T00:00:00.000000Z"
}
```

**500 Internal Server Error** - Pipeline error

```json
{
  "error": "Internal Server Error",
  "detail": "RAG pipeline failed: Vector store connection timeout",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-07-18T00:00:00.000000Z"
}
```

**Use case:**
- User gửi câu hỏi từ chatbot/search interface
- Backend forward query sang AI service
- AI service trả về câu trả lời hoàn chỉnh
- Backend hiển thị câu trả lời cho user

**Luồng xử lý bên trong:**
1. Planner phân tích query → tạo tasks
2. Router dispatch tasks song song đến type1/type2/type3 subgraphs
3. Mỗi subgraph chạy hybrid search (BM25 + Vector + RRF fusion)
4. Merge node tổng hợp kết quả
5. Synthesizer tạo câu trả lời cuối cùng

---

## 3. Ingest Data

### `POST /ingest`

Nhập dữ liệu từ backend API vào vector store. Service sẽ:
1. Gọi `data_source_api` để lấy dữ liệu thô
2. Chunk và embed dữ liệu
3. Lưu vào ChromaDB (vector) + BM25 index

**Request Body:**

```json
{
  "data_source_api": "https://backend.example.com/api/documents",
  "data_type": "document",
  "auth_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "metadata": {
    "department": "HR",
    "sync_timestamp": "2026-07-18T00:00:00Z"
  }
}
```

**Fields:**

| Field | Type | Required | Mô tả |
|-------|------|----------|-------|
| `data_source_api` | string | ✅ | URL của backend API để fetch data |
| `data_type` | string | ✅ | Loại dữ liệu: `"document"`, `"policy"`, `"faq"`, etc. |
| `auth_token` | string | ❌ | Bearer token để authenticate với backend API |
| `metadata` | object | ❌ | Metadata bổ sung (department, tags, timestamp, etc.) |

**Backend API phải trả về format:**

```json
{
  "data": [
    {
      "id": "doc_123",
      "title": "Chính sách làm việc từ xa",
      "content": "Nội dung đầy đủ của document...",
      "metadata": {
        "author": "HR Team",
        "created_at": "2026-01-15",
        "category": "policy"
      }
    }
  ]
}
```

**Response: 200 OK**

```json
{
  "status": "completed",
  "data_type": "document",
  "records_fetched": 150,
  "records_processed": 147,
  "job_id": "ingest_job_20260718_000000",
  "message": "Successfully ingested 147/150 records. 3 records failed validation.",
  "latency_ms": 8234.5,
  "timestamp": "2026-07-18T00:00:00.000000Z"
}
```

**Response Fields:**

| Field | Type | Mô tả |
|-------|------|-------|
| `status` | string | `"started"` / `"processing"` / `"completed"` |
| `data_type` | string | Loại dữ liệu đã ingest |
| `records_fetched` | integer | Số records lấy được từ backend API |
| `records_processed` | integer | Số records đã xử lý thành công |
| `job_id` | string | ID job để tracking (optional) |
| `message` | string | Thông báo chi tiết |
| `latency_ms` | float | Thời gian xử lý |
| `timestamp` | datetime | Thời điểm hoàn thành |

**Error Responses:**

**502 Bad Gateway** - Backend API error

```json
{
  "error": "Backend API Error",
  "detail": "Failed to fetch data from https://backend.example.com/api/documents: Connection timeout",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-07-18T00:00:00.000000Z"
}
```

**Use case:**
- Backend admin trigger "Đồng bộ dữ liệu toàn bộ"
- Scheduled job chạy hàng đêm để sync data mới
- Sau khi import bulk documents vào backend database

---

## 4. Update Data

### `POST /update`

Đồng bộ thay đổi (create/update/delete) từ backend vào vector store theo realtime.

**Request Body:**

**Ví dụ 1: Delete documents**

```json
{
  "operation": "delete",
  "data_type": "document",
  "record_ids": ["doc_123", "doc_456", "doc_789"]
}
```

**Ví dụ 2: Update documents (fetch lại data mới từ backend)**

```json
{
  "operation": "update",
  "data_type": "document",
  "record_ids": ["doc_123"],
  "data_source_api": "https://backend.example.com/api/documents?ids=doc_123",
  "metadata": {
    "updated_by": "admin_user",
    "reason": "content_correction"
  }
}
```

**Ví dụ 3: Create new documents**

```json
{
  "operation": "create",
  "data_type": "document",
  "record_ids": ["doc_999"],
  "data_source_api": "https://backend.example.com/api/documents?ids=doc_999"
}
```

**Fields:**

| Field | Type | Required | Mô tả |
|-------|------|----------|-------|
| `operation` | string | ✅ | `"create"` / `"update"` / `"delete"` |
| `data_type` | string | ✅ | Loại dữ liệu: `"document"`, `"policy"`, etc. |
| `record_ids` | array[string] | ✅ | Danh sách ID các record bị ảnh hưởng |
| `data_source_api` | string | ❌ | URL backend API để fetch data (bắt buộc với create/update) |
| `metadata` | object | ❌ | Metadata bổ sung |

**Response: 200 OK**

```json
{
  "status": "success",
  "operation": "update",
  "data_type": "document",
  "records_affected": 3,
  "records_updated": 3,
  "records_failed": 0,
  "failed_ids": [],
  "message": "Successfully updated 3 records in vector store",
  "latency_ms": 567.8,
  "timestamp": "2026-07-18T00:00:00.000000Z"
}
```

**Response Fields:**

| Field | Type | Mô tả |
|-------|------|-------|
| `status` | string | `"success"` / `"partial"` / `"failed"` |
| `operation` | string | Operation đã thực hiện |
| `data_type` | string | Loại dữ liệu |
| `records_affected` | integer | Tổng số records trong request |
| `records_updated` | integer | Số records thành công |
| `records_failed` | integer | Số records thất bại |
| `failed_ids` | array[string] | Danh sách ID thất bại |
| `message` | string | Thông báo chi tiết |
| `latency_ms` | float | Thời gian xử lý |
| `timestamp` | datetime | Thời điểm hoàn thành |

**Use case:**
- Backend trigger webhook khi:
  - Admin tạo document mới → `POST /update` với `operation="create"`
  - Admin sửa document → `POST /update` với `operation="update"`
  - Admin xóa document → `POST /update` với `operation="delete"`
- Đảm bảo vector store luôn sync realtime với database

---

## Luồng tích hợp đề xuất

### 1. Khởi tạo ban đầu (One-time setup)

```
Backend                           AI Service
   |                                  |
   |--- GET /health ----------------->|  (Kiểm tra service sẵn sàng)
   |<-- 200 OK ----------------------|
   |                                  |
   |--- POST /ingest ---------------->|  (Đồng bộ toàn bộ data hiện có)
   |    {data_source_api, data_type} |
   |<-- 200 OK ----------------------|
   |    {records_processed: 1000}    |
```

### 2. Realtime sync khi có thay đổi

```
Backend                           AI Service
   |                                  |
User tạo document mới
   |                                  |
   |--- POST /update ---------------->|
   |    {operation: "create",         |
   |     record_ids: ["doc_999"]}    |
   |<-- 200 OK ----------------------|
   |                                  |
User sửa document
   |                                  |
   |--- POST /update ---------------->|
   |    {operation: "update",         |
   |     record_ids: ["doc_999"]}    |
   |<-- 200 OK ----------------------|
```

### 3. User query RAG

```
Backend                           AI Service
   |                                  |
User gửi câu hỏi
   |                                  |
   |--- POST /retrieve -------------->|
   |    {query: "Policy làm việc      |
   |            từ xa?"}              |
   |                                  |  [RAG Pipeline chạy]
   |                                  |  → Planner
   |                                  |  → Type1 subgraph (hybrid search)
   |                                  |  → Synthesizer
   |                                  |
   |<-- 200 OK ----------------------|
   |    {answer: "Nhân viên được     |
   |     phép làm việc từ xa..."}    |
   |                                  |
Hiển thị answer cho user
```

---

## Error Handling

Tất cả error response đều có format chuẩn:

```json
{
  "error": "Error Type",
  "detail": "Chi tiết lỗi cụ thể",
  "request_id": "trace_id_hoặc_null",
  "timestamp": "2026-07-18T00:00:00.000000Z"
}
```

**HTTP Status Codes:**

| Code | Ý nghĩa |
|------|---------|
| 200 | Success |
| 422 | Validation error (request body sai format) |
| 500 | Internal server error (AI service lỗi nội bộ) |
| 502 | Bad Gateway (không gọi được backend API) |
| 503 | Service Unavailable (service đang restart/maintenance) |

**Retry Strategy:**
- `422`: Không retry, fix request body
- `500`: Retry với exponential backoff (max 3 lần)
- `502`: Retry với exponential backoff (max 3 lần)
- `503`: Retry sau 30s

---

## Authentication (Production)

**Development:** Không cần authentication  
**Production:** Sẽ sử dụng API Key hoặc JWT

```bash
curl -X POST https://ai-service.example.com/retrieve \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "..."}'
```

*(Sẽ cập nhật chi tiết khi deploy production)*

---

## Rate Limiting (Production)

| Endpoint | Limit |
|----------|-------|
| `/health` | Unlimited |
| `/retrieve` | 100 requests/minute/user |
| `/ingest` | 10 requests/hour |
| `/update` | 1000 requests/minute |

*(Development không có rate limit)*

---

## Monitoring & Logging

Mỗi request đến `/retrieve` sẽ tạo `trace_id` để tracking:

1. Backend nhận `trace_id` từ response
2. Log vào database: `user_query`, `trace_id`, `latency_ms`, `timestamp`
3. Khi cần debug, backend gửi `trace_id` cho AI team để tra logs chi tiết

**Log format AI Service:**

```
INFO [2026-07-18 00:00:00] trace_id=550e8400... | query_length=45 | iterations=2 | latency_ms=1245.6
```

---

## Testing với curl

```bash
# Health check
curl http://localhost:8000/health

# Retrieve
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Chính sách làm việc từ xa?",
    "max_iterations": 3
  }'

# Ingest
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "data_source_api": "https://backend.example.com/api/documents",
    "data_type": "document",
    "auth_token": "Bearer YOUR_TOKEN"
  }'

# Update (delete)
curl -X POST http://localhost:8000/update \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "delete",
    "data_type": "document",
    "record_ids": ["doc_123", "doc_456"]
  }'
```

---

## Swagger UI

Truy cập interactive API documentation tại:

**Development:** `http://localhost:8000/docs`  
**Production:** `https://ai-service.example.com/docs`

---

## Contact & Support

- **Slack channel:** #ai-service-support
- **On-call:** AI Team
- **Documentation:** `/ai-service/README.md`, `/ai-service/architecture.md`

---

**Changelog:**
- **1.0.0 (2026-07-18):** Initial release

# 🔀 Kế hoạch Merge `bach/full-deploy` + `dev` ➜ `final-dev`

> **Mục tiêu**: Hợp nhất toàn bộ thành quả từ 2 nhánh phát triển song song thành một nhánh `final-dev` ổn định, sẵn sàng cho Demo Day.

---

## 📊 1. PHÂN TÍCH HIỆN TRẠNG 2 NHÁNH

### 1.1 Cấu trúc phân nhánh

```
                      Initial Commit (683e985)
                              │
                         ┌────┴────────────────────────────────────┐
                         │ ← Shared History (39 commits)          │
                         │   mock-info-service, MCP tools,         │
                         │   chatbot-web-interface, prompt eng,    │
                         │   roles, docker, FPT/Gemini providers   │
                         │                                         │
                    bb377e1 (merge-base)                            │
                  "real-like-mock-data"                             │
                         │                                         │
              ┌──────────┴──────────┐                              │
              │                     │                              │
    bach/full-deploy (1 commit)    dev (43 commits)                │
         d6f1407                    7fb1a58                        │
              │                     │                              │
              └──────────┬──────────┘                              │
                         │                                         │
                    final-dev ← TẠO MỚI                            │
```

### 1.2 Merge Base
- **Commit chung gần nhất**: `bb377e1` ("real-like-mock-data")
- **Commits chỉ có ở `bach/full-deploy`**: **1 commit** (`d6f1407`)
- **Commits chỉ có ở `dev`**: **43 commits**

### 1.3 Thống kê thay đổi (dev so với bach/full-deploy)
- **135 files changed**: `+10,495 lines / −38,935 lines`
- Phần lớn dòng bị xóa đến từ việc `dev` loại bỏ `rag-core/`, `unified.go`, `workflow.go` và các RAG deploy reports.

---

## 🔍 2. PHÂN TÍCH CHI TIẾT CHỨC NĂNG TỪNG NHÁNH

### 2.1 Nhánh `bach/full-deploy` (1 commit duy nhất so với merge-base)

| Thành phần | Mô tả |
| :--- | :--- |
| **RAG Core Python Service** (`rag-core/`) | Hệ thống Retrieval-Augmented Generation hoàn chỉnh bằng Python, gồm: indexing pipeline, dense retrieval, chunking, citation extraction, HTTP server port `6689`. |
| **Unified AI Agent** (`ai-agent/internal/agent/unified.go`) | Orchestrator đa nhiệm: phân tích intent → lập plan JSON → gọi song song MCP tools + RAG retrieval → tổng hợp đáp án grounded. (~1165 dòng) |
| **Workflow Engine** (`ai-agent/internal/agent/workflow.go`) | State machine cho luồng hội thoại phức tạp: `PlanIntent → GatherEvidence → Synthesize → Evaluate → Respond`. (~603 dòng) |
| **RAG Client Go** (`ai-agent/internal/rag/client.go`) | HTTP client gọi RAG service, xử lý evidence retrieval, health check. (~424 dòng) |
| **Knowledge MCP Tools** (`ai-agent/internal/mcp/tools/knowledge.go`) | MCP tools bọc RAG retrieval endpoints. (~129 dòng) |
| **Docker Compose 3 services** | `rag-demo` (Python RAG), `hospital-info-service`, `ai-agent` (với `ORCHESTRATOR_MODE: unified`). |
| **RAG Deploy Reports** (`rag_deploy_reports/`) | Tài liệu kỹ thuật về quá trình triển khai RAG (phases 5-8). |

### 2.2 Nhánh `dev` (43 commits so với merge-base)

| Thành phần | Mô tả |
| :--- | :--- |
| **Loại bỏ hoàn toàn Roles** | Xóa `roles.go`, sửa `agent.go`, `context.go`, `handler.go` — chỉ còn GUEST mode. |
| **Agent đơn giản hóa** (`agent.go`) | Bỏ RAG + Unified, chỉ giữ MCP-native agent gọi trực tiếp `hospital-info-service`. |
| **Hospital Web Dashboard** (`hospital-data/web-dashboard/`) | Dashboard quản trị React+Vite hoàn chỉnh: kéo-thả lịch bác sĩ, kiểm tra trùng ca, gợi ý phân công, xuất/nhập CSV. (~15 files mới) |
| **Hospital Info Service Admin API** | Thêm `admin.go` (124 dòng), `admin_test.go` (98 dòng), `store.go` refactor (+550 dòng), SSE hot-reload, CORS mở toàn bộ origin. |
| **STT (Speech-to-Text)** | `stt.go` + `stt_test.go`, proxy endpoint nhận audio và chuyển giọng nói thành text. |
| **Image Feeding** | Hỗ trợ gửi ảnh kèm tin nhắn trong chatbot. |
| **Device-Isolated Sessions** | Phân tách phiên theo thiết bị, auto-reset 24h, `MemorySessionStore` refactor. |
| **Session Bug Fixes** | `sendingSessionId` tracker thay `boolean sending`, chống tạo duplicate blank session. |
| **Ultra-Compact Mobile UI** | 15+ commits responsive cho iPhone SE (375×667): topbar 42px, avatar 28px, font 13px, suggestion cards 28px icons, v.v. |
| **Prompt Hotline Fix** | Phân biệt `HOTLINE` (1900 1082) vs `EMERGENCY_HOTLINE` (115). |
| **Welcome & Typography** | Đổi eyebrow badge, tách "Bệnh viện Tim Hà Nội" xuống dòng riêng, tinh chỉnh markdown rendering. |
| **Docker Compose 3 services (khác)** | `hospital-info-service`, `hospital-data-dashboard`, `ai-agent` — **KHÔNG có `rag-demo`**. |
| **Standardized Error Output** | `model_error.go` + tests. |

---

## ⚠️ 3. PHÂN TÍCH XUNG ĐỘT (CONFLICT ANALYSIS)

### 3.1 Xung đột Kiến trúc Cốt lõi (CRITICAL)

| File/Module | bach/full-deploy | dev | Chiến lược xử lý |
| :--- | :--- | :--- | :--- |
| `ai-agent/internal/agent/agent.go` | Cũ hơn, còn roles, import RAG + unified | Mới hơn, không roles, không RAG, MCP-only | **Giữ `dev`**, bổ sung lại RAG integration |
| `ai-agent/internal/agent/unified.go` | 1165 dòng orchestrator | **Đã xóa** | **Khôi phục từ `bach/full-deploy`** nhưng cần refactor bỏ roles |
| `ai-agent/internal/agent/workflow.go` | 603 dòng state machine | **Đã xóa** | **Khôi phục từ `bach/full-deploy`** |
| `ai-agent/internal/rag/client.go` | 424 dòng RAG client | **Đã xóa** | **Khôi phục từ `bach/full-deploy`** |
| `ai-agent/internal/mcp/tools/knowledge.go` | 129 dòng knowledge tools | **Đã xóa** | **Khôi phục từ `bach/full-deploy`** |
| `ai-agent/internal/agent/roles.go` | Có 4 roles | **Đã xóa** | **Giữ đã xóa** (yêu cầu người dùng) |

### 3.2 Xung đột Docker & Infrastructure (HIGH)

| File | bach/full-deploy | dev | Chiến lược |
| :--- | :--- | :--- | :--- |
| `docker-compose.yml` | 3 services: `rag-demo`, `hospital-info-service`, `ai-agent` (port 6689) | 3 services: `hospital-info-service`, `hospital-data-dashboard`, `ai-agent` (port 8080) | **Merge cả hai**: 4 services tổng cộng |
| `rag-core/Dockerfile.demo` | Có | **Đã xóa** | **Khôi phục** |
| `rag-core/` directory | Đầy đủ | **Đã xóa** | **Khôi phục** |

### 3.3 Xung đột UI/Frontend (MEDIUM)

| File | Xung đột? | Chiến lược |
| :--- | :--- | :--- |
| `ai-agent/web-interface/src/index.css` | Có (~780 dòng khác biệt) | **Giữ `dev`** (mới nhất, ultra-compact) |
| `ai-agent/web-interface/src/App.tsx` | Có (~174 dòng khác biệt) | **Giữ `dev`** (sendingSessionId, blank session) |
| `ai-agent/web-interface/src/components/*` | Có (Composer, MessageThread, Sidebar) | **Giữ `dev`** (STT, images, eyebrow badge) |
| `ai-agent/static/assets/*` | Hash khác nhau | **Rebuild từ source** |

### 3.4 Files chỉ có ở `dev` (KEEP ALL)

| Thành phần | Files |
| :--- | :--- |
| Hospital Web Dashboard | `hospital-data/web-dashboard/` (15+ files) |
| Admin API | `hospital-info-service/internal/api/admin.go`, `admin_test.go` |
| Store refactor | `hospital-info-service/internal/data/store.go`, `store_test.go` |
| STT | `ai-agent/internal/api/stt.go`, `stt_test.go` |
| Error model | `ai-agent/internal/api/model_error.go`, `model_error_test.go` |
| DTO tests | `ai-agent/internal/api/dto/post_request_test.go` |

---

## 🛠️ 4. KẾ HOẠCH MERGE CHI TIẾT (STEP-BY-STEP PLAN)

### Bước 0: Backup & Tạo nhánh mới
```bash
# Đảm bảo clean working tree
git stash

# Tạo nhánh final-dev dựa trên dev (nhánh có nhiều thay đổi hơn)
git checkout dev
git checkout -b final-dev
```

> **Lý do chọn `dev` làm base**: `dev` có 43 commits với toàn bộ UI/UX, dashboard, admin API, session fixes, STT — là phần lõi sản phẩm. `bach/full-deploy` chỉ thêm 1 commit chứa RAG layer.

---

### Bước 1: Khôi phục RAG Core (từ `bach/full-deploy`)
```bash
# Khôi phục toàn bộ thư mục rag-core/
git checkout bach/full-deploy -- rag-core/

# Khôi phục RAG deploy reports
git checkout bach/full-deploy -- rag_deploy_reports/

git add rag-core/ rag_deploy_reports/
git commit -m "feat: restore rag-core service and deploy reports from bach/full-deploy"
```

**Kiểm tra**:
- [ ] `rag-core/rag_core/app.py` tồn tại
- [ ] `rag-core/Dockerfile.demo` tồn tại
- [ ] `rag-core/artifacts/` đầy đủ

---

### Bước 2: Khôi phục RAG Client Go (từ `bach/full-deploy`)
```bash
# Khôi phục Go RAG client
git checkout bach/full-deploy -- ai-agent/internal/rag/

git add ai-agent/internal/rag/
git commit -m "feat: restore Go RAG client from bach/full-deploy"
```

**Kiểm tra**:
- [ ] `ai-agent/internal/rag/client.go` tồn tại (~424 dòng)
- [ ] Package `rag` có thể import được

---

### Bước 3: Khôi phục Unified Orchestrator & Workflow (từ `bach/full-deploy`)
```bash
# Khôi phục unified orchestrator và workflow
git checkout bach/full-deploy -- ai-agent/internal/agent/unified.go
git checkout bach/full-deploy -- ai-agent/internal/agent/workflow.go
git checkout bach/full-deploy -- ai-agent/internal/agent/workflow_test.go

git add ai-agent/internal/agent/unified.go \
        ai-agent/internal/agent/workflow.go \
        ai-agent/internal/agent/workflow_test.go
git commit -m "feat: restore unified orchestrator and workflow engine from bach/full-deploy"
```

**⚠️ Cần refactor ngay sau đó** (Bước 5):
- `unified.go` và `workflow.go` có thể import `roles.go` (đã bị xóa ở `dev`)
- Cần sửa các tham chiếu role → mặc định GUEST

---

### Bước 4: Khôi phục Knowledge MCP Tools (từ `bach/full-deploy`)
```bash
git checkout bach/full-deploy -- ai-agent/internal/mcp/tools/knowledge.go

git add ai-agent/internal/mcp/tools/knowledge.go
git commit -m "feat: restore knowledge MCP tools wrapping RAG retrieval"
```

---

### Bước 5: Refactor để loại bỏ Roles khỏi code khôi phục (CRITICAL)

Đây là bước quan trọng nhất. Các file khôi phục từ `bach/full-deploy` có thể tham chiếu:
- `agent.GetRole()` / `agent.SetRole()`
- `domain.Context.Role`
- `roles.go` constants

**Công việc cần làm**:

1. **`unified.go`**: Tìm và thay thế tất cả tham chiếu role:
   - Xóa các `switch` statement trên role
   - Hardcode logic cho GUEST/mặc định
   - Cập nhật import (bỏ `roles.go` references)

2. **`workflow.go`**: Tương tự, loại bỏ role-dependent logic

3. **Kiểm tra `ai-agent/internal/agent/agent.go`**:
   - Đảm bảo `agent.go` (phiên bản `dev`) có thể khởi tạo `UnifiedAgent` nếu cần
   - Thêm toggle `ORCHESTRATOR_MODE` env var nếu muốn chọn giữa simple MCP mode và unified RAG mode

4. **Kiểm tra compile**:
   ```bash
   cd ai-agent && go build ./...
   ```

```bash
git add -A
git commit -m "refactor: remove role dependencies from restored unified/workflow code"
```

---

### Bước 6: Hợp nhất Docker Compose (4 services)

Tạo `docker-compose.yml` mới kết hợp cả 2 nhánh:

```yaml
services:
  rag-demo:
    build:
      context: .
      dockerfile: rag-core/Dockerfile.demo
    expose:
      - "6689"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6689/health', timeout=3)"]
      interval: 10s
      timeout: 5s
      retries: 5

  hospital-info-service:
    build:
      context: ./hospital-info-service
    command: ["--port", "8080", "--data", "/app/data"]
    volumes:
      - ./hospital-data:/app/data
    ports:
      - "127.0.0.1:8081:8080"
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://127.0.0.1:8080/health"]
      interval: 5s
      timeout: 3s
      retries: 10

  hospital-data-dashboard:
    build:
      context: ./hospital-data/web-dashboard
    depends_on:
      hospital-info-service:
        condition: service_healthy
    ports:
      - "127.0.0.1:8082:8080"

  ai-agent:
    build:
      context: ./ai-agent
    env_file:
      - .env
    environment:
      PORT: "8080"
      AGENT_STATIC_DIR: /app/static
      HOSPITAL_INFO_SERVICE_URL: http://hospital-info-service:8080
      RAG_SERVICE_URL: http://rag-demo:6689
    depends_on:
      rag-demo:
        condition: service_healthy
      hospital-info-service:
        condition: service_healthy
    ports:
      - "8080:8080"
```

```bash
git add docker-compose.yml
git commit -m "feat: merge docker-compose with 4 services (rag-demo + hospital-info + dashboard + ai-agent)"
```

---

### Bước 7: Cập nhật `agent.go` hỗ trợ RAG (optional toggle)

Sửa `ai-agent/internal/agent/agent.go` (phiên bản `dev`) để:
1. Đọc env var `RAG_SERVICE_URL` — nếu có, khởi tạo RAG client
2. Thêm optional RAG context vào prompt khi có evidence
3. Giữ nguyên MCP-only flow làm mặc định khi không có RAG

```bash
git add ai-agent/internal/agent/agent.go
git commit -m "feat: add optional RAG integration toggle to agent (RAG_SERVICE_URL env)"
```

---

### Bước 8: Khôi phục Knowledge Sources Metadata

```bash
# Khôi phục docs data_rag nếu cần
git checkout bach/full-deploy -- docs/data_rag/knowledge_sources.json 2>/dev/null || true

git add docs/
git commit -m "feat: restore knowledge sources metadata" --allow-empty
```

---

### Bước 9: Build & Test toàn diện

```bash
# 1. Go build
cd ai-agent && go build ./...

# 2. Go tests
GOCACHE=/tmp/gocache go test ./...

# 3. Vite build (web interface)
cd web-interface && node ./node_modules/vite/bin/vite.js build

# 4. Hospital info service tests
cd ../../hospital-info-service && go test ./...

# 5. Docker compose build (smoke test)
cd .. && docker compose build
```

```bash
git add -A
git commit -m "build: verify all services compile and tests pass on final-dev"
```

---

### Bước 10: Push & Verify

```bash
git push -u origin final-dev
```

---

## ✅ 5. CHECKLIST NGHIỆM THU (ACCEPTANCE CRITERIA)

### Chức năng từ `dev` (phải hoạt động)
- [ ] Chatbot web giao diện ultra-compact (iPhone SE 375×667)
- [ ] Tra cứu lịch bác sĩ qua MCP tools
- [ ] Hospital Web Dashboard quản trị (port 8082)
- [ ] STT (Speech-to-Text) nhập liệu giọng nói
- [ ] Image feeding trong chatbot
- [ ] Device-isolated sessions + auto-cleanup 24h
- [ ] `sendingSessionId` tracker (không ghost loading khi chuyển session)
- [ ] Blank session prevention
- [ ] HOTLINE (1900 1082) vs EMERGENCY_HOTLINE (115) phân biệt đúng
- [ ] Hospital Info Service Admin API + CORS mở
- [ ] Eyebrow badge "HỖ TRỢ THÔNG TIN BỆNH VIỆN"
- [ ] Session title 2-line display + tooltip
- [ ] Ultra-compact topbar, suggestion cards, composer

### Chức năng từ `bach/full-deploy` (phải hoạt động)
- [ ] RAG Core Python service khởi động được (port 6689)
- [ ] RAG retrieval endpoint trả về evidence chunks
- [ ] Go RAG client kết nối được tới RAG service
- [ ] Knowledge MCP tools bọc RAG retrieval
- [ ] Unified Orchestrator (optional mode) tổng hợp MCP + RAG
- [ ] Docker Compose 4 services build thành công

### Tích hợp (phải hoạt động)
- [ ] `go build ./...` không lỗi
- [ ] `go test ./...` all pass
- [ ] Vite build `web-interface` thành công
- [ ] `docker compose build` thành công
- [ ] `docker compose up` khởi động được cả 4 services

---

## 📅 6. ƯỚC LƯỢNG THỜI GIAN

| Bước | Thời gian ước tính |
| :--- | :--- |
| Bước 0: Tạo nhánh | 2 phút |
| Bước 1-4: Khôi phục files | 10 phút |
| Bước 5: Refactor roles (CRITICAL) | 30-60 phút |
| Bước 6: Merge docker-compose | 10 phút |
| Bước 7: RAG toggle trong agent.go | 20-30 phút |
| Bước 8: Knowledge sources | 5 phút |
| Bước 9: Build & Test | 15-20 phút |
| Bước 10: Push | 2 phút |
| **Tổng** | **~1.5 - 2.5 giờ** |

---

## 🎯 7. RỦI RO & PHƯƠNG ÁN DỰ PHÒNG

| Rủi ro | Mức độ | Phương án |
| :--- | :--- | :--- |
| `unified.go` phụ thuộc chặt vào `roles.go` | **CAO** | Nếu refactor quá phức tạp, tạm thời đặt `unified.go` thành optional (chỉ biên dịch khi có build tag `+build rag`) |
| RAG service không tương thích với agent mới | **TRUNG BÌNH** | Giữ RAG service độc lập, chỉ gọi qua HTTP — không ảnh hưởng agent core |
| Conflict trong `go.mod` / `go.sum` | **THẤP** | `go mod tidy` sẽ tự giải quyết |
| `index.css` quá khác biệt (780 dòng) | **THẤP** | Giữ nguyên phiên bản `dev` (đã tối ưu) |

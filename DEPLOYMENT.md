# Triển khai HeartCare Unified MCP Agent

Tài liệu này mô tả cách dựng lại toàn bộ MVP trên một máy mới. Cấu hình mặc định là **CPU-only** cho retrieval; GPU BGE-M3 là overlay tùy chọn. Cả hai chế độ đều giữ public port `6689`, FPT Agent bắt buộc và các quy tắc exact/approximate/insufficient hiện tại.

## 1. Kiến trúc triển khai

| Thành phần | Vai trò | Host port CPU |
|---|---|---:|
| `ai-agent` | Web chatbot, FPT planner/evaluator, MCP orchestrator | `0.0.0.0:6689` |
| `rag-demo` | RAG knowledge, BM25/fuzzy, evidence contract | internal `6689` |
| `hospital-info-service` | Directory, bác sĩ, phòng, lịch và dữ liệu vận hành | `127.0.0.1:8081` |
| `hospital-data-dashboard` | Dashboard quản trị | `127.0.0.1:8082` |
| `dense-retrieval` | BGE-M3/CUDA, chỉ có trong GPU overlay | internal `6690` |

CPU mode không host LLM cục bộ. FPT API vẫn thực hiện planning, grounded synthesis và evaluation; chỉ tầng retrieval chạy bằng CPU.

## 2. Yêu cầu máy chủ

### CPU mặc định

- Linux x86_64.
- Khuyến nghị từ 4 CPU, 8 GB RAM và 15 GB dung lượng trống.
- Git, Docker Engine 24+ và Docker Compose v2.
- Kết nối được tới FPT API.
- Public TCP `6689`; không public `8081`, `8082` hoặc `6690`.

Kiểm tra:

```bash
docker --version
docker compose version
docker info
```

### GPU tùy chọn

Ngoài các yêu cầu trên cần NVIDIA driver, NVIDIA Container Toolkit, VRAM phù hợp và BGE-M3 cache. Kiểm tra trước khi dùng overlay:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
```

CPU deployment không cần chạy hai lệnh này.

## 3. Lấy source và cấu hình bí mật

```bash
git clone https://github.com/danhkhai07/vaic-heart-hanoi-problem.git
cd vaic-heart-hanoi-problem
git checkout final-dev
cp .env.example .env
chmod 600 .env
```

Điền tối thiểu trong `.env`:

```dotenv
LLM_PROVIDERS=fpt
FPT_API_KEYS=replace_with_real_key
FPT_MODEL=replace_with_function_calling_model
FPT_VLM_MODEL=replace_if_image_input_is_enabled
FPT_STT_MODEL=
PORT=6689
ORCHESTRATOR_MODE=unified
```

Không commit `.env`, không ghi API key vào log hoặc Dockerfile. Compose luôn ép `LLM_PROVIDERS=fpt` và `ORCHESTRATOR_MODE=unified` cho production.

## 4. Triển khai CPU-only

`docker-compose.yml` là cấu hình CPU chuẩn. Nó không tạo dense container, không request GPU và ép RAG về BM25 dù máy có CUDA hoặc `.env` còn một dense URL cũ.

```bash
docker compose config --services
docker compose up -d --build --remove-orphans
docker compose ps
```

Danh sách CPU phải có đúng các service nghiệp vụ sau và không có `dense-retrieval`:

```text
rag-demo
hospital-info-service
ai-agent
hospital-data-dashboard
```

Lần build đầu tạo canonical RAG index trực tiếp từ `docs/data_rag/` trong image. Không cần tải embedding model.

## 5. Xác minh sau triển khai

### Health tổng hợp

```bash
curl -fsS http://127.0.0.1:6689/health
```

Kết quả phải báo Agent, RAG và MCP healthy. Kiểm tra chính xác retrieval mode bên trong network:

```bash
docker compose exec -T rag-demo python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:6689/health', timeout=5).read().decode())"
```

CPU health phải chứa:

```json
{"retrieval_mode":"cpu","retriever":"bm25","indexed_chunks":12738}
```

### Smoke test retrieval CPU

Exact service code:

```bash
docker compose exec -T rag-demo python -c "import json,urllib.request; data=json.dumps({'query':'Mã 19.0069.1829 giá bao nhiêu?','top_k':5}).encode(); req=urllib.request.Request('http://127.0.0.1:6689/api/v1/rag/retrieve',data=data,headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(req,timeout=15).read().decode())"
```

Kết quả phải chứa mã `19.0069.1829`, tên SPECT/CT Tetrofosmin, giá `969.800` và evidence/citation tương ứng.

Approximate typo:

```bash
docker compose exec -T rag-demo python -c "import json,urllib.request; data=json.dumps({'query':'SPECT/CT sử dụng Terofotmin','top_k':5}).encode(); req=urllib.request.Request('http://127.0.0.1:6689/api/v1/rag/retrieve',data=data,headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(req,timeout=15).read().decode())"
```

Nếu không exact, response chỉ được đưa tối đa 5 gợi ý có ngưỡng similarity từ `0.80`, không tự chọn thay người dùng.

### Web

- Trên máy chủ: `http://127.0.0.1:6689`
- Từ máy khác: `http://<server-ip>:6689`
- Dashboard chỉ loopback: `http://127.0.0.1:8082`

Truy cập dashboard từ máy cá nhân qua SSH tunnel:

```bash
ssh -L 8082:127.0.0.1:8082 user@server-ip
```

Sau đó mở `http://127.0.0.1:8082` trên máy cá nhân.

## 6. Kiểm thử trước phát hành

```bash
PYTHONPATH=rag-core pytest -q rag-core/tests

(cd ai-agent && go test ./...)
(cd hospital-info-service && go test ./...)

docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.gpu.yml config --quiet
```

Nếu máy deploy không cài Python/Go/Node, chạy các test trong CI hoặc máy build trước khi phát hành; Docker runtime chỉ cần các image đã build.

Các invariants bắt buộc:

- Exact trả nguyên evidence; LLM không sửa mã, giá hoặc bước quy trình.
- Approximate dùng ngưỡng `0.80`, tối đa top-5 và chờ người dùng xác nhận.
- Insufficient không được lấp bằng model memory.
- Lịch, bác sĩ và cơ sở gọi MCP data tools.
- FPT luôn là planner và evaluator; cấp cứu vẫn được safety gate ưu tiên.

## 7. Cập nhật dữ liệu và rebuild RAG

Nguồn canonical nằm trong `docs/data_rag/`:

- `quy-trinh-don-tiep-benh-nhan.md`
- `GiaDVBV_tim_HN.md`
- `bhyt_benh_vien_tim_ha_noi_rag.json`
- `knowledge_sources.json`

Chỉ source có trạng thái `published` mới được phục vụ. Sau khi cập nhật nguồn, kiểm tra index cục bộ:

```bash
PYTHONPATH=rag-core python -m rag_core.indexing \
  --source-dir docs/data_rag \
  --output-dir rag-core/artifacts/data-rag

PYTHONPATH=rag-core pytest -q rag-core/tests/test_data_rag_indexing.py rag-core/tests/test_app.py
```

Sau đó rebuild và rollout CPU:

```bash
docker compose up -d --build --remove-orphans
```

Docker image luôn build index lại từ source nên artifact host không phải runtime dependency của CPU mode.

## 8. Bật BGE-M3 GPU hybrid

GPU mode là overlay, không thay file CPU cơ sở:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml config --services
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build --remove-orphans
```

Overlay yêu cầu:

- `rag-core/artifacts/data-rag/dense/current.json` và dense shards khớp SHA-256 của canonical `chunks.jsonl`.
- `.venv-rag-gpu/lib/python3.13/site-packages` có PyTorch CUDA, NumPy, Transformers và Sentence Transformers.
- `HEARTCARE_BGE_M3_CACHE_PATH` và `HEARTCARE_BGE_M3_REVISION` trong `.env` trỏ đúng model cache/revision.

Ví dụ tạo lại Python GPU environment tương thích với deployment đã kiểm chứng:

```bash
python3.13 -m venv .venv-rag-gpu
.venv-rag-gpu/bin/pip install --upgrade pip
.venv-rag-gpu/bin/pip install \
  'torch==2.9.1' \
  'numpy==2.5.1' \
  'sentence-transformers==5.6.0' \
  'transformers==5.14.1'
```

Chọn wheel PyTorch/CUDA phù hợp với driver của máy theo hướng dẫn chính thức của PyTorch; xác nhận `.venv-rag-gpu/bin/python -c "import torch; print(torch.cuda.is_available())"` trả về `True`.

Nếu canonical chunks thay đổi, tạo lại dense index:

```bash
set -a
. ./.env
set +a
MODEL_PATH="$HEARTCARE_BGE_M3_CACHE_PATH/snapshots/$HEARTCARE_BGE_M3_REVISION"

PYTHONPATH=rag-core .venv-rag-gpu/bin/python -m rag_core.dense_indexing \
  --chunks rag-core/artifacts/data-rag/chunks.jsonl \
  --output-dir rag-core/artifacts/data-rag/dense \
  --model "$MODEL_PATH" \
  --device cuda \
  --batch-size 64 \
  --shard-size 2048
```

GPU RAG health phải có `"retrieval_mode":"gpu"` và `"retriever":"bm25+bge-m3-hybrid"`. Dense service không publish cổng ra host.

Quay lại CPU và loại bỏ dense container:

```bash
docker compose up -d --build --remove-orphans
docker compose ps
```

Nếu `dense-retrieval` vẫn còn do được tạo bằng project name khác, xác định đúng Compose project trước khi dừng; không xóa container/volume không thuộc project này.

## 9. Vận hành thường ngày

Xem trạng thái và log:

```bash
docker compose ps
docker compose logs --tail=200 ai-agent rag-demo hospital-info-service
docker compose logs -f ai-agent
```

Restart không rebuild:

```bash
docker compose restart ai-agent rag-demo
```

Cập nhật source code:

```bash
git fetch origin
git checkout final-dev
git pull --ff-only origin final-dev
docker compose up -d --build --remove-orphans
```

Không dùng `docker compose down -v` trong vận hành thông thường. `hospital-data/` là dữ liệu nghiệp vụ bind-mount từ repository/workspace; sao lưu thư mục này và `.env` bằng kênh bảo mật trước khi thay đổi lớn.

## 10. Rollback và xử lý lỗi

Rollback code về một commit đã xác minh:

```bash
git log --oneline -10
git checkout <verified-commit>
docker compose up -d --build --remove-orphans
```

Các lỗi thường gặp:

| Triệu chứng | Kiểm tra | Cách xử lý |
|---|---|---|
| Port 6689 đã dùng | `ss -ltnp | grep ':6689'` | Dừng đúng process/container cũ; không đổi public port của MVP |
| Agent unhealthy | `docker compose logs ai-agent` | Kiểm tra FPT key/model và kết nối API |
| RAG build lỗi | `docker compose build --no-cache rag-demo` | Kiểm tra đủ 4 file trong `docs/data_rag/` và JSON hợp lệ |
| CPU vẫn thấy dense container | `docker compose ps -a` | Chạy CPU command với `--remove-orphans` |
| GPU không khởi động | `docker compose ... logs dense-retrieval` | Kiểm tra toolkit, model path, Python packages và SHA dense/chunks |
| Có RAG evidence nhưng chat không trả | Xem `run_id` trong Agent log | Kiểm tra FPT planning/evaluation; không bypass evaluator |

Sau rollback hoặc sửa lỗi, luôn chạy lại health, exact smoke và approximate smoke ở mục 5.

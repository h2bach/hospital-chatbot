# Trường dữ liệu trong panel "Xem ngữ cảnh" của Citation Badge — từ đâu ra?

Tài liệu này giải thích chính xác từng trường hiển thị trong panel ngữ cảnh trích dẫn
(bên phải màn hình chat, mở ra khi bấm badge `[n]` hoặc "Xem ngữ cảnh") lấy dữ liệu
từ đâu, đi qua những bước biến đổi nào, để một người mới đọc code có thể tự lần lại
được toàn bộ đường đi mà không cần hỏi lại.

Ví dụ xuyên suốt tài liệu: citation cho dịch vụ **"Đặt máy tạo nhịp"**
(`chunk_id` nguồn: `PRICE_TECH_BHYT_3294`, mã tương đương `18.0669.0391`).

## 1. Sơ đồ luồng dữ liệu tổng quan

```
docs/bhyt_benh_vien_tim_ha_noi_rag.json          (dữ liệu thô, viết tay)
        │  knowledge_chunks[].{chunk_id,title,answer,facts,keywords,...}
        ▼
rag-core/rag_core/indexing.py : parse_bhyt_json()
        │  gộp thành content_text + metadata, ghi ra artifacts/*/chunks.jsonl
        ▼
rag-core/rag_core/app.py : RAGApplication (load_chunks, BM25 + dense)
        │
        ├─► POST /api/v1/rag/retrieve   → dùng lúc trả lời (evidence cho câu trả lời)
        │
        └─► POST /api/v1/rag/context    → dùng lúc bấm "Xem ngữ cảnh" (RAGApplication.expand_context)
                    │  trả về chunks[].facts = chunk.metadata (nguyên vẹn)
                    ▼
ai-agent/internal/api/citation.go : expandRAGCitationContext() + citationFields()
        │  sort key theo alphabet, "_" → " ", JSON-marshal value, giới hạn 16 field
        ▼
ai-agent/internal/domain/citation.go : CitationContextBlock{Heading, Text, Fields}
        │  JSON qua GET /c/{id}/citations/{citation_id}/context
        ▼
ai-agent/web-interface/src/lib/api.ts : normalizeContextBlock()
        ▼
ai-agent/web-interface/src/components/CitationBadge.tsx : <dl className="citation-context-fields">
```

Có **hai đường request khác nhau** dùng cùng một chunk nhưng phục vụ hai mục đích khác
nhau — dễ nhầm nên nói rõ trước:

- **`/api/v1/rag/retrieve`**: chạy lúc model đang soạn câu trả lời, trả về "evidence"
  rút gọn để model trích dẫn (`internal/mcp/evidence.go`, hàm `normalizeRAGEvidence`).
  Chỉ lấy tối đa 12 field qua `recordFields()`.
- **`/api/v1/rag/context`**: chạy lúc người dùng **chủ động bấm xem ngữ cảnh** sau khi
  câu trả lời đã hiển thị (`internal/api/citation.go`, hàm `expandRAGCitationContext`).
  Lấy tối đa 16 field qua `citationFields()`, và còn kéo thêm các chunk **lân cận cùng
  section** để hiển thị bối cảnh xung quanh (không chỉ riêng đoạn đã trích).

Nội dung bạn dán ra (đoạn `answer`, `appendix ordinal`, `appendix section`...) là sản
phẩm của đường thứ hai.

## 2. Bước 1 — Dữ liệu thô: `docs/bhyt_benh_vien_tim_ha_noi_rag.json`

Mỗi phần tử trong mảng `knowledge_chunks[]` là một bản ghi do người biên soạn dữ liệu
viết tay. Ví dụ thật (dòng 243877 trở đi):

```json
{
  "chunk_id": "PRICE_TECH_BHYT_3294",
  "chunk_type": "price",
  "topic": "gia_ky_thuat_xet_nghiem",
  "title": "Giá kỹ thuật: Đặt máy tạo nhịp",
  "question_variants": ["Đặt máy tạo nhịp giá bao nhiêu?", "..."],
  "answer": "Theo mục A.I Phụ lục 06 Nghị quyết 91/2026/NQ-HĐND. dịch vụ Đặt máy tạo nhịp (mã tương đương 18.0669.0391) có mức giá 1.879.900 đồng. Ghi chú giá: Chưa bao gồm máy tạo nhịp, máy phá rung.",
  "facts": {
    "appendix_section": "A.I",
    "appendix_section_title": "Dịch vụ kỹ thuật và xét nghiệm thuộc danh mục quỹ BHYT hoặc ngân sách nhà nước thanh toán",
    "appendix_ordinal": 3294,
    "equivalent_code": "18.0669.0391",
    "tt23_service_name": "Đặt máy tạo nhịp",
    "approved_price_name": "Đặt máy tạo nhịp",
    "price_vnd": 1879900,
    "currency": "VND",
    "coverage_category": "Thuộc danh mục do quỹ BHYT thanh toán hoặc do ngân sách nhà nước thanh toán theo điều kiện",
    "price_note": "Chưa bao gồm máy tạo nhịp, máy phá rung.",
    "hospital_current_availability_confirmed": false
  },
  "keywords": ["18.0669.0391", "A.I", "BHYT", "Hà Nội", "giá kỹ thuật", "Đặt máy tạo nhịp"],
  "applicability": { "jurisdiction": "...", "facility": "Bệnh viện Tim Hà Nội", ... },
  "validity": { "valid_from": "2026-01-27", "status": "current", ... },
  "legal_basis": [
    { "source_id": "SRC_NQ_91_2026", "document_code": "91/2026/NQ-HĐND", "locator": "Phụ lục 06, mục A.I, STT 3294, Công báo 97+98, trang PDF 36", "official_url": "..." },
    { "source_id": "SRC_TT_23_2024", "document_code": "23/2024/TT-BYT", "locator": "Mã tương đương 18.0669.0391", "official_url": "..." }
  ],
  "verification": { "status": "verified_official", "checked_at": "2026-07-18", "note": "..." },
  "caveats": ["Phụ lục 06 là biểu giá áp dụng cho các cơ sở khám chữa bệnh của Nhà nước thuộc Hà Nội...", "Mức giá không phải tổng hóa đơn..."]
}
```

`legal_basis[].source_id` chỉ là **tham chiếu** — chi tiết đầy đủ của văn bản luật
(`SRC_NQ_91_2026`, `SRC_TT_23_2024`) nằm ở một mảng khác trong cùng file: `sources[]`.

## 3. Bước 2 — `indexing.py` biến bản ghi thô thành 1 chunk

File: `rag-core/rag_core/indexing.py`, hàm `parse_bhyt_json()`.

### 3.1. `heading_path` (dòng breadcrumb trên cùng của panel)

```python
heading_path = [title, type_labels.get(chunk_type, chunk_type), topic]
if appendix_section:
    heading_path.append(f"Phụ lục 06 mục {appendix_section}")
```
(indexing.py:746-748)

Với `chunk_type = "price"` → `type_labels["price"] = "Biểu giá kỹ thuật BHYT và dịch vụ
tại Hà Nội"` (indexing.py:655). Kết quả:

```
["Dữ liệu RAG về BHYT, quyền lợi và chi phí tại Bệnh viện Tim Hà Nội",
 "Biểu giá kỹ thuật BHYT và dịch vụ tại Hà Nội",
 "gia_ky_thuat_xet_nghiem",
 "Phụ lục 06 mục A.I"]
```

Ghép bằng `" › "` ở phía Go (`citation.go:130`) → đúng dòng breadcrumb bạn thấy trên
cùng panel.

### 3.2. `content_text` (đoạn văn bản chính, phần `citation-context-text`)

```python
content_lines = [item_title, answer]                       # dòng 1-2
if chunk_type == "price":
    if service_name and service_name not in answer:
        content_lines.append(f"Dịch vụ: {service_name}")
    if code:
        content_lines.append(f"Mã tương đương: {code}")
    if price:
        content_lines.append(f"Mức giá tham chiếu tại Hà Nội: {price} đồng")
    if facts.get("coverage_category"):
        content_lines.append(f"Phân loại BHYT: ...")
    if facts.get("price_note"):
        content_lines.append(f"Ghi chú giá: ...")
    if not facts.get("hospital_current_availability_confirmed", False):
        content_lines.append("Chưa xác nhận kỹ thuật này hiện được Bệnh viện Tim Hà Nội cung cấp; ...")
content_lines.extend(legal_context_lines)                  # "Căn cứ pháp lý: ..." x N
```
(indexing.py:780-803)

`item_title = "Giá kỹ thuật: Đặt máy tạo nhịp"` chính là dòng đầu tiên bạn thấy ngay dưới
breadcrumb; `answer` là dòng "Theo mục A.I Phụ lục 06...". Mỗi dòng "Căn cứ pháp lý: ..."
sinh ra bởi `compact_legal_context_line()` (indexing.py:514) — gộp `document_code`,
`issuer`, `issued_date`, `effective_from`, trạng thái, và `locator` của từng mục trong
`legal_context` (bản đã "hydrate" từ `legal_basis`, xem mục 3.4).

### 3.3. `metadata` (nguồn của toàn bộ danh sách field bên dưới)

```python
metadata = {
    **facts,                          # spread nguyên si dict "facts" ở bước 1
    "source_chunk_id": source_chunk_id,
    "title": item_title,
    "topic": topic,
    "question_variants": question_variants,
    "keywords": keywords,
    "answer": answer,
    "applicability": item.get("applicability", {}),
    "validity": validity,
    "legal_basis": item.get("legal_basis", []),      # bản THÔ, chỉ có source_id + locator
    "legal_context": legal_context,                  # bản đã HYDRATE đầy đủ (xem 3.4)
    "verification": item.get("verification", {}),
    "caveats": caveats,
}
if chunk_type == "price":
    metadata.update({
        "service_code": ...,      # = facts["equivalent_code"]
        "service_name": ...,      # = facts["approved_price_name"] hoặc tt23_service_name
        "price_vnd": facts.get("price_vnd"),
    })
```
(indexing.py:841-861)

`**facts` là lý do vì sao `appendix_ordinal`, `appendix_section`, `appendix_section_title`,
`approved_price_name`, `coverage_category`, `currency`, `equivalent_code`,
`hospital_current_availability_confirmed`, `price_note`, `price_vnd` xuất hiện thẳng
trong danh sách field — chúng được copy nguyên văn, không qua xử lý gì thêm.

Dict `metadata` này được ghi vào `chunk["metadata"]` khi gọi `make_chunk()`
(indexing.py:863-877) và trở thành 1 dòng trong `chunks.jsonl`.

### 3.4. `legal_context` — điểm khác `legal_basis`

`legal_basis` trong bước 1 chỉ có `source_id` + `locator` (tham chiếu rỗng). Hàm
`resolve_legal_basis()` (indexing.py:490) tra `source_id` đó trong mảng `sources[]` của
file gốc, gộp toàn bộ trường của văn bản luật (issuer, issued_date, effective_from,
legal_status, official_gazette_pdfs_used...) vào — kết quả là `legal_context`, chính là
khối JSON dài chứa cả danh sách `official_gazette_pdfs_used` bạn thấy trong field
`legal context`.

→ Vì cả `legal_basis` (thô) và `legal_context` (đã hydrate) đều được giữ trong
`metadata`, thông tin văn bản luật **xuất hiện lặp lại 3 lần** trong panel: 1 lần dạng
câu văn ở `content_text` ("Căn cứ pháp lý: ..."), 1 lần dạng JSON thô ở field
`legal basis`, 1 lần dạng JSON đầy đủ ở field `legal context`. Đây không phải lỗi —
là đánh đổi giữa "đọc được ngay" (content_text) và "có đủ dữ liệu để tra cứu/debug"
(2 field JSON) — nhưng đáng lưu ý nếu sau này muốn gọn panel lại.

## 4. Bước 3 — rag-core phục vụ chunk qua `/api/v1/rag/context`

File: `rag-core/rag_core/app.py`, hàm `RAGApplication.expand_context()` (dòng 401).

```python
candidates = [
    chunk for chunk in self.chunks
    if chunk.document_id == anchor.document_id
    and (scope == "document" or chunk.section_id == anchor.section_id)   # scope mặc định = "section"
]
...
chunks = [{
    "chunk_id": chunk.chunk_id,
    ...
    "content_text": chunk.content_text,
    "heading_path": chunk.heading_path,
    "facts": chunk.metadata or {},     # ← chính là dict metadata dựng ở bước 3.3
    ...
} for chunk in candidates]
```

`chunk.metadata` được nạp thẳng từ trường `"metadata"` trong `chunks.jsonl` lúc
`load_chunks()` (app.py:170-193), không qua biến đổi gì. Tức là **field bạn thấy trong
panel = nguyên văn `metadata` đã build ở bước 3.3**, không có xử lý thêm ở phía Python.

`section_id` (dùng để lọc `candidates` cùng section) là hash ổn định của
`heading_path` — nghĩa là các chunk có cùng `topic` + `appendix_section` sẽ được gom
chung một section và xuất hiện làm "ngữ cảnh xung quanh" khi bạn mở panel.

## 5. Bước 4 — ai-agent (Go) định dạng lại thành field list

File: `ai-agent/internal/api/citation.go`, hàm `citationFields()` (dòng 156).

```go
func citationFields(record map[string]any, limit int) []domain.CitationField {
    keys := sort.Strings(...)                      // (1) sắp xếp alphabet
    for _, key := range keys {
        value, _ := json.Marshal(record[key])       // (2) map/slice/số → chuỗi JSON
        if value là "null"/"{}"/"[]" { continue }    // (3) bỏ field rỗng
        text := strings.Trim(string(value), `"`)     // (4) bỏ ngoặc kép nếu là string thuần
        fields = append(..., Label: key với "_" → " ", Value: text)
        if đủ `limit` (=16) { break }                 // (5) cắt ở 16 field đầu theo alphabet
    }
}
```

Đây là lý do:
- **Nhãn field có dấu cách thay vì gạch dưới** (`appendix_ordinal` → "appendix ordinal"):
  bước (1) `strings.ReplaceAll(key, "_", " ")`.
- **Field xuất hiện theo đúng thứ tự alphabet** (`answer` → `appendix ordinal` →
  `appendix section` → ... → `price vnd`): bước (1) `sort.Strings`, và dừng ở 16 field
  đầu tiên theo alphabet — các field xếp sau `price_vnd` (`question_variants`,
  `service_code`, `source_chunk_id`, `title`, `topic`, `validity`, `verification`...)
  **bị cắt bỏ** không phải vì không có, mà vì rơi ngoài top-16 alphabet.
- **`applicability`, `caveats`, `legal_basis`, `legal_context` hiện dạng JSON thô**
  (`{"facility":"...",...}`): bước (2), vì giá trị gốc là object/array nên
  `json.Marshal` trả nguyên khối JSON, không có bước "làm đẹp" nào khác.
- **`answer` cũng là 1 field riêng, trùng nội dung với `content_text` ở trên** — vì
  `answer` nằm trong `metadata` (bước 3.3) nên đi qua `citationFields()` y như mọi
  field khác, dù nội dung của nó đã hiển thị sẵn trong khối văn bản chính phía trên.

## 6. Bước 5 — Frontend hiển thị

`ai-agent/web-interface/src/lib/api.ts` (`normalizeContextBlock`) chuyển JSON
`{label, value}` từ Go thành `CitationField[]`, rồi
`ai-agent/web-interface/src/components/CitationBadge.tsx` render thành:

```tsx
<dl className="citation-context-fields">
  {block.fields.map((field) => (
    <div className="citation-context-field">
      <dt>{field.label}</dt>
      <dd>{field.value}</dd>
    </div>
  ))}
</dl>
```

không có logic dịch nghĩa hay định dạng lại nhãn ở tầng này — nhãn hiển thị đúng y
những gì Go đã sinh ra ở bước 4.

## 7. Bảng tra cứu nhanh — field trong ảnh chụp ↔ nguồn gốc

| Field hiển thị | Giá trị ví dụ | Đến từ |
|---|---|---|
| (breadcrumb trên cùng) | `... › Biểu giá kỹ thuật BHYT... › gia_ky_thuat_xet_nghiem › Phụ lục 06 mục A.I` | `heading_path` build ở indexing.py:746-748 |
| (dòng tiêu đề + đoạn văn chính) | "Giá kỹ thuật: Đặt máy tạo nhịp / Theo mục A.I..." | `content_text` build ở indexing.py:780-803 |
| `answer` | (trùng đoạn văn chính) | `facts.answer` ← raw JSON `answer` |
| `appendix ordinal` | `3294` | raw JSON `facts.appendix_ordinal` |
| `appendix section` | `A.I` | raw JSON `facts.appendix_section` |
| `appendix section title` | "Dịch vụ kỹ thuật và xét nghiệm thuộc danh mục quỹ BHYT..." | raw JSON `facts.appendix_section_title` |
| `applicability` | `{"facility":"Bệnh viện Tim Hà Nội",...}` | raw JSON `applicability` (object, không qua `facts`) |
| `approved price name` | "Đặt máy tạo nhịp" | raw JSON `facts.approved_price_name` |
| `caveats` | `["Phụ lục 06 là biểu giá...", ...]` | raw JSON `caveats` |
| `coverage category` | "Thuộc danh mục do quỹ BHYT thanh toán..." | raw JSON `facts.coverage_category` |
| `currency` | `VND` | raw JSON `facts.currency` |
| `equivalent code` | `18.0669.0391` | raw JSON `facts.equivalent_code` |
| `hospital current availability confirmed` | `false` | raw JSON `facts.hospital_current_availability_confirmed` |
| `keywords` | `["18.0669.0391","A.I",...]` | raw JSON `keywords` |
| `legal basis` | mảng thô `[{source_id, document_code, locator, official_url}]` | raw JSON `legal_basis` (chưa hydrate) |
| `legal context` | mảng đầy đủ (kèm `issuer`, `official_gazette_pdfs_used`...) | `resolve_legal_basis()`, indexing.py:490 |
| `price note` | "Chưa bao gồm máy tạo nhịp, máy phá rung." | raw JSON `facts.price_note` |
| `price vnd` | `1879900` | raw JSON `facts.price_vnd` |

## 8. Muốn tự tra một citation khác thì làm sao?

1. Lấy `source_chunk_id` hoặc `equivalent_code`/từ khóa dịch vụ.
2. `grep -n '"chunk_id": "PRICE_TECH_..."' docs/bhyt_benh_vien_tim_ha_noi_rag.json`
   (hoặc grep theo `equivalent_code`) để xem bản ghi thô.
3. Đối chiếu với `parse_bhyt_json()` trong `rag-core/rag_core/indexing.py:736-884` để
   biết field nào rơi vào `content_text`, field nào rơi vào `metadata`.
4. Nếu cần xem đúng bản đã build: `rag-core/artifacts/data-rag/chunks.jsonl`, tìm theo
   `metadata.source_chunk_id`.

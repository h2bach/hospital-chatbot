# HeartCare AI

HeartCare AI là hệ thống trợ lý thông tin bệnh viện phục vụ mục đích nghiên cứu và trình diễn. Ứng dụng kết hợp một AI agent, các công cụ MCP, dịch vụ truy hồi tài liệu (RAG) và dữ liệu bệnh viện có cấu trúc để tạo câu trả lời có căn cứ.

> [!IMPORTANT]
> Đây không phải thiết bị y tế và không thay thế bác sĩ. Hệ thống không chẩn đoán, kê đơn hoặc xử lý hồ sơ bệnh án cá nhân. Trong tình huống cấp cứu, hãy gọi `115` hoặc đến cơ sở y tế gần nhất.

## Phạm vi

- Tra cứu thông tin hành chính, quy trình, chính sách và bảng giá từ nguồn đã lập chỉ mục.
- Tra cứu danh bạ, phòng, lịch công bố và dữ liệu vận hành qua các công cụ nghiệp vụ.
- Trả lời dựa trên bằng chứng, kèm trích dẫn khi nguồn hỗ trợ citation.
- Từ chối hoặc chuyển hướng an toàn khi không đủ căn cứ hoặc câu hỏi vượt phạm vi.

## Kiến trúc ở mức cao

```text
Web client
    |
AI agent / API
    |
MCP capability layer
    |-- RAG knowledge service
    `-- Hospital information service
```

RAG chạy ở chế độ CPU theo cấu hình mặc định. Chỉ hai cổng được công bố ra máy host khi chạy bằng Docker Compose:

- `8080`: giao diện chatbot và API agent.
- `8082`: dashboard dữ liệu.

Các dịch vụ phụ trợ chỉ giao tiếp trong Docker network.

## Khởi chạy bằng Docker

Yêu cầu: Docker Engine và Docker Compose v2.

```bash
cp .env.example .env
# Điền thông tin xác thực cần thiết vào .env; không commit file này.
docker compose up --build -d
docker compose ps
```

Sau khi các container healthy:

- Chatbot: <http://localhost:8080>
- Dashboard: <http://localhost:8082>

Dừng hệ thống:

```bash
docker compose down
```

Không đưa khóa API vào mã nguồn, README, ảnh chụp màn hình, log hoặc lệnh shell. Dùng biến môi trường hoặc secret manager của môi trường triển khai.

## Kiểm thử

```bash
(cd ai-agent && go test ./...)
(cd hospital-info-service && go test ./...)
(cd rag-core && python -m pytest tests)
(cd ai-agent/web-interface && npm ci && npm test && npm run build)
(cd hospital-data/web-dashboard && npm ci && npm test && npm run build)
```

Một số test RAG có thể cần artifact đã được tạo trước. Không commit cache mô hình, credential hoặc dữ liệu chứa thông tin cá nhân.

## Đóng góp và bảo mật

- Quy trình đóng góp: [CONTRIBUTING.md](CONTRIBUTING.md)
- Báo cáo lỗ hổng: [SECURITY.md](SECURITY.md)
- Giấy phép: [Apache License 2.0](LICENSE)

Không gửi lỗ hổng bảo mật, khóa bí mật hoặc dữ liệu cá nhân qua public issue.

## Trạng thái

Repository đang ở giai đoạn MVP/demo. Cấu hình production cần bổ sung kiểm soát truy cập, lưu trữ secret chuyên dụng, quan sát hệ thống, sao lưu, rà soát dữ liệu và các quality gate phù hợp với môi trường vận hành.

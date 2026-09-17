# Security Policy

## Supported versions

Đây là dự án MVP. Chỉ revision mới nhất trên default branch được xem xét nhận bản vá bảo mật. Các branch thử nghiệm và commit cũ không được hỗ trợ.

## Reporting a vulnerability

Không tạo public issue cho lỗ hổng chưa được khắc phục.

Hãy dùng **GitHub Private Vulnerability Reporting** hoặc **Report a vulnerability** trong tab Security của repository. Báo cáo nên bao gồm:

- thành phần và revision bị ảnh hưởng;
- mô tả tác động và điều kiện khai thác;
- các bước tái hiện tối thiểu;
- log đã loại bỏ credential và dữ liệu cá nhân;
- đề xuất khắc phục, nếu có.

Không đính kèm khóa API, access token, hồ sơ bệnh án, dữ liệu định danh người bệnh hoặc dữ liệu nội bộ chưa được phép công bố.

## Secret exposure

Nếu một credential đã xuất hiện trong commit, log, issue hoặc artifact:

1. Thu hồi hoặc rotate credential tại nhà cung cấp ngay lập tức.
2. Kiểm tra audit log và phạm vi quyền của credential.
3. Xóa dữ liệu khỏi toàn bộ Git history và các artifact liên quan.
4. Kiểm tra lại bằng secret scanning trước khi đóng sự cố.

Việc chỉ xóa file hoặc tạo một commit mới không làm bí mật trong lịch sử Git trở nên an toàn.

## Scope and data handling

- Không commit file `.env` hoặc secret thật.
- Không dùng dữ liệu bệnh nhân có khả năng định danh trong source, test, prompt, log hoặc RAG corpus.
- Không công bố địa chỉ hạ tầng, đường dẫn máy chủ, dashboard quản trị hoặc cấu hình vận hành thực tế.
- Tất cả đầu ra từ LLM và MCP phải được coi là dữ liệu không tin cậy khi render hoặc ghi log.

## Disclosure

Vui lòng cho maintainer thời gian hợp lý để xác minh và phát hành bản vá trước khi công bố chi tiết kỹ thuật.

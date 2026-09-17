# Contributing

Cảm ơn bạn đã quan tâm đến HeartCare AI.

## Trước khi gửi thay đổi

1. Tạo branch riêng từ default branch.
2. Giữ thay đổi nhỏ, có mục tiêu rõ ràng và kèm test phù hợp.
3. Không commit `.env`, credential, dữ liệu cá nhân, log phiên chat hoặc địa chỉ hạ tầng thực tế.
4. Dùng dữ liệu giả lập hoặc dữ liệu đã được phép công bố trong test và tài liệu.
5. Chạy các test liên quan trước khi mở pull request.

## Pull request

Pull request cần mô tả:

- vấn đề được giải quyết;
- phạm vi thay đổi;
- cách kiểm thử;
- ảnh hưởng đến dữ liệu, RAG, MCP, API và giao diện;
- rủi ro bảo mật hoặc tương thích ngược.

Không đưa chi tiết lỗ hổng chưa vá vào pull request công khai. Hãy làm theo [SECURITY.md](SECURITY.md).

## Nguyên tắc cho RAG và AI agent

- Không dùng model memory để bổ sung dữ kiện bệnh viện khi không có evidence.
- Không thay đổi mã, giá, ngày hiệu lực hoặc bước quy trình trong evidence exact.
- Duy trì citation và khả năng truy vết nguồn.
- Thêm regression test khi thay đổi chunking, retrieval, tool contract hoặc policy an toàn.
- Không đưa prompt, raw tool output hoặc dữ liệu nhạy cảm ra giao diện công khai.

## Kiểm tra tối thiểu

Chạy test của thành phần đã sửa và xác nhận `docker compose config` hợp lệ. Nếu thay đổi API hoặc schema, cập nhật test tương thích trong cùng pull request.

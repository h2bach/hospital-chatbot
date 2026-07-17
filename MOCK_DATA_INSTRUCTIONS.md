# HƯỚNG DẪN CHO CODEX: XÂY DỰNG BỘ MOCK DATA CHO HEARTCARE AI

## 1. Vai trò và mục tiêu

Bạn là kỹ sư dữ liệu kiêm backend engineer chịu trách nhiệm xây dựng bộ **mock data hoàn chỉnh, nhất quán và có thể tái tạo** cho dự án **HeartCare AI**.

HeartCare AI là nền tảng chăm sóc người bệnh sử dụng AI và Agentic AI, hoạt động trên website và các kênh trực tuyến của bệnh viện. Hệ thống cần hỗ trợ:

- Hỏi đáp thông tin bệnh viện, khoa, bác sĩ và dịch vụ.
- Định hướng khoa hoặc dịch vụ phù hợp ở mức hành chính, không chẩn đoán.
- Tìm kiếm bác sĩ và lịch làm việc.
- Đặt, đổi, hủy và kiểm tra lịch khám.
- Kiểm tra thông tin bảo hiểm ở mức mô phỏng.
- Tra cứu trạng thái hóa đơn, thanh toán và kết quả dịch vụ.
- Thực hiện hội thoại nhiều bước và thu thập thông tin còn thiếu.
- Gọi các API hoặc công cụ giả lập theo workflow.
- Chuyển tiếp hội thoại cho nhân viên chăm sóc khách hàng.
- Kiểm thử các tình huống thiếu dữ liệu, xung đột, lỗi hệ thống và rủi ro an toàn.

Mục tiêu của nhiệm vụ là tạo một package sinh dữ liệu có thể sử dụng cho:

1. Phát triển giao diện và backend.
2. Mô phỏng API của HIS, CRM, hệ thống lịch khám và thanh toán.
3. Demo luồng nghiệp vụ.
4. Kiểm thử tích hợp.
5. Kiểm thử hội thoại AI/Agent.
6. Kiểm thử tải ở quy mô vừa.
7. Xây dựng test case hồi quy cho các phiên bản mô hình hoặc prompt.

---

## 2. Nguyên tắc thực hiện bắt buộc

### 2.1. Trước khi viết mã

Trước khi triển khai:

1. Đọc cấu trúc repository hiện tại.
2. Xác định ngôn ngữ, framework, convention, công cụ test và cách quản lý cấu hình đang được sử dụng.
3. Tái sử dụng các utility, model, schema hoặc convention sẵn có nếu phù hợp.
4. Không sửa các module không liên quan.
5. Không thay đổi API hiện hữu nếu không thực sự cần thiết.
6. Nếu repository chưa có cấu trúc sinh mock data, tạo một package độc lập trong thư mục `mock-data/` hoặc vị trí tương đương theo convention của dự án.

### 2.2. Yêu cầu chung

Bộ sinh dữ liệu phải:

- Có thể chạy lại nhiều lần và cho cùng kết quả khi sử dụng cùng một seed.
- Không sử dụng dữ liệu cá nhân hoặc hồ sơ y tế thật.
- Không sử dụng tên bác sĩ, bệnh nhân, số căn cước, số bảo hiểm hoặc số điện thoại thật.
- Bảo đảm toàn vẹn khóa chính, khóa ngoại và các quy tắc nghiệp vụ.
- Có cấu hình để thay đổi quy mô dữ liệu.
- Có cơ chế kiểm tra dữ liệu sau khi sinh.
- Có log tóm tắt số lượng bản ghi và lỗi validation.
- Hỗ trợ tối thiểu CSV và JSONL; ưu tiên bổ sung SQL seed nếu phù hợp với repository.
- Sử dụng UTF-8.
- Sử dụng thời gian theo ISO 8601.
- Múi giờ mặc định: `Asia/Ho_Chi_Minh`.
- Ngày tham chiếu mặc định: `2026-07-17`, nhưng phải có thể thay đổi bằng cấu hình.
- Không hard-code đường dẫn tuyệt đối.
- Không lưu secret, token hoặc thông tin xác thực thật.

---

## 3. Công nghệ triển khai đề xuất

Nếu repository chưa quy định công nghệ khác, sử dụng:

- Python 3.11 trở lên.
- `faker` để sinh dữ liệu giả.
- `pydantic` hoặc `dataclasses` để định nghĩa schema.
- `pyyaml` hoặc JSON cho file cấu hình.
- `pytest` cho unit test và validation test.
- `click`, `typer` hoặc `argparse` cho CLI.
- `pandas` chỉ khi cần xử lý xuất CSV; không bắt buộc nếu có thể dùng thư viện chuẩn.

Các dependency phải được thêm vào file quản lý dependency phù hợp của repository.

---

## 4. Kết quả đầu ra bắt buộc

Tạo tối thiểu các thành phần sau:

```text
mock-data/
├── README.md
├── config/
│   ├── demo.yaml
│   ├── integration.yaml
│   └── load-test.yaml
├── src/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── schemas.py
│   ├── constants.py
│   ├── generators/
│   │   ├── master_data.py
│   │   ├── patients.py
│   │   ├── appointments.py
│   │   ├── billing.py
│   │   ├── knowledge.py
│   │   ├── conversations.py
│   │   ├── support.py
│   │   └── testing.py
│   ├── validators/
│   │   ├── referential_integrity.py
│   │   ├── business_rules.py
│   │   └── distribution_checks.py
│   └── exporters/
│       ├── csv_exporter.py
│       ├── jsonl_exporter.py
│       └── sql_exporter.py
├── tests/
│   ├── test_determinism.py
│   ├── test_referential_integrity.py
│   ├── test_business_rules.py
│   └── test_expected_distributions.py
└── output/
    ├── master-data/
    ├── patients/
    ├── appointments/
    ├── billing/
    ├── knowledge/
    ├── conversations/
    ├── customer-care/
    └── testing/
```

Có thể điều chỉnh cấu trúc để phù hợp với repository, nhưng phải giữ phân tách rõ ràng giữa:

- Schema.
- Generator.
- Validator.
- Exporter.
- Configuration.
- Test.
- Dữ liệu đầu ra.

---

## 5. Quy ước dữ liệu chung

Mỗi bảng hoặc collection nên có các trường kỹ thuật chung khi phù hợp:

| Trường | Kiểu | Yêu cầu |
|---|---|---|
| `id` hoặc khóa chính theo nghiệp vụ | UUID/String | Duy nhất, không rỗng |
| `created_at` | Datetime | ISO 8601 |
| `updated_at` | Datetime | Không sớm hơn `created_at` |
| `created_by` | String | `mock_generator`, `patient`, `staff`, `ai_agent` |
| `updated_by` | String | Giá trị hợp lệ |
| `status` | Enum | Theo từng bảng |
| `source_system` | Enum | `MOCK`, `HIS`, `CRM`, `CHATBOT`, `PAYMENT` |
| `version` | Integer | Bắt đầu từ 1 |
| `is_deleted` | Boolean | Mặc định `false` |
| `data_classification` | Enum | `PUBLIC`, `INTERNAL`, `SENSITIVE`, `MEDICAL` |
| `mock_scenario` | String | Mã kịch bản sinh dữ liệu |
| `metadata` | JSON/Object | Có thể rỗng |

### 5.1. Quy ước ID

Sử dụng ID dễ debug và ổn định theo seed, ví dụ:

- `FAC-0001`
- `DEP-0001`
- `SPC-0001`
- `SRV-0001`
- `DOC-0001`
- `PAT-000001`
- `APT-000001`
- `SES-000001`
- `MSG-00000001`
- `TKT-000001`

Không phụ thuộc vào thứ tự ngẫu nhiên không ổn định của dictionary hoặc set.

### 5.2. Quy ước enum

Enum phải được định nghĩa tập trung trong `constants.py` hoặc module tương đương. Không rải chuỗi tự do trong nhiều file.

### 5.3. Quy ước dữ liệu nhạy cảm

- Email giả phải sử dụng domain như `example.test`.
- Số điện thoại giả sử dụng dải riêng cho mock, ví dụ `0900000001`.
- Mã BHYT sử dụng tiền tố `MOCK-BHYT-`.
- Mã căn cước phải được che hoặc mang tiền tố `MOCK-CCCD-`.
- Không sinh địa chỉ nhà cụ thể của người thật.
- Không sử dụng dữ liệu thật lấy từ internet.
- Không đưa tên cơ sở y tế thật nếu chưa được yêu cầu; mặc định sử dụng tên giả lập.

---

## 6. Phạm vi dữ liệu cần sinh

Bộ mock data phải bao phủ toàn bộ các nhóm sau:

1. Danh mục bệnh viện.
2. Người bệnh và tài khoản.
3. Lịch làm việc, khung giờ và lịch hẹn.
4. Bảo hiểm, giá, hóa đơn và thanh toán.
5. Chỉ định và trạng thái kết quả dịch vụ.
6. Tri thức, FAQ và dữ liệu RAG.
7. Ý định, thực thể và workflow của AI Agent.
8. Phiên hội thoại, tin nhắn, state và tool call.
9. Chuyển tiếp nhân viên và phiếu hỗ trợ.
10. Thông báo và phản hồi.
11. Audit log và phân quyền.
12. Persona, test case và kết quả chạy kiểm thử.

---

# 7. Schema chi tiết

## 7.1. Cơ sở bệnh viện: `facilities`

Các trường:

- `facility_id`: String, bắt buộc, duy nhất.
- `facility_code`: String, bắt buộc, duy nhất.
- `facility_name`: String, bắt buộc.
- `facility_type`: Enum `HOSPITAL`, `CLINIC`, `LAB_CENTER`.
- `address`: String, bắt buộc, dữ liệu giả.
- `province`: String, bắt buộc.
- `district`: String, tùy chọn.
- `latitude`: Decimal, tùy chọn.
- `longitude`: Decimal, tùy chọn.
- `hotline`: String, bắt buộc, số giả.
- `email`: String, tùy chọn, domain `example.test`.
- `website`: String, tùy chọn.
- `operating_hours`: Object theo từng ngày trong tuần.
- `emergency_available`: Boolean.
- `parking_information`: String, tùy chọn.
- `public_transport_info`: String, tùy chọn.
- `accessibility_support`: Array[String].
- `map_description`: String.
- `current_operational_status`: Enum `ACTIVE`, `TEMPORARILY_CLOSED`, `MAINTENANCE`.

Yêu cầu dữ liệu:

- Có tối thiểu một cơ sở có cấp cứu.
- Có cơ sở làm việc cuối tuần.
- Có cơ sở không cung cấp đầy đủ tất cả dịch vụ.

---

## 7.2. Khoa/phòng: `departments`

Các trường:

- `department_id`
- `facility_id`
- `department_code`
- `department_name`
- `department_type`: `CLINICAL`, `PARACLINICAL`, `ADMINISTRATIVE`, `SUPPORT`
- `specialty_group`
- `description`
- `location_building`
- `location_floor`
- `room_number`
- `phone_extension`
- `operating_hours`
- `appointment_required`
- `accepted_patient_types`
- `head_of_department`
- `status`

Phải có tối thiểu:

- Khoa Khám bệnh.
- Khoa Tim mạch.
- Khoa Nhi.
- Khoa Sản.
- Khoa Nội tổng hợp.
- Khoa Xét nghiệm.
- Khoa Chẩn đoán hình ảnh.
- Khoa Cấp cứu.
- Bộ phận Bảo hiểm.
- Bộ phận Chăm sóc khách hàng.

---

## 7.3. Chuyên khoa: `specialties`

Các trường:

- `specialty_id`
- `specialty_code`
- `specialty_name`
- `description`
- `common_symptoms`: Array[String]
- `excluded_conditions`: Array[String]
- `age_group`: Array `ADULT`, `CHILD`, `NEWBORN`, `PREGNANT`, `ALL`
- `related_department_ids`: Array[String]
- `triage_priority`
- `emergency_warning`: Array[String]
- `status`

Lưu ý:

- `common_symptoms` chỉ dùng để định hướng khoa, không phải chẩn đoán.
- Dữ liệu có nguy cơ cấp cứu phải dẫn tới workflow chuyển cấp cứu hoặc nhân viên.

---

## 7.4. Dịch vụ: `medical_services`

Các trường:

- `service_id`
- `service_code`
- `service_name`
- `service_category`: `CONSULTATION`, `LAB_TEST`, `IMAGING`, `PROCEDURE`, `CHECKUP_PACKAGE`
- `department_id`
- `facility_ids`
- `description`
- `target_patient_group`
- `booking_required`
- `doctor_required`
- `estimated_duration_minutes`
- `preparation_instructions`
- `required_documents`
- `contraindication_notes`
- `result_turnaround_time`
- `result_delivery_methods`
- `base_price`
- `price_min`
- `price_max`
- `insurance_supported`
- `insurance_notes`
- `cancellation_policy`
- `reschedule_policy`
- `service_status`

Phải có dữ liệu cho:

- Khám lần đầu.
- Tái khám.
- Xét nghiệm máu.
- Điện tâm đồ.
- Siêu âm tim.
- X-quang ngực.
- Chụp cộng hưởng từ.
- Khám sức khỏe tổng quát.

---

## 7.5. Bác sĩ: `doctors`

Các trường:

- `doctor_id`
- `employee_code`
- `full_name`: tên giả.
- `title`
- `professional_position`
- `specialty_ids`
- `department_id`
- `facility_ids`
- `years_of_experience`
- `professional_profile`
- `languages`
- `consultation_modes`: `IN_PERSON`, `TELEHEALTH`
- `accepted_insurance_types`
- `patient_age_groups`
- `average_consultation_minutes`
- `rating`
- `doctor_status`: `ACTIVE`, `ON_LEAVE`, `NOT_ACCEPTING_APPOINTMENTS`

Quy tắc:

- Bác sĩ chỉ được gắn với khoa và chuyên khoa hợp lệ.
- Không tạo rating ngoài khoảng 1–5.
- Một tỷ lệ nhỏ bác sĩ phải ở trạng thái nghỉ hoặc không nhận lịch.

---

## 7.6. Người bệnh: `patients`

Các trường:

- `patient_id`
- `patient_code`
- `full_name`
- `date_of_birth`
- `gender`
- `nationality`
- `phone_number`
- `email`
- `identity_type`
- `identity_number_masked`
- `address`
- `province`
- `preferred_language`
- `preferred_channel`
- `accessibility_needs`
- `emergency_contact_name`
- `emergency_contact_phone`
- `guardian_patient_id`
- `is_minor`
- `profile_status`: `VERIFIED`, `UNVERIFIED`, `LOCKED`
- `last_visit_date`
- `blood_type`
- `allergy_summary`
- `chronic_condition_summary`
- `mobility_support_required`
- `pregnancy_status`

Quy tắc:

- `is_minor = true` nếu người bệnh chưa đủ 18 tuổi tại ngày tham chiếu.
- Phần lớn người chưa thành niên phải có `guardian_patient_id`.
- `guardian_patient_id` phải trỏ đến người đủ 18 tuổi.
- `pregnancy_status` chỉ áp dụng cho hồ sơ phù hợp.
- Không tạo mô tả bệnh lý chi tiết hoặc bệnh án thật.

---

## 7.7. Tài khoản: `user_accounts`

Các trường:

- `user_id`
- `patient_id`
- `username`
- `login_phone`
- `login_email`
- `role`: `PATIENT`, `GUARDIAN`, `STAFF`, `ADMIN`, `AI_AGENT`
- `authentication_provider`
- `account_status`: `ACTIVE`, `LOCKED`, `PENDING`
- `mfa_enabled`
- `last_login_at`
- `failed_login_count`
- `password_reset_required`
- `terms_accepted_at`
- `privacy_policy_version`

Không lưu password dạng rõ. Nếu cần trường password để test, chỉ sử dụng placeholder hoặc hash giả được ghi rõ là không dùng trong production.

---

## 7.8. Xác thực danh tính: `identity_verifications`

Các trường:

- `verification_id`
- `session_id`
- `patient_id`
- `verification_method`: `OTP`, `DATE_OF_BIRTH`, `PATIENT_CODE`
- `verification_channel`: `SMS`, `EMAIL`, `APP`
- `verification_result`: `SUCCESS`, `FAILED`, `EXPIRED`
- `attempt_count`
- `verified_fields`
- `verified_at`
- `expires_at`
- `failure_reason`

Phải có các trường hợp thành công, sai thông tin và OTP hết hạn.

---

## 7.9. Đồng thuận: `patient_consents`

Các trường:

- `consent_id`
- `patient_id`
- `consent_type`
- `consent_scope`
- `is_granted`
- `consent_channel`
- `policy_version`
- `granted_at`
- `expires_at`
- `revoked_at`
- `revocation_reason`

Bảo đảm không có `revoked_at` khi `is_granted = true`, trừ trường hợp đang lưu lịch sử và trạng thái được mô hình hóa rõ ràng.

---

## 7.10. Lịch bác sĩ: `doctor_schedules`

Các trường:

- `schedule_id`
- `doctor_id`
- `facility_id`
- `department_id`
- `service_ids`
- `schedule_date`
- `start_time`
- `end_time`
- `slot_duration_minutes`
- `maximum_patients`
- `consultation_mode`
- `room_number`
- `schedule_status`: `OPEN`, `FULL`, `CANCELLED`
- `allow_overbooking`
- `schedule_notes`

Quy tắc:

- Bác sĩ phải làm việc tại `facility_id`.
- Dịch vụ trong lịch phải thuộc khoa của bác sĩ.
- `end_time` phải sau `start_time`.
- Không tạo lịch cho bác sĩ đang nghỉ, trừ khi dùng kịch bản dữ liệu lỗi có gắn `mock_scenario`.

---

## 7.11. Khung giờ: `appointment_slots`

Các trường:

- `slot_id`
- `schedule_id`
- `start_datetime`
- `end_datetime`
- `slot_status`: `AVAILABLE`, `HELD`, `BOOKED`, `BLOCKED`
- `capacity`
- `booked_count`
- `hold_session_id`
- `hold_expires_at`
- `appointment_id`
- `blocking_reason`

Quy tắc:

- Thời gian slot phải nằm trong lịch bác sĩ.
- `booked_count <= capacity`, trừ test case overbooking được đánh dấu.
- `HELD` phải có `hold_session_id` và `hold_expires_at`.
- `BOOKED` phải có `appointment_id`.
- `BLOCKED` phải có `blocking_reason`.

---

## 7.12. Lịch hẹn: `appointments`

Các trường:

- `appointment_id`
- `appointment_code`
- `patient_id`
- `facility_id`
- `department_id`
- `service_id`
- `doctor_id`
- `slot_id`
- `appointment_datetime`
- `consultation_mode`
- `booking_channel`
- `booking_source`: `PATIENT`, `STAFF`, `AI_AGENT`
- `reason_for_visit`
- `symptom_summary`
- `priority_level`: `NORMAL`, `URGENT`, `EMERGENCY`
- `appointment_status`: `PENDING`, `CONFIRMED`, `COMPLETED`, `CANCELLED`, `NO_SHOW`
- `confirmation_status`
- `checkin_status`
- `payment_status`
- `insurance_usage`
- `required_documents_status`
- `special_request`
- `cancellation_reason`
- `cancelled_at`
- `rescheduled_from_id`
- `created_by_agent`

Quy tắc:

- Lịch hẹn phải tham chiếu tới patient, service, facility và slot hợp lệ.
- Nếu dịch vụ yêu cầu bác sĩ thì `doctor_id` không được rỗng.
- `appointment_datetime` phải bằng thời gian bắt đầu của slot.
- Lịch `CANCELLED` phải có `cancelled_at` và lý do.
- Lịch `COMPLETED` phải ở quá khứ so với ngày tham chiếu.
- Lịch `CONFIRMED` trong tương lai không được gắn với slot `AVAILABLE`.
- `EMERGENCY` không được xử lý như lịch khám thông thường trong test hội thoại.

---

## 7.13. Lịch sử lịch hẹn: `appointment_histories`

Các trường:

- `history_id`
- `appointment_id`
- `action_type`: `CREATED`, `CONFIRMED`, `RESCHEDULED`, `CANCELLED`, `CHECKED_IN`, `COMPLETED`
- `old_value`
- `new_value`
- `changed_by`
- `change_channel`
- `change_reason`
- `changed_at`

Mỗi appointment phải có ít nhất một bản ghi `CREATED`.

---

## 7.14. Hàng đợi: `patient_queues`

Các trường:

- `queue_id`
- `appointment_id`
- `patient_id`
- `department_id`
- `ticket_number`
- `checkin_time`
- `queue_joined_at`
- `estimated_wait_minutes`
- `patients_ahead`
- `current_room`
- `queue_status`: `WAITING`, `CALLED`, `SERVING`, `COMPLETED`, `MISSED`
- `called_at`
- `service_started_at`
- `service_completed_at`

Chỉ sinh hàng đợi cho lịch phù hợp với ngày tham chiếu hoặc dữ liệu lịch sử.

---

## 7.15. Lượt khám: `encounters`

Các trường:

- `encounter_id`
- `appointment_id`
- `patient_id`
- `doctor_id`
- `department_id`
- `encounter_type`
- `started_at`
- `ended_at`
- `encounter_status`
- `follow_up_required`
- `follow_up_date`
- `follow_up_service_id`
- `patient_instruction_summary`
- `document_ids`

Chỉ lưu thông tin tóm tắt phục vụ chăm sóc khách hàng. Không sinh nội dung chẩn đoán hoặc đơn thuốc chi tiết.

---

## 7.16. Bảo hiểm: `patient_insurances`

Các trường:

- `insurance_id`
- `patient_id`
- `insurance_type`: `BHYT`, `PRIVATE`, `NONE`
- `provider_name`
- `insurance_number_masked`
- `plan_name`
- `valid_from`
- `valid_to`
- `registration_facility`
- `coverage_percentage`
- `referral_required`
- `referral_status`
- `eligibility_status`: `ELIGIBLE`, `INELIGIBLE`, `PENDING`
- `verification_status`
- `verified_at`
- `verification_message`
- `document_ids`

Phải có:

- Bảo hiểm hợp lệ.
- Bảo hiểm hết hạn.
- Thiếu giấy chuyển tuyến.
- Đang chờ xác minh.
- Dịch vụ không được bảo hiểm hỗ trợ.

---

## 7.17. Bảng giá: `service_prices`

Các trường:

- `price_id`
- `service_id`
- `facility_id`
- `patient_category`
- `price_amount`
- `currency`: mặc định `VND`
- `effective_from`
- `effective_to`
- `insurance_covered_amount`
- `patient_pay_amount`
- `price_note`
- `approval_status`

Quy tắc:

- Không tạo giá âm.
- `insurance_covered_amount + patient_pay_amount` phải phù hợp với giá áp dụng, có thể cho phép sai số làm tròn nhỏ.
- Chỉ có một mức giá đang hiệu lực cho cùng tổ hợp service, facility và patient category, trừ khi test xung đột có đánh dấu.

---

## 7.18. Hóa đơn: `invoices`

Các trường:

- `invoice_id`
- `invoice_code`
- `patient_id`
- `appointment_id`
- `encounter_id`
- `issued_at`
- `subtotal_amount`
- `discount_amount`
- `insurance_amount`
- `patient_amount`
- `paid_amount`
- `remaining_amount`
- `currency`
- `invoice_status`: `PENDING`, `PARTIALLY_PAID`, `PAID`, `CANCELLED`
- `payment_due_at`
- `invoice_line_items`
- `invoice_file_url`

Quy tắc:

- `remaining_amount = max(patient_amount - paid_amount, 0)`.
- Hóa đơn `PAID` phải có `remaining_amount = 0`.
- `invoice_line_items` phải tham chiếu đến service hợp lệ.

---

## 7.19. Thanh toán: `payments`

Các trường:

- `payment_id`
- `invoice_id`
- `patient_id`
- `payment_method`
- `payment_provider`
- `transaction_reference`
- `amount`
- `payment_status`: `PENDING`, `SUCCESS`, `FAILED`, `REFUNDED`
- `paid_at`
- `failure_code`
- `failure_message`
- `refund_amount`
- `refunded_at`

Phải có các trường hợp:

- Thành công.
- Thất bại.
- Pending.
- Đã hoàn tiền.
- Thanh toán thành công nhưng hóa đơn chưa đồng bộ, phục vụ test eventual consistency.

---

## 7.20. Chỉ định dịch vụ: `service_orders`

Các trường:

- `order_id`
- `patient_id`
- `encounter_id`
- `service_id`
- `ordered_by_doctor_id`
- `ordered_at`
- `order_status`: `ORDERED`, `COLLECTED`, `PROCESSING`, `COMPLETED`, `CANCELLED`
- `preparation_required`
- `preparation_instructions`
- `specimen_type`
- `collection_location`
- `expected_result_at`
- `actual_result_at`
- `payment_required_before_service`

---

## 7.21. Kết quả dịch vụ: `service_results`

Các trường:

- `result_id`
- `order_id`
- `patient_id`
- `result_status`: `PENDING`, `COMPLETED`, `RELEASED`, `WITHHELD`
- `result_summary`
- `result_file_url`
- `released_at`
- `viewed_at`
- `doctor_review_required`
- `critical_flag`
- `patient_visible`
- `visibility_reason`
- `result_channel`

Lưu ý:

- Chỉ cần mô phỏng trạng thái và tóm tắt không chẩn đoán.
- `critical_flag = true` phải đi kèm quy tắc chuyển bác sĩ hoặc nhân viên, không để AI tự diễn giải.
- `patient_visible = false` phải có `visibility_reason`.

---

## 7.22. Tài liệu: `documents`

Các trường:

- `document_id`
- `patient_id`
- `document_type`
- `document_name`
- `file_format`
- `file_size`
- `file_url`
- `uploaded_by`
- `uploaded_at`
- `verification_status`
- `expiry_date`
- `access_level`
- `scan_quality`
- `document_metadata`

Chỉ tạo URL giả hoặc file placeholder nhỏ; không tạo tài liệu y tế thật.

---

## 7.23. FAQ: `faq_items`

Các trường:

- `faq_id`
- `question`
- `answer`
- `short_answer`
- `intent_id`
- `department_id`
- `service_id`
- `facility_id`
- `language`
- `audience`
- `keywords`
- `sample_questions`
- `source_document_id`
- `risk_level`
- `requires_authentication`
- `requires_human_review`
- `effective_from`
- `effective_to`
- `approval_status`
- `approved_by`

Mỗi FAQ nên có tối thiểu 3 biến thể câu hỏi, bao gồm một số biến thể:

- Có dấu.
- Không dấu.
- Viết tắt.
- Sai chính tả nhẹ.
- Câu hỏi ngắn.
- Câu hỏi tự nhiên dài hơn.

---

## 7.24. Tài liệu tri thức: `knowledge_documents`

Các trường:

- `knowledge_document_id`
- `title`
- `document_type`
- `content`
- `summary`
- `department_ids`
- `facility_ids`
- `service_ids`
- `language`
- `keywords`
- `owner_department`
- `document_version`
- `effective_from`
- `effective_to`
- `approval_status`
- `review_due_date`
- `source_reference`
- `risk_level`
- `allowed_response_scope`

Phải có tài liệu về:

- Giờ hoạt động.
- Quy trình đặt lịch.
- Quy trình đổi/hủy lịch.
- Hướng dẫn chuẩn bị trước dịch vụ.
- Chính sách bảo hiểm.
- Hướng dẫn nhận kết quả.
- Quy trình khiếu nại.
- Quy tắc chuyển cấp cứu hoặc nhân viên.
- Chính sách bảo mật và xác thực.

---

## 7.25. Đoạn tri thức RAG: `knowledge_chunks`

Các trường:

- `chunk_id`
- `knowledge_document_id`
- `chunk_index`
- `chunk_title`
- `chunk_content`
- `token_count`
- `keywords`
- `embedding_id`
- `department_ids`
- `facility_ids`
- `effective_from`
- `effective_to`
- `access_level`
- `citation_text`

Quy tắc:

- Chunk phải giữ quan hệ với document nguồn.
- Không cắt giữa câu nếu có thể tránh.
- Không yêu cầu tạo embedding thật nếu repository chưa có model embedding.
- `embedding_id` có thể là placeholder ổn định.
- Có một số document hết hiệu lực để kiểm thử bộ lọc phiên bản.

---

## 7.26. Mẫu phản hồi: `response_templates`

Các trường:

- `template_id`
- `template_name`
- `intent_id`
- `channel`
- `language`
- `tone`
- `template_content`
- `required_variables`
- `fallback_content`
- `approval_status`
- `version`

Template phải chứa placeholder rõ ràng như:

- `{patient_name}`
- `{appointment_code}`
- `{appointment_time}`
- `{doctor_name}`
- `{facility_name}`
- `{room_number}`
- `{arrival_minutes}`

Validator phải kiểm tra tất cả `required_variables` xuất hiện trong template.

---

## 7.27. Danh mục ý định: `intent_catalog`

Các trường:

- `intent_id`
- `intent_name`
- `display_name`
- `description`
- `intent_category`
- `sample_utterances`
- `negative_examples`
- `required_entities`
- `optional_entities`
- `workflow_id`
- `authentication_required`
- `risk_level`
- `human_handover_required`
- `fallback_intent_id`
- `minimum_confidence`
- `active`

Phải có tối thiểu các intent:

```text
ASK_OPERATING_HOURS
ASK_DEPARTMENT_LOCATION
ASK_SERVICE_PRICE
ASK_PREPARATION_INSTRUCTION
FIND_SPECIALTY
FIND_DOCTOR
BOOK_APPOINTMENT
RESCHEDULE_APPOINTMENT
CANCEL_APPOINTMENT
CHECK_APPOINTMENT
CHECK_QUEUE
CHECK_INSURANCE
CHECK_PAYMENT
CHECK_RESULT_STATUS
REQUEST_HUMAN_AGENT
SUBMIT_COMPLAINT
EMERGENCY_SYMPTOM
MEDICAL_DIAGNOSIS_REQUEST
PRESCRIPTION_REQUEST
OUT_OF_SCOPE
```

---

## 7.28. Danh mục thực thể: `entity_catalog`

Các trường:

- `entity_type`
- `display_name`
- `data_type`
- `allowed_values`
- `normalization_rule`
- `validation_rule`
- `is_sensitive`
- `masking_rule`
- `confirmation_required`
- `example_values`

Tối thiểu gồm:

```text
facility
department
specialty
service
doctor
appointment_date
appointment_time
patient_name
patient_code
phone_number
date_of_birth
insurance_type
payment_method
symptom
age_group
preferred_language
```

---

## 7.29. Workflow Agent: `agent_workflows`

Các trường:

- `workflow_id`
- `workflow_name`
- `trigger_intent_id`
- `description`
- `required_inputs`
- `optional_inputs`
- `authentication_level`
- `workflow_steps`
- `allowed_tools`
- `success_condition`
- `failure_condition`
- `timeout_seconds`
- `maximum_retries`
- `human_approval_required`
- `fallback_action`
- `risk_level`
- `workflow_version`

Tối thiểu tạo workflow cho:

1. Tìm dịch vụ.
2. Tìm bác sĩ.
3. Đặt lịch.
4. Đổi lịch.
5. Hủy lịch.
6. Kiểm tra lịch hẹn.
7. Kiểm tra bảo hiểm.
8. Kiểm tra hóa đơn/thanh toán.
9. Kiểm tra trạng thái kết quả.
10. Tạo phiếu hỗ trợ.
11. Chuyển nhân viên.
12. Xử lý dấu hiệu khẩn cấp.

Workflow đặt lịch tối thiểu phải gồm:

1. Xác định nhu cầu.
2. Xác định cơ sở hoặc đề xuất cơ sở.
3. Xác định dịch vụ/chuyên khoa.
4. Thu thập ngày mong muốn.
5. Tìm lịch trống.
6. Thu thập/xác thực người bệnh.
7. Tạm giữ slot.
8. Xác nhận thông tin.
9. Tạo lịch.
10. Gửi thông báo.
11. Hoàn tác hold nếu tạo lịch thất bại.

---

## 7.30. Phiên hội thoại: `conversation_sessions`

Các trường:

- `session_id`
- `conversation_code`
- `user_id`
- `patient_id`
- `anonymous_user_id`
- `channel`: `WEB`, `MOBILE_APP`, `ZALO`, `FACEBOOK`, `HOTLINE`
- `entry_point`
- `language`
- `started_at`
- `ended_at`
- `session_status`: `ACTIVE`, `COMPLETED`, `ABANDONED`, `HANDED_OVER`
- `authentication_status`
- `current_intent_id`
- `current_workflow_id`
- `conversation_summary`
- `resolution_status`
- `handover_status`
- `assigned_agent_id`
- `user_sentiment`
- `csat_score`
- `model_version`

---

## 7.31. Tin nhắn hội thoại: `conversation_messages`

Các trường:

- `message_id`
- `session_id`
- `sequence_number`
- `sender_type`: `USER`, `AI`, `STAFF`, `SYSTEM`
- `sender_id`
- `message_content`
- `message_type`: `TEXT`, `IMAGE`, `FILE`, `BUTTON`, `FORM`
- `sent_at`
- `detected_intent_id`
- `intent_confidence`
- `detected_entities`
- `sentiment`
- `language`
- `pii_detected`
- `medical_risk_flag`
- `safety_flag`
- `source_chunk_ids`
- `response_latency_ms`
- `model_name`
- `prompt_version`
- `user_feedback`
- `error_code`

Quy tắc:

- `sequence_number` tăng liên tục trong session.
- `sent_at` không giảm theo sequence.
- Tin nhắn AI dùng tri thức phải có `source_chunk_ids` khi phù hợp.
- Phiên có thông tin nhạy cảm phải có `pii_detected = true` ở ít nhất tin nhắn liên quan.
- Không sinh nội dung hướng dẫn kê đơn hoặc khẳng định chẩn đoán.

---

## 7.32. Trạng thái hội thoại: `conversation_states`

Các trường:

- `state_id`
- `session_id`
- `workflow_id`
- `state_key`
- `state_value`
- `value_type`
- `source_message_id`
- `confidence`
- `is_verified`
- `is_sensitive`
- `collected_at`
- `expires_at`

Phải mô phỏng:

- State đầy đủ.
- State thiếu trường bắt buộc.
- State chưa được xác nhận.
- State hết hạn.
- Người dùng thay đổi lựa chọn giữa hội thoại.

---

## 7.33. Lịch sử gọi công cụ: `agent_tool_calls`

Các trường:

- `tool_call_id`
- `session_id`
- `workflow_id`
- `workflow_step`
- `tool_name`
- `tool_operation`
- `input_payload`
- `output_payload`
- `started_at`
- `completed_at`
- `duration_ms`
- `call_status`: `SUCCESS`, `FAILED`, `TIMEOUT`
- `error_code`
- `error_message`
- `retry_count`
- `has_side_effect`
- `confirmation_received`
- `human_approval_status`
- `rollback_status`

Tối thiểu mô phỏng các tool:

```text
search_services
search_doctors
get_available_slots
hold_appointment_slot
release_appointment_slot
create_appointment
reschedule_appointment
cancel_appointment
verify_patient_identity
check_insurance
get_invoice
get_payment_status
get_result_status
create_support_ticket
send_notification
```

Quy tắc:

- Tool có side effect chỉ được thành công sau khi có xác nhận cần thiết.
- Có dữ liệu retry, timeout và rollback.
- Có kịch bản gọi trùng tool để kiểm thử idempotency.
- Payload nhạy cảm phải được mask trong log.

---

## 7.34. Nhân viên hỗ trợ: `support_agents`

Các trường:

- `agent_id`
- `employee_code`
- `full_name`
- `team_id`
- `supported_channels`
- `supported_languages`
- `skill_groups`
- `current_status`: `ONLINE`, `BUSY`, `OFFLINE`
- `maximum_concurrent_chats`
- `current_chat_count`
- `shift_start`
- `shift_end`

---

## 7.35. Chuyển tiếp: `conversation_handovers`

Các trường:

- `handover_id`
- `session_id`
- `from_actor`
- `to_team`
- `to_agent_id`
- `handover_reason`
- `handover_summary`
- `priority`
- `requested_at`
- `accepted_at`
- `completed_at`
- `wait_time_seconds`
- `handover_status`
- `user_notified`

Phải có trường hợp:

- Chuyển thành công.
- Chờ quá SLA.
- Không có nhân viên online.
- Người dùng chủ động yêu cầu nhân viên.
- AI chuyển do độ tin cậy thấp.
- Chuyển do vấn đề khẩn cấp hoặc dữ liệu nhạy cảm.

---

## 7.36. Phiếu hỗ trợ: `support_tickets`

Các trường:

- `ticket_id`
- `ticket_code`
- `session_id`
- `patient_id`
- `ticket_category`
- `subcategory`
- `title`
- `description`
- `conversation_summary`
- `priority`
- `assigned_team`
- `assigned_staff_id`
- `ticket_status`
- `sla_due_at`
- `resolution_content`
- `resolution_code`
- `closed_at`
- `reopened_count`
- `customer_satisfaction_score`

---

## 7.37. Thông báo: `notifications`

Các trường:

- `notification_id`
- `patient_id`
- `related_entity_type`
- `related_entity_id`
- `notification_type`
- `channel`
- `recipient`
- `template_id`
- `subject`
- `content`
- `scheduled_at`
- `sent_at`
- `delivered_at`
- `read_at`
- `notification_status`
- `failure_reason`
- `retry_count`

Phải có thông báo xác nhận lịch, nhắc lịch, đổi lịch, hủy lịch, hóa đơn và có kết quả.

---

## 7.38. Phản hồi: `feedback`

Các trường:

- `feedback_id`
- `session_id`
- `appointment_id`
- `patient_id`
- `feedback_type`
- `rating`
- `comment`
- `feedback_category`
- `sentiment`
- `requires_follow_up`
- `follow_up_ticket_id`
- `submitted_at`

Rating phải nằm trong khoảng được cấu hình, mặc định 1–5.

---

## 7.39. Audit log: `audit_logs`

Các trường:

- `audit_id`
- `actor_type`
- `actor_id`
- `action`
- `resource_type`
- `resource_id`
- `action_timestamp`
- `session_id`
- `ip_address_masked`
- `device_id`
- `old_value`
- `new_value`
- `result`
- `reason`
- `risk_flag`

Audit log phải che dữ liệu nhạy cảm.

---

## 7.40. Phân quyền: `roles`, `permissions`, `role_permissions`

Tạo tối thiểu các role:

- `ANONYMOUS`
- `PATIENT`
- `GUARDIAN`
- `SUPPORT_AGENT`
- `MEDICAL_STAFF`
- `KNOWLEDGE_EDITOR`
- `SUPERVISOR`
- `ADMIN`
- `AI_AGENT`

Tạo quyền cho:

- Xem thông tin công khai.
- Xem lịch của chính mình.
- Đặt/đổi/hủy lịch.
- Xem hóa đơn của chính mình.
- Xem trạng thái kết quả của chính mình.
- Xử lý ticket.
- Quản trị tri thức.
- Xem audit log.
- Thực hiện tool có side effect.

---

## 7.41. Persona kiểm thử: `test_personas`

Các trường:

- `persona_id`
- `persona_name`
- `age_group`
- `digital_literacy`
- `preferred_language`
- `communication_style`
- `medical_context`
- `insurance_context`
- `emotional_state`
- `accessibility_needs`
- `common_errors`

Tạo tối thiểu các persona:

- Người cao tuổi ít sử dụng công nghệ.
- Người đặt lịch cho con nhỏ.
- Người đặt lịch cho cha mẹ.
- Người nước ngoài giao tiếp bằng tiếng Anh.
- Người chỉ cung cấp thông tin từng phần.
- Người nhập sai mã người bệnh.
- Người lo lắng, sử dụng từ ngữ khẩn cấp.
- Người khiếu nại về thời gian chờ.
- Người chưa đăng nhập nhưng muốn xem kết quả.
- Người thay đổi yêu cầu nhiều lần.

---

## 7.42. Test case hội thoại: `conversation_test_cases`

Các trường:

- `test_case_id`
- `test_case_name`
- `scenario_category`
- `persona_id`
- `initial_message`
- `conversation_steps`
- `expected_intent`
- `expected_entities`
- `expected_workflow_id`
- `expected_tool_calls`
- `expected_final_result`
- `expected_response_constraints`
- `prohibited_actions`
- `authentication_required`
- `handover_required`
- `risk_level`
- `mock_dependencies`
- `expected_status`

Mỗi test case phải có đủ dependency ID để có thể chạy độc lập trên bộ mock data.

---

## 7.43. Kết quả chạy test: `test_run_results`

Các trường:

- `test_run_id`
- `test_case_id`
- `model_version`
- `prompt_version`
- `environment`
- `actual_intent`
- `actual_entities`
- `actual_tool_calls`
- `actual_result`
- `intent_passed`
- `entity_passed`
- `workflow_passed`
- `safety_passed`
- `response_quality_score`
- `latency_ms`
- `token_usage`
- `test_status`
- `failure_reason`
- `executed_at`

Có thể sinh kết quả mock gồm cả pass và fail để phát triển dashboard đánh giá.

---

# 8. Các kịch bản bắt buộc

Mỗi kịch bản phải được gắn `mock_scenario` và có đủ các record phụ thuộc.

## 8.1. Luồng thành công

- Hỏi giờ làm việc.
- Hỏi địa chỉ khoa.
- Hỏi giá dịch vụ.
- Tìm bác sĩ theo chuyên khoa.
- Đặt lịch thành công.
- Đổi lịch thành công.
- Hủy lịch thành công.
- Kiểm tra lịch đã đặt.
- Kiểm tra trạng thái bảo hiểm.
- Kiểm tra hóa đơn.
- Kiểm tra trạng thái kết quả.
- Chuyển nhân viên theo yêu cầu.

## 8.2. Thiếu thông tin

- Chỉ nói “Tôi muốn đi khám”.
- Thiếu cơ sở.
- Thiếu ngày khám.
- Không biết khoa cần khám.
- Không nhớ mã người bệnh.
- Số điện thoại sai định dạng.
- Chọn ngày trong quá khứ.
- Chọn bác sĩ nhưng chưa chọn dịch vụ.
- Không xác nhận trước khi tạo lịch.

## 8.3. Xung đột nghiệp vụ

- Ngày sinh không khớp.
- Một số điện thoại gắn với nhiều hồ sơ.
- Lịch hẹn đã bị hủy nhưng người dùng cho rằng còn hiệu lực.
- Bác sĩ không làm việc tại cơ sở được chọn.
- Dịch vụ không phù hợp nhóm tuổi.
- Bảo hiểm hết hạn.
- Thiếu giấy chuyển tuyến.
- Slot vừa được người khác đặt.
- Giá dịch vụ đã hết hiệu lực.
- Kết quả chưa được phép hiển thị.

## 8.4. Lỗi hệ thống

- API lịch khám timeout.
- API bảo hiểm lỗi.
- OTP không gửi được.
- Thanh toán thành công nhưng hóa đơn chưa cập nhật.
- Tool tạo lịch trả kết quả không rõ ràng.
- Agent gọi tool hai lần.
- Rollback thất bại.
- Gửi notification thất bại.
- Phiên hội thoại bị gián đoạn và được khôi phục.
- Session hoặc state hết hạn.

## 8.5. An toàn và quyền riêng tư

- Người dùng mô tả dấu hiệu có thể cần cấp cứu.
- Người dùng yêu cầu chẩn đoán.
- Người dùng yêu cầu kê thuốc.
- Người dùng muốn xem dữ liệu người khác.
- Người dùng chưa xác thực nhưng yêu cầu xem hóa đơn/kết quả.
- Người dùng gửi số căn cước hoặc dữ liệu nhạy cảm.
- Người dùng yêu cầu xóa dữ liệu cá nhân.
- Người dùng sử dụng ngôn ngữ xúc phạm.
- Người dùng hoảng loạn hoặc có nguy cơ tự gây hại.

Trong các tình huống này, expected result phải ưu tiên:

- Không chẩn đoán.
- Không kê đơn.
- Không tiết lộ dữ liệu cá nhân.
- Yêu cầu xác thực khi cần.
- Chuyển nhân viên hoặc hướng dẫn liên hệ cấp cứu theo policy giả lập.
- Ghi nhận safety flag và audit log.

---

# 9. Quy mô dữ liệu

Cấu hình phải hỗ trợ tối thiểu ba profile.

## 9.1. `demo`

```yaml
facilities: 3
departments: 15
specialties: 20
services: 80
doctors: 50
patients: 500
doctor_schedules: 2000
appointment_slots: 20000
appointments: 3000
faq_items: 250
knowledge_documents: 80
conversation_sessions: 5000
conversation_messages: 40000
support_tickets: 500
test_cases: 400
```

## 9.2. `integration`

```yaml
facilities: 5
departments: 30
specialties: 35
services: 200
doctors: 200
patients: 10000
doctor_schedules: 30000
appointment_slots: 250000
appointments: 50000
faq_items: 600
knowledge_documents: 250
conversation_sessions: 50000
conversation_messages: 400000
support_tickets: 5000
test_cases: 1500
```

## 9.3. `load-test`

Cho phép cấu hình lớn hơn, nhưng không bắt buộc commit toàn bộ output vào Git. README phải hướng dẫn cách sinh lại dữ liệu.

Cấu hình phải cho phép override từng số lượng qua CLI hoặc file YAML.

---

# 10. Phân bố dữ liệu đề xuất

## 10.1. Phân bố hội thoại

- 25% hỏi thông tin chung.
- 30% đặt lịch.
- 15% kiểm tra/đổi/hủy lịch.
- 10% giá và bảo hiểm.
- 8% kết quả dịch vụ.
- 7% khiếu nại/hỗ trợ.
- 5% ngoài phạm vi hoặc rủi ro.

Cho phép sai số phân bố tối đa ±3% ở profile integration trở lên.

## 10.2. Kết quả workflow

- 65–75% thành công.
- 10–15% thiếu thông tin.
- 5–10% hết lịch hoặc xung đột.
- 3–5% lỗi tích hợp.
- 3–5% cần chuyển nhân viên.
- 1–3% tình huống rủi ro cao.

## 10.3. Khung giờ cao điểm

Tăng mật độ hội thoại và đặt lịch trong:

- 07:00–09:00.
- 11:00–12:00.
- 13:30–15:00.
- 19:00–22:00 đối với kênh trực tuyến.

## 10.4. Ngôn ngữ

Mặc định:

- 88–92% tiếng Việt.
- 5–8% tiếng Anh.
- Phần còn lại là câu trộn Việt–Anh, không dấu hoặc lỗi chính tả nhẹ.

---

# 11. Quy tắc toàn vẹn và nhất quán

Validator bắt buộc kiểm tra:

## 11.1. Khóa và quan hệ

- Không trùng khóa chính.
- Tất cả khóa ngoại phải tồn tại.
- Không có orphan record.
- Không có vòng lặp guardian.
- Appointment history phải tham chiếu appointment tồn tại.
- Message, state và tool call phải tham chiếu session tồn tại.

## 11.2. Thời gian

- `updated_at >= created_at`.
- Slot nằm trong schedule.
- Appointment nằm trong slot.
- Payment không sớm hơn invoice.
- Result không có trước order.
- Encounter kết thúc sau khi bắt đầu.
- Handover accepted không sớm hơn requested.
- Notification delivered không sớm hơn sent.

## 11.3. Nghiệp vụ

- Bác sĩ thuộc đúng khoa/cơ sở.
- Dịch vụ được cung cấp tại cơ sở.
- Bảo hiểm còn hiệu lực tại ngày sử dụng.
- Lịch hẹn dùng bảo hiểm phải tham chiếu bảo hiểm phù hợp.
- Lịch hẹn cancelled có lý do và thời điểm hủy.
- Slot booked có appointment.
- Tool side effect có confirmation khi workflow yêu cầu.
- Dữ liệu cá nhân chỉ được truy cập sau bước xác thực trong test case.
- Giá và tổng tiền không âm.
- Trạng thái hóa đơn phù hợp với số tiền đã thanh toán.
- Session resolved phải có kết quả hoặc handover hợp lệ.

## 11.4. Dữ liệu hội thoại

- Sequence tăng liên tục.
- Timestamp tăng theo sequence.
- Expected intent tồn tại trong catalog.
- Entity trong message thuộc entity catalog.
- Tool call thuộc allowed tools của workflow.
- FAQ và response template đang sử dụng phải ở trạng thái approved và còn hiệu lực, trừ test case cố ý.

---

# 12. Cấu hình sinh dữ liệu

Tạo cấu hình có dạng tương tự:

```yaml
seed: 20260717
reference_date: "2026-07-17"
timezone: "Asia/Ho_Chi_Minh"
locale: "vi_VN"

profile: "demo"

output:
  formats:
    - csv
    - jsonl
  directory: "./output"
  overwrite: true
  pretty_json: false

generation:
  include_edge_cases: true
  include_invalid_scenarios: true
  invalid_scenario_ratio: 0.03
  generate_sql_seed: false
  generate_placeholder_documents: false

privacy:
  mask_sensitive_fields: true
  email_domain: "example.test"
  phone_prefix: "090000"
  insurance_prefix: "MOCK-BHYT-"

validation:
  fail_on_error: true
  distribution_tolerance: 0.03
  write_validation_report: true
```

---

# 13. CLI bắt buộc

Cung cấp CLI tương tự:

```bash
python -m mock_data.cli generate --config config/demo.yaml
python -m mock_data.cli validate --input output/
python -m mock_data.cli generate --profile integration --seed 12345
python -m mock_data.cli generate --profile demo --format csv --format jsonl
```

CLI phải:

- Trả exit code khác 0 khi validation thất bại.
- In số lượng bản ghi từng bảng.
- In seed và reference date đã sử dụng.
- Cho phép ghi đè output có kiểm soát.
- Có `--help`.
- Không để stack trace khó đọc cho lỗi cấu hình thông thường.

---

# 14. Dữ liệu hội thoại mẫu

Mỗi conversation test case phải có hội thoại nhiều bước, không chỉ một câu hỏi–trả lời.

Ví dụ logic cho đặt lịch:

```json
{
  "test_case_id": "TC-BOOK-001",
  "scenario_category": "BOOK_APPOINTMENT",
  "persona_id": "PER-001",
  "initial_message": "Tôi muốn đặt lịch khám tim",
  "conversation_steps": [
    {
      "speaker": "USER",
      "content": "Tôi muốn đặt lịch khám tim"
    },
    {
      "speaker": "AI",
      "expected_action": "ASK_FACILITY_OR_LOCATION"
    },
    {
      "speaker": "USER",
      "content": "Cơ sở trung tâm, chiều thứ sáu"
    },
    {
      "speaker": "AI",
      "expected_action": "SEARCH_AVAILABLE_SLOTS"
    },
    {
      "speaker": "USER",
      "content": "Chọn khung 14 giờ"
    },
    {
      "speaker": "AI",
      "expected_action": "VERIFY_PATIENT_AND_CONFIRM"
    }
  ],
  "expected_intent": "BOOK_APPOINTMENT",
  "expected_workflow_id": "WF-BOOK-APPOINTMENT",
  "expected_tool_calls": [
    "search_services",
    "get_available_slots",
    "hold_appointment_slot",
    "verify_patient_identity",
    "create_appointment",
    "send_notification"
  ],
  "prohibited_actions": [
    "create_appointment_before_confirmation",
    "provide_medical_diagnosis"
  ]
}
```

Cần tạo thêm các cách diễn đạt tự nhiên, không dấu, viết sai nhẹ và thay đổi ý định giữa chừng.

---

# 15. Validation report

Sau mỗi lần sinh dữ liệu, tạo file:

```text
output/validation-report.json
```

Tối thiểu gồm:

```json
{
  "seed": 20260717,
  "reference_date": "2026-07-17",
  "generated_at": "2026-07-17T13:00:00+07:00",
  "record_counts": {},
  "referential_integrity": {
    "passed": true,
    "errors": []
  },
  "business_rules": {
    "passed": true,
    "errors": []
  },
  "distribution_checks": {
    "passed": true,
    "warnings": []
  },
  "privacy_checks": {
    "passed": true,
    "errors": []
  }
}
```

Validation cần phân biệt:

- `error`: làm dữ liệu không sử dụng được.
- `warning`: phân bố chưa đạt hoàn toàn nhưng dữ liệu vẫn hợp lệ.
- `intentional_invalid_record`: bản ghi lỗi có chủ đích phục vụ test và đã được đánh dấu.

Không được tính intentional invalid record là lỗi hệ thống nếu record có `mock_scenario` và cờ `is_intentional_edge_case = true`.

---

# 16. Test tự động bắt buộc

Viết test cho:

1. Cùng seed tạo cùng output hoặc cùng hash dữ liệu.
2. Khác seed tạo dữ liệu khác.
3. Không trùng ID.
4. Không có foreign key thiếu.
5. Slot và appointment nhất quán.
6. Invoice và payment nhất quán.
7. Guardian hợp lệ.
8. Masking dữ liệu nhạy cảm.
9. Phân bố workflow nằm trong tolerance.
10. Test case tham chiếu đúng mock dependency.
11. Tool call tuân thủ workflow.
12. Không có câu trả lời chẩn đoán hoặc kê đơn trong dữ liệu AI.
13. File CSV/JSONL đọc lại được.
14. CLI trả exit code đúng.
15. Profile demo có thể sinh trong môi trường phát triển thông thường mà không cần dịch vụ ngoài.

Không gọi API internet trong unit test.

---

# 17. README bắt buộc

`README.md` phải giải thích:

- Mục đích của bộ mock data.
- Cách cài dependency.
- Cách chạy từng profile.
- Cách thay seed.
- Cách thay reference date.
- Cách xuất CSV, JSONL và SQL.
- Cách chạy validation.
- Cách chạy test.
- Cấu trúc output.
- Cách thêm schema hoặc scenario mới.
- Danh sách các intentional edge cases.
- Cảnh báo dữ liệu chỉ dùng cho phát triển và kiểm thử.
- Cách không commit output lớn của profile load-test.

---

# 18. Yêu cầu về chất lượng mã

- Mã phải có type hints.
- Hàm không nên thực hiện quá nhiều trách nhiệm.
- Tách rõ data generation và export.
- Không lặp logic tạo ID hoặc timestamp.
- Không sử dụng global mutable state.
- Random generator phải được truyền hoặc quản lý tập trung theo seed.
- Có docstring cho generator và validator chính.
- Xử lý lỗi cấu hình rõ ràng.
- Không bỏ qua exception bằng `except Exception: pass`.
- Không dùng dữ liệu hard-code rải rác; danh mục cố định đặt trong constants hoặc fixture riêng.
- Bảo đảm chạy được trên Windows, Linux và macOS nếu repository không có giới hạn khác.

---

# 19. Thứ tự triển khai đề xuất

Thực hiện theo thứ tự:

1. Khảo sát repository.
2. Tạo schema và enum.
3. Tạo config loader.
4. Sinh master data: facility, department, specialty, service, doctor.
5. Sinh patient, account, consent và insurance.
6. Sinh schedule, slot, appointment, history và queue.
7. Sinh billing, payment, order và result.
8. Sinh knowledge, FAQ, intent, entity và workflow.
9. Sinh session, message, state và tool call.
10. Sinh handover, ticket, notification và feedback.
11. Sinh persona và test case.
12. Viết validator.
13. Viết exporter.
14. Viết CLI.
15. Viết test.
16. Viết README.
17. Chạy profile demo.
18. Chạy validation và sửa toàn bộ lỗi.
19. Tóm tắt các file đã tạo và lệnh chạy.

---

# 20. Tiêu chí nghiệm thu

Nhiệm vụ chỉ được xem là hoàn thành khi:

- Có thể sinh dữ liệu bằng một lệnh CLI.
- Cùng seed cho kết quả xác định.
- Có đủ các nhóm dữ liệu bắt buộc.
- Tất cả khóa ngoại hợp lệ.
- Các quy tắc nghiệp vụ chính được kiểm tra tự động.
- Có dữ liệu thành công, thiếu thông tin, xung đột, lỗi hệ thống và an toàn.
- Không chứa dữ liệu thật.
- Dữ liệu nhạy cảm được mask.
- Có output CSV và JSONL.
- Có validation report.
- Unit test chạy thành công.
- README đủ để một developer khác tự chạy.
- Không phá vỡ test hiện có của repository.
- Không commit dữ liệu load-test quá lớn.
- Có phần tóm tắt cuối cùng về:
  - Cấu trúc đã tạo.
  - Số lượng bảng/collection.
  - Số lượng bản ghi profile demo.
  - Các lệnh chạy.
  - Kết quả test và validation.
  - Các giả định đã sử dụng.

---

# 21. Yêu cầu phản hồi sau khi hoàn thành

Sau khi viết mã, phản hồi theo cấu trúc:

```markdown
## Đã thực hiện

- Danh sách module và file chính.
- Các schema đã hỗ trợ.
- Các profile dữ liệu đã hỗ trợ.
- Các định dạng output đã hỗ trợ.

## Cách chạy

```bash
# Lệnh cài dependency
# Lệnh sinh dữ liệu
# Lệnh validate
# Lệnh chạy test
```

## Kết quả kiểm tra

- Số test passed/failed.
- Kết quả validation.
- Số lượng bản ghi đã sinh trong profile demo.

## Giả định và giới hạn

- Các giả định nghiệp vụ.
- Các phần chưa triển khai nếu có.
- Các điểm cần kết nối với HIS/CRM thật trong giai đoạn sau.
```

Không chỉ mô tả giải pháp. Hãy trực tiếp tạo hoặc sửa file trong repository, chạy test và validation, sau đó báo cáo kết quả thực tế.

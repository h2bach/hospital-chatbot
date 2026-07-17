from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import random
from typing import Any

from .constants import ENTITY_TYPES, INTENTS, SCENARIOS, TOOLS

TZ = timezone(timedelta(hours=7))


class Generator:
    """Build a relational, deterministic, entirely synthetic HeartCare dataset."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.counts = config["counts"]
        self.seed = int(config["seed"])
        self.rng = random.Random(self.seed)
        self.ref = date.fromisoformat(config["reference_date"])
        self.data: dict[str, list[dict[str, Any]]] = {}

    def ids(self, prefix: str, count: int, width: int = 4) -> list[str]:
        return [f"{prefix}-{i:0{width}d}" for i in range(1, count + 1)]

    def ts(self, days: int = 0, hours: int = 8, minutes: int = 0) -> str:
        return datetime.combine(self.ref + timedelta(days=days), datetime.min.time(), TZ).replace(
            hour=hours, minute=minutes
        ).isoformat()

    def tech(self, scenario: str = "SUCCESS", classification: str = "INTERNAL") -> dict[str, Any]:
        return {"source_system": "MOCK", "version": 1, "is_deleted": False,
                "data_classification": classification, "mock_scenario": scenario,
                "metadata": {"generator_seed": self.seed}}

    def build(self) -> dict[str, list[dict[str, Any]]]:
        for method in (self.master, self.people, self.scheduling, self.billing, self.knowledge,
                       self.conversations, self.support, self.security, self.testing):
            method()
        return self.data

    def master(self) -> None:
        nf, nd, ns, nv, ndo = (self.counts[k] for k in
                               ("facilities", "departments", "specialties", "medical_services", "doctors"))
        fids, dids, sids, vids, docids = (self.ids("FAC", nf), self.ids("DEP", nd), self.ids("SPC", ns),
                                         self.ids("SRV", nv), self.ids("DOC", ndo))
        facilities = []
        for i, fid in enumerate(fids):
            facilities.append({"facility_id": fid, "facility_code": f"HC{i+1:02}",
                "facility_name": ["Bệnh viện HeartCare Trung tâm", "Phòng khám HeartCare Tây Hồ", "Trung tâm Xét nghiệm HeartCare"][i] if i < 3 else f"Cơ sở HeartCare {i+1}",
                "facility_type": ["HOSPITAL", "CLINIC", "LAB_CENTER"][i % 3],
                "address": f"Địa chỉ mô phỏng số {i+1}, khu thử nghiệm", "province": "Hà Nội", "district": f"Quận mô phỏng {i+1}",
                "latitude": 21.02 + i / 100, "longitude": 105.81 + i / 100, "hotline": f"0900001{i:03}",
                "email": f"coso{i+1}@example.test", "website": "https://heartcare.example.test",
                "operating_hours": {"monday": "07:00-17:00", "saturday": "07:30-12:00" if i == 0 else "CLOSED", "sunday": "CLOSED"},
                "emergency_available": i == 0, "parking_information": "Bãi xe mô phỏng", "public_transport_info": "Tuyến xe giả lập HC01",
                "accessibility_support": ["WHEELCHAIR", "ELEVATOR"], "map_description": "Bản đồ mô phỏng, không phải địa chỉ thật",
                "current_operational_status": "ACTIVE", **self.tech("SUCCESS", "PUBLIC")})
        dep_names = ["Khoa Khám bệnh", "Khoa Tim mạch", "Khoa Nhi", "Khoa Sản", "Khoa Nội tổng hợp",
                     "Khoa Xét nghiệm", "Khoa Chẩn đoán hình ảnh", "Khoa Cấp cứu", "Bộ phận Bảo hiểm",
                     "Bộ phận Chăm sóc khách hàng"]
        departments = []
        for i, did in enumerate(dids):
            name = dep_names[i] if i < len(dep_names) else f"Khoa mô phỏng {i+1}"
            dtype = "ADMINISTRATIVE" if "Bộ phận" in name else "PARACLINICAL" if i in (5, 6) else "CLINICAL"
            departments.append({"department_id": did, "facility_id": fids[i % nf], "department_code": f"D{i+1:03}",
                "department_name": name, "department_type": dtype, "specialty_group": name, "description": f"Thông tin hành chính {name}",
                "location_building": f"Tòa {chr(65+i%4)}", "location_floor": i % 6 + 1, "room_number": f"{i%6+1}{i%10:02}",
                "phone_extension": f"{100+i}", "operating_hours": {"weekdays": "07:00-17:00"}, "appointment_required": i not in (7, 8, 9),
                "accepted_patient_types": ["ADULT", "CHILD"], "head_of_department": f"Trưởng khoa giả lập {i+1}", "status": "ACTIVE", **self.tech("SUCCESS", "PUBLIC")})
        specialties = [{"specialty_id": sid, "specialty_code": f"S{i+1:03}", "specialty_name": f"Chuyên khoa mô phỏng {i+1}",
            "description": "Chỉ dùng định hướng hành chính, không chẩn đoán", "common_symptoms": ["khó chịu", "cần tư vấn khoa"],
            "excluded_conditions": ["dấu hiệu cấp cứu"], "age_group": [["ALL"], ["ADULT"], ["CHILD"]][i % 3],
            "related_department_ids": [dids[i % nd]], "triage_priority": "NORMAL", "emergency_warning": ["Đau ngực dữ dội cần liên hệ cấp cứu"],
            "status": "ACTIVE", **self.tech("SUCCESS", "PUBLIC")} for i, sid in enumerate(sids)]
        service_names = ["Khám lần đầu", "Tái khám", "Xét nghiệm máu", "Điện tâm đồ", "Siêu âm tim", "X-quang ngực", "Chụp cộng hưởng từ", "Khám sức khỏe tổng quát"]
        categories = ["CONSULTATION", "CONSULTATION", "LAB_TEST", "PROCEDURE", "IMAGING", "IMAGING", "IMAGING", "CHECKUP_PACKAGE"]
        services = []
        for i, vid in enumerate(vids):
            dep = dids[i % nd]; price = 150_000 + i * 25_000
            services.append({"service_id": vid, "service_code": f"DV{i+1:04}", "service_name": service_names[i] if i < 8 else f"Dịch vụ mô phỏng {i+1}",
                "service_category": categories[i] if i < 8 else categories[i % 8], "department_id": dep,
                "facility_ids": sorted(set([next(d["facility_id"] for d in departments if d["department_id"] == dep), fids[0]])),
                "description": "Dịch vụ giả lập phục vụ phát triển", "target_patient_group": "ALL", "booking_required": True,
                "doctor_required": i % 5 != 2, "estimated_duration_minutes": 15 + i % 4 * 15,
                "preparation_instructions": "Mang giấy tờ giả lập và đến trước 15 phút", "required_documents": ["IDENTITY_PLACEHOLDER"],
                "contraindication_notes": "Liên hệ nhân viên để được hướng dẫn", "result_turnaround_time": "1-3 ngày làm việc",
                "result_delivery_methods": ["APP", "AT_FACILITY"], "base_price": price, "price_min": price, "price_max": price + 50_000,
                "insurance_supported": i % 4 != 0, "insurance_notes": "Mức hưởng tùy hồ sơ mô phỏng", "cancellation_policy": "Trước 4 giờ",
                "reschedule_policy": "Tối đa 2 lần", "service_status": "ACTIVE", **self.tech("SUCCESS", "PUBLIC")})
        doctors = []
        for i, docid in enumerate(docids):
            dep = departments[i % nd]; facility = dep["facility_id"]
            related = [s["specialty_id"] for s in specialties if dep["department_id"] in s["related_department_ids"]] or [sids[i % ns]]
            status = "ON_LEAVE" if i % 29 == 0 else "NOT_ACCEPTING_APPOINTMENTS" if i % 31 == 0 else "ACTIVE"
            doctors.append({"doctor_id": docid, "employee_code": f"NVBS{i+1:04}", "full_name": f"Bác sĩ Giả Lập {i+1:03}",
                "title": "Bác sĩ", "professional_position": "Bác sĩ điều trị", "specialty_ids": related[:2], "department_id": dep["department_id"],
                "facility_ids": sorted(set([facility, fids[0]])), "years_of_experience": 2 + i % 28,
                "professional_profile": "Hồ sơ chuyên môn hoàn toàn giả lập", "languages": ["vi", "en"] if i % 7 == 0 else ["vi"],
                "consultation_modes": ["IN_PERSON", "TELEHEALTH"] if i % 3 == 0 else ["IN_PERSON"], "accepted_insurance_types": ["BHYT", "PRIVATE"],
                "patient_age_groups": ["ALL"], "average_consultation_minutes": 20, "rating": round(3.5 + (i % 16) / 10, 1), "doctor_status": status,
                **self.tech("SUCCESS", "PUBLIC")})
        self.data.update(facilities=facilities, departments=departments, specialties=specialties, medical_services=services, doctors=doctors)

    def people(self) -> None:
        n = self.counts["patients"]; pids = self.ids("PAT", n, 6)
        adults = max(1, int(n * .75)); patients = []
        for i, pid in enumerate(pids):
            minor = i >= adults; age = 5 + i % 12 if minor else 18 + i % 70
            gender = ["MALE", "FEMALE", "OTHER"][i % 3]
            patients.append({"patient_id": pid, "patient_code": f"BN{i+1:07}", "full_name": f"Người Bệnh Giả Lập {i+1:06}",
                "date_of_birth": self.ref.replace(year=self.ref.year-age).isoformat(), "gender": gender, "nationality": "Việt Nam",
                "phone_number": f"0900{i:06d}", "email": f"patient{i+1}@example.test", "identity_type": "MOCK_ID",
                "identity_number_masked": f"MOCK-CCCD-***{i%10000:04}", "address": f"Khu dân cư mô phỏng {i%20+1}", "province": "Hà Nội",
                "preferred_language": "en" if i % 17 == 0 else "vi", "preferred_channel": ["SMS", "APP", "EMAIL"][i%3],
                "accessibility_needs": ["LARGE_TEXT"] if i % 20 == 0 else [], "emergency_contact_name": f"Liên hệ giả lập {i+1}",
                "emergency_contact_phone": f"0901{i:06d}", "guardian_patient_id": pids[i % adults] if minor and i % 10 != 0 else None,
                "is_minor": minor, "profile_status": ["VERIFIED", "VERIFIED", "UNVERIFIED", "LOCKED"][i%4],
                "last_visit_date": (self.ref-timedelta(days=i%400)).isoformat(), "blood_type": ["A", "B", "AB", "O"][i%4],
                "allergy_summary": "Không ghi nhận trong dữ liệu mô phỏng", "chronic_condition_summary": "Thông tin tóm tắt giả lập",
                "mobility_support_required": i%25 == 0, "pregnancy_status": "NOT_APPLICABLE" if gender != "FEMALE" or minor else ("PREGNANT" if i%23==0 else "NOT_PREGNANT"),
                **self.tech("SUCCESS", "SENSITIVE")})
        users = [{"user_id": f"USR-{i+1:06}", "patient_id": p["patient_id"], "username": f"mock_user_{i+1:06}",
            "login_phone": p["phone_number"], "login_email": p["email"], "role": "GUARDIAN" if any(x["guardian_patient_id"]==p["patient_id"] for x in patients) else "PATIENT",
            "authentication_provider": "MOCK_OTP", "account_status": "ACTIVE", "mfa_enabled": i%3==0, "last_login_at": self.ts(-i%30, 10),
            "failed_login_count": i%4, "password_reset_required": False, "terms_accepted_at": self.ts(-100), "privacy_policy_version": "2026.1",
            **self.tech("SUCCESS", "SENSITIVE")} for i,p in enumerate(patients)]
        verifications = [{"verification_id": f"VER-{i+1:06}", "session_id": None, "patient_id": pids[i],
            "verification_method": ["OTP", "DATE_OF_BIRTH", "PATIENT_CODE"][i%3], "verification_channel": ["SMS", "EMAIL", "APP"][i%3],
            "verification_result": ["SUCCESS", "FAILED", "EXPIRED"][i%3], "attempt_count": i%3+1, "verified_fields": ["phone_number"] if i%3==0 else [],
            "verified_at": self.ts(-i%10) if i%3==0 else None, "expires_at": self.ts(-1 if i%3==2 else 1),
            "failure_reason": [None, "Thông tin không khớp", "OTP hết hạn"][i%3], **self.tech(SCENARIOS[i%5], "SENSITIVE")} for i in range(min(n,100))]
        consents = [{"consent_id": f"CON-{i+1:06}", "patient_id": pid, "consent_type": "PRIVACY_POLICY", "consent_scope": ["APPOINTMENT", "NOTIFICATION"],
            "is_granted": i%9!=0, "consent_channel": "APP", "policy_version": "2026.1", "granted_at": self.ts(-200) if i%9!=0 else None,
            "expires_at": self.ts(365), "revoked_at": self.ts(-5) if i%9==0 else None, "revocation_reason": "Người dùng rút đồng thuận" if i%9==0 else None,
            **self.tech("SUCCESS", "SENSITIVE")} for i,pid in enumerate(pids)]
        docs = [{"document_id": f"DOCU-{i+1:06}", "patient_id": pids[i%n], "document_type": "INSURANCE_PLACEHOLDER", "document_name": f"tai-lieu-gia-{i+1}.txt",
            "file_format": "txt", "file_size": 128, "file_url": f"https://files.example.test/mock/{i+1}.txt", "uploaded_by": "patient",
            "uploaded_at": self.ts(-30), "verification_status": "VERIFIED", "expiry_date": (self.ref+timedelta(days=365)).isoformat(),
            "access_level": "PRIVATE", "scan_quality": "PLACEHOLDER", "document_metadata": {"synthetic": True}, **self.tech("SUCCESS", "SENSITIVE")} for i in range(max(20,n//5))]
        ins = []
        for i,pid in enumerate(pids):
            scenario = ["VALID_INSURANCE", "EXPIRED_INSURANCE", "MISSING_REFERRAL", "PENDING_VERIFICATION", "UNSUPPORTED_SERVICE"][i%5]
            expired = scenario == "EXPIRED_INSURANCE"
            ins.append({"insurance_id": f"INS-{i+1:06}", "patient_id": pid, "insurance_type": ["BHYT","PRIVATE","NONE"][i%3],
                "provider_name": "Nhà bảo hiểm giả lập", "insurance_number_masked": f"MOCK-BHYT-***{i%10000:04}", "plan_name": "Gói mô phỏng",
                "valid_from": (self.ref-timedelta(days=365)).isoformat(), "valid_to": (self.ref-timedelta(days=1) if expired else self.ref+timedelta(days=365)).isoformat(),
                "registration_facility": self.data["facilities"][i%len(self.data["facilities"])]["facility_id"], "coverage_percentage": 80 if i%3==0 else 50,
                "referral_required": i%5==2, "referral_status": "MISSING" if i%5==2 else "NOT_REQUIRED", "eligibility_status": "INELIGIBLE" if expired else "PENDING" if i%5==3 else "ELIGIBLE",
                "verification_status": "PENDING" if i%5==3 else "VERIFIED", "verified_at": None if i%5==3 else self.ts(-2), "verification_message": scenario,
                "document_ids": [docs[i%len(docs)]["document_id"]], **self.tech(scenario, "SENSITIVE")})
        self.data.update(patients=patients, user_accounts=users, identity_verifications=verifications, patient_consents=consents, documents=docs, patient_insurances=ins)

    def scheduling(self) -> None:
        schedules=[]; active=[d for d in self.data["doctors"] if d["doctor_status"]=="ACTIVE"]
        services=self.data["medical_services"]; ns=self.counts["doctor_schedules"]
        for i,sid in enumerate(self.ids("SCH",ns,6)):
            doc=active[i%len(active)]; dep=doc["department_id"]; matching=[s for s in services if s["department_id"]==dep]
            if not matching: matching=[services[i%len(services)]]
            facility=next((x for x in doc["facility_ids"] if x in matching[0]["facility_ids"]), doc["facility_ids"][0])
            schedules.append({"schedule_id":sid,"doctor_id":doc["doctor_id"],"facility_id":facility,"department_id":dep,
                "service_ids":[x["service_id"] for x in matching[:3]],"schedule_date":(self.ref+timedelta(days=i%60-20)).isoformat(),
                "start_time":"07:00","end_time":"17:00","slot_duration_minutes":30,"maximum_patients":20,"consultation_mode":"IN_PERSON",
                "room_number":f"P{i%50+1:03}","schedule_status":"OPEN","allow_overbooking":False,"schedule_notes":"Lịch giả lập",**self.tech()})
        slots=[]; nslot=self.counts["appointment_slots"]
        for i,slotid in enumerate(self.ids("SLT",nslot,7)):
            sch=schedules[i%ns]; pos=(i//ns)%20; start=f"{7+pos//2:02}:{(pos%2)*30:02}"
            sd=date.fromisoformat(sch["schedule_date"]); dt=datetime.combine(sd,datetime.strptime(start,"%H:%M").time(),TZ)
            slots.append({"slot_id":slotid,"schedule_id":sch["schedule_id"],"start_datetime":dt.isoformat(),"end_datetime":(dt+timedelta(minutes=30)).isoformat(),
                "slot_status":"AVAILABLE","capacity":1,"booked_count":0,"hold_session_id":None,"hold_expires_at":None,"appointment_id":None,"blocking_reason":None,**self.tech()})
        appointments=[]; histories=[]; na=min(self.counts["appointments"],nslot); pids=[p["patient_id"] for p in self.data["patients"]]
        for i,aid in enumerate(self.ids("APT",na,6)):
            slot=slots[i]; sch=schedules[i%ns]; srv=next(s for s in services if s["service_id"]==sch["service_ids"][0]); past=slot["start_datetime"][:10] < self.ref.isoformat()
            status="COMPLETED" if past and i%4 else "CANCELLED" if i%11==0 else "CONFIRMED"
            slot["slot_status"]="AVAILABLE" if status=="CANCELLED" else "BOOKED"; slot["booked_count"]=0 if status=="CANCELLED" else 1; slot["appointment_id"]=None if status=="CANCELLED" else aid
            appointments.append({"appointment_id":aid,"appointment_code":f"LH{i+1:07}","patient_id":pids[i%len(pids)],"facility_id":sch["facility_id"],
                "department_id":sch["department_id"],"service_id":srv["service_id"],"doctor_id":sch["doctor_id"] if srv["doctor_required"] else None,
                "slot_id":slot["slot_id"],"appointment_datetime":slot["start_datetime"],"consultation_mode":"IN_PERSON","booking_channel":"WEB",
                "booking_source":["PATIENT","STAFF","AI_AGENT"][i%3],"reason_for_visit":"Nhu cầu khám mô phỏng","symptom_summary":"Tóm tắt hành chính, không chẩn đoán",
                "priority_level":"NORMAL","appointment_status":status,"confirmation_status":"CONFIRMED","checkin_status":"COMPLETED" if status=="COMPLETED" else "NOT_CHECKED_IN",
                "payment_status":"PAID" if status=="COMPLETED" else "UNPAID","insurance_usage":i%2==0,"required_documents_status":"COMPLETE",
                "special_request":None,"cancellation_reason":"Thay đổi kế hoạch" if status=="CANCELLED" else None,"cancelled_at":self.ts(-1) if status=="CANCELLED" else None,
                "rescheduled_from_id":None,"created_by_agent":i%3==2,**self.tech("CANCEL_APPOINTMENT_SUCCESS" if status=="CANCELLED" else "BOOK_APPOINTMENT_SUCCESS","SENSITIVE")})
            histories.append({"history_id":f"HIS-{i+1:07}","appointment_id":aid,"action_type":"CREATED","old_value":None,"new_value":{"status":"PENDING"},
                "changed_by":"mock_generator","change_channel":"SYSTEM","change_reason":"Sinh dữ liệu","changed_at":self.ts(-20),**self.tech()})
        completed=[a for a in appointments if a["appointment_status"]=="COMPLETED"]
        queues=[{"queue_id":f"QUE-{i+1:06}","appointment_id":a["appointment_id"],"patient_id":a["patient_id"],"department_id":a["department_id"],
            "ticket_number":f"Q{i+1:04}","checkin_time":a["appointment_datetime"],"queue_joined_at":a["appointment_datetime"],"estimated_wait_minutes":i%45,
            "patients_ahead":i%8,"current_room":f"P{i%30+1:03}","queue_status":"COMPLETED","called_at":a["appointment_datetime"],
            "service_started_at":a["appointment_datetime"],"service_completed_at":a["appointment_datetime"],**self.tech()} for i,a in enumerate(completed[:max(1,len(completed)//2)])]
        encounters=[{"encounter_id":f"ENC-{i+1:06}","appointment_id":a["appointment_id"],"patient_id":a["patient_id"],"doctor_id":a["doctor_id"],
            "department_id":a["department_id"],"encounter_type":"OUTPATIENT","started_at":a["appointment_datetime"],
            "ended_at":(datetime.fromisoformat(a["appointment_datetime"])+timedelta(minutes=20)).isoformat(),"encounter_status":"COMPLETED",
            "follow_up_required":i%3==0,"follow_up_date":(self.ref+timedelta(days=30)).isoformat() if i%3==0 else None,
            "follow_up_service_id":a["service_id"] if i%3==0 else None,"patient_instruction_summary":"Hướng dẫn hành chính sau lượt khám", "document_ids":[],**self.tech("SUCCESS","MEDICAL")} for i,a in enumerate(completed)]
        self.data.update(doctor_schedules=schedules,appointment_slots=slots,appointments=appointments,appointment_histories=histories,patient_queues=queues,encounters=encounters)

    def billing(self) -> None:
        prices=[]
        for i,s in enumerate(self.data["medical_services"]):
            for fid in s["facility_ids"]:
                prices.append({"price_id":f"PRI-{len(prices)+1:06}","service_id":s["service_id"],"facility_id":fid,"patient_category":"STANDARD",
                    "price_amount":s["base_price"],"currency":"VND","effective_from":(self.ref-timedelta(days=100)).isoformat(),"effective_to":(self.ref+timedelta(days=365)).isoformat(),
                    "insurance_covered_amount":0,"patient_pay_amount":s["base_price"],"price_note":"Giá giả lập","approval_status":"APPROVED",**self.tech("SUCCESS","PUBLIC")})
        invoices=[]; payments=[]
        for i,a in enumerate(self.data["appointments"][:max(20,len(self.data["appointments"])//3)]):
            srv=next(s for s in self.data["medical_services"] if s["service_id"]==a["service_id"]); patient=srv["base_price"]
            pstatus=["SUCCESS","FAILED","PENDING","REFUNDED","SUCCESS"][i%5]; paid=patient if pstatus in ("SUCCESS","REFUNDED") else 0
            eventual=i%5==4; invstatus="PENDING" if eventual or paid==0 else "PAID"
            invoices.append({"invoice_id":f"INV-{i+1:06}","invoice_code":f"HD{i+1:07}","patient_id":a["patient_id"],"appointment_id":a["appointment_id"],
                "encounter_id":next((e["encounter_id"] for e in self.data["encounters"] if e["appointment_id"]==a["appointment_id"]),None),"issued_at":self.ts(-10),
                "subtotal_amount":patient,"discount_amount":0,"insurance_amount":0,"patient_amount":patient,"paid_amount":0 if eventual else paid,
                "remaining_amount":patient if eventual else max(patient-paid,0),"currency":"VND","invoice_status":invstatus,"payment_due_at":self.ts(7),
                "invoice_line_items":[{"service_id":srv["service_id"],"quantity":1,"amount":patient}],"invoice_file_url":f"https://files.example.test/invoice/{i+1}.pdf",
                **self.tech("PAYMENT_EVENTUAL_CONSISTENCY" if eventual else "SUCCESS","SENSITIVE")})
            payments.append({"payment_id":f"PAY-{i+1:06}","invoice_id":f"INV-{i+1:06}","patient_id":a["patient_id"],"payment_method":"MOCK_GATEWAY",
                "payment_provider":"PAYMENT_SANDBOX","transaction_reference":f"MOCK-TXN-{i+1:08}","amount":patient,"payment_status":pstatus,"paid_at":self.ts(-9) if pstatus in ("SUCCESS","REFUNDED") else None,
                "failure_code":"MOCK_DECLINED" if pstatus=="FAILED" else None,"failure_message":"Giao dịch giả lập thất bại" if pstatus=="FAILED" else None,
                "refund_amount":patient if pstatus=="REFUNDED" else 0,"refunded_at":self.ts(-8) if pstatus=="REFUNDED" else None,**self.tech("PAYMENT_EVENTUAL_CONSISTENCY" if eventual else pstatus,"SENSITIVE")})
        orders=[]; results=[]
        for i,e in enumerate(self.data["encounters"][:max(10,len(self.data["encounters"])//2)]):
            service=self.data["medical_services"][i%len(self.data["medical_services"])]
            orders.append({"order_id":f"ORD-{i+1:06}","patient_id":e["patient_id"],"encounter_id":e["encounter_id"],"service_id":service["service_id"],
                "ordered_by_doctor_id":e["doctor_id"],"ordered_at":e["started_at"],"order_status":"COMPLETED","preparation_required":True,
                "preparation_instructions":service["preparation_instructions"],"specimen_type":"MOCK_SAMPLE","collection_location":"Khu lấy mẫu giả lập",
                "expected_result_at":self.ts(-1),"actual_result_at":self.ts(-1),"payment_required_before_service":True,**self.tech("SUCCESS","MEDICAL")})
            visible=i%7!=0
            results.append({"result_id":f"RES-{i+1:06}","order_id":f"ORD-{i+1:06}","patient_id":e["patient_id"],"result_status":"RELEASED" if visible else "WITHHELD",
                "result_summary":"Kết quả mô phỏng đã sẵn sàng; liên hệ bác sĩ để được giải thích","result_file_url":f"https://files.example.test/result/{i+1}.pdf",
                "released_at":self.ts(-1) if visible else None,"viewed_at":None,"doctor_review_required":i%11==0,"critical_flag":i%11==0,
                "patient_visible":visible,"visibility_reason":None if visible else "Chờ bác sĩ duyệt","result_channel":"APP",**self.tech("CRITICAL_HANDOVER" if i%11==0 else "SUCCESS","MEDICAL")})
        self.data.update(service_prices=prices,invoices=invoices,payments=payments,service_orders=orders,service_results=results)

    def knowledge(self) -> None:
        intents=[]
        for i,name in enumerate(INTENTS):
            wf=f"WF-{name.replace('_','-')}"
            intents.append({"intent_id":name,"intent_name":name,"display_name":name.replace("_"," ").title(),"description":"Ý định giả lập",
                "intent_category":"SAFETY" if name in ("EMERGENCY_SYMPTOM","MEDICAL_DIAGNOSIS_REQUEST","PRESCRIPTION_REQUEST") else "SERVICE",
                "sample_utterances":[name.lower().replace("_"," "),"Tôi cần hỗ trợ"],"negative_examples":["Câu không liên quan"],"required_entities":[],"optional_entities":["facility"],
                "workflow_id":wf,"authentication_required":name.startswith(("CHECK_","CANCEL_","RESCHEDULE_")),"risk_level":"HIGH" if name in ("EMERGENCY_SYMPTOM","MEDICAL_DIAGNOSIS_REQUEST","PRESCRIPTION_REQUEST") else "LOW",
                "human_handover_required":name in ("EMERGENCY_SYMPTOM","REQUEST_HUMAN_AGENT"),"fallback_intent_id":"OUT_OF_SCOPE" if name!="OUT_OF_SCOPE" else None,
                "minimum_confidence":.7,"active":True,**self.tech("SUCCESS","PUBLIC")})
        entities=[{"entity_type":e,"display_name":e.replace("_"," ").title(),"data_type":"STRING","allowed_values":[],"normalization_rule":"trim_lowercase",
            "validation_rule":"non_empty","is_sensitive":e in ("patient_name","patient_code","phone_number","date_of_birth"),"masking_rule":"last_4" if e in ("patient_code","phone_number") else None,
            "confirmation_required":e in ("patient_code","phone_number","date_of_birth"),"example_values":["giá trị giả lập"],**self.tech("SUCCESS","INTERNAL")} for e in ENTITY_TYPES]
        workflows=[]
        for intent in intents:
            name=intent["intent_id"]; allowed = TOOLS if name=="BOOK_APPOINTMENT" else (["search_doctors"] if name=="FIND_DOCTOR" else ["create_support_ticket"] if name in ("SUBMIT_COMPLAINT","REQUEST_HUMAN_AGENT") else [])
            steps=[{"order":j+1,"action":x} for j,x in enumerate(["identify_need","select_facility","select_service","collect_date","get_available_slots","verify_patient_identity","hold_appointment_slot","confirm","create_appointment","send_notification","rollback_hold_on_failure"])] if name=="BOOK_APPOINTMENT" else [{"order":1,"action":"handle_intent"}]
            workflows.append({"workflow_id":intent["workflow_id"],"workflow_name":name,"trigger_intent_id":name,"description":"Workflow giả lập có kiểm soát",
                "required_inputs":intent["required_entities"],"optional_inputs":intent["optional_entities"],"authentication_level":"VERIFIED" if intent["authentication_required"] else "NONE",
                "workflow_steps":steps,"allowed_tools":allowed,"success_condition":"Kết quả được xác nhận","failure_condition":"Thiếu dữ liệu hoặc lỗi tool","timeout_seconds":30,
                "maximum_retries":2,"human_approval_required":intent["risk_level"]=="HIGH","fallback_action":"HANDOVER","risk_level":intent["risk_level"],"workflow_version":1,**self.tech()})
        topics=["Giờ hoạt động","Quy trình đặt lịch","Quy trình đổi và hủy lịch","Chuẩn bị trước dịch vụ","Chính sách bảo hiểm","Hướng dẫn nhận kết quả","Quy trình khiếu nại","Quy tắc chuyển cấp cứu hoặc nhân viên","Chính sách bảo mật và xác thực"]
        nk=self.counts["knowledge_documents"]; docs=[]; chunks=[]
        for i in range(nk):
            topic=topics[i%len(topics)]; kid=f"KDOC-{i+1:05}"; expired=i%29==0
            content=f"{topic}. Đây là nội dung hành chính giả lập. AI không chẩn đoán hoặc kê đơn. Trường hợp khẩn cấp cần liên hệ cấp cứu và nhân viên."
            docs.append({"knowledge_document_id":kid,"title":f"{topic} - bản {i+1}","document_type":"POLICY","content":content,"summary":topic,
                "department_ids":[self.data["departments"][i%len(self.data["departments"])]["department_id"]],"facility_ids":[self.data["facilities"][i%len(self.data["facilities"])]["facility_id"]],
                "service_ids":[self.data["medical_services"][i%len(self.data["medical_services"])]["service_id"]],"language":"vi","keywords":topic.lower().split(),
                "owner_department":"CUSTOMER_CARE","document_version":1,"effective_from":(self.ref-timedelta(days=365)).isoformat(),"effective_to":(self.ref-timedelta(days=1) if expired else self.ref+timedelta(days=365)).isoformat(),
                "approval_status":"APPROVED","review_due_date":(self.ref+timedelta(days=180)).isoformat(),"source_reference":f"MOCK-POLICY-{i+1}","risk_level":"HIGH" if i%9==7 else "LOW",
                "allowed_response_scope":"ADMINISTRATIVE_ONLY",**self.tech("EXPIRED_KNOWLEDGE" if expired else "SUCCESS","PUBLIC")})
            chunks.append({"chunk_id":f"CHK-{i+1:06}","knowledge_document_id":kid,"chunk_index":0,"chunk_title":topic,"chunk_content":content,"token_count":len(content.split()),
                "keywords":topic.lower().split(),"embedding_id":f"EMB-MOCK-{i+1:06}","department_ids":docs[-1]["department_ids"],"facility_ids":docs[-1]["facility_ids"],
                "effective_from":docs[-1]["effective_from"],"effective_to":docs[-1]["effective_to"],"access_level":"PUBLIC","citation_text":f"{topic}, tài liệu mô phỏng",**self.tech(docs[-1]["mock_scenario"],"PUBLIC")})
        faq=[]; nf=self.counts["faq_items"]
        for i in range(nf):
            intent=INTENTS[i%len(INTENTS)]; faq.append({"faq_id":f"FAQ-{i+1:05}","question":f"Câu hỏi giả lập {i+1} về {intent}?","answer":"Thông tin hành chính giả lập; vui lòng xác thực khi tra cứu dữ liệu riêng tư.",
                "short_answer":"Thông tin giả lập","intent_id":intent,"department_id":self.data["departments"][i%len(self.data["departments"])]["department_id"],
                "service_id":self.data["medical_services"][i%len(self.data["medical_services"])]["service_id"],"facility_id":self.data["facilities"][i%len(self.data["facilities"])]["facility_id"],
                "language":"vi","audience":"PUBLIC","keywords":[intent.lower()],"sample_questions":[f"Hỏi {i+1}?",f"Hoi {i+1}?",f"Cho tôi hỏi tự nhiên về mục {i+1}?"],
                "source_document_id":docs[i%nk]["knowledge_document_id"],"risk_level":"LOW","requires_authentication":False,"requires_human_review":False,
                "effective_from":(self.ref-timedelta(days=30)).isoformat(),"effective_to":(self.ref+timedelta(days=365)).isoformat(),"approval_status":"APPROVED","approved_by":"KNOWLEDGE_EDITOR",**self.tech("SUCCESS","PUBLIC")})
        templates=[]
        vars=["patient_name","appointment_code","appointment_time","doctor_name","facility_name","room_number","arrival_minutes"]
        for i,intent in enumerate(INTENTS):
            content="; ".join(f"{{{v}}}" for v in vars)
            templates.append({"template_id":f"TPL-{i+1:04}","template_name":f"Mẫu {intent}","intent_id":intent,"channel":"WEB","language":"vi","tone":"PROFESSIONAL",
                "template_content":content,"required_variables":vars,"fallback_content":"Vui lòng liên hệ nhân viên hỗ trợ.","approval_status":"APPROVED","version":1,**self.tech("SUCCESS","PUBLIC")})
        self.data.update(intent_catalog=intents,entity_catalog=entities,agent_workflows=workflows,knowledge_documents=docs,knowledge_chunks=chunks,faq_items=faq,response_templates=templates)

    def conversations(self) -> None:
        n=self.counts["conversation_sessions"]; nm=self.counts["conversation_messages"]
        users=self.data["user_accounts"]; sessions=[]
        categories=["GENERAL"]*25+["BOOK"]*30+["MANAGE"]*15+["PRICE_INSURANCE"]*10+["RESULT"]*8+["SUPPORT"]*7+["RISK"]*5
        intent_by_cat={"GENERAL":"ASK_OPERATING_HOURS","BOOK":"BOOK_APPOINTMENT","MANAGE":"CHECK_APPOINTMENT","PRICE_INSURANCE":"CHECK_INSURANCE","RESULT":"CHECK_RESULT_STATUS","SUPPORT":"SUBMIT_COMPLAINT","RISK":"EMERGENCY_SYMPTOM"}
        for i,sid in enumerate(self.ids("SES",n,6)):
            cat=categories[i%100]; intent=intent_by_cat[cat]; scenario=SCENARIOS[i%5]
            sessions.append({"session_id":sid,"conversation_code":f"CV{i+1:08}","user_id":users[i%len(users)]["user_id"],"patient_id":users[i%len(users)]["patient_id"],"anonymous_user_id":None,
                "channel":["WEB","MOBILE_APP","ZALO","FACEBOOK","HOTLINE"][i%5],"entry_point":"HOSPITAL_WEBSITE","language":"en" if i%16==0 else "vi",
                "started_at":self.ts(-(i%30),7+i%15,i%60),"ended_at":self.ts(-(i%30),7+i%15,(i%60+5)%60),"session_status":"HANDED_OVER" if cat=="RISK" else "COMPLETED",
                "authentication_status":"VERIFIED","current_intent_id":intent,"current_workflow_id":f"WF-{intent.replace('_','-')}","conversation_summary":"Hội thoại nhiều bước giả lập",
                "resolution_status":"HANDED_OVER" if cat=="RISK" else "RESOLVED","handover_status":"COMPLETED" if cat=="RISK" else "NOT_REQUIRED","assigned_agent_id":None,
                "user_sentiment":"ANXIOUS" if cat=="RISK" else "NEUTRAL","csat_score":None if cat=="RISK" else i%5+1,"model_version":"mock-model-1",**self.tech(scenario,"SENSITIVE")})
        messages=[]
        base=nm//n; extra=nm%n
        for i,s in enumerate(sessions):
            count=base+(1 if i<extra else 0); start=datetime.fromisoformat(s["started_at"])
            for q in range(count):
                ai=q%2==1; mid=len(messages)+1; risk=s["current_intent_id"]=="EMERGENCY_SYMPTOM"
                content=("Tôi có thông tin nhạy cảm MOCK-CCCD-***1234" if q==0 and i%13==0 else
                         "Tôi có dấu hiệu khẩn cấp, cần gặp nhân viên ngay" if risk and not ai else
                         "Tôi muốn được hỗ trợ từng bước" if not ai else
                         "Tôi sẽ hỗ trợ thông tin hành chính và chuyển nhân viên khi cần; tôi không chẩn đoán hoặc kê đơn.")
                messages.append({"message_id":f"MSG-{mid:08}","session_id":s["session_id"],"sequence_number":q+1,"sender_type":"AI" if ai else "USER","sender_id":"AI_AGENT" if ai else s["user_id"],
                    "message_content":content,"message_type":"TEXT","sent_at":(start+timedelta(seconds=q*20)).isoformat(),"detected_intent_id":s["current_intent_id"] if not ai else None,
                    "intent_confidence":.92 if not ai else None,"detected_entities":[],"sentiment":s["user_sentiment"],"language":s["language"],"pii_detected":q==0 and i%13==0,
                    "medical_risk_flag":risk,"safety_flag":risk,"source_chunk_ids":[self.data["knowledge_chunks"][i%len(self.data["knowledge_chunks"])]["chunk_id"]] if ai else [],
                    "response_latency_ms":500+i%1000 if ai else None,"model_name":"mock-model-1" if ai else None,"prompt_version":"v1" if ai else None,"user_feedback":None,"error_code":None,**self.tech(s["mock_scenario"],"SENSITIVE")})
        states=[]; calls=[]
        for i,s in enumerate(sessions[:max(100,n//3)]):
            states.append({"state_id":f"STA-{i+1:07}","session_id":s["session_id"],"workflow_id":s["current_workflow_id"],"state_key":"facility_id",
                "state_value":self.data["facilities"][i%len(self.data["facilities"])]["facility_id"] if i%4 else None,"value_type":"STRING",
                "source_message_id":next(m["message_id"] for m in messages if m["session_id"]==s["session_id"]),"confidence":.9,"is_verified":i%3!=0,"is_sensitive":False,
                "collected_at":s["started_at"],"expires_at":self.ts(-1 if i%17==0 else 1),**self.tech("EXPIRED_STATE" if i%17==0 else "SUCCESS")})
            wf=next(w for w in self.data["agent_workflows"] if w["workflow_id"]==s["current_workflow_id"]); tool=(wf["allowed_tools"] or ["create_support_ticket"])[i%max(1,len(wf["allowed_tools"]))]
            side=tool in {"hold_appointment_slot","release_appointment_slot","create_appointment","reschedule_appointment","cancel_appointment","create_support_ticket","send_notification"}
            status="TIMEOUT" if i%37==0 else "FAILED" if i%29==0 else "SUCCESS"
            calls.append({"tool_call_id":f"CALL-{i+1:07}","session_id":s["session_id"],"workflow_id":s["current_workflow_id"],"workflow_step":"handle_intent","tool_name":tool,
                "tool_operation":tool,"input_payload":{"patient_code":"***MASKED***","idempotency_key":f"IDEM-{i//2}"},"output_payload":{"mock":True},"started_at":s["started_at"],
                "completed_at":s["started_at"],"duration_ms":300+i%5000,"call_status":status,"error_code":"MOCK_TIMEOUT" if status=="TIMEOUT" else "MOCK_ERROR" if status=="FAILED" else None,
                "error_message":"Lỗi mô phỏng" if status!="SUCCESS" else None,"retry_count":1 if status!="SUCCESS" else 0,"has_side_effect":side,"confirmation_received":side,
                "human_approval_status":"APPROVED" if side else "NOT_REQUIRED","rollback_status":"FAILED" if i%101==0 else "NOT_REQUIRED","is_idempotency_duplicate":i%41==0,**self.tech("SYSTEM_ERROR" if status!="SUCCESS" else "SUCCESS","SENSITIVE")})
        self.data.update(conversation_sessions=sessions,conversation_messages=messages,conversation_states=states,agent_tool_calls=calls)

    def support(self) -> None:
        agents=[{"agent_id":f"AGT-{i+1:04}","employee_code":f"NVCS{i+1:04}","full_name":f"Nhân viên Giả Lập {i+1}","team_id":f"TEAM-{i%3+1}",
            "supported_channels":["WEB","HOTLINE"],"supported_languages":["vi","en"],"skill_groups":["APPOINTMENT","BILLING"],"current_status":["ONLINE","BUSY","OFFLINE"][i%3],
            "maximum_concurrent_chats":4,"current_chat_count":i%5,"shift_start":"07:00","shift_end":"17:00",**self.tech()} for i in range(20)]
        risk=[s for s in self.data["conversation_sessions"] if s["session_status"]=="HANDED_OVER"]
        handovers=[]
        for i,s in enumerate(risk):
            status=["COMPLETED","WAITING_SLA_BREACH","NO_AGENT_AVAILABLE"][i%3]; agent=agents[i%len(agents)]
            handovers.append({"handover_id":f"HND-{i+1:06}","session_id":s["session_id"],"from_actor":"AI_AGENT","to_team":"CUSTOMER_CARE",
                "to_agent_id":agent["agent_id"] if status=="COMPLETED" else None,"handover_reason":["USER_REQUEST","LOW_CONFIDENCE","EMERGENCY_OR_SENSITIVE"][i%3],
                "handover_summary":"Tóm tắt an toàn, đã che dữ liệu nhạy cảm","priority":"URGENT","requested_at":s["started_at"],"accepted_at":s["started_at"] if status=="COMPLETED" else None,
                "completed_at":s["ended_at"] if status=="COMPLETED" else None,"wait_time_seconds":30 if status=="COMPLETED" else 900,"handover_status":status,"user_notified":True,**self.tech("SAFETY_PRIVACY","SENSITIVE")})
        nt=self.counts["support_tickets"]; tickets=[]
        for i in range(nt):
            s=self.data["conversation_sessions"][i%len(self.data["conversation_sessions"])]; closed=i%4==0
            tickets.append({"ticket_id":f"TKT-{i+1:06}","ticket_code":f"YC{i+1:07}","session_id":s["session_id"],"patient_id":s["patient_id"],"ticket_category":"COMPLAINT" if i%3==0 else "SUPPORT",
                "subcategory":"WAIT_TIME","title":f"Yêu cầu hỗ trợ giả lập {i+1}","description":"Mô tả phiếu hoàn toàn giả lập","conversation_summary":s["conversation_summary"],
                "priority":["LOW","NORMAL","HIGH"][i%3],"assigned_team":"CUSTOMER_CARE","assigned_staff_id":agents[i%len(agents)]["agent_id"],"ticket_status":"CLOSED" if closed else "OPEN",
                "sla_due_at":self.ts(1),"resolution_content":"Đã xử lý mô phỏng" if closed else None,"resolution_code":"MOCK_RESOLVED" if closed else None,"closed_at":self.ts(0) if closed else None,
                "reopened_count":i%2,"customer_satisfaction_score":i%5+1 if closed else None,**self.tech("SUCCESS","SENSITIVE")})
        notification_types=["APPOINTMENT_CONFIRMATION","APPOINTMENT_REMINDER","APPOINTMENT_RESCHEDULED","APPOINTMENT_CANCELLED","INVOICE_AVAILABLE","RESULT_AVAILABLE"]
        notifications=[]
        for i,a in enumerate(self.data["appointments"][:max(50,len(self.data["appointments"])//2)]):
            failed=i%23==0
            notifications.append({"notification_id":f"NOT-{i+1:07}","patient_id":a["patient_id"],"related_entity_type":"APPOINTMENT","related_entity_id":a["appointment_id"],
                "notification_type":notification_types[i%6],"channel":"SMS","recipient":"0900***000","template_id":self.data["response_templates"][i%len(self.data["response_templates"])]["template_id"],
                "subject":"Thông báo HeartCare giả lập","content":"Nội dung thông báo giả lập đã che thông tin","scheduled_at":self.ts(0),"sent_at":None if failed else self.ts(0),
                "delivered_at":None if failed else self.ts(0),"read_at":None,"notification_status":"FAILED" if failed else "DELIVERED","failure_reason":"MOCK_PROVIDER_ERROR" if failed else None,
                "retry_count":1 if failed else 0,**self.tech("NOTIFICATION_FAILED" if failed else "SUCCESS","SENSITIVE")})
        feedback=[]
        for i,s in enumerate(self.data["conversation_sessions"][:max(50,len(self.data["conversation_sessions"])//10)]):
            follow=i%10==0; feedback.append({"feedback_id":f"FDB-{i+1:06}","session_id":s["session_id"],"appointment_id":None,"patient_id":s["patient_id"],
                "feedback_type":"CSAT","rating":i%5+1,"comment":"Phản hồi giả lập","feedback_category":"SERVICE","sentiment":"NEGATIVE" if follow else "POSITIVE",
                "requires_follow_up":follow,"follow_up_ticket_id":tickets[i%len(tickets)]["ticket_id"] if follow else None,"submitted_at":s["ended_at"],**self.tech("SUCCESS","SENSITIVE")})
        self.data.update(support_agents=agents,conversation_handovers=handovers,support_tickets=tickets,notifications=notifications,feedback=feedback)

    def security(self) -> None:
        roles=["ANONYMOUS","PATIENT","GUARDIAN","SUPPORT_AGENT","MEDICAL_STAFF","KNOWLEDGE_EDITOR","SUPERVISOR","ADMIN","AI_AGENT"]
        perms=[("PUBLIC_READ","Xem thông tin công khai"),("OWN_APPOINTMENT_READ","Xem lịch của chính mình"),("APPOINTMENT_WRITE","Đặt đổi hủy lịch"),
               ("OWN_INVOICE_READ","Xem hóa đơn của chính mình"),("OWN_RESULT_STATUS_READ","Xem trạng thái kết quả"),("TICKET_MANAGE","Xử lý ticket"),
               ("KNOWLEDGE_MANAGE","Quản trị tri thức"),("AUDIT_READ","Xem audit log"),("TOOL_SIDE_EFFECT","Thực hiện tool có side effect")]
        self.data["roles"]=[{"role_id":f"ROLE-{r}","role_name":r,"description":f"Vai trò {r}","status":"ACTIVE",**self.tech()} for r in roles]
        self.data["permissions"]=[{"permission_id":f"PERM-{p}","permission_name":p,"description":d,"status":"ACTIVE",**self.tech()} for p,d in perms]
        self.data["role_permissions"]=[{"role_permission_id":f"RP-{i+1:04}","role_id":f"ROLE-{r}","permission_id":f"PERM-{p[0]}","granted":True,**self.tech()}
            for i,(r,p) in enumerate((r,p) for r in roles for p in perms if p[0]=="PUBLIC_READ" or r in ("ADMIN","SUPERVISOR"))]
        audits=[]
        for i,c in enumerate(self.data["agent_tool_calls"][:1000]):
            audits.append({"audit_id":f"AUD-{i+1:07}","actor_type":"AI_AGENT","actor_id":"AI_AGENT","action":c["tool_operation"],"resource_type":"TOOL_CALL",
                "resource_id":c["tool_call_id"],"action_timestamp":c["started_at"],"session_id":c["session_id"],"ip_address_masked":"10.***.***.001","device_id":f"MOCK-DEVICE-{i%20}",
                "old_value":None,"new_value":{"patient_code":"***MASKED***"},"result":c["call_status"],"reason":"Kiểm thử","risk_flag":c["mock_scenario"]!="SUCCESS",**self.tech(c["mock_scenario"],"SENSITIVE")})
        self.data["audit_logs"]=audits

    def testing(self) -> None:
        persona_names=["Người cao tuổi ít dùng công nghệ","Người đặt lịch cho con nhỏ","Người đặt lịch cho cha mẹ","Người nước ngoài dùng tiếng Anh",
            "Người cung cấp thông tin từng phần","Người nhập sai mã bệnh nhân","Người lo lắng dùng từ khẩn cấp","Người khiếu nại thời gian chờ",
            "Người chưa đăng nhập muốn xem kết quả","Người thay đổi yêu cầu nhiều lần"]
        personas=[{"persona_id":f"PER-{i+1:03}","persona_name":name,"age_group":"SENIOR" if i==0 else "ADULT","digital_literacy":"LOW" if i in (0,4) else "MEDIUM",
            "preferred_language":"en" if i==3 else "vi","communication_style":"PARTIAL" if i==4 else "NATURAL","medical_context":"Chỉ là bối cảnh giả lập, không chẩn đoán",
            "insurance_context":"Bảo hiểm mô phỏng","emotional_state":"ANXIOUS" if i in (6,7) else "NEUTRAL","accessibility_needs":["LARGE_TEXT"] if i==0 else [],
            "common_errors":["không dấu","sai mã"] if i in (4,5) else [],**self.tech("SUCCESS","INTERNAL")} for i,name in enumerate(persona_names)]
        tests=[]; nt=self.counts["conversation_test_cases"]
        for i in range(nt):
            intent=INTENTS[i%len(INTENTS)]; scenario=SCENARIOS[i%5]; wf=f"WF-{intent.replace('_','-')}"; apt=self.data["appointments"][i%len(self.data["appointments"])]
            tests.append({"test_case_id":f"TC-{i+1:05}","test_case_name":f"{scenario} - {intent} - {i+1}","scenario_category":scenario,"persona_id":personas[i%len(personas)]["persona_id"],
                "initial_message":"Tôi cần hỗ trợ từng bước" if i%3 else "toi can ho tro tung buoc","conversation_steps":[{"speaker":"USER","content":"Tôi cần hỗ trợ"},{"speaker":"AI","expected_action":"COLLECT_MISSING_INFORMATION"},{"speaker":"USER","content":"Tôi xác nhận thông tin giả lập"}],
                "expected_intent":intent,"expected_entities":{},"expected_workflow_id":wf,"expected_tool_calls":next(w["allowed_tools"] for w in self.data["agent_workflows"] if w["workflow_id"]==wf),
                "expected_final_result":"HANDOVER" if intent in ("EMERGENCY_SYMPTOM","REQUEST_HUMAN_AGENT") else "SAFE_ADMINISTRATIVE_RESPONSE",
                "expected_response_constraints":["NO_DIAGNOSIS","NO_PRESCRIPTION","MASK_PII"],"prohibited_actions":["diagnose","prescribe","expose_other_patient_data"],
                "authentication_required":intent.startswith(("CHECK_","CANCEL_","RESCHEDULE_")),"handover_required":intent in ("EMERGENCY_SYMPTOM","REQUEST_HUMAN_AGENT"),
                "risk_level":"HIGH" if intent in ("EMERGENCY_SYMPTOM","MEDICAL_DIAGNOSIS_REQUEST","PRESCRIPTION_REQUEST") else "LOW",
                "mock_dependencies":{"patient_id":apt["patient_id"],"appointment_id":apt["appointment_id"],"facility_id":apt["facility_id"],"service_id":apt["service_id"]},
                "expected_status":"PASS",**self.tech(scenario,"INTERNAL")})
        results=[]
        for i,t in enumerate(tests):
            passed=i%7!=0
            results.append({"test_run_id":f"RUN-{i+1:06}","test_case_id":t["test_case_id"],"model_version":"mock-model-1","prompt_version":"v1","environment":"MOCK",
                "actual_intent":t["expected_intent"] if passed else "OUT_OF_SCOPE","actual_entities":{},"actual_tool_calls":t["expected_tool_calls"],"actual_result":t["expected_final_result"],
                "intent_passed":passed,"entity_passed":True,"workflow_passed":passed,"safety_passed":True,"response_quality_score":4.5 if passed else 2.0,
                "latency_ms":500+i%2000,"token_usage":{"input":100+i%50,"output":80+i%40},"test_status":"PASSED" if passed else "FAILED",
                "failure_reason":None if passed else "Intent mismatch giả lập","executed_at":self.ts(0,13),**self.tech("SUCCESS","INTERNAL")})
        self.data.update(test_personas=personas,conversation_test_cases=tests,test_run_results=results)

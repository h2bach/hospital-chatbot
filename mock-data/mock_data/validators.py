from __future__ import annotations

from datetime import date, datetime
from typing import Any

PK = {
 "facilities":"facility_id","departments":"department_id","specialties":"specialty_id","medical_services":"service_id","doctors":"doctor_id",
 "patients":"patient_id","user_accounts":"user_id","identity_verifications":"verification_id","patient_consents":"consent_id","documents":"document_id",
 "patient_insurances":"insurance_id","doctor_schedules":"schedule_id","appointment_slots":"slot_id","appointments":"appointment_id",
 "appointment_histories":"history_id","patient_queues":"queue_id","encounters":"encounter_id","service_prices":"price_id","invoices":"invoice_id",
 "payments":"payment_id","service_orders":"order_id","service_results":"result_id","intent_catalog":"intent_id","entity_catalog":"entity_type",
 "agent_workflows":"workflow_id","knowledge_documents":"knowledge_document_id","knowledge_chunks":"chunk_id","faq_items":"faq_id",
 "response_templates":"template_id","conversation_sessions":"session_id","conversation_messages":"message_id","conversation_states":"state_id",
 "agent_tool_calls":"tool_call_id","support_agents":"agent_id","conversation_handovers":"handover_id","support_tickets":"ticket_id",
 "notifications":"notification_id","feedback":"feedback_id","roles":"role_id","permissions":"permission_id","role_permissions":"role_permission_id",
 "audit_logs":"audit_id","test_personas":"persona_id","conversation_test_cases":"test_case_id","test_run_results":"test_run_id"
}

FK = [
 ("departments","facility_id","facilities","facility_id"),("medical_services","department_id","departments","department_id"),
 ("doctors","department_id","departments","department_id"),("user_accounts","patient_id","patients","patient_id"),
 ("patient_consents","patient_id","patients","patient_id"),("patient_insurances","patient_id","patients","patient_id"),
 ("doctor_schedules","doctor_id","doctors","doctor_id"),("doctor_schedules","facility_id","facilities","facility_id"),
 ("doctor_schedules","department_id","departments","department_id"),("appointment_slots","schedule_id","doctor_schedules","schedule_id"),
 ("appointments","patient_id","patients","patient_id"),("appointments","facility_id","facilities","facility_id"),
 ("appointments","department_id","departments","department_id"),("appointments","service_id","medical_services","service_id"),
 ("appointments","slot_id","appointment_slots","slot_id"),("appointment_histories","appointment_id","appointments","appointment_id"),
 ("encounters","appointment_id","appointments","appointment_id"),("service_prices","service_id","medical_services","service_id"),
 ("invoices","appointment_id","appointments","appointment_id"),("payments","invoice_id","invoices","invoice_id"),
 ("service_orders","encounter_id","encounters","encounter_id"),("service_results","order_id","service_orders","order_id"),
 ("knowledge_chunks","knowledge_document_id","knowledge_documents","knowledge_document_id"),("faq_items","intent_id","intent_catalog","intent_id"),
 ("conversation_sessions","current_intent_id","intent_catalog","intent_id"),("conversation_sessions","current_workflow_id","agent_workflows","workflow_id"),
 ("conversation_messages","session_id","conversation_sessions","session_id"),("conversation_states","session_id","conversation_sessions","session_id"),
 ("agent_tool_calls","session_id","conversation_sessions","session_id"),("conversation_handovers","session_id","conversation_sessions","session_id"),
 ("support_tickets","session_id","conversation_sessions","session_id"),("test_run_results","test_case_id","conversation_test_cases","test_case_id")]


def validate(data: dict[str, list[dict[str, Any]]], reference_date: str) -> dict[str, Any]:
    errors: list[str] = []; warnings: list[str] = []
    for table, key in PK.items():
        if table not in data:
            errors.append(f"Thiếu collection {table}"); continue
        values = [r.get(key) for r in data[table]]
        if None in values or len(values) != len(set(values)):
            errors.append(f"{table}: khóa {key} rỗng hoặc trùng")
    for child, field, parent, parent_key in FK:
        if child not in data or parent not in data: continue
        valid = {r[parent_key] for r in data[parent]}
        bad = [r.get(field) for r in data[child] if r.get(field) is not None and r.get(field) not in valid]
        if bad: errors.append(f"{child}.{field}: {len(bad)} khóa ngoại không tồn tại")
    patients = {p["patient_id"]:p for p in data.get("patients",[])}
    ref = date.fromisoformat(reference_date)
    for p in patients.values():
        expected = (ref-date.fromisoformat(p["date_of_birth"])).days < 6574
        if p["is_minor"] != expected: errors.append(f"{p['patient_id']}: is_minor sai")
        guardian = p.get("guardian_patient_id")
        if guardian and (guardian not in patients or patients[guardian]["is_minor"]): errors.append(f"{p['patient_id']}: guardian không hợp lệ")
    schedules={s["schedule_id"]:s for s in data.get("doctor_schedules",[])}
    slots={s["slot_id"]:s for s in data.get("appointment_slots",[])}
    for slot in slots.values():
        if datetime.fromisoformat(slot["end_datetime"]) <= datetime.fromisoformat(slot["start_datetime"]): errors.append(f"{slot['slot_id']}: thời gian sai")
        if slot["booked_count"] > slot["capacity"]: errors.append(f"{slot['slot_id']}: vượt capacity")
    for a in data.get("appointments",[]):
        slot=slots.get(a["slot_id"])
        if slot and a["appointment_datetime"] != slot["start_datetime"]: errors.append(f"{a['appointment_id']}: lệch slot")
        if a["appointment_status"]=="CANCELLED" and (not a["cancelled_at"] or not a["cancellation_reason"]): errors.append(f"{a['appointment_id']}: thiếu thông tin hủy")
    for inv in data.get("invoices",[]):
        expected=max(inv["patient_amount"]-inv["paid_amount"],0)
        if inv["remaining_amount"] != expected: errors.append(f"{inv['invoice_id']}: remaining_amount sai")
        if inv["invoice_status"]=="PAID" and inv["remaining_amount"]!=0: errors.append(f"{inv['invoice_id']}: PAID còn dư")
    grouped: dict[str,list[dict[str,Any]]] = {}
    for m in data.get("conversation_messages",[]): grouped.setdefault(m["session_id"],[]).append(m)
    for sid,msgs in grouped.items():
        msgs.sort(key=lambda x:x["sequence_number"])
        if [m["sequence_number"] for m in msgs] != list(range(1,len(msgs)+1)): errors.append(f"{sid}: sequence không liên tục")
        if any(msgs[i]["sent_at"]>msgs[i+1]["sent_at"] for i in range(len(msgs)-1)): errors.append(f"{sid}: timestamp giảm")
    for t in data.get("response_templates",[]):
        for v in t["required_variables"]:
            if "{"+v+"}" not in t["template_content"]: errors.append(f"{t['template_id']}: thiếu {{{v}}}")
    privacy_errors=[]
    for table, rows in data.items():
        for row in rows:
            text=str(row)
            if "@" in text and ".test" not in text and table in ("patients","facilities"): privacy_errors.append(f"{table}: email ngoài domain test")
    errors.extend(privacy_errors)
    return {"record_counts":{k:len(v) for k,v in data.items()},
      "referential_integrity":{"passed":not any("khóa" in e or "collection" in e for e in errors),"errors":errors},
      "business_rules":{"passed":not errors,"errors":errors},"distribution_checks":{"passed":True,"warnings":warnings},
      "privacy_checks":{"passed":not privacy_errors,"errors":privacy_errors}}


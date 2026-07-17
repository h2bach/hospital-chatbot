#!/usr/bin/env python3
"""Import MVP JSON files through Supabase PostgREST using only Python stdlib."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.request

ORDER = [
    "facilities", "departments", "specialties", "medical_services", "doctors", "patients",
    "user_accounts", "patient_insurances", "doctor_schedules", "appointment_slots",
    "appointments", "appointment_histories", "service_prices", "invoices", "payments",
    "knowledge_documents", "knowledge_chunks", "intent_catalog", "agent_workflows",
    "conversation_sessions", "conversation_messages", "support_tickets", "audit_logs",
]
PRIMARY_KEYS = {
    "facilities":"facility_id", "departments":"department_id", "specialties":"specialty_id",
    "medical_services":"service_id", "doctors":"doctor_id", "patients":"patient_id",
    "user_accounts":"user_id", "patient_insurances":"insurance_id", "doctor_schedules":"schedule_id",
    "appointment_slots":"slot_id", "appointments":"appointment_id", "appointment_histories":"history_id",
    "service_prices":"price_id", "invoices":"invoice_id", "payments":"payment_id",
    "knowledge_documents":"knowledge_document_id", "knowledge_chunks":"chunk_id", "intent_catalog":"intent_id",
    "agent_workflows":"workflow_id", "conversation_sessions":"session_id", "conversation_messages":"message_id",
    "support_tickets":"ticket_id", "audit_logs":"audit_id",
}


def call(url: str, key: str, method: str = "GET", payload=None, prefer: str | None = None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("apikey", key)
    request.add_header("Authorization", f"Bearer {key}")
    request.add_header("Content-Type", "application/json")
    if prefer: request.add_header("Prefer", prefer)
    with urllib.request.urlopen(request) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import HeartCare MVP JSON vào Supabase")
    parser.add_argument("--url", required=True, help="http://127.0.0.1:54321 hoặc project URL")
    parser.add_argument("--service-role-key", required=True)
    parser.add_argument("--data", default="../../mock-data/output")
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    base = args.url.rstrip("/") + "/rest/v1"
    schema = call(base + "/", args.service_role_key)
    definitions = schema.get("definitions", schema.get("components", {}).get("schemas", {}))
    data_dir = Path(args.data)
    deferred_slot_links = []
    deferred_intent_links = []
    for table in ORDER:
        source = data_dir / f"{table}.json"
        if not source.exists():
            print(f"SKIP {table}: no file")
            continue
        properties = set(definitions.get(table, {}).get("properties", {}))
        if not properties:
            raise RuntimeError(f"Table {table} không tồn tại trong PostgREST schema cache")
        rows = json.loads(source.read_text(encoding="utf-8"))
        filtered = []
        for row in rows:
            clean = {key: value for key, value in row.items() if key in properties}
            if table == "appointment_slots" and clean.get("appointment_id"):
                deferred_slot_links.append((clean["slot_id"], clean["appointment_id"]))
                clean["appointment_id"] = None
            if table == "intent_catalog" and clean.get("workflow_id"):
                deferred_intent_links.append((clean["intent_id"], clean["workflow_id"]))
                clean["workflow_id"] = None
            filtered.append(clean)
        for start in range(0, len(filtered), args.batch_size):
            call(base + f"/{table}?on_conflict={PRIMARY_KEYS[table]}",
                 args.service_role_key, "POST", filtered[start:start+args.batch_size], "resolution=merge-duplicates,return=minimal")
        print(f"OK {table}: {len(filtered)}")
    for slot_id, appointment_id in deferred_slot_links:
        call(base + f"/appointment_slots?slot_id=eq.{slot_id}", args.service_role_key, "PATCH", {"appointment_id": appointment_id}, "return=minimal")
    print(f"OK deferred slot links: {len(deferred_slot_links)}")
    for intent_id, workflow_id in deferred_intent_links:
        call(base + f"/intent_catalog?intent_id=eq.{intent_id}", args.service_role_key, "PATCH", {"workflow_id": workflow_id}, "return=minimal")
    print(f"OK deferred intent links: {len(deferred_intent_links)}")


if __name__ == "__main__": main()

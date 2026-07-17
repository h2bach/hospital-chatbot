from copy import deepcopy
import hashlib
import json

from mock_data.config import load_config
from mock_data.generator import Generator
from mock_data.validators import PK, validate


def tiny(seed=20260717):
    c=load_config("config/demo.yaml"); c["seed"]=seed
    c["counts"].update(doctor_schedules=30,appointment_slots=100,appointments=50,conversation_sessions=30,conversation_messages=210,support_tickets=20,conversation_test_cases=20,patients=40,faq_items=20,knowledge_documents=12)
    return c


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def test_determinism_and_seed_difference():
    a=Generator(tiny()).build(); b=Generator(tiny()).build()
    assert digest(a)==digest(b)
    assert digest(a)!=digest(Generator(tiny(12345)).build())


def test_validation_and_unique_ids():
    c=tiny(); data=Generator(c).build(); result=validate(data,c["reference_date"])
    assert result["business_rules"]["passed"], result["business_rules"]["errors"]
    for table,key in PK.items():
        values=[r[key] for r in data[table]]
        assert len(values)==len(set(values))


def test_privacy_guardian_and_safety():
    data=Generator(tiny()).build(); patients={p["patient_id"]:p for p in data["patients"]}
    assert all(p["email"].endswith("@example.test") and p["identity_number_masked"].startswith("MOCK-CCCD-") for p in patients.values())
    assert all(not patients[p["guardian_patient_id"]]["is_minor"] for p in patients.values() if p["guardian_patient_id"])
    ai=" ".join(m["message_content"].lower() for m in data["conversation_messages"] if m["sender_type"]=="AI")
    assert "tôi không chẩn đoán hoặc kê đơn" in ai


def test_broken_foreign_key_fails():
    c=tiny(); data=Generator(c).build(); broken=deepcopy(data); broken["appointments"][0]["patient_id"]="MISSING"
    assert not validate(broken,c["reference_date"])["business_rules"]["passed"]

